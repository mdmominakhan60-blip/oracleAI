"""BUS-258 волна 3.3 — welcome-цепочка W1-W3: суточный отбор первой ценности.

Контракт (дизайн BUS-190 §1, копирайт BUS-263 §4):
- отбор: onboarded=1, статус active, morning_push=1, НЕТ first_ritual/first_question,
  onboard_done ≥24ч назад;
- контур: d1/d3/d7 от onboard_done, kind='welcome_chain', key='d{1,3,7}:{tg_id}';
- одно касание за прогон (d3 не слипается с запоздалым d1);
- стопы: first-событие (отбор), morning_push=0, статус != active, пустой шаблон;
- W3: {top_first_step} — агрегат по событиям, подстановка обязательна.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.repo import comms, users
from app.services import scheduler


class RecordingBot:
    def __init__(self):
        self.sent: list[tuple[int, str, str]] = []

    async def send_message(self, tg_id, text, reply_markup=None):
        self.sent.append((tg_id, text, ""))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


async def _user(db, tg_id: int, *, onboard_done: datetime | None,
                morning_push: int = 1, status: str = "active",
                onboarded: int = 1, lang: str = "ru") -> dict:
    """Юзер-кандидат; onboard_done пишется напрямую в events."""
    await users.ensure(db, tg_id, f"W-{tg_id}")
    await users.update(db, tg_id, onboarded=onboarded, sub_level="free",
                       sub_until=None, morning_push=morning_push,
                       status=status, lang=lang)
    if onboard_done is not None:
        await db.execute(
            "INSERT INTO events(tg_id, name, day, created_at) "
            "VALUES(:tg_id, 'onboard_done', :day, :created_at)",
            {"tg_id": tg_id, "day": onboard_done.strftime("%Y-%m-%d"),
             "created_at": _iso(onboard_done)})
        await db.commit()
    return await users.get(db, tg_id)


async def _first_event(db, tg_id: int, name: str) -> None:
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) "
        "VALUES(:tg_id, :name, :day, :created_at)",
        {"tg_id": tg_id, "name": name, "day": "2026-09-01",
         "created_at": "2026-09-01T00:00:00+00:00"})
    await db.commit()


@pytest.fixture(autouse=True)
def _no_webapp(monkeypatch):
    """Кнопка d1 зависит от webapp_url; в тестах она опциональна."""
    monkeypatch.setattr(scheduler.settings, "webapp_url", "")


# ─────────────────────────── отбор аудитории ─────────────────────────────────

async def test_audience_onboarded_without_first_value(db):
    """Кандидат: onboarded, без first-событий, onboard_done ≥24ч назад."""
    now = datetime.now(timezone.utc)
    await _user(db, 6101, onboard_done=now - timedelta(hours=30))
    audience = await scheduler._welcome_audience(db, now)
    assert [u["tg_id"] for u in audience] == [6101]


async def test_audience_excludes_before_24h(db):
    """onboard_done меньше 24ч назад — рано, касания нет."""
    now = datetime.now(timezone.utc)
    await _user(db, 6102, onboard_done=now - timedelta(hours=10))
    assert await scheduler._welcome_audience(db, now) == []


async def test_audience_excludes_with_first_value(db):
    """Стоп: появилось first_ritual ИЛИ first_question — юзер вне отбора."""
    now = datetime.now(timezone.utc)
    for tg_id, event in ((6103, "first_ritual"), (6104, "first_question")):
        await _user(db, tg_id, onboard_done=now - timedelta(days=2))
        await _first_event(db, tg_id, event)
    assert await scheduler._welcome_audience(db, now) == []


async def test_audience_excludes_push_off_and_inactive(db):
    """Стопы: morning_push=0 и статус != active отсекаются отбором."""
    now = datetime.now(timezone.utc)
    await _user(db, 6105, onboard_done=now - timedelta(days=2), morning_push=0)
    await _user(db, 6106, onboard_done=now - timedelta(days=2), status="banned")
    await _user(db, 6107, onboard_done=now - timedelta(days=2), onboarded=0)
    assert await scheduler._welcome_audience(db, now) == []


async def test_audience_excludes_without_onboard_done(db):
    """Нет события onboard_done — нет точки входа, юзер не отбирается."""
    now = datetime.now(timezone.utc)
    await _user(db, 6108, onboard_done=None)
    assert await scheduler._welcome_audience(db, now) == []


# ─────────────────────────── контур d1/d3/d7 ─────────────────────────────────

async def test_chain_d1_sent_after_24h(db):
    """W1 уходит в первые сутки после 24ч; текст с {name}, без плейсхолдеров."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6111, onboard_done=now - timedelta(hours=26))
    bot = RecordingBot()

    await scheduler._welcome_chain(bot, db, user, now_utc=now)

    assert len(bot.sent) == 1
    tg_id, text, _ = bot.sent[0]
    assert tg_id == 6111
    assert "{name}" not in text and "{top_first_step}" not in text
    assert await comms.already_sent(db, tg_id, "welcome_chain", "d1:6111")


