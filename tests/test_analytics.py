"""Аналитика: запись в фоне, ретеншен, last_seen без спама (G14).

События пишутся fire-and-forget, чтобы не держать пользовательский запрос ради
INSERT; `drain()` даёт тестам дождаться фоновых записей. Пуринг и touch-throttle
убирают лишние записи с горячего пути.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone

from app.repo import analytics as analytics_repo
from app.repo import users
from app.services import analytics, chat


async def test_track_persists_after_drain(db):
    """Фоновая запись события доезжает до базы после drain()."""
    await analytics.track(db, "test_event", 1001, props={"x": 1})
    await analytics.drain()
    cur = await db.execute(
        "SELECT COUNT(*) c FROM events WHERE name='test_event' AND tg_id=1001")
    assert (await cur.fetchone())["c"] == 1


async def test_track_once_is_idempotent(db):
    assert await analytics.track_once(
        db, analytics.E_FIRST_RITUAL, 1001,
        props={"surface_action": "practice_done"}, surface="miniapp",
    )
    assert not await analytics.track_once(
        db, analytics.E_FIRST_RITUAL, 1001,
        props={"surface_action": "practice_done"}, surface="miniapp",
    )
    cur = await db.execute(
        "SELECT COUNT(*) c FROM events WHERE tg_id=1001 AND name=?",
        (analytics.E_FIRST_RITUAL,),
    )
    assert (await cur.fetchone())["c"] == 1


async def test_track_open_records_d1_d7_once(db):
    await users.ensure(db, 1001, "А")
    user = await users.get(db, 1001)
    await chat.track_open(db, user)
    old = datetime.now(timezone.utc) - timedelta(days=8)
    await db.execute(
        "UPDATE events SET day=?, created_at=? WHERE tg_id=? AND name=?",
        (old.date().isoformat(), old.isoformat(), 1001, analytics.E_MINIAPP_OPEN),
    )
    await db.commit()
    await chat.track_open(db, user)
    await chat.track_open(db, user)
    cur = await db.execute(
        "SELECT name, COUNT(*) c FROM events WHERE tg_id=1001 AND name IN (?, ?, ?) "
        "GROUP BY name",
        (analytics.E_RETURN_D1, analytics.E_RETURN_D7, analytics.E_MINIAPP_OPEN),
    )
    counts = {row["name"]: row["c"] for row in await cur.fetchall()}
    assert counts[analytics.E_MINIAPP_OPEN] == 3
    assert counts[analytics.E_RETURN_D1] == 1
    assert counts[analytics.E_RETURN_D7] == 1


async def test_track_open_records_d30_milestone(db):
    """D30: на 31-й день milestone записывается один раз, повторы не дублируют."""
    await users.ensure(db, 2002, "Б")
    user = await users.get(db, 2002)
    await chat.track_open(db, user)
    old = datetime.now(timezone.utc) - timedelta(days=31)
    await db.execute(
        "UPDATE events SET day=?, created_at=? WHERE tg_id=? AND name=?",
        (old.date().isoformat(), old.isoformat(), 2002, analytics.E_MINIAPP_OPEN),
    )
    await db.commit()
    await chat.track_open(db, user)
    await chat.track_open(db, user)
    cur = await db.execute(
        "SELECT name, COUNT(*) c FROM events WHERE tg_id=2002 AND name IN (?, ?) "
        "GROUP BY name",
        (analytics.E_RETURN_D30, analytics.E_MINIAPP_OPEN),
    )
    counts = {row["name"]: row["c"] for row in await cur.fetchall()}
    assert counts[analytics.E_MINIAPP_OPEN] == 3
    assert counts[analytics.E_RETURN_D30] == 1


async def test_track_open_utm_prop_only_when_valid(db):
    """BUS-562: utm из startapp — отдельный prop miniapp_open; невалид = organic.

    Словарь аналитики: source — server-owned (push|broadcast из dispatch-
    контекста), utm — пасс-тру токен. Milestone-механика D1/D7/D30 не меняется.
    """
    await users.ensure(db, 3003, "В")
    user = await users.get(db, 3003)

    async def last_open_props(tg_id: int):
        cur = await db.execute(
            "SELECT props_json FROM events WHERE tg_id=? AND name=? "
            "ORDER BY created_at DESC, id DESC LIMIT 1",
            (tg_id, analytics.E_MINIAPP_OPEN),
        )
        row = await cur.fetchone()
        return json.loads(row["props_json"]) if row and row["props_json"] else None

    await chat.track_open(db, user)
    assert await last_open_props(3003) is None  # organic — props нет

    await chat.track_open(db, user, utm="bc42")
    assert await last_open_props(3003) == {"utm": "bc42"}

    await chat.track_open(db, user, utm="Push Channel!")  # не ascii-токен
    assert await last_open_props(3003) is None

    await chat.track_open(db, user, utm="x" * 100)  # длиннее лимита
    assert await last_open_props(3003) is None

    # milestones не затронуты utm-веткой
    old = datetime.now(timezone.utc) - timedelta(days=8)
    await db.execute(
        "UPDATE events SET day=?, created_at=? WHERE tg_id=? AND name=?",
        (old.date().isoformat(), old.isoformat(), 3003, analytics.E_MINIAPP_OPEN),
    )
    await db.commit()
    await chat.track_open(db, user, utm="bc42")
    cur = await db.execute(
        "SELECT COUNT(*) c FROM events WHERE tg_id=3003 AND name=?",
        (analytics.E_RETURN_D1,))
    assert (await cur.fetchone())["c"] == 1


async def test_activation_funnel_uses_first_open_cohort(db):
    await analytics.track_now(
        db, analytics.E_MINIAPP_OPEN, 1001, surface="miniapp",
    )
    funnel = await analytics_repo.activation_funnel(db, days=30)
    assert funnel["cohort"] == 1
    steps = {step["step"]: step for step in funnel["steps"]}
    assert "age_gate" not in steps
    assert steps["first_question"]["value"] == 0


async def test_prune_removes_old_events(db):
    """События старее окна удаляются, свежие остаются."""
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()
    await db.executemany(
        "INSERT INTO events(tg_id, name, day, created_at) VALUES(?,?,?,?)",
        [(1001, "old_event", "2026-01-01", old),
         (1001, "fresh_event", "2026-08-03", fresh)])
    await db.commit()

    removed = await analytics.prune(db, days=120)
    assert removed == 1, "должно удалиться только старое событие"
    cur = await db.execute("SELECT COUNT(*) c FROM events")
    assert (await cur.fetchone())["c"] == 1


async def test_touch_throttled_to_once_per_interval(db):
    """Повторный touch в пределах 5 минут не пишет last_seen."""
    await users.ensure(db, 1001, "А")
    users._last_seen_cache[1001] = time.time()   # «только что трогали»
    await users.touch(db, 1001)
    await asyncio.sleep(0.02)
    u = await users.get(db, 1001)
    assert u["last_seen"] is None, "touch в пределах окна не должен писать"

    users._last_seen_cache[1001] = 0.0            # окно прошло
    await users.touch(db, 1001)
    await asyncio.sleep(0.02)
    u = await users.get(db, 1001)
    assert u["last_seen"] is not None, "после окна touch обязан записать"


def test_safe_web_source_rejects_pii_and_injection():
    """Валидатор source: только ascii-токены, всё прочее → None."""
    assert analytics.safe_web_source("Google") == "google"
    assert analytics.safe_web_source("t_me") == "t_me"
    assert analytics.safe_web_source(None) is None
    assert analytics.safe_web_source("") is None
    assert analytics.safe_web_source("x" * 49) is None
    assert analytics.safe_web_source("mail@example.com") is None
    assert analytics.safe_web_source("'; DROP TABLE events;--") is None
    assert analytics.safe_web_source("утм-скрипт") is None
    assert analytics.safe_web_source("a b") is None


async def test_repeat_purchase_event_after_second_payment(db, user):
    """Вторая успешная оплата того же tg_id пишет repeat_purchase."""
    from app.services import billing as svc

    order1 = await svc.checkout_plan(db, user["tg_id"], "vip")
    await svc.apply_payment(db, order1["payload"], charge_id="ch_1",
                            amount_stars=order1["amount_stars"])
    await analytics.drain()

    cur = await db.execute(
        "SELECT COUNT(*) c FROM events WHERE name=? AND tg_id=?",
        (analytics.E_REPEAT_PAID, user["tg_id"]))
    assert (await cur.fetchone())["c"] == 0, "первая оплата — ещё не repeat"

    order2 = await svc.checkout_plan(db, user["tg_id"], "vip")
    await svc.apply_payment(db, order2["payload"], charge_id="ch_2",
                            amount_stars=order2["amount_stars"])
    await analytics.drain()

    cur = await db.execute(
        "SELECT COUNT(*) c FROM events WHERE name=? AND tg_id=?",
        (analytics.E_REPEAT_PAID, user["tg_id"]))
    assert (await cur.fetchone())["c"] == 1, "вторая оплата — repeat_purchase"
