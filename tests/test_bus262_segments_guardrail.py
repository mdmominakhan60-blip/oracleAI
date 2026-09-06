"""BUS-262 волна 3.7 — winback_90d, cancelled_5_7d, guardrail 1/7д.

Контракт:
- winback_90d: юзер с redemption winback-батча за 90 дней — в сегменте;
  чужие батчи не попадают; без redemption — нет.
- cancelled_5_7d: подписка истекла 5-7 дней назад — в сегменте; границы 5/7д
  включительны (дизайн WB2: 5+ дней, триггер scheduler WINBACK2_AFTER_DAYS=5).
  Существующий cancelled_recent (30д, BUS-169/232) — не трогаем.
- guardrail: вторая маркетинговая отправка (welcome_chain) в ту же ISO-неделю
  блокируется; событийные (winback2, post_limit, low_balance) — вне лимита.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.repo import comms, growth, users
from app.services import scheduler


class RecordingBot:
    def __init__(self):
        self.sent: list[tuple[int, str, str]] = []

    async def send_message(self, tg_id, text, reply_markup=None):
        self.sent.append((tg_id, text, ""))


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# ─────────────────────────── winback_90d ────────────────────────────────────

async def _winback_redemption(db, tg_id: int, code: str, days_ago: int) -> None:
    """Прямая запись redemption для теста."""
    await db.execute(
        "INSERT INTO promo_redemptions(code, tg_id, created_at) "
        "VALUES(:code, :tg_id, :created_at)",
        {"code": code, "tg_id": tg_id,
         "created_at": _iso(datetime.now(timezone.utc) - timedelta(days=days_ago))})
    await db.commit()


async def _ensure_with_sub(db, tg_id: int, *, sub_until: str | None = None) -> dict:
    await users.ensure(db, tg_id, f"U-{tg_id}")
    await users.update(db, tg_id, onboarded=1, sub_level="free",
                       sub_until=sub_until, morning_push=1, status="active",
                       lang="ru")
    return await users.get(db, tg_id)


async def test_winback_90d_user_with_recent_redemption(db):
    """Redemption winback-кода 30 дней назад — юзер в сегменте."""
    batch = "winback_2026-08"
    codes = await growth.create_codes(db, 3, kind="plan_days", days=7,
                                      plan_code="trial", batch=batch,
                                      max_uses=1, valid_days=14)
    code = codes[0]
    await _winback_redemption(db, 6201, code, days_ago=30)
    await _ensure_with_sub(db, 6201)

    assert await users.segment_ids(db, "winback_90d") == [6201]
    assert await users.segment_count(db, "winback_90d") == 1


async def test_winback_90d_no_redemption(db):
    """Без redemption winback-кода — юзер не в сегменте."""
    await _ensure_with_sub(db, 6202)

    assert await users.segment_ids(db, "winback_90d") == []


async def test_winback_90d_other_batch_excluded(db):
    """Redemption из не-winback батча — не попадает в сегмент."""
    other_batch = "promo_2026_summer"
    codes = await growth.create_codes(db, 2, kind="plan_days", days=7,
                                      plan_code="trial", batch=other_batch,
                                      max_uses=1, valid_days=14)
    await _winback_redemption(db, 6203, codes[0], days_ago=10)
    await _ensure_with_sub(db, 6203)

    assert await users.segment_ids(db, "winback_90d") == []


async def test_winback_90d_old_redemption_outside_window(db):
    """Redemption старше 90 дней — не в сегменте."""
    batch = "winback_2026-05"
    codes = await growth.create_codes(db, 2, kind="plan_days", days=7,
                                      plan_code="trial", batch=batch,
                                      max_uses=1, valid_days=14)
    await _winback_redemption(db, 6204, codes[0], days_ago=100)
    await _ensure_with_sub(db, 6204)

    assert await users.segment_ids(db, "winback_90d") == []


# ─────────────────────────── cancelled_5_7d ─────────────────────────────────

async def test_cancelled_5_7d_window_bounds(db):
    """5-7 дней после истечения — в сегменте; 4д/8д/активна/никогда — нет."""
    now = datetime.now(timezone.utc)
    await _ensure_with_sub(db, 6211, sub_until=_iso(now - timedelta(days=6)))
    await _ensure_with_sub(db, 6212, sub_until=_iso(now - timedelta(days=4)))
    await _ensure_with_sub(db, 6213, sub_until=_iso(now - timedelta(days=8)))
    await _ensure_with_sub(db, 6214, sub_until=_iso(now + timedelta(days=1)))
    await _ensure_with_sub(db, 6215, sub_until=None)

    assert sorted(await users.segment_ids(db, "cancelled_5_7d")) == [6211]


async def test_cancelled_5_7d_boundary_5_days(db):
    """Ровно 5 дней — верхняя граница включительна."""
    now = datetime.now(timezone.utc)
    await _ensure_with_sub(db, 6216, sub_until=_iso(now - timedelta(days=5)))

    assert await users.segment_ids(db, "cancelled_5_7d") == [6216]


async def test_cancelled_5_7d_boundary_7_days(db):
    """7 дней — нижняя граница включительна (timing-safe: 7-epsilon)."""
    now = datetime.now(timezone.utc)
    await _ensure_with_sub(db, 6217, sub_until=_iso(now - timedelta(days=7) + timedelta(seconds=1)))

    assert await users.segment_ids(db, "cancelled_5_7d") == [6217]


async def test_cancelled_recent_30d_untouched(db):
    """Существующий cancelled_recent (30д) — не затронут новым предикатом."""
    now = datetime.now(timezone.utc)
    # 6 дней — попадает в оба; 20 дней — только в cancelled_recent (30д)
    await _ensure_with_sub(db, 6218, sub_until=_iso(now - timedelta(days=6)))
    await _ensure_with_sub(db, 6219, sub_until=_iso(now - timedelta(days=20)))

    assert sorted(await users.segment_ids(db, "cancelled_recent")) == [6218, 6219]
    assert sorted(await users.segment_ids(db, "cancelled_5_7d")) == [6218]


# ─────────────────────────── guardrail 1/7д ─────────────────────────────────

@pytest.fixture(autouse=True)
def _no_webapp(monkeypatch):
    monkeypatch.setattr(scheduler.settings, "webapp_url", "")


async def _welcome_user(db, tg_id: int, *, onboard_done: datetime) -> dict:
    """Юзер для welcome-цепочки."""
    await users.ensure(db, tg_id, f"G-{tg_id}")
    await users.update(db, tg_id, onboarded=1, sub_level="free",
                       sub_until=None, morning_push=1, status="active",
                       lang="ru")
    await db.execute(
        "INSERT INTO events(tg_id, name, day, created_at) "
        "VALUES(:tg_id, 'onboard_done', :day, :created_at)",
        {"tg_id": tg_id, "day": onboard_done.strftime("%Y-%m-%d"),
         "created_at": _iso(onboard_done)})
    await db.commit()
    return await users.get(db, tg_id)


async def test_guardrail_blocks_second_marketing_in_same_week(db):
    """Вторая welcome в ту же ISO-неделю блокируется guardrail."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)  # понедельник, W37
    user = await _welcome_user(db, 6231, onboard_done=now - timedelta(days=2))
    bot = RecordingBot()

    # Первая отправка — проходит.
    await scheduler._welcome_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1
    week_key = now.strftime("%G-W%V")
    assert await comms.already_sent(db, 6231, "guardrail", week_key)

    # Вторая в тот же день — блокируется.
    bot.sent.clear()
    await scheduler._welcome_chain(bot, db, user, now_utc=now)
    assert bot.sent == [], "guardrail: вторая маркетинговая в ту же неделю"