async def test_chain_one_touch_per_run(db):
    """d1 и d3 не слипаются: за прогон уходит только одно касание."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6112, onboard_done=now - timedelta(days=4))
    bot = RecordingBot()

    await scheduler._welcome_chain(bot, db, user, now_utc=now)

    assert len(bot.sent) == 1
    assert await comms.already_sent(db, 6112, "welcome_chain", "d1:6112")
    assert not await comms.already_sent(db, 6112, "welcome_chain", "d3:6112")


async def test_chain_progresses_to_d7(db):
    """Прогоны через d3-и d7-сроки: d1 → d3 → d7, каждый в свой.

    Guardrail 1/7д (BUS-262) разводит шаги по ISO-неделям, поэтому прогоны
    разнесены на 8 суток — иначе d3/d7 блокировались бы неделей d1."""
    now = datetime.now(timezone.utc)
    # onboard_done за 8 суток: все три срока в прошлом, касания
    # размазываются по неделям (одно за прогон).
    user = await _user(db, 6113, onboard_done=now - timedelta(days=8))
    bot = RecordingBot()
    for _ in range(3):
        await scheduler._welcome_chain(bot, db, user, now_utc=now)
        user = await users.get(db, 6113)
        now += timedelta(days=8)
    await scheduler._welcome_chain(bot, db, user, now_utc=now)

    keys = [await comms.already_sent(db, 6113, "welcome_chain", k)
            for k in ("d1:6113", "d3:6113", "d7:6113")]
    assert keys == [True, True, True]
    d7_text = bot.sent[-1][1]
    assert "{top_first_step}" not in d7_text and "{name}" not in d7_text


async def test_chain_d3_not_sent_before_3_days(db):
    """W2 не уходит раньше 3 суток от onboard_done: 2-й прогон через сутки — d3 ещё рано."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6114, onboard_done=now - timedelta(hours=26))
    bot = RecordingBot()

    await scheduler._welcome_chain(bot, db, user, now_utc=now)   # d1
    assert len(bot.sent) == 1

    await scheduler._welcome_chain(
        bot, db, user, now_utc=now + timedelta(days=1))       # ~50ч: d3 рано
    assert len(bot.sent) == 1, "d3 ушёл раньше срока"


async def test_chain_exits_on_first_value(db):
    """Стоп: после first-события следующий шаг не уходит вовсе."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6115, onboard_done=now - timedelta(days=4))
    bot = RecordingBot()

    await scheduler._welcome_chain(bot, db, user, now_utc=now)   # d1
    await _first_event(db, 6115, "first_question")
    audience = await scheduler._welcome_audience(db, now + timedelta(days=4))
    assert audience == []
    # Немедленный выход и вне отбора: юзер достиг first-value, пока sweep
    # шёл по партии (аудитория снимается в начале прогона).
    await scheduler._welcome_chain(bot, db, user, now_utc=now + timedelta(days=4))
    assert len(bot.sent) == 1
    assert not await comms.already_sent(db, 6115, "welcome_chain", "d3:6115")


async def test_chain_silent_when_template_missing(db):
    """Нет шаблона в content — молчим (не шлём пустоту/кашу), шаг не помечен."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6116, onboard_done=now - timedelta(hours=30))
    bot = RecordingBot()

    with patch("app.services.scheduler.content.get_text",
               return_value=""):
        await scheduler._welcome_chain(bot, db, user, now_utc=now)

    assert bot.sent == []
    assert not await comms.already_sent(db, 6116, "welcome_chain", "d1:6116")


