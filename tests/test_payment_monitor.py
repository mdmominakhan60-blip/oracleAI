from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.repo import users
from app.services import payment_monitor


@pytest.mark.asyncio
async def test_monitor_detects_stale_orders_and_deduplicates_alerts(db, monkeypatch):
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    await users.ensure(db, 1, "Владелец")
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, status, payload, "
        "created_at) VALUES(?,?,?,?,?,?,?,?)",
        (1001, "product", "demo", "Demo", 100, "pending", "monitor-payload",
         (now - timedelta(hours=3)).isoformat()),
    )
    sent = []

    async def fake_send(_tg_id, text, *, html=True):
        sent.append((text, html))
        return True

    monkeypatch.setattr(payment_monitor.telegram, "send_message", fake_send)
    first = await payment_monitor.run(None, db, now=now)
    second = await payment_monitor.run(None, db, now=now + timedelta(minutes=1))

    assert first["status"] == "degraded"
    assert first["checks"]["pending_orders_stale"] == 1
    assert len(sent) == 1
    assert sent[0][1] is False
    assert "monitor-payload" not in sent[0][0]
    assert second["status"] == "degraded"
    third = await payment_monitor.run(None, db, now=now + timedelta(hours=7))
    assert third["status"] == "degraded"
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_monitor_reconciles_recovery_and_failure_journal_is_safe(db):
    from app.api.routers.webhooks import _failure

    await users.ensure(db, 1, "Владелец")
    await _failure(db, "cryptobot", "signature_rejected", status_code=401)
    snapshot = await payment_monitor.build_snapshot(
        db, now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc), external=False)
    assert snapshot["checks"]["webhook_failures_24h"]["cryptobot"] == 1

    cur = await db.execute("SELECT code, status_code FROM payment_webhook_failures")
    row = await cur.fetchone()
    assert row["code"] == "signature_rejected"
    assert row["status_code"] == 401
    assert "payload" not in str(row).lower()
    assert "tg_id" not in str(row).lower()


@pytest.mark.asyncio
async def test_monitor_timeline_quiet_hours_and_review_marker(db):
    from app.repo import billing
    from app.api.routers.webhooks import _failure

    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    await users.ensure(db, 1001, "Покупатель")
    await db.execute(
        "INSERT INTO webhook_events(event_id, provider, kind, payload, created_at) VALUES(?,?,?,?,?)",
        ("evt-safe", "cryptobot", "invoice_paid", "PRIVATE RAW", now.isoformat()),
    )
    await _failure(db, "cryptobot", "signature_rejected", status_code=401)
    snapshot = await payment_monitor.build_snapshot(db, now=now, external=False)
    timeline = snapshot["checks"]["webhook_timeline"]
    assert any(row["event"] == "invoice_paid" for row in timeline)
    assert "PRIVATE RAW" not in str(timeline)
    assert payment_monitor._in_quiet_hours(now.replace(hour=23), {
        "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"})
    assert not payment_monitor._in_quiet_hours(now, {
        "quiet_hours_start": "22:00", "quiet_hours_end": "07:00"})
    order = await billing.create_order(db, 1001, "product", sku="demo", title="Demo")
    marked = await payment_monitor.mark_for_review(db, order["id"], 1)
    assert marked["marked_for_review"] is True
    assert marked["status"] == "pending"
    row = await billing.get_order(db, order["id"])
    assert "manual_review" in (row["meta_json"] or "")


@pytest.mark.asyncio
async def test_demo_payload_has_requested_figures_and_is_in_memory():
    from app.services.analytics import demo_dashboard

    data = await demo_dashboard(days=30)
    assert data["demo"] == {
        "active": True,
        "label": "ДЕМО · тестовые данные",
        "note": "Не реальные пользователи, заказы или баланс",
        "operating_days": 17,
    }
    assert data["overview"]["users_total"] == 451
    assert data["monetization"]["repeat_payers"] == 130
    assert data["overview"]["stars_total"] == 17056
    assert len(data["timeseries"]) == 30


@pytest.mark.asyncio
async def test_monitor_normalizes_corrupt_preferences_and_order_meta(db):
    from app.repo import billing, content

    await content.set_setting(db, "system.payment_notifications", {
        "degraded_cooldown_hours": "not-a-number",
        "critical_cooldown_hours": 9999,
        "quiet_hours_start": "99:99",
        "quiet_hours_end": "nope",
        "secondary_enabled": "false",
    })
    prefs = await payment_monitor.notification_preferences(db)
    assert prefs["degraded_cooldown_hours"] == 6
    assert prefs["critical_cooldown_hours"] == 168
    assert prefs["quiet_hours_start"] == "23:00"
    assert prefs["quiet_hours_end"] == "07:00"
    assert prefs["secondary_enabled"] is False

    order = await billing.create_order(db, 1001, "product", sku="malformed", title="Malformed")
    await db.execute("UPDATE orders SET meta_json=? WHERE id=?", ("[]", order["id"]))
    await db.commit()
    result = await payment_monitor.recheck_order(db, order["id"])
    assert result["found"] is True
    assert result["asset"] == ""
    assert result["review_status"] == ""
    marked = await payment_monitor.mark_for_review(db, order["id"], 1)
    assert marked["marked_for_review"] is True
    assert marked["review_status"] == "manual_review"
