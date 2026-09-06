"""Приёмка BUS-265 п.1 — планировщик: дедупликация и устойчивость тика.

Нагрузочный сценарий: два параллельных тика на одного пользователя. Журнал
`deliveries` (PK tg_id, kind, key) — единственная защита от дубля; отметка
ставится до отправки. Проверяем, что при конкуренции уходит ровно одна
отправка, а временный сбой возвращает право отправки (retry).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.repo import comms, users
from app.services import scheduler


class RecordingBot:
    """Фейковый бот: фиксирует тексты и умеет «падать» по флагу."""

    def __init__(self, fail_times: int = 0):
        self.sent: list[tuple[int, str]] = []
        self.fail_times = fail_times

    async def send_message(self, tg_id, text, reply_markup=None):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("временный сбой сети")
        self.sent.append((tg_id, text))


async def test_claim_race_single_winner(db):
    """Два параллельных claim одного kind+key — выигрывает ровно один."""
    results = await asyncio.gather(
        comms.claim(db, 3001, "welcome_chain", "d1:3001"),
        comms.claim(db, 3001, "welcome_chain", "d1:3001"),
    )
    assert sorted(results) == [False, True], "оба claim прошли: дубль гарантирован"
    assert await comms.already_sent(db, 3001, "welcome_chain", "d1:3001")


async def _vip_user(db, tg_id: int):
    await users.ensure(db, tg_id, f"Тик-{tg_id}")
    await users.update(db, tg_id, onboarded=1, tz="Europe/Moscow",
                       morning_push=1, sub_level="vip")
    return await users.get(db, tg_id)


def _freeze_now(monkeypatch):
    """Фиксирует часы планировщика на реальном московском времени, но с
    «выключенными» остальными сценариями — тик отработает только прогноз дня.

    Возвращает (settings_cache, день_московский).
    """
    msk_now = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Moscow"))
    settings_cache = {"morning_hour": msk_now.hour, "weekly_hour": -1,
                      "practice_hour": -1, "weekly_weekday": -1,
                      "monthly_day": 32, "horoscope_hour": -1}

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return msk_now.astimezone(tz) if tz else msk_now

    async def fake_settings(db_):
        return settings_cache

    monkeypatch.setattr(scheduler, "datetime", FixedDatetime)
    monkeypatch.setattr(scheduler, "_load_settings", fake_settings)
    return settings_cache, msk_now.strftime("%Y-%m-%d")


async def test_two_parallel_ticks_send_once(db, monkeypatch):
    """Нагрузочный сценарий: 2 параллельных тика на одного юзера.

    Утренний прогноз уходит ровно один раз: claim forecasting:{day}
    пропускает второго отправителя даже при наложении по времени.
    """
    _, day = _freeze_now(monkeypatch)
    user = await _vip_user(db, 3002)

    async def two_tick_users(db_, zones):
        return [user, user]  # один юзер попал в два «тика» одновременно

    monkeypatch.setattr(scheduler, "_audience", two_tick_users)
    monkeypatch.setattr(scheduler, "BATCH_PAUSE", 0)

    bots = [RecordingBot(), RecordingBot()]
    await asyncio.gather(scheduler.tick(bots[0], db),
                         scheduler.tick(bots[1], db))

    all_sent = bots[0].sent + bots[1].sent
    forecasts = [text for tg, text in all_sent if text.startswith("🌅")]
    assert len(forecasts) == 1, \
        f"прогноз ушёл {len(forecasts)} раз при параллельных тиках: {all_sent}"
    assert await comms.already_sent(db, 3002, "forecast", day), \
        "прогноз не отмечен в журнале после тика"
    cur = await db.execute(
        "SELECT COUNT(*) n FROM deliveries WHERE kind='forecast' AND key=:day",
        {"day": day})
    assert (await cur.fetchone())["n"] == 1, "в журнале больше одной отметки"


async def test_send_once_retries_after_temporary_failure(db):
    """Временный сбой доставки возвращает claim — повтор позже отправит."""
    bot = RecordingBot(fail_times=1)
    ok = await scheduler._send_once(bot, db, 3003, "winback2", "k1", "текст")
    assert not ok, "сбой не распознан"
    assert not await comms.already_sent(db, 3003, "winback2", "k1"), \
        "claim не снят после временного сбоя — повтор невозможен"

    bot2 = RecordingBot()
    ok2 = await scheduler._send_once(bot2, db, 3003, "winback2", "k1", "текст")
    assert ok2, "повтор после сбоя не отправился"
    assert await comms.already_sent(db, 3003, "winback2", "k1")


async def test_send_once_never_resends_after_success(db):
    """После успешной отправки повторный вызов с тем же kind+key молчит."""
    bot = RecordingBot()
    assert await scheduler._send_once(bot, db, 3004, "reactivate", "r1", "раз")
    assert not await scheduler._send_once(bot, db, 3004, "reactivate", "r1", "два")
    assert bot.sent == [(3004, "раз")]


async def test_error_one_user_does_not_break_sweep(db, monkeypatch):
    """Ошибка сценария одного юзера не валит sweep — второй получает свой прогноз.

    Паттерн tick(): try/except вокруг каждого юзера в цикле аудитории.
    """
    _, day = _freeze_now(monkeypatch)
    u1 = await _vip_user(db, 3010)
    u2 = await _vip_user(db, 3011)

    async def two_users(db_, zones):
        return [u1, u2]

    orig = scheduler._tick_user

    async def flaky(bot_, db_, user, *a, **kw):
        if user["tg_id"] == 3010:
            raise RuntimeError("сценарий упал для первого юзера")
        await orig(bot_, db_, user, *a, **kw)

    monkeypatch.setattr(scheduler, "_audience", two_users)
    monkeypatch.setattr(scheduler, "_tick_user", flaky)
    monkeypatch.setattr(scheduler, "BATCH_PAUSE", 0)

    bot = RecordingBot()
    await scheduler.tick(bot, db)

    assert await comms.already_sent(db, 3011, "forecast", day), \
        "падение первого юзера оборвало sweep: второй остался без прогноза"
    assert not await comms.already_sent(db, 3010, "forecast", day), \
        "упавший юзер получил отправку"
