"""API новых разделов: практики, гороскопы, шеринг, web-оплата, новые экраны панели.

Соединение с БД подменяется через `dependency_overrides` — иначе тесты писали бы
в боевой файл, указанный в .env.
"""
from __future__ import annotations

import pytest

from conftest import TEST_DEV_KEY  # noqa: E402

pytest.importorskip("httpx", reason="httpx нужен для тестов API")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.main import app  # noqa: E402
from app.repo import users  # noqa: E402


@pytest.fixture
async def client(db, user):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                      headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def as_user(user, params: dict | None = None) -> dict:
    return {"dev_user": user["tg_id"], **(params or {})}


# ────────────────────────────── практики ──────────────────────────────────────

async def test_practices_catalog_has_categories(client, user):
    res = await client.get("/api/practices", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    assert data["categories"], "нет разделов практик"
    assert len(data["items"]) >= 10, "каталог практик почти пуст"
    assert all(p["steps"] and p["today_step"] for p in data["items"])


async def test_practices_filter_by_category(client, user):
    res = await client.get("/api/practices",
                           params=as_user(user, {"category": "love"}))
    assert res.status_code == 200
    items = res.json()["items"]
    assert items and {p["category"] for p in items} == {"love"}


async def test_practice_lifecycle(client, user):
    started = await client.post("/api/practices/money_mirror/start",
                                params=as_user(user))
    assert started.status_code == 200
    assert started.json()["started"] is True

    done = await client.post("/api/practices/money_mirror/done", params=as_user(user))
    assert done.status_code == 200
    assert done.json()["streak"] == 1
    assert done.json()["message"]

    again = await client.post("/api/practices/money_mirror/done", params=as_user(user))
    assert again.json()["already"] is True, "повторное нажатие накрутило стрик"

    stopped = await client.post("/api/practices/money_mirror/stop",
                                params=as_user(user))
    assert stopped.json()["ok"] is True


async def test_unknown_practice_is_404(client, user):
    res = await client.post("/api/practices/выдумка/start", params=as_user(user))
    assert res.status_code == 404


async def test_practice_card_endpoint(client, user):
    res = await client.get("/api/practices/mantra_lakshmi", params=as_user(user))
    assert res.status_code == 200
    item = res.json()
    assert item["text"], "у мантры нет текста"
    assert item["signs"], "нет знаков продвижения"


# ────────────────────────────── гороскопы ─────────────────────────────────────

async def test_horoscope_for_own_sign(client, user):
    res = await client.get("/api/horoscope", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    assert data["sign"] and data["text"]
    assert len(data["text"]) > 60


async def test_horoscope_all_signs(client, user):
    res = await client.get("/api/horoscope/all", params=as_user(user))
    assert res.status_code == 200
    assert len(res.json()) == 12


async def test_horoscope_unknown_sign_is_404(client, user):
    res = await client.get("/api/horoscope",
                           params=as_user(user, {"sign": "Дракон"}))
    assert res.status_code == 404


# ─────────────────────────── дневник: вопрос дня ──────────────────────────────

async def test_diary_prompt_is_personal(client, user):
    res = await client.get("/api/diary/prompt", params=as_user(user))
    assert res.status_code == 200
    data = res.json()
    assert data["prompt"] and not data["written_today"]

    await client.post("/api/diary", params=as_user(user),
                      json={"text": "день прошёл спокойно"})
    after = await client.get("/api/diary/prompt", params=as_user(user))
    assert after.json()["written_today"] is True


# ──────────────────────────── картинки для сторис ─────────────────────────────

async def test_share_state_is_reported(client, user):
    res = await client.get("/api/share/enabled", params=as_user(user))
    assert res.status_code == 200
    assert set(res.json()) == {"cards", "flag"}


async def test_share_reading_requires_ownership(client, db, user):
    """Прямая ссылка на картинку чужого расклада не должна работать."""
    from app.services import chat as chat_svc
    drawn = await chat_svc.draw(db, user, "one")
    await users.ensure(db, 4242, "Чужая")
    res = await client.get(f"/api/share/reading/{drawn['reading_id']}.png",
                           params={"dev_user": 4242})
    assert res.status_code == 404


async def test_share_missing_reading_is_404(client, user):
    res = await client.get("/api/share/reading/999999.png", params=as_user(user))
    assert res.status_code == 404


async def test_share_reading_png_renders(client, db, user):
    """Своя карточка расклада отдаётся картинкой (рендер в потоке, G16)."""
    from app.services import chat as chat_svc
    drawn = await chat_svc.draw(db, user, "one")
    res = await client.get(f"/api/share/reading/{drawn['reading_id']}.png",
                           params=as_user(user))
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n", "ответ не похож на PNG"


# ────────────────────────────── web-оплата ────────────────────────────────────

async def test_web_checkout_hidden_when_flag_off(client, user):
    """Флаг `web_payments` выключен по умолчанию — предлагать оплату нельзя."""
    res = await client.post("/api/shop/web-checkout", params=as_user(user),
                            json={"plan": "vip"})
    assert res.status_code == 404


async def test_web_checkout_needs_configuration(client, db, user):
    from app.repo import content
    await content.set_flag(db, "web_payments", is_on=True)
    res = await client.post("/api/shop/web-checkout", params=as_user(user),
                            json={"plan": "vip"})
    # ссылки на чекаут нет в .env — честный 503, а не битая ссылка клиентке
    assert res.status_code == 503


async def test_paddle_webhook_requires_signature(client):
    res = await client.post("/api/webhooks/paddle",
                            json={"event_id": "evt_1",
                                  "event_type": "transaction.completed"})
    assert res.status_code in (401, 503)


# ─────────────────────────── админка: новые экраны ────────────────────────────

async def test_admin_costs_are_reported(client, db):
    await users.ensure(db, 1, "Владелец")
    res = await client.get("/api/admin/costs", params={"dev_user": 1})
    assert res.status_code == 200
    data = res.json()
    for key in ("cost_usd", "calls", "per_paying_usd", "by_purpose", "by_model"):
        assert key in data, key


async def test_admin_safety_log(client, db, user):
    from app.services import chat as chat_svc
    await users.ensure(db, 1, "Владелец")
    await chat_svc.ask(db, user, "не хочу жить")
    res = await client.get("/api/admin/safety", params={"dev_user": 1})
    assert res.status_code == 200
    assert res.json()["recent"], "кризисное обращение не попало в панель"


async def test_admin_horoscopes_build(client, db):
    await users.ensure(db, 1, "Владелец")
    res = await client.post("/api/admin/horoscopes/build", params={"dev_user": 1})
    assert res.status_code == 200
    assert res.json()["built"] == 12
    listed = await client.get("/api/admin/horoscopes", params={"dev_user": 1})
    assert len(listed.json()["items"]) == 12


async def test_web_checkout_binds_server_order(client, db, user, monkeypatch):
    import json

    from app.config import settings
    from app.repo import billing as billing_repo, content
    from app.services import paddle

    await content.set_flag(db, "web_payments", is_on=True)
    monkeypatch.setattr(settings, "paddle_checkout_url",
                        "https://pay.paddle.io/checkout/test")
    monkeypatch.setattr(settings, "paddle_api_key", "test-key")
    monkeypatch.setattr(settings, "paddle_price_ids", "vip:pri_test_vip")
    captured = {}

    async def fake_create_transaction(*, price_id, custom_data):
        captured.update(price_id=price_id, custom_data=custom_data)
        return {"id": "txn_test",
                "link": "https://pay.paddle.io/checkout/test?transaction_id=txn_test"}

    monkeypatch.setattr(paddle, "create_transaction", fake_create_transaction)
    res = await client.post("/api/shop/web-checkout", params=as_user(user),
                            json={"plan": "vip"})
    assert res.status_code == 200
    assert res.json()["link"].endswith("transaction_id=txn_test")
    assert captured == {
        "price_id": "pri_test_vip",
        "custom_data": {"order_payload": captured["custom_data"]["order_payload"]},
    }
    order = await billing_repo.order_by_payload(db,
                                                 captured["custom_data"]["order_payload"])
    assert order and order["status"] == "pending"
    assert order["tg_id"] == user["tg_id"]
    assert order["sku"] == "vip"
    assert json.loads(order["meta_json"])["paddle_transaction_id"] == "txn_test"


async def test_paddle_webhook_grants_only_bound_pending_order(client, db, user, monkeypatch):
    import hashlib
    import hmac
    import json
    import time

    from app.config import settings
    from app.repo import billing as billing_repo

    secret = "paddle-test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)
    order = await billing_repo.create_order(
        db, user["tg_id"], "plan", sku="vip", title="VIP", surface="web",
        meta={"grant_kind": "plan", "grant_code": "vip", "grant_qty": 1,
              "valid_days": 30, "provider": "paddle"})
    await billing_repo.set_order_meta(
        db, order["payload"], paddle_transaction_id="txn_bound_1")
    body = json.dumps({
        "event_id": "evt_bound_1",
        "event_type": "transaction.completed",
        "data": {
            "id": "txn_bound_1", "status": "completed", "currency_code": "USD",
            "custom_data": {"order_payload": order["payload"]},
        },
    }, separators=(",", ":")).encode()
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + body,
                      hashlib.sha256).hexdigest()
    headers = {"Paddle-Signature": f"ts={ts};h1={digest}"}

    first = await client.post("/api/webhooks/paddle", content=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["granted"] is True
    webhook_row = await (await db.execute(
        "SELECT payload FROM webhook_events WHERE event_id=?", ("evt_bound_1",)
    )).fetchone()
    assert webhook_row["payload"] is None
    paid = await billing_repo.order_by_payload(db, order["payload"])
    assert paid["status"] == "paid"

    second = await client.post("/api/webhooks/paddle", content=body, headers=headers)
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


async def test_crypto_webhook_replays_are_rejected(client, db, user, monkeypatch):
    """Аудит 2.4: повторная доставка invoice_paid не выдаёт Кристаллы дважды."""
    import hashlib
    import hmac
    import json

    from app.config import settings
    from app.repo import billing as billing_repo

    secret = "crypto-test-secret"
    monkeypatch.setattr(settings, "cryptobot_api_token", secret)
    order = await billing_repo.create_order(
        db, user["tg_id"], "crystals", sku="crystals_100", title="100 Кристаллов",
        meta={"grant_kind": "crystals", "grant_code": "crystals_100", "grant_qty": 100,
              "provider": "cryptobot", "asset": "TON", "cryptobot_invoice_id": 992},
    )
    body = json.dumps({"payload": {"update_type": "invoice_paid", "payload": {
        "invoice_id": 992, "payload": order["payload"], "status": "paid", "asset": "TON",
    }}}, separators=(",", ":")).encode()
    signature = hmac.new(hashlib.sha256(secret.encode()).digest(), body,
                         hashlib.sha256).hexdigest()
    headers = {"crypto-pay-api-signature": signature}

    first = await client.post("/api/webhooks/cryptobot", content=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["granted"] is True

    second = await client.post("/api/webhooks/cryptobot", content=body, headers=headers)
    assert second.status_code == 200
    payload = second.json()
    assert payload["granted"] is False, "реплей выдал Кристаллы второй раз"
    assert payload["duplicate"] is True

    fresh = await billing_repo.order_by_payload(db, order["payload"])
    assert fresh["status"] == "paid"


async def test_crypto_invoice_binds_server_selected_ton_asset(client, user, monkeypatch):
    from app.config import settings
    from app.services import cryptobot

    monkeypatch.setattr(settings, "cryptobot_api_token", "test-token")
    captured = {}

    async def fake_create_invoice(*, amount_usd, payload, description, asset=None):
        captured.update(amount_usd=amount_usd, payload=payload, description=description, asset=asset)
        return {"invoice_id": 991, "link": "https://t.me/CryptoBot?start=invoice-991"}

    monkeypatch.setattr(cryptobot, "create_invoice", fake_create_invoice)
    response = await client.post(
        "/api/shop/crypto-invoice", params=as_user(user),
        json={"sku": "crystals_100", "asset": "TON"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["asset"] == "TON"
    assert captured["asset"] == "TON"
    assert captured["amount_usd"] > 0


async def test_crypto_invoice_rejects_unknown_asset(client, user, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cryptobot_api_token", "test-token")
    response = await client.post(
        "/api/shop/crypto-invoice", params=as_user(user),
        json={"sku": "crystals_100", "asset": "DOGE"},
    )
    assert response.status_code == 400


async def test_crypto_webhook_rejects_asset_mismatch(client, db, user, monkeypatch):
    import hashlib
    import hmac
    import json

    from app.config import settings
    from app.repo import billing as billing_repo

    secret = "crypto-test-secret"
    monkeypatch.setattr(settings, "cryptobot_api_token", secret)
    order = await billing_repo.create_order(
        db, user["tg_id"], "crystals", sku="crystals_100", title="100 Кристаллов",
        meta={"grant_kind": "crystals", "grant_code": "crystals_100", "grant_qty": 100,
              "provider": "cryptobot", "asset": "TON", "cryptobot_invoice_id": 991},
    )
    body = json.dumps({"payload": {"update_type": "invoice_paid", "payload": {
        "invoice_id": 991, "payload": order["payload"], "status": "paid", "asset": "USDT",
    }}}, separators=(",", ":")).encode()
    signature = hmac.new(hashlib.sha256(secret.encode()).digest(), body, hashlib.sha256).hexdigest()
    response = await client.post(
        "/api/webhooks/cryptobot", content=body,
        headers={"crypto-pay-api-signature": signature},
    )
    assert response.status_code == 200
    assert response.json()["unmatched"] is True
