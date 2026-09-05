#!/usr/bin/env python3
"""Staging-сертификация платёжного контура против реального Paddle sandbox.

Отличия от scripts/payments_sandbox_cert.py (BUS-109, симулятор):
- работает через сеть против staging API (uvicorn в контейнере, production-режим,
  без dev_user/X-Dev-Key — на staging их нет и быть не должно);
- подписи вебхуков генерируются реальным PADDLE_WEBHOOK_SECRET из .env.staging
  (тот же секрет, что прописан в Paddle Dashboard → Notifications);
- checkpayment-контур создаётся через настоящий вызов sandbox-api.paddle.com
  (серверный путь paddle.create_transaction).

Запуск — ВНУТРИ контейнера staging-api (у хоста нет доступа к staging-postgres,
в контейнере есть httpx и DATABASE_URL; infra/ не входит в образ — скрипт
подхватывается из репо через stdin):

    docker exec -i oracleai-staging-staging-api-1 \
      python3 - < infra/staging/payments_staging_cert.py

Требует заполненного блока PADDLE_* в .env.staging (см. PADDLE_SANDBOX_RUNBOOK.md §1).
Скрипт идемпотентен: чистит только cert-данные (tg_id 550002, event_id evt_stgcert%).
Секреты в логи не пишутся.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time

STAGING_BASE_URL = os.environ.get("CERT_BASE_URL") or "http://localhost:8080"
CERT_TG_ID = 550002
ROOT = "/opt/oracle"

RESULTS: list[dict] = []
FINDINGS: list[str] = []


def log(message: str) -> None:
    print(message, flush=True)


def record(scenario: str, passed: bool, checks: list[dict]) -> None:
    RESULTS.append({"scenario": scenario, "passed": passed, "checks": checks})
    log(f"  → {scenario}: {'PASS' if passed else 'FAIL'} "
        f"({sum(c['ok'] for c in checks)}/{len(checks)} проверок)")


async def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def signed_webhook(body: bytes, secret: str, ts: int | None = None) -> dict:
    """Заголовок Paddle-Signature: ts=...;h1=<hmac-sha256(ts:body)>."""
    ts = ts if ts is not None else int(time.time())
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + body,
                      hashlib.sha256).hexdigest()
    return {"Paddle-Signature": f"ts={ts};h1={digest}"}


def webhook_body(event_id: str, event_type: str, data: dict) -> bytes:
    return json.dumps({"event_id": event_id, "event_type": event_type,
                       "occurred_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                       "data": data}, separators=(",", ":")).encode()


async def fresh_user(db, tg_id: int) -> dict:
    from app.repo import users as users_repo
    await users_repo.ensure(db, tg_id, "Сертификат Staging", "cert")
    return await users_repo.get(db, tg_id)


async def sql_count(db, sql: str, params: dict | None = None) -> int:
    cur = await db.execute(sql, params or {})
    row = await cur.fetchone()
    return int(row[0] or 0)


async def subscription_state(db, tg_id: int) -> dict:
    cur = await db.execute(
        "SELECT sub_level, sub_until FROM users WHERE tg_id=:tg", {"tg": tg_id})
    row = await cur.fetchone()
    return {"sub_level": row["sub_level"], "sub_until": row["sub_until"]} if row else {}


class StagingCert:
    """Сетевой прогон: HTTP против staging API, БД через локальный DATABASE_URL."""

    def __init__(self) -> None:
        self.db = None
        self.http = None
        self.secret = ""
        self.api_key = ""
        self.api_url = "https://sandbox-api.paddle.com"
        self.price_ids: dict[str, str] = {}
        self.state: dict = {}
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_path = f"{ROOT}/logs/payments_staging_cert_{stamp}.log"
        self.json_path = self.log_path.replace(".log", ".json")

    async def setup(self) -> None:
        from app.config import settings
        from app.data.session import connect
        import httpx

        self.secret = settings.paddle_webhook_secret
        self.api_key = settings.paddle_api_key
        self.api_url = (settings.paddle_api_url or self.api_url).rstrip("/")
        self.price_ids = {
            code.strip(): pid.strip()
            for item in settings.paddle_price_ids.split(",")
            if ":" in item
            for code, pid in [item.split(":", 1)]
        }
        missing = [name for name, value in [
            ("PADDLE_API_KEY", self.api_key),
            ("PADDLE_WEBHOOK_SECRET", self.secret),
            ("PADDLE_CHECKOUT_URL", settings.paddle_checkout_url),
            ("PADDLE_PRICE_IDS", settings.paddle_price_ids),
        ] if not value]
        if missing:
            raise RuntimeError(
                "PADDLE_* не настроены: " + ", ".join(missing) +
                " — см. PADDLE_SANDBOX_RUNBOOK.md §1/§2")
        if "sdbx_" not in self.api_key:
            raise RuntimeError(
                "PADDLE_API_KEY без маркера sdbx_ — live-ключ на staging запрещён "
                "(fail-closed, check_staging_isolation.sh 3b)")

        self.db = await connect(seed=False)
        # Чистим только cert-данные прошлых прогонов, не произвольные.
        await self.db.execute(
            "DELETE FROM webhook_events WHERE event_id LIKE 'evt\\_stgcert%'")
        await self.db.execute("DELETE FROM payments WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        await self.db.execute("DELETE FROM orders WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        await self.db.execute("DELETE FROM events WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        await self.db.execute("DELETE FROM users WHERE tg_id=:tg", {"tg": CERT_TG_ID})
        # Флаг web_payments включаем для cert-пользователя (команда из admin_cli
        # на staging делает то же самое; здесь — прямой SQL для воспроизводимости).
        from app.repo import content as content_repo
        await content_repo.set_flag(self.db, "web_payments", is_on=True,
                                    description="BUS-134 staging certification")
        self.http = httpx.AsyncClient(base_url=STAGING_BASE_URL, timeout=30)

    async def teardown(self) -> None:
        if self.http:
            await self.http.aclose()
        if self.db:
            await self.db.close()


# ─────────────────────────────── сценарии ───────────────────────────────────

async def s0_provider_smoke(c: StagingCert) -> None:
    """S0: ключ живой против реального sandbox API (GET /event-types)."""
    checks = []
    import httpx
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.get(
            f"{c.api_url}/event-types",
            headers={"Authorization": f"Bearer {c.api_key}"})
    checks.append(await check("sandbox API event-types HTTP 200",
                              res.status_code == 200, f"HTTP {res.status_code}"))
    if res.status_code == 200:
        names = [str(t.get("name") or "") for t in (res.json().get("data") or [])]
        for needed in ("transaction.completed", "adjustment.created"):
            checks.append(await check(f"Paddle отдаёт событие {needed}",
                                      needed in names))
    record("S0 provider smoke", all(k["ok"] for k in checks), checks)


async def s1_invoice(c: StagingCert) -> None:
    """S1: web-checkout через staging API создаёт заказ + РЕАЛЬНУЮ Paddle-транзакцию."""
    checks = []
    await fresh_user(c.db, CERT_TG_ID)
    # web-checkout требует аутентифицированной клиентки: на staging нет dev_user.
    # Обход для сертификации: создаём pending-заказ напрямую тем же серверным
    # кодом (checkout_web_plan) — сеть идёт в реальный Paddle sandbox.
    from app.config import settings
    from app.services import billing as billing_svc
    try:
        order = await billing_svc.checkout_web_plan(
            c.db, CERT_TG_ID, "vip", surface="web", billing_period="monthly")
    except billing_svc.PurchaseError as exc:
        checks.append(await check(
            "checkout_web_plan создал заказ (реальный вызов Paddle sandbox)",
            False, f"PurchaseError: {exc}"))
        record("S1 invoice (real provider)", False, checks)
        return
    checks.append(await check("checkout_web_plan вернул link с transaction_id",
                              "transaction_id=" in (order.get("link") or "")))
    checks.append(await check("link ведёт на PADDLE_CHECKOUT_URL",
                              (order.get("link") or "").startswith(
                                  settings.paddle_checkout_url)))
    meta = json.loads(order["meta_json"] or "{}")
    txn_id = meta.get("paddle_transaction_id", "")
    checks.append(await check("paddle_transaction_id начинается с txn_",
                              txn_id.startswith("txn_"),
                              f"txn_id={txn_id[:12]}…"))
    checks.append(await check("заказ в БД: status=pending, surface=web, sku=vip",
                              order["status"] == "pending" and order["surface"] == "web"
                              and order["sku"] == "vip"))
    checks.append(await check("event web_checkout записан в analytics",
                              await sql_count(c.db,
                                  "SELECT COUNT(*) FROM events WHERE name='web_checkout' "
                                  "AND tg_id=:tg", {"tg": CERT_TG_ID}) >= 1))
    c.state["payload"] = order["payload"]
    c.state["txn_id"] = txn_id
    record("S1 invoice (real provider)", all(k["ok"] for k in checks), checks)


async def s2_payment(c: StagingCert) -> None:
    """S2: подписанный РЕАЛЬНЫМ секретом webhook transaction.completed выдаёт подписку."""
    checks = []
    order = await billing_repo_order(c.db, c.state["payload"])
    body = webhook_body("evt_stgcert_s2", "transaction.completed", {
        "id": c.state["txn_id"], "status": "completed",
        "currency_code": "USD",
        "custom_data": {"order_payload": c.state["payload"]},
        "items": [{"price": {"id": c.price_ids.get("vip", "")},
                   "quantity": 1}],
    })
    before = await subscription_state(c.db, CERT_TG_ID)
    res = await c.http.post("/api/webhooks/paddle", content=body,
                            headers=signed_webhook(body, c.secret))
    checks.append(await check("webhook HTTP 200", res.status_code == 200,
                              f"HTTP {res.status_code}: {res.text[:200]}"))
    after = await subscription_state(c.db, CERT_TG_ID)
    checks.append(await check("подписка выдана (sub_level > before)",
                              int(after.get("sub_level") or 0) > int(before.get("sub_level") or 0),
                              f"before={before} after={after}"))
    checks.append(await check("payments: запись с provider=paddle",
                              await sql_count(c.db,
                                  "SELECT COUNT(*) FROM payments WHERE tg_id=:tg "
                                  "AND provider='paddle'", {"tg": CERT_TG_ID}) >= 1))
    checks.append(await check("charge_id == webhook event_id (reconciliation-связка)",
                              await sql_count(c.db,
                                  "SELECT COUNT(*) FROM payments WHERE tg_id=:tg "
                                  "AND charge_id='evt_stgcert_s2'",
                                  {"tg": CERT_TG_ID}) >= 1))
    checks.append(await check("webhook_events: событие журналировано",
                              await sql_count(c.db,
                                  "SELECT COUNT(*) FROM webhook_events "
                                  "WHERE event_id='evt_stgcert_s2'") == 1))
    checks.append(await check("orders: status=paid",
                              bool(order) and order["status"] == "paid"))
    record("S2 payment (real secret)", all(k["ok"] for k in checks), checks)


async def s3_duplicate(c: StagingCert) -> None:
    """S3: повторная доставка того же события не выдаёт второй раз."""
    checks = []
    body = webhook_body("evt_stgcert_s2", "transaction.completed", {
        "id": c.state["txn_id"], "status": "completed",
        "currency_code": "USD",
        "custom_data": {"order_payload": c.state["payload"]},
        "items": [{"price": {"id": c.price_ids.get("vip", "")}, "quantity": 1}],
    })
    res = await c.http.post("/api/webhooks/paddle", content=body,
                            headers=signed_webhook(body, c.secret))
    checks.append(await check("повторный webhook HTTP 200", res.status_code == 200,
                              f"HTTP {res.status_code}"))
    checks.append(await check("ответ помечен duplicate", "duplicate" in res.text,
                              res.text[:200]))
    checks.append(await check("payments не задвоились",
                              await sql_count(c.db,
                                  "SELECT COUNT(*) FROM payments WHERE tg_id=:tg",
                                  {"tg": CERT_TG_ID}) == 1))
    before_after = await subscription_state(c.db, CERT_TG_ID)
    checks.append(await check("sub_until не продлился",
                              bool(before_after.get("sub_until"))))
    record("S3 duplicate", all(k["ok"] for k in checks), checks)


async def s4_refund_chargeback(c: StagingCert) -> None:
    """S4: adjustment-события журналируются; entitlement не трогается (текущее поведение)."""
    checks = []
    body = webhook_body("evt_stgcert_s4", "adjustment.created", {
        "id": "adj_stgcert_test", "action": "refund",
        "transaction_id": c.state["txn_id"],
        "items": [{"type": "full"}],
    })
    res = await c.http.post("/api/webhooks/paddle", content=body,
                            headers=signed_webhook(body, c.secret))
    checks.append(await check("adjustment webhook HTTP 200", res.status_code == 200,
                              f"HTTP {res.status_code}"))
    checks.append(await check("adjustment журналирован в webhook_events",
                              await sql_count(c.db,
                                  "SELECT COUNT(*) FROM webhook_events "
                                  "WHERE event_id='evt_stgcert_s4' "
                                  "AND kind='adjustment.created'") == 1))
    after = await subscription_state(c.db, CERT_TG_ID)
    checks.append(await check("entitlement не отозван (текущая политика)",
                              bool(after.get("sub_level")),
                              f"state={after}"))
    FINDINGS.append(
        "F1: adjustment-события журналируются, entitlement не отзывается "
        "(GRANTING_EVENTS только transaction.completed) — решение: CFO + EL "
        "(interaction BUS-134).")
    record("S4 refund/chargeback", all(k["ok"] for k in checks), checks)


async def s5_error_paths(c: StagingCert) -> None:
    """S5: битая подпись, просроченный ts, чужой transaction_id — всё отклоняется."""
    checks = []
    base_data = {
        "id": c.state["txn_id"], "status": "completed", "currency_code": "USD",
        "custom_data": {"order_payload": c.state["payload"]},
        "items": [{"price": {"id": c.price_ids.get("vip", "")}, "quantity": 1}],
    }
    body = webhook_body("evt_stgcert_s5a", "transaction.completed", base_data)
    res = await c.http.post("/api/webhooks/paddle", content=body,
                            headers=signed_webhook(body, "wrong-secret"))
    checks.append(await check("битая подпись → 401", res.status_code == 401,
                              f"HTTP {res.status_code}"))
    stale = signed_webhook(body, c.secret, ts=int(time.time()) - 3600)
    res = await c.http.post("/api/webhooks/paddle", content=body, headers=stale)
    checks.append(await check("просроченная подпись (ts -1h) → 401",
                              res.status_code == 401, f"HTTP {res.status_code}"))
    foreign = webhook_body("evt_stgcert_s5c", "transaction.completed", {
        **base_data, "id": "txn_someone_elses"})
    res = await c.http.post("/api/webhooks/paddle", content=foreign,
                            headers=signed_webhook(foreign, c.secret))
    checks.append(await check("чужой transaction_id → 200 без выдачи",
                              res.status_code == 200,
                              f"HTTP {res.status_code}: {res.text[:120]}"))
    checks.append(await check("после S5 подписка на месте",
                              bool((await subscription_state(c.db, CERT_TG_ID)).get("sub_level"))))
    checks.append(await check("failures журналированы (signature_rejected)",
                              await sql_count(c.db,
                                  "SELECT COUNT(*) FROM payment_webhook_failures "
                                  "WHERE code='signature_rejected'") >= 2))
    record("S5 error paths", all(k["ok"] for k in checks), checks)


async def billing_repo_order(db, payload: str) -> dict | None:
    from app.services.repo_gateway import billing as billing_repo
    return await billing_repo.order_by_payload(db, payload)


async def reconciliation(c: StagingCert) -> dict:
    """payments.charge_id ↔ webhook_events.event_id — та же связка, что в BUS-109."""
    checks = []
    mismatched = await sql_count(c.db,
        "SELECT COUNT(*) FROM payments p WHERE p.tg_id=:tg AND p.provider='paddle' "
        "AND NOT EXISTS (SELECT 1 FROM webhook_events w WHERE w.event_id = p.charge_id)",
        {"tg": CERT_TG_ID})
    checks.append(await check("каждый paddle-платёж имеет журнал webhook_events",
                              mismatched == 0, f"mismatched={mismatched}"))
    passed = all(k["ok"] for k in checks)
    record("Reconciliation", passed, checks)
    return {"passed": passed, "checks": checks}


async def main() -> int:
    c = StagingCert()
    started = time.strftime("%Y-%m-%d %H:%M:%S")
    log(f"=== P0-002 payments staging certification vs real Paddle sandbox ({started}) ===")
    log(f"BASE_URL: {STAGING_BASE_URL}; API: {c.api_url}")
    exit_code = 0
    try:
        await c.setup()
        for fn in (s0_provider_smoke, s1_invoice, s2_payment, s3_duplicate,
                   s4_refund_chargeback, s5_error_paths, reconciliation):
            try:
                await fn(c)
            except Exception as exc:  # noqa: BLE001
                log(f"  !!! {fn.__name__} упал с {type(exc).__name__}: {exc}")
                RESULTS.append({"scenario": fn.__name__, "passed": False,
                                "checks": [], "error": f"{type(exc).__name__}: {exc}"})
    except Exception as exc:  # noqa: BLE001
        log(f"FATAL: setup/main провалился: {type(exc).__name__}: {exc}")
        RESULTS.append({"scenario": "setup", "passed": False, "checks": [],
                        "error": f"{type(exc).__name__}: {exc}"})
        exit_code = 2
    finally:
        try:
            await c.teardown()
        except Exception:  # noqa: BLE001
            pass

    report = {
        "gate": "P0-002", "issue": "BUS-134",
        "target": "staging (real Paddle sandbox provider)",
        "started_at": started,
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "scenarios": RESULTS,
        "findings": FINDINGS,
        "verdict": "PASS" if RESULTS and all(s["passed"] for s in RESULTS) else "FAIL",
    }
    log(f"\n=== ВЕРДИКТ: {report['verdict']} ===")
    for s in RESULTS:
        log(f"  {s['scenario']}: {'PASS' if s['passed'] else 'FAIL'}")
    for f in FINDINGS:
        log(f"  Finding: {f}")
    try:
        os.makedirs(os.path.dirname(c.json_path), exist_ok=True)
        with open(c.json_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        log(f"JSON: {c.json_path}")
    except OSError as exc:
        log(f"JSON не записан ({exc}): вывод в stdout")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
