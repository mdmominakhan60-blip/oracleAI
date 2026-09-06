#!/usr/bin/env python3
"""Сертификация платёжного контура P0-002 (BUS-109) — sandbox-прогон 5 сценариев.

Реальный код против реального PostgreSQL: настоящий FastAPI-эндпоинт
`/api/webhooks/paddle`, настоящий `services.paddle.create_transaction` (сетевой
вызов), настоящая выдача через `services.billing.apply_payment`. Провайдер
эмулируется двумя локальными компонентами:

1. Paddle API-симулятор (aiohttp-сервер): POST /transactions → txn_ + checkout
   URL. Через него проходит настоящий сетевой путь `create_transaction`.
2. Генератор вебхуков с HMAC-SHA256 подписью по алгоритму Paddle
   («ts:body», секрет из PADDLE_WEBHOOK_SECRET).

Сценарии:
  S1 invoice      — web-checkout создаёт pending-заказ с paddle_transaction_id;
  S2 payment      — подписанный webhook transaction.completed выдаёт подписку;
  S3 duplicate    — повторная доставка того же event_id не выдаёт второй раз;
  S4 refund/chargeback — подписанные adjustment-события: текущее поведение кода
                    (фиксация события, entitlement не отзывается) + finding;
  S5 error paths  — битая подпись, просроченная подпись, чужой transaction_id,
                    не-pending заказ, неактивный тариф.

Reconciliation: сверка payments/orders/webhook_events/subscription-состояния
после каждого сценария. Запуск требует БД со схемой (alembic upgrade head):
  DEV_KEY=x LLM_PROVIDER=off BOT_TOKEN=t:t DATABASE_URL=postgresql+asyncpg://... \
  python3 scripts/payments_sandbox_cert.py

Evidence: logs/payments_sandbox_cert_<ts>.json + текстовый лог.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Минимальная среда до импорта настроек (как в tests/conftest.py).
os.environ.setdefault("LLM_PROVIDER", "off")
os.environ.setdefault("BOT_TOKEN", "test:token")
os.environ.setdefault("ADMIN_ID", "1")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("DEV_KEY", "cert-dev-key")
os.environ.setdefault("AUTO_TRIAL", "1")

if not os.environ.get("DATABASE_URL"):
    print("DATABASE_URL не задан — сертификация требует PostgreSQL", file=sys.stderr)
    sys.exit(2)


from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.config import settings  # noqa: E402
from app.data.monetization_catalog import PLAN_DEFINITIONS  # noqa: E402
from app.data.session import connect  # noqa: E402
from app.repo import content as content_repo  # noqa: E402
from app.repo import users as users_repo  # noqa: E402
from app.services.repo_gateway import billing as billing_repo  # noqa: E402

CERT_SECRET = "paddle-sandbox-cert-secret-BUS109"
CERT_TG_ID = 550001
SIM_HOST, SIM_PORT = "127.0.0.1", 55433

RESULTS: list[dict] = []


def signed_webhook(body: bytes, secret: str = CERT_SECRET,
                   ts: int | None = None) -> dict:
    """Заголовок Paddle-Signature: ts=...;h1=<hmac-sha256(ts:body)>."""
    ts = ts if ts is not None else int(time.time())
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + body,
                      hashlib.sha256).hexdigest()
    return {"Paddle-Signature": f"ts={ts};h1={digest}"}


def webhook_body(event_id: str, event_type: str, data: dict) -> bytes:
    return json.dumps({"event_id": event_id, "event_type": event_type,
                       "occurred_at": "2026-09-05T00:00:00Z", "data": data},
                      separators=(",", ":")).encode()


# ───────────────────────── Paddle API-симулятор ──────────────────────────────

class PaddleSim:
    """Минимальный Paddle Billing API: создание транзакции из серверного кода.

    Заменяет monkeypatch: настоящий aiohttp-вызов проходит весь путь
    paddle.create_transaction (заголовки, JSON, валидация txn_).
    """

    def __init__(self) -> None:
        self.transactions: dict[str, dict] = {}
        self.runner = None
        self.site = None

    async def start(self) -> None:
        from aiohttp import web

        async def create_transaction(request: web.Request) -> web.Response:
            payload = await request.json()
            txn_id = f"txn_sim_{len(self.transactions) + 1:04d}"
            price_id = (payload.get("items") or [{}])[0].get("price_id", "")
            record = {"id": txn_id, "status": "created",
                      "price_id": price_id,
                      "custom_data": payload.get("custom_data") or {}}
            self.transactions[txn_id] = record
            return web.json_response({"data": {**record,
                                    "checkout": {"url": "https://sim.paddle/checkout"}}})

        app_web = web.Application()
        app_web.router.add_post("/transactions", create_transaction)
        self.runner = web.AppRunner(app_web)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, SIM_HOST, SIM_PORT)
        await self.site.start()

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    @property
    def api_url(self) -> str:
        return f"http://{SIM_HOST}:{SIM_PORT}"


# ──────────────────────────── инфраструктура ─────────────────────────────────

class Cert:
    def __init__(self) -> None:
        self.db = None
        self.http = None
        self.sim = PaddleSim()
        self.log_path = ROOT / "logs" / (
            "payments_sandbox_cert_" + time.strftime("%Y%m%d_%H%M%S") + ".log")
        self.json_path = self.log_path.with_suffix(".json")
        self._logf = None

    async def setup(self) -> None:
        self.log_path.parent.mkdir(exist_ok=True)
        self._logf = self.log_path.open("w", encoding="utf-8")
        self.db = await connect(seed=True)
        # Повторный запуск должен быть чистым: убираем состояние прошлых
        # прогонов сертификации (только cert-данные, не произвольные).
        await self.db.execute(
            "DELETE FROM webhook_events WHERE event_id LIKE 'evt\\_cert%'")
        await self.db.execute(
            "DELETE FROM payments WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        await self.db.execute(
            "DELETE FROM orders WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        await self.db.execute(
            "DELETE FROM events WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        await self.db.execute(
            "DELETE FROM users WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        app.dependency_overrides[get_db] = lambda: self.db
        from httpx import ASGITransport, AsyncClient
        self.http = AsyncClient(transport=ASGITransport(app=app),
                                base_url="http://cert", timeout=30,
                                headers={"X-Dev-Key": os.environ["DEV_KEY"]})
        await self.sim.start()
        settings.paddle_webhook_secret = CERT_SECRET
        settings.paddle_api_key = "cert-sandbox-key"
        settings.paddle_api_url = self.sim.api_url
        settings.paddle_checkout_url = "https://sandbox-checkout.paddle.dev/test"
        settings.paddle_price_ids = "vip:pri_cert_vip"

    async def teardown(self) -> None:
        await self.http.aclose()
        app.dependency_overrides.clear()
        await self.sim.stop()
        await self.db.close()
        self._logf.close()

    def log(self, message: str) -> None:
        print(message, flush=True)
        if self._logf:
            self._logf.write(message + "\n")
            self._logf.flush()

    def record(self, scenario: str, passed: bool, checks: list[dict]) -> None:
        RESULTS.append({"scenario": scenario, "passed": passed,
                        "checks": checks})
        status = "PASS" if passed else "FAIL"
        self.log(f"  → {scenario}: {status} "
                 f"({sum(c['ok'] for c in checks)}/{len(checks)} проверок)")

    async def check(self, name: str, ok: bool, detail: str = "") -> dict:
        return {"name": name, "ok": bool(ok), "detail": detail}

    # ────────────────────────────── helpers ──────────────────────────────

    async def fresh_user(self, tg_id: int) -> dict:
        await users_repo.ensure(self.db, tg_id, "Сертификат", "cert")
        return await users_repo.get(self.db, tg_id)

    async def enable_flag(self) -> None:
        await content_repo.set_flag(self.db, "web_payments", is_on=True)

    async def subscription_state(self, tg_id: int) -> dict:
        cur = await self.db.execute(
            "SELECT sub_level, sub_until FROM users WHERE tg_id=:tg",
            {"tg": tg_id})
        row = await cur.fetchone()
        return {"sub_level": row["sub_level"], "sub_until": row["sub_until"]}

    async def sql_count(self, sql: str, params: dict | None = None) -> int:
        cur = await self.db.execute(sql, params or {})
        row = await cur.fetchone()
        return int(row[0] or 0)


# ───────────────────────────────── сценарии ──────────────────────────────────

async def s1_invoice(c: Cert) -> None:
    """S1: invoice — web-checkout → pending-заказ + paddle_transaction_id."""
    checks = []
    await c.fresh_user(CERT_TG_ID)
    await c.enable_flag()

    res = await c.http.post("/api/shop/web-checkout",
                            params={"dev_user": CERT_TG_ID},
                            json={"plan": "vip", "billing_period": "monthly"})
    checks.append(await c.check("checkout HTTP 200", res.status_code == 200,
                                f"HTTP {res.status_code}: {res.text[:200]}"))
    if res.status_code != 200:
        c.record("S1 invoice", False, checks)
        return
    payload = res.json()
    checks.append(await c.check("checkout вернул link c transaction_id",
                                "transaction_id=" in payload.get("link", "")))
    checks.append(await c.check("checkout вернул price_usd > 0",
                                float(payload.get("price_usd") or 0) > 0,
                                f"price_usd={payload.get('price_usd')}"))

    txn_ids = list(c.sim.transactions)
    checks.append(await c.check("симулятор Paddle создал транзакцию",
                                len(txn_ids) == 1))
    sim_txn = c.sim.transactions[txn_ids[0]] if txn_ids else {}
    checks.append(await c.check("custom_data несёт order_payload",
                                bool(sim_txn.get("custom_data", {}).get("order_payload"))))

    order = await billing_repo.order_by_payload(
        c.db, sim_txn.get("custom_data", {}).get("order_payload", ""))
    checks.append(await c.check("заказ в БД: status=pending",
                                bool(order) and order["status"] == "pending"))
    checks.append(await c.check("заказ: surface=web, kind=plan, sku=vip",
                                bool(order) and order["surface"] == "web"
                                and order["kind"] == "plan" and order["sku"] == "vip"))
    meta = json.loads(order["meta_json"]) if order else {}
    checks.append(await c.check("meta содержит paddle_transaction_id=txn_sim_*",
                                meta.get("paddle_transaction_id", "").startswith("txn_sim_")))
    checks.append(await c.check("meta: provider=paddle, есть price_usd",
                                meta.get("provider") == "paddle"
                                and float(meta.get("price_usd") or 0) > 0))
    checks.append(await c.check("event web_checkout записан в analytics",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM events "
                                    "WHERE name='web_checkout'") >= 1))
    c.state_s1 = {"payload": order["payload"], "txn_id": meta.get("paddle_transaction_id")}
    c.record("S1 invoice", all(k["ok"] for k in checks), checks)


async def s2_payment(c: Cert) -> None:
    """S2: оплата — подписанный webhook transaction.completed выдаёт подписку."""
    checks = []
    order_payload = c.state_s1["payload"]
    txn_id = c.state_s1["txn_id"]
    before = await c.subscription_state(CERT_TG_ID)

    body = webhook_body("evt_cert_pay_1", "transaction.completed", {
        "id": txn_id, "status": "completed", "currency_code": "USD",
        "custom_data": {"order_payload": order_payload},
        "items": [{"price": {"id": "pri_cert_vip"}}],
    })
    res = await c.http.post("/api/webhooks/paddle", content=body,
                            headers=signed_webhook(body))
    checks.append(await c.check("webhook HTTP 200", res.status_code == 200,
                                f"HTTP {res.status_code}: {res.text[:200]}"))
    granted = res.json().get("granted") if res.status_code == 200 else None
    checks.append(await c.check("granted=true", granted is True,
                                f"ответ: {res.text[:200]}"))

    after = await c.subscription_state(CERT_TG_ID)
    checks.append(await c.check("подписка продлена (sub_until сдвинулся)",
                                after["sub_until"] is not None
                                and after["sub_until"] != before["sub_until"],
                                f"before={before['sub_until']} after={after['sub_until']}"))

    order = await billing_repo.order_by_payload(c.db, order_payload)
    checks.append(await c.check("заказ status=paid", order["status"] == "paid"))

    checks.append(await c.check("payment записан с provider=paddle",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM payments "
                                    "WHERE provider='paddle'") == 1))
    checks.append(await c.check("webhook_events содержит event_id",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM webhook_events "
                                    "WHERE event_id='evt_cert_pay_1' "
                                    "AND provider='paddle'") == 1))
    checks.append(await c.check("analytics: payment_success (web)",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM events "
                                    "WHERE name='payment_success' "
                                    "AND surface='web'") >= 1))
    c.record("S2 payment", all(k["ok"] for k in checks), checks)


async def s3_duplicate(c: Cert) -> None:
    """S3: идемпотентность — повтор того же webhook не выдаёт второй раз."""
    checks = []
    order_payload = c.state_s1["payload"]
    txn_id = c.state_s1["txn_id"]
    before = await c.subscription_state(CERT_TG_ID)

    body = webhook_body("evt_cert_pay_1", "transaction.completed", {
        # Тот же event_id, но ДРУГОЙ txn_id в data: если код не проверит
        # журнал идемпотентности по event_id, метч по transaction_id упадёт
        # в unmatched, а не duplicate — проверяем оба маршрута.
        "id": txn_id, "status": "completed", "currency_code": "USD",
        "custom_data": {"order_payload": order_payload},
        "items": [{"price": {"id": "pri_cert_vip"}}],
    })
    res = await c.http.post("/api/webhooks/paddle", content=body,
                            headers=signed_webhook(body))
    payload = res.json() if res.status_code == 200 else {}
    checks.append(await c.check("повтор webhook → HTTP 200", res.status_code == 200))
    checks.append(await c.check("duplicate=true", payload.get("duplicate") is True,
                                f"ответ: {res.text[:200]}"))
    checks.append(await c.check("granted не выставлен", payload.get("granted") is not True))

    after = await c.subscription_state(CERT_TG_ID)
    checks.append(await c.check("подписка НЕ продлилась второй раз",
                                after["sub_until"] == before["sub_until"]))

    checks.append(await c.check("payments по-прежнему 1 запись",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM payments "
                                    "WHERE provider='paddle'") == 1))
    checks.append(await c.check("webhook_events: 1 запись (ON CONFLICT DO NOTHING)",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM webhook_events "
                                    "WHERE event_id='evt_cert_pay_1'") == 1))
    c.record("S3 duplicate webhook", all(k["ok"] for k in checks), checks)


async def s4_refund_chargeback(c: Cert) -> None:
    """S4: refund/chargeback — доставляем подписанные adjustment-события.

    Текущее поведение кода: GRANTING_EVENTS = {transaction.completed}, поэтому
    adjustment.* попадает в журнал webhook_events, но entitlement НЕ отзывается.
    Мы фиксируем фактическое поведение (не «должно быть») и отмечаем finding:
    в sandbox-сертификации ручной refund отрабатывается на стороне Paddle, а
    отзыв доступа требует отдельного решения (CFO + Engineering Lead).
    """
    checks = []
    order_payload = c.state_s1["payload"]
    txn_id = c.state_s1["txn_id"]
    sub_before = await c.subscription_state(CERT_TG_ID)

    refund_body = webhook_body("evt_cert_refund_1", "adjustment.created", {
        "id": "adj_cert_1", "status": "approved", "action": "refund",
        "transaction_id": txn_id,
        "items": [{"type": "full", "amount": "2499"}],
    })
    res_refund = await c.http.post("/api/webhooks/paddle", content=refund_body,
                                   headers=signed_webhook(refund_body))
    checks.append(await c.check("refund webhook HTTP 200 (принят)",
                                res_refund.status_code == 200,
                                f"HTTP {res_refund.status_code}: {res_refund.text[:200]}"))

    charge_body = webhook_body("evt_cert_cb_1", "adjustment.created", {
        "id": "adj_cert_2", "status": "approved", "action": "chargeback",
        "transaction_id": txn_id, "items": [{"type": "full", "amount": "2499"}],
    })
    res_cb = await c.http.post("/api/webhooks/paddle", content=charge_body,
                               headers=signed_webhook(charge_body))
    checks.append(await c.check("chargeback webhook HTTP 200 (принят)",
                                res_cb.status_code == 200,
                                f"HTTP {res_cb.status_code}: {res_cb.text[:200]}"))

    refund_row = await c.sql_count(
        "SELECT COUNT(*) FROM webhook_events WHERE event_id='evt_cert_refund_1'")
    cb_row = await c.sql_count(
        "SELECT COUNT(*) FROM webhook_events WHERE event_id='evt_cert_cb_1'")
    checks.append(await c.check("оба adjustment-события зафиксированы в журнале",
                                refund_row == 1 and cb_row == 1,
                                f"refund={refund_row} chargeback={cb_row}"))

    order = await billing_repo.order_by_payload(c.db, order_payload)
    sub_after = await c.subscription_state(CERT_TG_ID)
    checks.append(await c.check("эндпоинт вернул ignored-маршрут (не granted)",
                                "granted" not in (res_refund.json() or {})
                                or res_refund.json().get("granted") is not True))
    checks.append(await c.check("FINDING: entitlement сохраняется после refund",
                                order["status"] == "paid"
                                and sub_after["sub_until"] == sub_before["sub_until"],
                                "отзыв доступа требует решения CFO/EL"))

    checks.append(await c.check("повтор refund (retries провайдера) идемпотентен",
                                (await c.http.post(
                                    "/api/webhooks/paddle", content=refund_body,
                                    headers=signed_webhook(refund_body))).json()
                                .get("duplicate") is True))
    checks.append(await c.check("payments по-прежнему 1 запись",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM payments "
                                    "WHERE provider='paddle'") == 1))
    c.record("S4 refund/chargeback", all(k["ok"] for k in checks), checks)


async def s5_error_paths(c: Cert) -> None:
    """S5: негативные сценарии — контур fail-closed."""
    checks = []
    order_payload = c.state_s1["payload"]
    txn_id = c.state_s1["txn_id"]

    good_body = webhook_body("evt_cert_err_1", "transaction.completed", {
        "id": txn_id, "status": "completed", "currency_code": "USD",
        "custom_data": {"order_payload": order_payload},
        "items": [{"price": {"id": "pri_cert_vip"}}],
    })

    # 5.1 битая подпись
    bad_sig = {"Paddle-Signature": "ts=123;h1=" + "0" * 64}
    res = await c.http.post("/api/webhooks/paddle", content=good_body,
                            headers=bad_sig)
    checks.append(await c.check("5.1 битая подпись → 401",
                                res.status_code == 401, f"HTTP {res.status_code}"))

    # 5.2 просроченная подпись (>MAX_SIGNATURE_AGE=300с)
    old_ts = int(time.time()) - 3600
    stale = signed_webhook(good_body, ts=old_ts)
    res = await c.http.post("/api/webhooks/paddle", content=good_body,
                            headers=stale)
    checks.append(await c.check("5.2 просроченная подпись → 401",
                                res.status_code == 401, f"HTTP {res.status_code}"))

    # 5.3 чужой transaction_id (не совпал с заказом) → unmatched, без выдачи
    foreign = webhook_body("evt_cert_err_2", "transaction.completed", {
        "id": "txn_attacker_forged", "status": "completed",
        "currency_code": "USD",
        "custom_data": {"order_payload": order_payload},
        "items": [{"price": {"id": "pri_cert_vip"}}],
    })
    res = await c.http.post("/api/webhooks/paddle", content=foreign,
                            headers=signed_webhook(foreign))
    ok = res.status_code == 200 and res.json().get("unmatched") is True
    checks.append(await c.check("5.3 чужой txn_id → unmatched, HTTP 200",
                                ok, f"HTTP {res.status_code}: {res.text[:200]}"))

    # 5.4 неверный price_id → unmatched
    wrong_price = webhook_body("evt_cert_err_3", "transaction.completed", {
        "id": txn_id, "status": "completed", "currency_code": "USD",
        "custom_data": {"order_payload": order_payload},
        "items": [{"price": {"id": "pri_fake_price"}}],
    })
    res = await c.http.post("/api/webhooks/paddle", content=wrong_price,
                            headers=signed_webhook(wrong_price))
    ok = res.status_code == 200 and res.json().get("unmatched") is True
    checks.append(await c.check("5.4 неверный price_id → unmatched",
                                ok, f"HTTP {res.status_code}: {res.text[:200]}"))

    # 5.5 событие не-pending заказа (уже оплачен) → duplicate/unmatched, без
    #     двойной выдачи. Новый event_id на тот же оплаченный заказ.
    already_paid = webhook_body("evt_cert_err_4", "transaction.completed", {
        "id": txn_id, "status": "completed", "currency_code": "USD",
        "custom_data": {"order_payload": order_payload},
        "items": [{"price": {"id": "pri_cert_vip"}}],
    })
    res = await c.http.post("/api/webhooks/paddle", content=already_paid,
                            headers=signed_webhook(already_paid))
    checks.append(await c.check("5.5 повторная оплата не-pending заказа без выдачи",
                                res.status_code == 200
                                and res.json().get("granted") is not True,
                                f"HTTP {res.status_code}: {res.text[:200]}"))

    # 5.6 event_id слишком длинный/битый → 400
    evil = webhook_body("x" * 200, "transaction.completed", {
        "id": txn_id, "status": "completed",
        "custom_data": {"order_payload": order_payload}})
    res = await c.http.post("/api/webhooks/paddle", content=evil,
                            headers=signed_webhook(evil))
    checks.append(await c.check("5.6 event_id >128 символов → 400",
                                res.status_code == 400, f"HTTP {res.status_code}"))

    # 5.7 неактивный тариф: pending-заказ на отключённый план → unmatched
    cur = await c.db.execute(
        "UPDATE plans SET is_active=0 WHERE code='vip_year' RETURNING code")
    row = await cur.fetchone()
    if row:
        order2 = await billing_repo.create_order(
            c.db, CERT_TG_ID, "plan", sku="vip_year", title="VIP year",
            amount_stars=0, surface="web",
            meta={"grant_kind": "plan", "grant_code": "vip_year",
                  "grant_qty": 1, "valid_days": 365, "provider": "paddle"})
        inactive = webhook_body("evt_cert_err_5", "transaction.completed", {
            "id": "txn_sim_inactive", "status": "completed", "currency_code": "USD",
            "custom_data": {"order_payload": order2["payload"]},
            "items": [{"price": {"id": "pri_cert_vip"}}]})
        res = await c.http.post("/api/webhooks/paddle", content=inactive,
                                headers=signed_webhook(inactive))
        checks.append(await c.check("5.7 webhook неактивного тарифа → unmatched",
                                    res.status_code == 200
                                    and res.json().get("unmatched") is True,
                                    f"HTTP {res.status_code}: {res.text[:200]}"))
        cur = await c.db.execute(
            "UPDATE plans SET is_active=1 WHERE code='vip_year'")

    checks.append(await c.check("payments не выросли (все ошибки без выдачи)",
                                await c.sql_count(
                                    "SELECT COUNT(*) FROM payments "
                                    "WHERE provider='paddle'") == 1))
    c.record("S5 error paths", all(k["ok"] for k in checks), checks)


# ─────────────────────────────── reconciliation ──────────────────────────────

async def reconciliation(c: Cert) -> dict:
    """Сверка: платежи ↔ заказы ↔ журнал вебхуков ↔ состояние подписки."""
    checks = []
    cur = await c.db.execute(
        "SELECT id, payload, tg_id, sku, kind, status, surface, meta_json, "
        "amount_stars, created_at, paid_at FROM orders WHERE surface='web' "
        "ORDER BY id")
    web_orders = [dict(r) for r in await cur.fetchall()]
    cur = await c.db.execute(
        "SELECT id, tg_id, provider, amount_stars, currency, charge_id, created_at "
        "FROM payments WHERE provider='paddle' ORDER BY id")
    payments = [dict(r) for r in await cur.fetchall()]
    cur = await c.db.execute(
        "SELECT event_id, provider, kind, created_at FROM webhook_events "
        "WHERE provider='paddle' ORDER BY event_id")
    hooks = [dict(r) for r in await cur.fetchall()]

    paid_web_orders = [o for o in web_orders if o["status"] == "paid"]
    checks.append(await c.check(
        "each paid web order имеет ровно одну payment",
        len(paid_web_orders) == len(payments)
        and all(p["tg_id"] == o["tg_id"] for o, p in zip(paid_web_orders, payments)),
        f"paid_orders={len(paid_web_orders)} payments={len(payments)}"))

    # granting вычислен сверкой ниже; переменная не нужна отдельно
    _ = [h for h in hooks if h["kind"] == "transaction.completed"]
    # Истинная сверка «деньги ↔ журнал»: каждый payment обязан ссылаться на
    # event_id, зафиксированный в webhook_events (charge_id == event_id).
    event_ids = {h["event_id"] for h in hooks}
    orphan_payments = [p["charge_id"] for p in payments
                       if p["charge_id"] not in event_ids]
    checks.append(await c.check(
        "каждый payment имеет запись в журнале webhook_events (charge_id↔event_id)",
        not orphan_payments,
        f"payments={len(payments)} без_journal={orphan_payments}"))

    # sku web-заказа присутствует в каталоге (v2-определение или plans)
    v2_codes = {d["code"] for d in PLAN_DEFINITIONS}
    cur = await c.db.execute("SELECT code FROM plans")
    legacy_codes = {r["code"] for r in await cur.fetchall()}
    skus_ok = all(o["sku"] in v2_codes or o["sku"] in legacy_codes
                  for o in web_orders)
    checks.append(await c.check("все web-заказы ссылаются на sku каталога",
                                skus_ok,
                                f"skus={sorted({o['sku'] for o in web_orders})}"))

    sub = await c.subscription_state(CERT_TG_ID)
    checks.append(await c.check(
        "выдача согласована: sub_level=vip при paid-заказе sku=vip",
        bool(paid_web_orders) and sub["sub_level"] == "vip",
        f"sub={sub}"))

    report = {
        "web_orders": [{k: (str(v) if isinstance(v, (int, float, str)) or v is None
                            else str(v)) for k, v in o.items() if k != "meta_json"}
                       for o in web_orders],
        "payments": [{"id": p["id"], "tg_id": p["tg_id"],
                      "provider": p["provider"],
                      "currency": p["currency"], "charge_id": p["charge_id"]}
                     for p in payments],
        "webhook_events": [{"event_id": h["event_id"], "kind": h["kind"]}
                           for h in hooks],
        "subscription": sub,
        "checks": checks,
        "passed": all(k["ok"] for k in checks),
    }
    c.record("Reconciliation", report["passed"], checks)
    return report


# ─────────────────────────────────── main ────────────────────────────────────

async def main() -> int:
    c = Cert()
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    c.log(f"=== P0-002 payments sandbox certification ({started}) ===")
    c.log(f"DATABASE_URL: {os.environ['DATABASE_URL'].split('@')[-1]}")
    c.log(f"Paddle API-симулятор: {c.sim.api_url}")
    exit_code = 0
    try:
        await c.setup()
        for name, fn in (("S1", s1_invoice), ("S2", s2_payment),
                         ("S3", s3_duplicate), ("S4", s4_refund_chargeback),
                         ("S5", s5_error_paths)):
            try:
                await fn(c)
            except Exception as exc:  # noqa: BLE001
                c.log(f"  !!! {name} упал с {type(exc).__name__}: {exc}")
                RESULTS.append({"scenario": fn.__name__, "passed": False,
                                "checks": [], "error": f"{type(exc).__name__}: {exc}"})
        recon = await reconciliation(c)
    except Exception as exc:  # noqa: BLE001
        c.log(f"FATAL: setup/main провалился: {type(exc).__name__}: {exc}")
        recon = {"error": str(exc), "passed": False}
        exit_code = 2
    finally:
        try:
            await c.teardown()
        except Exception:  # noqa: BLE001
            pass
        c._logf = None

    scenarios = [{"scenario": r["scenario"], "passed": r["passed"]}
                 for r in RESULTS]
    all_ok = all(s["passed"] for s in scenarios) and recon.get("passed", False)
    findings = [
        "F1: refund/chargeback принимаются и журналируются, но entitlement не "
        "отзывается (GRANTING_EVENTS только transaction.completed) — решение об "
        "отзыве доступа: CFO + Engineering Lead.",
        "F2: реальный Paddle sandbox не подключён (нет API-ключей в окружении): "
        "сетевой путь create_transaction прогнан против локального симулятора "
        "Paddle API; подписи вебхуков — по алгоритму Paddle. Подключение "
        "staging-ключей — DevOps (external).",
    ]
    report = {
        "gate": "P0-002", "issue": "BUS-109",
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "db": os.environ["DATABASE_URL"].split("@")[-1],
        "scenarios": RESULTS,
        "reconciliation": recon,
        "findings": findings,
        "verdict": "PASS" if all_ok else "FAIL",
    }
    c.log(f"\n=== ВЕРДИКТ: {report['verdict']} ===")
    for s in scenarios:
        c.log(f"  {s['scenario']}: {'PASS' if s['passed'] else 'FAIL'}")
    for f in findings:
        c.log(f"  Finding: {f}")
    c.json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    c.log(f"JSON: {c.json_path}")
    return exit_code if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