# ─────────────────────────── W3-персонализация ───────────────────────────────

async def test_welcome_top_first_step_aggregate(db):
    """Агрегат: частота first-событий за 90д решает подстановку."""
    now = datetime.now(timezone.utc)
    since = _iso(now - timedelta(days=1))
    for tg_id in range(6120, 6123):
        await db.execute(
            "INSERT INTO events(tg_id, name, day, created_at) "
            "VALUES(:t, 'first_ritual', '2026-09-05', :c)",
            {"t": tg_id, "c": since})
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) "
        "VALUES(6123, 'first_question', '2026-09-05', :c)", {"c": since})
    await db.commit()
    assert await scheduler._welcome_top_first_step(db, "ru") == "практика"
    assert await scheduler._welcome_top_first_step(db, "en") == "practices"


async def test_welcome_top_first_step_empty_base(db):
    """Нет событий — дефолтная фраза, не пустая строка."""
    assert await scheduler._welcome_top_first_step(db, "ru") == "карта дня"
    assert await scheduler._welcome_top_first_step(db, "en") == "card of the day"


async def test_chain_d7_substitutes_top_first_step(db):
    """d7 с реальными событиями: {top_first_step} заменён агрегатом.

    Прогоны разнесены на 8 суток: guardrail 1/7д (BUS-262) держит шаги
    в разных ISO-неделях."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6131, onboard_done=now - timedelta(days=25))
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) "
        "VALUES(6132, 'first_question', '2026-09-05', :c)",
        {"c": _iso(now - timedelta(days=1))})
    await db.commit()
    bot = RecordingBot()
    for _ in range(4):
        await scheduler._welcome_chain(bot, db, user, now_utc=now)
        user = await users.get(db, 6131)
        now += timedelta(days=8)
    await scheduler._welcome_chain(bot, db, user, now_utc=now)

    d7_text = next(t for _, t, _ in bot.sent if "вопрос" in t or "week" in t)
    assert "вопрос" in d7_text


# ─────────────────────────── суточный sweep ──────────────────────────────────

async def test_daily_sweep_runs_once_per_day(db):
    """Sweep идемпотентен в сутках: повторный вызов в тот же день — no-op."""
    now = datetime(2026, 9, 6, 10, 5, tzinfo=timezone.utc)
    assert await scheduler._daily_sweep_due(db, scheduler.WELCOME_LAST_RUN_KEY, now)
    assert not await scheduler._daily_sweep_due(db, scheduler.WELCOME_LAST_RUN_KEY, now)
    next_day = now + timedelta(days=1)
    assert await scheduler._daily_sweep_due(db, scheduler.WELCOME_LAST_RUN_KEY, next_day)


async def test_daily_sweeps_sends_and_marks_day(db):
    """Полный sweep в час WELCOME_SWEEP_HOUR: касание уходит, день отмечен."""
    now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    await _user(db, 6141, onboard_done=now - timedelta(days=2))
    bot = RecordingBot()

    await scheduler._daily_sweeps(bot, db, now)
    assert len(bot.sent) == 1
    assert await comms.already_sent(db, 6141, "welcome_chain", "d1:6141")

    await scheduler._daily_sweeps(bot, db, now + timedelta(minutes=10))
    assert len(bot.sent) == 1, "повторный sweep в тот же день отправил дубль"


async def test_daily_sweeps_skips_outside_hour(db):
    """Вне суточного часа sweep не отбирает и не отправляет."""
    now = datetime(2026, 9, 6, 14, 0, tzinfo=timezone.utc)
    await _user(db, 6142, onboard_done=now - timedelta(days=2))
    bot = RecordingBot()

    await scheduler._daily_sweeps(bot, db, now)
    assert bot.sent == []
