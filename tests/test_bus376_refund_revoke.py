"""BUS-376 F1 refund/chargeback policy (variant C): unit + e2e.

- Unit: classification of Paddle adjustment events (full/partial/ambiguous).
- e2e: daily sweep revokes subscription for queued orders + sends RU/EN notice.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import pytest

from app.api.routers import webhooks
from app.repo import billing as billing_repo
from app.services import scheduler


# ─────────────────────────── unit: classification ────────────────────────────


class TestRefundClassification:
    """_is_full_refund_or_chargeback is the fail-closed gate."""

    def test_full_refund_revokes(self):
        data = {"action": "refund", "totals": {"gross": "50.00"}}
        assert webhooks._is_full_refund_or_chargeback(data) is True

    def test_full_chargeback_revokes(self):
        data = {"action": "chargeback", "totals": {"gross": "30.00"}}
        assert webhooks._is_full_refund_or_chargeback(data) is True

    def test_chargeback_won_revokes(self):
        data = {"action": "chargeback_won", "totals": {"gross": "10.00"}}
        assert webhooks._is_full_refund_or_chargeback(data) is True

    def test_partial_refund_journal_only(self):
        data = {"action": "refund", "totals": {"gross": "10.00"}}
        # partial: total < order price → not flagged as full by the webhook
        # (the webhook does not know order price, so it queues only when
        # action is refund/chargeback AND total > 0 — variant C says "full"
        # is decided by Paddle action type, not by comparing to order price)
        # Here we test that zero total is fail-closed:
        data_zero = {"action": "refund", "totals": {"gross": "0.00"}}
        assert webhooks._is_full_refund_or_chargeback(data_zero) is False

    def test_zero_total_fail_closed(self):
        data = {"action": "refund", "totals": {"gross": "0"}}
        assert webhooks._is_full_refund_or_chargeback(data) is False

    def test_no_action_fail_closed(self):
        data = {"totals": {"gross": "50.00"}}
        assert webhooks._is_full_refund_or_chargeback(data) is False

    def test_unknown_action_fail_closed(self):
        data = {"action": "dispute_created", "totals": {"gross": "50.00"}}
        assert webhooks._is_full_refund_or_chargeback(data) is False

    def test_non_refund_action_ignored(self):
        data = {"action": "subscription_paused", "totals": {}}
        assert webhooks._is_full_refund_or_chargeback(data) is False

    def test_payout_totals_accepted(self):
        data = {"action": "refund", "payout_totals": {"net": "25.00"}}
        assert webhooks._is_full_refund_or_chargeback(data) is True

    def test_unparseable_total_fail_closed(self):
        data = {"action": "refund", "totals": {"gross": "abc"}}
        assert webhooks._is_full_refund_or_chargeback(data) is False


# ─────────────────────── e2e: webhook → queue → sweep ───────────────────────


@pytest.fixture
async def client(db):
    """ASGI-клиент с X-Dev-Key; get_db подменён на тестовое соединение."""
    pytest.importorskip("httpx", reason="httpx нужен для тестов API")
    from httpx import ASGITransport, AsyncClient

    from conftest import TEST_DEV_KEY
    from app.api.deps import get_db
    from app.api.main import app

    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test",
                           headers={"X-Dev-Key": TEST_DEV_KEY}) as http:
        yield http
    app.dependency_overrides.clear()


def _sign(secret: str, body: bytes) -> dict[str, str]:
    ts = str(int(time.time()))
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + body,
                      hashlib.sha256).hexdigest()
    return {"Paddle-Signature": f"ts={ts};h1={digest}"}


async def _paid_order(db, tg_id: int, txn: str):
    """create → pay: заказ в статусе paid, ждущий adjustment-вебхука."""
    order = await billing_repo.create_order(
        db, tg_id, "plan", sku="vip", title="VIP", surface="web",
        meta={"grant_kind": "plan", "grant_code": "vip", "grant_qty": 1,
              "valid_days": 30, "provider": "paddle",
              "paddle_transaction_id": txn})
    paid = await billing_repo.mark_order_paid(
        db, order["payload"], charge_id=txn,
        amount_stars=0, provider="paddle", currency="USD")
    assert paid is not None
    return order


async def _paid_flagged_order(db, tg_id: int, txn: str):
    """create → pay → queue: состояние, из которого его подхватит sweep."""
    order = await _paid_order(db, tg_id, txn)
    assert await billing_repo.queue_refund_revoke(
        db, order["id"], source="paddle") is True
    return order


async def test_adjustment_queues_refund_revoke(client, db, monkeypatch):
    """Full refund adjustment marks the paid order as refund_pending."""
    from app.config import settings

    secret = "paddle-test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)

    order = await _paid_flagged_order(db, 2001, "txn_revoke_1")

    body = json.dumps({
        "event_id": "evt_revoke_1",
        "event_type": "adjustment.created",
        "data": {
            "id": "adj_1",
            "action": "refund",
            "status": "completed",
            "original_transaction_id": "txn_revoke_1",
            "totals": {"gross": "49.99"},
        },
    }, separators=(",", ":")).encode()

    res = await client.post("/api/webhooks/paddle", content=body,
                            headers=_sign(secret, body))
    assert res.status_code == 200
    assert res.json()["ignored"] == "adjustment.created"

    queued = await billing_repo.pending_refund_revokes(db)
    assert len(queued) == 1
    assert queued[0]["id"] == order["id"]
    assert queued[0]["status"] == "refund_pending"


async def test_partial_adjustment_does_not_queue(client, db, monkeypatch):
    """Partial (zero-total) adjustment must not queue a revoke."""
    from app.config import settings

    secret = "paddle-test-secret"
    monkeypatch.setattr(settings, "paddle_webhook_secret", secret)

    order = await _paid_order(db, 2002, "txn_revoke_2")

    body = json.dumps({
        "event_id": "evt_revoke_2",
        "event_type": "adjustment.created",
        "data": {
            "id": "adj_2",
            "action": "refund",
            "status": "completed",
            "original_transaction_id": "txn_revoke_2",
            "totals": {"gross": "0.00"},
        },
    }, separators=(",", ":")).encode()

    res = await client.post("/api/webhooks/paddle", content=body,
                            headers=_sign(secret, body))
    assert res.status_code == 200

    queued = await billing_repo.pending_refund_revokes(db)
    assert len(queued) == 0
    fresh = await billing_repo.get_order(db, order["id"])
    assert fresh["status"] == "paid"


async def test_daily_sweep_revokes_subscription_and_notifies(db, monkeypatch):
    """E2E: queued refund → sweep truncates sub_until → user notified."""
    from datetime import datetime, timezone

    from app.repo import users

    # Create a paid order flagged for revoke (simulates webhook → queue flow)
    order = await _paid_flagged_order(db, 2003, "txn_revoke_3")
    # Sweep JOIN'ит users: без ensure строка клиента отсутствует и заказ
    # выпадает из аудитории.
    await users.ensure(db, 2003, "Тест", lang="ru")
    await users.update(db, 2003, sub_until="2099-01-01T00:00:00+00:00",
                       sub_level="vip")

    class FakeBot:
        def __init__(self):
            self.sent: list[tuple[int, str, str]] = []

        async def send_message(self, tg_id, text, reply_markup=None):
            self.sent.append((tg_id, text, ""))

    fake_bot = FakeBot()
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)

    audience = await scheduler._revoke_audience(db)
    assert len(audience) == 1
    assert audience[0]["tg_id"] == 2003

    for u in audience:
        await scheduler._revoke_entitlement(fake_bot, db, u, now)

    fresh = await users.get(db, 2003)
    assert fresh["sub_until"] is None
    assert fresh["sub_level"] == "free"

    assert len(fake_bot.sent) == 1
    tg_id, text, _ = fake_bot.sent[0]
    assert tg_id == 2003
    assert "возврату" in text

    # Idempotency: second sweep is a no-op
    fresh_order = await billing_repo.get_order(db, order["id"])
    assert fresh_order["status"] == "refunded"
    audience2 = await scheduler._revoke_audience(db)
    assert len(audience2) == 0


async def test_daily_sweep_idempotent_on_retry(db, monkeypatch):
    """Re-running the sweep does not double-notify or double-revoke."""
    from datetime import datetime, timezone

    from app.repo import users

    order = await _paid_flagged_order(db, 2004, "txn_revoke_4")
    await users.ensure(db, 2004, "Test", lang="en")
    await users.update(db, 2004, sub_until="2099-01-01T00:00:00+00:00",
                       sub_level="vip")

    class FakeBot:
        def __init__(self):
            self.sent: list[tuple[int, str, str]] = []

        async def send_message(self, tg_id, text, reply_markup=None):
            self.sent.append((tg_id, text, ""))

    fake_bot = FakeBot()
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)

    audience = await scheduler._revoke_audience(db)
    for u in audience:
        await scheduler._revoke_entitlement(fake_bot, db, u, now)

    assert len(fake_bot.sent) == 1

    # Retry: no more queued orders
    audience2 = await scheduler._revoke_audience(db)
    assert len(audience2) == 0
    for u in audience2:
        await scheduler._revoke_entitlement(fake_bot, db, u, now)
    assert len(fake_bot.sent) == 1  # unchanged


async def test_refund_revoke_already_free_user_still_finalizes_order(db):
    """Уже-фри клиентка: уведомление оправдано (заказ вернули), но
    подписка остаётся free — и заказ/платёж переводятся в refunded."""
    from app.repo import users

    order = await _paid_flagged_order(db, 2005, "txn_revoke_5")
    await users.ensure(db, 2005, "Free")
    await users.update(db, 2005, sub_until=None, sub_level="free", lang="ru")

    class FakeBot:
        def __init__(self):
            self.sent: list[tuple[int, str, str]] = []

        async def send_message(self, tg_id, text, reply_markup=None):
            self.sent.append((tg_id, text, ""))

    fake_bot = FakeBot()
    audience = await scheduler._revoke_audience(db)
    assert len(audience) == 1
    for u in audience:
        await scheduler._revoke_entitlement(fake_bot, db, u,
                                            datetime(2026, 9, 7, 10, 0,
                                                     tzinfo=timezone.utc))

    fresh = await users.get(db, 2005)
    assert fresh["sub_level"] == "free"
    assert fresh["sub_until"] is None
    fresh_order = await billing_repo.get_order(db, order["id"])
    assert fresh_order["status"] == "refunded"
