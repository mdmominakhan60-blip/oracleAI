"""BUS-259 волна 3.4 — onboarding-дожим O1-O2: суточный отбор вне _audience.

Контракт (дизайн BUS-190 §2, копирайт BUS-263 §5):
- отбор: onboarded=0, статус active, start ≥24ч назад — вне _audience;
- контур: O1 (день 1, кнопка web_app), O2 (день 3, финальное);
- kind='onboard_nudge', key='d1|d3:{tg_id}';
- стопы: onboarded=1 (отбор), O2 отправлен → заморозка навсегда;
- отбор по событию start, не по users.created_at.
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


async def _user(db, tg_id: int, *, start: datetime | None,
                status: str = "active", onboarded: int = 0,
                lang: str = "ru") -> dict:
    """Юзер-кандидат; событие start пишется напрямую в events."""
    await users.ensure(db, tg_id, f"O-{tg_id}")
    await users.update(db, tg_id, onboarded=onboarded, sub_level="free",
                       sub_until=None, status=status, lang=lang)
    if start is not None:
        await db.execute(
            "INSERT INTO events(tg_id, name, day, created_at) "
            "VALUES(:tg_id, 'start', :day, :created_at)",
            {"tg_id": tg_id, "day": start.strftime("%Y-%m-%d"),
             "created_at": start.isoformat()})
        await db.commit()
    return await users.get(db, tg_id)


@pytest.fixture(autouse=True)
def _no_webapp(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "webapp_url", "")


# ─────────────────────────── отбор аудитории ─────────────────────────────────

async def test_audience_unonboarded_after_24h(db):
    """Кандидат: неонбордингнутый, активный, start ≥24ч назад."""
    now = datetime.now(timezone.utc)
    await _user(db, 6201, start=now - timedelta(hours=30))
    audience = await scheduler._onboard_audience(db, now)
    assert [u["tg_id"] for u in audience] == [6201]


async def test_audience_excludes_before_24h(db):
    """start меньше 24ч назад — рано, касания нет."""
    now = datetime.now(timezone.utc)
    await _user(db, 6202, start=now - timedelta(hours=10))
    assert await scheduler._onboard_audience(db, now) == []


async def test_audience_excludes_onboarded_and_inactive(db):
    """Стопы: onboarded=1 и статус != active отсекаются самим отбором."""
    now = datetime.now(timezone.utc)
    await _user(db, 6203, start=now - timedelta(days=2), onboarded=1)
    await _user(db, 6204, start=now - timedelta(days=2), status="banned")
    assert await scheduler._onboard_audience(db, now) == []


async def test_audience_excludes_without_start_event(db):
    """Нет события start — нет триггера, юзер не отбирается."""
    now = datetime.now(timezone.utc)
    await _user(db, 6205, start=None)
    assert await scheduler._onboard_audience(db, now) == []


# ─────────────────────────── контур O1/O2 ────────────────────────────────────

async def test_chain_o1_sent_after_24h(db):
    """O1 уходит в первые сутки после 24ч; текст без плейсхолдеров."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6211, start=now - timedelta(hours=26))
    bot = RecordingBot()

    await scheduler._onboard_chain(bot, db, user, now_utc=now)

    assert len(bot.sent) == 1
    tg_id, text, _ = bot.sent[0]
    assert tg_id == 6211
    assert "{name}" not in text
    assert await comms.already_sent(db, tg_id, "onboard_nudge", "d1:6211")


async def test_chain_o2_not_before_3_days(db):
    """O2 не уходит раньше 3 суток от первого start (на 2-е сутки ещё нет)."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6212, start=now - timedelta(days=2))
    bot = RecordingBot()

    await scheduler._onboard_chain(bot, db, user, now_utc=now)   # O1
    assert len(bot.sent) == 1

    # На 2-е сутки от O1 = 3-и сутки от start минус час — O2 ещё рано.
    await scheduler._onboard_chain(bot, db, user,
                                   now_utc=now + timedelta(days=1, hours=-1))
    assert len(bot.sent) == 1, "O2 ушёл раньше срока"


async def test_chain_o2_sent_on_day_3(db):
    """O2 уходит на третьи сутки; после него новых касаний нет."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6213, start=now - timedelta(hours=30))
    bot = RecordingBot()

    await scheduler._onboard_chain(bot, db, user, now_utc=now)   # O1
    await scheduler._onboard_chain(bot, db, user,
                                   now_utc=now + timedelta(days=3))
    assert len(bot.sent) == 2
    assert await comms.already_sent(db, 6213, "onboard_nudge", "d3:6213")

    await scheduler._onboard_chain(bot, db, user,
                                   now_utc=now + timedelta(days=10))
    assert len(bot.sent) == 2, "после O2 цепочка должна молчать"


