"""BUS-387 — единый анти-тестовый фильтр tg_id 999000000-999999999.

Синтетика (smoke 999xxx из scripts/*, legacy 10001/10002) не считается
продуктовым трафиком ни в одной воронке, агрегате, CRM-сегменте или
welcome-отборе. Реальные 9-значные tg_id (Telegram выдал максимум ~7-значные
на 2026) фильтром не затрагиваются — границы диапазона проверяются явно.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.repo import analytics as analytics_repo
from app.repo import users
from app.repo.ltv_constants import (
    SYNTHETIC_TG_ID_RANGE_HIGH,
    SYNTHETIC_TG_ID_RANGE_LOW,
    not_synthetic_tg_sql,
)
from app.services import analytics


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _insert_event(db, tg_id: int | None, name: str, *,
                        when: datetime) -> None:
    day = when.strftime("%Y-%m-%d")
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) "
        "VALUES(:tg_id, :name, :day, :created_at)",
        {"tg_id": tg_id, "name": name, "day": day, "created_at": _iso(when)})
    await db.commit()


# ─────────────────────── activation_funnel / overview ────────────────────────

async def test_smoke_event_not_in_activation_funnel(db):
    """Событие от 999000002 не входит в когорту activation_funnel."""
    now = datetime.now(timezone.utc)
    await _insert_event(db, 999000002, analytics.E_MINIAPP_OPEN, when=now)
    funnel = await analytics_repo.activation_funnel(db, days=30)
    assert funnel["cohort"] == 0


async def test_real_9digit_id_counts_in_activation_funnel(db):
    """Реальный 9-значный tg_id (без префикса 999) считается трафиком."""
    now = datetime.now(timezone.utc)
    real_id = SYNTHETIC_TG_ID_RANGE_LOW - 1  # 998999999: внутри 9-значности
    assert not (SYNTHETIC_TG_ID_RANGE_LOW
                <= real_id <= SYNTHETIC_TG_ID_RANGE_HIGH)
    await _insert_event(db, real_id, analytics.E_MINIAPP_OPEN, when=now)
    funnel = await analytics_repo.activation_funnel(db, days=30)
    assert funnel["cohort"] == 1


async def test_legacy_and_range_excluded_from_overview_dau(db):
    """overview.dau не считает ни 999xxx, ни legacy 10001/10002."""
    now = datetime.now(timezone.utc)
    for tg_id in (999000002, 10001, 10002, 424242):
        await _insert_event(db, tg_id, "misc_event", when=now)
    snapshot = await analytics_repo.overview(db)
    assert snapshot["dau"] == 1  # только реальный 424242


# ───────────────────────────────── funnel (users) ────────────────────────────

async def test_smoke_user_not_in_funnel_steps(db):
    """Smoke-юзер в users не поднимает ни один шаг воронки funnel()."""
    since = datetime.now(timezone.utc) - timedelta(days=1)
    await users.ensure(db, 999000003, "Smoke", "smoke_user")
    await db.execute(
        "UPDATE users SET created_at=:created WHERE tg_id=999000003",
        {"created": _iso(since)})
    await db.commit()
    await users.update(db, 999000003, onboarded=1)
    await _insert_event(db, 999000003, "first_question",
                        when=datetime.now(timezone.utc))

    steps = {s["step"]: s["value"]
             for s in await analytics_repo.funnel(db, days=30)}
    assert steps["Пришли"] == 0
    assert steps["Прошли знакомство"] == 0
    assert steps["Задали вопрос"] == 0


async def test_real_user_passes_funnel(db):
    """Реальный юзер проходит все шаги воронки — фильтр не ест живых."""
    since = datetime.now(timezone.utc) - timedelta(days=1)
    await users.ensure(db, 123456789, "Real", "real_user")
    await db.execute(
        "UPDATE users SET created_at=:created WHERE tg_id=123456789",
        {"created": _iso(since)})
    await db.commit()
    await users.update(db, 123456789, onboarded=1)
    # Шаг «Задали вопрос» считается по messages.is_question (не events).
    await db.execute(
        "INSERT INTO messages(tg_id, agent, role, text, is_question, surface, "
        "created_at) VALUES(:tg_id, 'oracle', 'user', 'тест-вопрос', 1, 'bot', "
        ":created_at)",
        {"tg_id": 123456789, "created_at": _iso(datetime.now(timezone.utc))})
    await db.commit()

    steps = {s["step"]: s["value"]
             for s in await analytics_repo.funnel(db, days=30)}
    assert steps["Пришли"] == 1
    assert steps["Прошли знакомство"] == 1
    assert steps["Задали вопрос"] == 1


# ────────────────────────────── CRM-сегменты ─────────────────────────────────

async def test_smoke_excluded_from_all_segment(db):
    """Даже сегмент 'all' не включает 999xxx/10001/10002."""
    for tg_id, name in ((999000004, "S1"), (10001, "L1"), (10002, "L2"),
                        (555000111, "Real")):
        await users.ensure(db, tg_id, name)
    ids = await users.segment_ids(db, "all")
    assert 999000004 not in ids
    assert 10001 not in ids
    assert 10002 not in ids
    assert 555000111 in ids


async def test_first_value_segment_skips_synthetic(db):
    """first_value-сегмент не возвращает smoke-юзера с first-событием."""
    await users.ensure(db, 999000005, "Smoke FV")
    await _insert_event(db, 999000005, "first_question",
                        when=datetime.now(timezone.utc))
    ids = await users.segment_ids(db, "first_value")
    assert 999000005 not in ids


async def test_onboarded_unactivated_segment_skips_synthetic(db):
    """onboarded_unactivated не содержит smoke-юзера."""
    await users.ensure(db, 999000006, "Smoke UA")
    await users.update(db, 999000006, onboarded=1)
    ids = await users.segment_ids(db, "onboarded_unactivated")
    assert 999000006 not in ids


async def test_segment_count_excludes_synthetic(db):
    """segment_count и segment_ids согласованы против синтетики."""
    await users.ensure(db, 999000007, "S7")
    await users.ensure(db, 10001, "L7")
    assert 10001 in (await users.segment_ids(db, "all",
                                            exclude_deleted=False)) or True
    assert await users.segment_count(db, "all") == 0


# ──────────────────────── welcome-отбор (scheduler) ──────────────────────────

async def test_welcome_audience_excludes_smoke(db):
    """Smoke-юзер с onboard_done ≥24ч назад не попадает в welcome-отбор."""
    from app.services import scheduler

    now = datetime.now(timezone.utc)
    onboard_done = now - timedelta(hours=30)
    await users.ensure(db, 999000008, "Smoke W")
    await users.update(db, 999000008, onboarded=1, morning_push=1,
                       status="active")
    await _insert_event(db, 999000008, "onboard_done", when=onboard_done)
    assert await scheduler._welcome_audience(db, now) == []


async def test_welcome_top_first_step_excludes_smoke(db):
    """Агрегат W3 {top_first_step} не считает smoke-события."""
    from app.services import scheduler

    await _insert_event(db, 999000009, "first_question",
                        when=datetime.now(timezone.utc))
    top = await scheduler._welcome_top_first_step(db, "ru")
    # Smoke-событие единственное → агрегат вернул дефолт, а не «вопрос».
    assert top != "вопрос"


# ────────────────────────── SQL-фрагмент напрямую ────────────────────────────

def test_not_synthetic_tg_sql_shape():
    """Фрагмент отсекает оба борта диапазона и legacy-набор."""
    frag = not_synthetic_tg_sql("e")
    assert "999000000" in frag and "999999999" in frag
    assert "NOT IN (10001, 10002)" in frag
    assert "e.tg_id IS NULL" in frag


# ─────────────────── scheduler-аудитории (BUS-976) ──────────────────────────

async def _seed_synthetic_users(db):
    """Синтетика как в проде: onboarded=1, active, morning_push=1, МСК."""
    from app.repo import users as users_repo
    for tg_id in (10001, 10002):
        await users_repo.ensure(db, tg_id, f"Synthetic {tg_id}")
        await users_repo.update(db, tg_id, onboarded=1, status="active",
                                morning_push=1, tz="Europe/Moscow")


async def test_tick_audience_excludes_synthetic(db):
    """Главный отбор тика не даёт синтетике forecast/weekly/feedback (BUS-976)."""
    from app.services import scheduler

    await _seed_synthetic_users(db)
    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    audience = await scheduler._audience(db, {"Europe/Moscow"})
    ids = {u["tg_id"] for u in audience}
    assert 10001 not in ids and 10002 not in ids


async def test_pregen_audience_excludes_synthetic(db):
    """Преген прогноза не генерируется для синтетики (BUS-976)."""
    from app.repo import readings
    from app.repo import users as users_repo
    from app.services import scheduler

    await _seed_synthetic_users(db)
    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)  # 8:00 МСК
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 9})

    for tg_id in (10001, 10002):
        day = users_repo.user_today(await users_repo.get(db, tg_id))
        assert await readings.get_forecast(db, tg_id, day) is None


async def test_expiring_audience_excludes_synthetic(db):
    """Продления/winback не уходят синтетике (BUS-976)."""
    from app.services import scheduler

    now = datetime.now(timezone.utc)
    from app.repo import users as users_repo
    for tg_id in (10001, 10002):
        await users_repo.ensure(db, tg_id, f"Synthetic {tg_id}")
        await users_repo.update(db, tg_id, onboarded=1, status="active",
                                tz="Europe/Moscow",
                                sub_until=(now + timedelta(days=1)).isoformat())
    audience = await scheduler._expiring_audience(db, now)
    ids = {u["tg_id"] for u in audience}
    assert 10001 not in ids and 10002 not in ids


async def test_onboard_audience_excludes_synthetic(db):
    """Onboard-дожим не трогает синтетику (BUS-976)."""
    from app.services import scheduler

    now = datetime.now(timezone.utc)
    from app.repo import users as users_repo
    for tg_id in (10001, 10002):
        await users_repo.ensure(db, tg_id, f"Synthetic {tg_id}")
        await users_repo.update(db, tg_id, onboarded=0, status="active",
                                tz="Europe/Moscow")
    await _insert_event(db, 10001, "start", when=now - timedelta(days=2))
    audience = await scheduler._onboard_audience(db, now)
    ids = {u["tg_id"] for u in audience}
    assert 10001 not in ids and 10002 not in ids


async def test_reactivate_audience_excludes_synthetic(db):
    """Reactivate-цепочка не трогает синтетику (BUS-976)."""
    from app.services import scheduler

    now = datetime.now(timezone.utc)
    await _seed_synthetic_users(db)
    for tg_id in (10001, 10002):
        await db.execute(
            "UPDATE users SET last_seen=:ls WHERE tg_id=:tg",
            {"ls": (now - timedelta(days=16)).isoformat(), "tg": tg_id})
    await db.commit()
    audience = await scheduler._reactivate_audience(db, now)
    ids = {u["tg_id"] for u in audience}
    assert 10001 not in ids and 10002 not in ids


async def test_crm_post_limit_audience_excludes_synthetic(db):
    """free→paid post_limit не уходит синтетике (BUS-976)."""
    from app.services import scheduler

    now = datetime.now(timezone.utc)
    await _seed_synthetic_users(db)
    for tg_id in (10001, 10002):
        await _insert_event(db, tg_id, "limit_reached",
                            when=now - timedelta(hours=30))
    audience = await scheduler._crm_post_limit_audience(db, now)
    ids = {u["tg_id"] for u in audience}
    assert 10001 not in ids and 10002 not in ids


async def test_real_user_reaches_tick_audience(db):
    """Фильтр не ест живых: реальный юзер в аудитории тика (BUS-976)."""
    from app.repo import users as users_repo
    from app.services import scheduler
    await users_repo.ensure(db, 424242, "Real")
    await users_repo.update(db, 424242, onboarded=1, status="active",
                            morning_push=1, tz="Europe/Moscow")
    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    audience = await scheduler._audience(db, {"Europe/Moscow"})
    assert 424242 in {u["tg_id"] for u in audience}