async def test_guardrail_allows_in_next_week(db):
    """Новая неделя — guardrail сброшен, отправка проходит."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)  # W37
    user = await _welcome_user(db, 6232, onboard_done=now - timedelta(days=2))
    bot = RecordingBot()

    await scheduler._welcome_chain(bot, db, user, now_utc=now)
    assert len(bot.sent) == 1

    bot.sent.clear()
    next_week = now + timedelta(days=8)  # W38
    await scheduler._welcome_chain(bot, db, user, now_utc=next_week)
    assert len(bot.sent) == 1, "guardrail: новая неделя — можно"


async def test_guardrail_does_not_block_event_driven(db):
    """Событийные сообщения (winback2) — вне guardrail."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    await users.ensure(db, 6233, "WB-6233")
    await users.update(db, 6233, onboarded=1, sub_level="trial",
                       sub_until=_iso(now - timedelta(days=7)),
                       expiry_notified=2, lang="ru")
    bot = RecordingBot()

    await scheduler._winback(bot, db, await users.get(db, 6233), now_utc=now)
    assert len(bot.sent) == 1
    week_key = now.strftime("%G-W%V")
    assert await comms.already_sent(db, 6233, "winback2", _iso(now - timedelta(days=7)))
    # guardrail НЕ затронут событийной отправкой
    assert not await comms.already_sent(db, 6233, "guardrail", week_key)


async def test_guardrail_reserved_on_successful_send(db):
    """guardrail резервируется только при успешной отправке (_send_once=True)."""
    now = datetime(2026, 9, 7, 10, 0, tzinfo=timezone.utc)
    user = await _welcome_user(db, 6234, onboard_done=now - timedelta(days=2))

    # _send_once возвращает False (занято) — guardrail не резервируется.
    with patch("app.services.scheduler._send_once", return_value=False):
        await scheduler._welcome_chain(RecordingBot(), db, user, now_utc=now)
    week_key = now.strftime("%G-W%V")
    assert not await comms.already_sent(db, 6234, "guardrail", week_key)
