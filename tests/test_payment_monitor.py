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
async def test_monitor_dead_channel_caps_delivery_attempts(db, monkeypatch):
    """BUS-850: мёртвый канал не ретрит алерт на каждом тике — cooldown идёт
    от попытки доставки, а бюджет из MAX попыток закрывает ретраи совсем."""
    from app.repo import content

    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    await users.ensure(db, 1, "Владелец")
    await content.set_setting(db, "system.payment_notifications",
                              {"degraded_cooldown_hours": 1, "critical_cooldown_hours": 1})
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, status, payload, "
        "created_at) VALUES(?,?,?,?,?,?,?,?)",
        (1001, "product", "demo", "Demo", 100, "pending", "monitor-payload",
         (now - timedelta(hours=3)).isoformat()),
    )
    attempts: list[str] = []

    async def dead_send(_tg_id, text, *, html=True):
        attempts.append(text)
        return False

    monkeypatch.setattr(payment_monitor.telegram, "send_message", dead_send)
    max_attempts = payment_monitor.MAX_ALERT_DELIVERY_ATTEMPTS
    first = await payment_monitor.run(None, db, now=now)
    assert first["last_alert_at"] == first["checked_at"]
    second = await payment_monitor.run(None, db, now=now + timedelta(hours=1, minutes=10))
    third = await payment_monitor.run(
        None, db, now=now + timedelta(hours=2, minutes=20))
    assert len(attempts) == max_attempts
    assert third["alert_failed_attempts"] == max_attempts
    # Бюджет проверяется ДО попытки: третий тик ещё разрешён, исчерпание
    # вступает в силу со следующего.
    assert third["alert_attempts_exhausted"] is False
    assert third["last_alert_delivered"] is False
    assert third["last_alert_delivery_failed_at"] == third["checked_at"]

    # Бюджет исчерпан: даже с прошедшим cooldown новых попыток нет.
    after = await payment_monitor.run(None, db, now=now + timedelta(hours=3, minutes=30))
    assert len(attempts) == max_attempts
    assert after["alert_attempts_exhausted"] is True

    # Восстановление канала + переход в ok открывает новый период: алерт
    # доставляется, бюджет сбрасывается.
    async def alive_send(_tg_id, text, *, html=True):
        return True

    monkeypatch.setattr(payment_monitor.telegram, "send_message", alive_send)
    await db.execute("DELETE FROM orders WHERE sku='demo'")
    recovered = await payment_monitor.run(None, db, now=now + timedelta(hours=4, minutes=40))
    assert recovered["status"] == "ok"
    assert recovered["last_alert_delivered"] is True
    assert recovered["alert_failed_attempts"] == 0
    assert recovered["alert_attempts_exhausted"] is False


@pytest.mark.asyncio
async def test_monitor_attempt_budget_resets_on_status_change(db, monkeypatch):
    """Смена status-периода (degraded → critical) открывает новый бюджет."""
    from app.repo import content

    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    await users.ensure(db, 1, "Владелец")
    await content.set_setting(db, "system.payment_notifications",
                              {"degraded_cooldown_hours": 1, "critical_cooldown_hours": 1})
    await db.execute(
        "INSERT INTO orders(tg_id, kind, sku, title, amount_stars, status, payload, "
        "created_at) VALUES(?,?,?,?,?,?,?,?)",
        (1001, "product", "demo", "Demo", 100, "pending", "monitor-payload",
         (now - timedelta(hours=3)).isoformat()),
    )

    async def dead_send(_tg_id, text, *, html=True):
        return False

    monkeypatch.setattr(payment_monitor.telegram, "send_message", dead_send)
    for offset in (0, 70, 140):  # три попытки: 12:00, 13:10, 14:20
        await payment_monitor.run(None, db, now=now + timedelta(minutes=offset))
    assert (await payment_monitor.run(
        None, db, now=now + timedelta(minutes=210)))["alert_attempts_exhausted"] is True

    # Аномалия сверки → critical: свежий период, попытка снова делается.
    await db.execute("UPDATE users SET crystals=999 WHERE tg_id=1")
    state = await payment_monitor.run(None, db, now=now + timedelta(minutes=280))
    assert state["status"] == "critical"
    assert state["alert_attempts_exhausted"] is False
    assert state["alert_failed_attempts"] == 1


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