async def test_chain_o2_is_terminal_freeze(db):
    """O2 отправлен → заморозка навсегда: повторный прогон не отправляет.

    Заморозка держится на дедупе kind+key: сколько бы прогонов ни прошло,
    d3 ушёл один раз, новых шагов у цепочки нет.
    """
    now = datetime.now(timezone.utc)
    user = await _user(db, 6214, start=now - timedelta(days=5))
    bot = RecordingBot()

    for _ in range(3):
        await scheduler._onboard_chain(bot, db, user, now_utc=now)

    assert len(bot.sent) == 1
    assert await comms.already_sent(db, 6214, "onboard_nudge", "d3:6214")
    assert not await comms.already_sent(db, 6214, "onboard_nudge", "d1:6214")


async def test_chain_exits_when_onboarded_after_o1(db):
    """Стоп: onboarded стал 1 после O1 → O2 не уходит вовсе.

    Второй вызов цепочки — прямой (в обход отбора), чтобы доказать: даже
    если юзер до цепочки доехал до постановки onboarded=1, O2 удержан.
    """
    now = datetime.now(timezone.utc)
    user = await _user(db, 6215, start=now - timedelta(hours=30))
    bot = RecordingBot()

    await scheduler._onboard_chain(bot, db, user, now_utc=now)   # O1
    assert len(bot.sent) == 1

    await users.update(db, 6215, onboarded=1)
    audience = await scheduler._onboard_audience(db, now + timedelta(days=4))
    assert audience == []
    user = await users.get(db, 6215)
    assert user["onboarded"] == 1
    await scheduler._onboard_chain(bot, db, user,
                                   now_utc=now + timedelta(days=4))
    assert len(bot.sent) == 1
    assert not await comms.already_sent(db, 6215, "onboard_nudge", "d3:6215")


async def test_chain_d1_late_only_o2_sent(db):
    """Пропуск d1 (простой сервиса): на 4-е сутки уходит только O2, без d1.

    Обратная сторона «не навязываем»: d1 устарел, догонять его отдельным
    касанием — лишний пинг неактивированному.
    """
    now = datetime.now(timezone.utc)
    user = await _user(db, 6216, start=now - timedelta(days=4))
    bot = RecordingBot()

    await scheduler._onboard_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1
    assert await comms.already_sent(db, 6216, "onboard_nudge", "d3:6216")
    assert not await comms.already_sent(db, 6216, "onboard_nudge", "d1:6216")


async def test_chain_silent_when_template_missing(db):
    """Нет шаблона в content — молчим, шаг не помечен."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6217, start=now - timedelta(hours=30))
    bot = RecordingBot()

    with patch("app.services.scheduler.content.get_text", return_value=""):
        await scheduler._onboard_chain(bot, db, user, now_utc=now)

    assert bot.sent == []
    assert not await comms.already_sent(db, 6217, "onboard_nudge", "d1:6217")


async def test_chain_uses_lang(db):
    """EN-клиентка получает EN-текст (get_text с lang=en)."""
    now = datetime.now(timezone.utc)
    user = await _user(db, 6218, start=now - timedelta(hours=30), lang="en")
    bot = RecordingBot()

    await scheduler._onboard_chain(bot, db, user, now_utc=now)

    text = bot.sent[0][1]
    assert "one step left" in text


# ─────────────────────────── суточный sweep ──────────────────────────────────

async def test_daily_sweeps_sends_and_marks_day(db):
    """Полный sweep в час WELCOME_SWEEP_HOUR: O1 уходит, день отмечен."""
    now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    await _user(db, 6221, start=now - timedelta(days=2))
    bot = RecordingBot()

    await scheduler._daily_sweeps(bot, db, now)
    assert len(bot.sent) == 1
    assert await comms.already_sent(db, 6221, "onboard_nudge", "d1:6221")

    await scheduler._daily_sweeps(bot, db, now + timedelta(minutes=10))
    assert len(bot.sent) == 1, "повторный sweep в тот же день отправил дубль"


async def test_daily_sweeps_independent_day_marks(db):
    """Welcome- и onboard-отметки суток независимы: welcome уже гонялся
    в этот день — onboard-цепочка всё равно отрабатывает."""
    from app.repo import content
    now = datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc)
    await _user(db, 6222, start=now - timedelta(days=2))
    await content.set_setting(db, scheduler.WELCOME_LAST_RUN_KEY,
                              now.strftime("%Y-%m-%d"))
    bot = RecordingBot()

    from app.repo import users as users_repo
    await users_repo.update(db, 6222, morning_push=0)
    await scheduler._daily_sweeps(bot, db, now)
    assert len(bot.sent) == 1


async def test_daily_sweep_due_onboard_key(db):
    """Идемпотентность по ключу crm.onboard_last_run."""
    now = datetime(2026, 9, 6, 10, 5, tzinfo=timezone.utc)
    assert await scheduler._daily_sweep_due(
        db, scheduler.ONBOARD_LAST_RUN_KEY, now)
    assert not await scheduler._daily_sweep_due(
        db, scheduler.ONBOARD_LAST_RUN_KEY, now)
