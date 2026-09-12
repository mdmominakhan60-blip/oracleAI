"""Приёмка BUS-265 п.1 — планировщик: дедупликация и устойчивость тика.

Нагрузочный сценарий: два параллельных тика на одного пользователя. Журнал
`deliveries` (PK tg_id, kind, key) — единственная защита от дубля; отметка
ставится до отправки. Проверяем, что при конкуренции уходит ровно одна
отправка, а временный сбой возвращает право отправки (retry).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.data.session import utcnow
from app.repo import comms, users
from app.repo.comms import CLAIM_TIMEOUT_S
from app.services import scheduler


class RecordingBot:
    """Фейковый бот: фиксирует тексты и умеет «падать» по флагу."""

    def __init__(self, fail_times: int = 0, forbidden: bool = False):
        self.sent: list[tuple[int, str]] = []
        self.fail_times = fail_times
        self.forbidden = forbidden

    async def send_message(self, tg_id, text, reply_markup=None):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("временный сбой сети")
        if self.forbidden:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=tg_id, text=text),
                message="Forbidden: bot was blocked by the user")
        self.sent.append((tg_id, text))


async def test_claim_race_single_winner(db):
    """Два параллельных claim одного kind+key — выигрывает ровно один.

    Победитель оставляет строку в status='sending' — ещё НЕ терминальное
    состояние: until mark_sent/failed already_sent обязан быть False.
    """
    results = await asyncio.gather(
        comms.claim(db, 3001, "welcome_chain", "d1:3001"),
        comms.claim(db, 3001, "welcome_chain", "d1:3001"),
    )
    assert sorted(results) == [False, True], "оба claim прошли: дубль гарантирован"
    assert not await comms.already_sent(db, 3001, "welcome_chain", "d1:3001"), \
        "sending — не терминальный статус, already_sent не должен срабатывать"
    cur = await db.execute(
        "SELECT status FROM deliveries WHERE tg_id=3001 AND kind='welcome_chain' AND key='d1:3001'")
    assert (await cur.fetchone())["status"] == "sending"


async def test_claim_reclaims_stale_sending_after_timeout(db):
    """BUS-313 F1: крэш процесса между claim и mark — строка застревает в
    'sending' и никогда не пере-claimается (claim брал только failed).

    Через CLAIM_TIMEOUT_S право возвращается: следующий тик пере-занимает
    stale-sending и доотправляет. Дедуп держится — sent/forbidden по-прежнему
    не пере-занимаются.
    """
    # Крэш-симуляция: claim прошёл, mark не случился.
    assert await comms.claim(db, 3020, "onboard_nudge", "d3:3020")
    cur = await db.execute(
        "SELECT status, created_at FROM deliveries "
        "WHERE tg_id=3020 AND kind='onboard_nudge' AND key='d3:3020'")
    row = await cur.fetchone()
    assert row["status"] == "sending"
    crashed_at = datetime.fromisoformat(row["created_at"])

    # Свежий claim (прошли секунды, а не CLAIM_TIMEOUT_S) ещё не пере-занимает:
    # окно активной отправки защищено.
    assert not await comms.claim(db, 3020, "onboard_nudge", "d3:3020"), \
        "свежая sending-строка пере-занята — окно активной отправки нарушено"

    # Прошло CLAIM_TIMEOUT_S: reclaim срабатывает.
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = crashed_at + timedelta(seconds=comms.CLAIM_TIMEOUT_S + 5)
            return fixed.astimezone(tz) if tz else fixed

    orig_now = comms.datetime
    comms.datetime = FixedDatetime
    try:
        assert await comms.claim(db, 3020, "onboard_nudge", "d3:3020"), \
            "stale-sending старше CLAIM_TIMEOUT_S не пере-занят: доставка зависла навсегда"
    finally:
        comms.datetime = orig_now

    # Терминальные статусы reclaim не трогает — дедуп не потерян.
    await comms.mark_sent(db, 3020, "onboard_nudge", "d3:3020")
    assert not await comms.claim(db, 3020, "onboard_nudge", "d3:3020"), \
        "sent-строка пере-занята после reclaim-фикса — дубль уйдёт клиентке"


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
    """Временный сбой → failed-строка остаётся в журнале, retry пере-занимает."""
    bot = RecordingBot(fail_times=1)
    ok = await scheduler._send_once(bot, db, 3003, "winback2", "k1", "текст")
    assert not ok, "сбой не распознан"
    assert not await comms.already_sent(db, 3003, "winback2", "k1"), \
        "failed не должен считаться терминальным"
    cur = await db.execute(
        "SELECT status FROM deliveries WHERE tg_id=3003 AND kind='winback2' AND key='k1'")
    assert (await cur.fetchone())["status"] == "failed", \
        "строка после временного сбоя должна остаться в журнале как failed"

    bot2 = RecordingBot()
    ok2 = await scheduler._send_once(bot2, db, 3003, "winback2", "k1", "текст")
    assert ok2, "повтор после сбоя не отправился (claim не пере-занял failed)"
    assert await comms.already_sent(db, 3003, "winback2", "k1")


async def test_forbidden_first_day_is_soft_retry(db, monkeypatch):
    """BUS-369: первый Forbidden — мягкий retry (failed), порог = 3 дня подряд.

    Тест замораживает «сегодня» через monkeypatch: счётчик неудач ведётся
    по датам, и три _send_once в одном тесте не должны наливаться в один день.
    """
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            fixed = datetime(2026, 9, 7, tzinfo=timezone.utc)
            return fixed.astimezone(tz) if tz else fixed

    monkeypatch.setattr(scheduler.comms, "datetime", FixedDatetime)

    bot = RecordingBot(forbidden=True)
    ok = await scheduler._send_once(bot, db, 3005, "winback2", "f1", "текст")
    assert not ok, "forbidden не должен считаться успешной отправкой"
    # Мягкий retry: первый Forbidden не терминален.
    cur = await db.execute(
        "SELECT status, error FROM deliveries WHERE tg_id=3005 AND kind='winback2' AND key='f1'")
    row = await cur.fetchone()
    assert row["status"] == "failed", \
        f"первый Forbidden — мягкий retry, ожидали failed, получили {row['status']!r}"
    assert row["error"] == "TelegramForbiddenError", \
        f"в error ждём только класс исключения, получили {row['error']!r}"

    # Повторный вызов с тем же kind+key: claim НЕ пере-занимает sending/forbidden,
    # но failed пере-занимается — ретрай уйдёт, и это ок до порога.
    ok2 = await scheduler._send_once(bot, db, 3005, "winback2", "f1", "текст")
    assert not ok2
    cur = await db.execute(
        "SELECT status FROM deliveries WHERE tg_id=3005 AND kind='winback2' AND key='f1'")
    assert (await cur.fetchone())["status"] == "failed"


async def test_forbidden_third_day_is_terminal(db, monkeypatch):
    """BUS-369: 3-й день подряд с Forbidden → forbidden-строка навсегда."""
    for day in (7, 8, 9):  # 3 дня подряд: 2026-09-07..09

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                fixed = datetime(2026, 9, day, tzinfo=timezone.utc)
                return fixed.astimezone(tz) if tz else fixed

        monkeypatch.setattr(scheduler.comms, "datetime", FixedDatetime)
        ok = await scheduler._send_once(RecordingBot(forbidden=True), db,
                                        3005, "winback2", f"d{day}", "текст")
        assert not ok

    cur = await db.execute(
        "SELECT status, error FROM deliveries WHERE tg_id=3005 AND kind='winback2' AND key='d9'")
    row = await cur.fetchone()
    assert row["status"] == "forbidden", \
        f"3-й день подряд — терминальный forbidden, получили {row['status']!r}"
    assert row["error"] == "TelegramForbiddenError"

    # Повторный вызов с тем же kind+key — никаких попыток отправки, строка не меняется.
    bot2 = RecordingBot()
    assert not await scheduler._send_once(bot2, db, 3005, "winback2", "d9", "текст")
    assert bot2.sent == [], "forbidden-строка ретраится — повтор уйдёт клиентке"


async def test_forbidden_row_not_reset_by_other_success(db, monkeypatch):
    """Успех по другому kind/key не сбрасывает счётчик чужого forbidden-пути.

    BUS-369: после 3 дней подряд статус терминален; успех соседних доставок
    не перезаписывает forbidden-строку и не снимает already_sent.
    """
    for day in (7, 8, 9):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                fixed = datetime(2026, 9, day, tzinfo=timezone.utc)
                return fixed.astimezone(tz) if tz else fixed

        monkeypatch.setattr(scheduler.comms, "datetime", FixedDatetime)
        await scheduler._send_once(RecordingBot(forbidden=True), db,
                                   3006, "winback2", f"d{day}", "текст")
    assert await comms.already_sent(db, 3006, "winback2", "d9")

    # Успешная отправка другого kind и другого key того же юзера.
    assert await scheduler._send_once(RecordingBot(), db, 3006, "reactivate", "fx", "ок")
    # Успех того же kind, но другого key.
    assert await scheduler._send_once(RecordingBot(), db, 3006, "winback2", "fy", "ок")

    cur = await db.execute(
        "SELECT status, error FROM deliveries WHERE tg_id=3006 AND kind='winback2' AND key='d9'")
    row = await cur.fetchone()
    assert row["status"] == "forbidden" and row["error"] == "TelegramForbiddenError", \
        "успех соседних доставок перезаписал forbidden-строку"


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


# ─────────────────── BUS-313 F1: reclaim зависших sending-строк ─────────────────


async def test_reclaim_stale_sending_moves_to_failed(db):
    """Крэш между claim и mark: sending старше CLAIM_TIMEOUT_S → failed.

    Следующий claim() пере-занимает failed → retry уходит (dedup не дублирует).
    """
    # Ручная вставка: имитируем крэш процесса — строка в sending без claimed_at.
    past = (datetime.now(timezone.utc)
            - timedelta(seconds=CLAIM_TIMEOUT_S + 30)).isoformat()
    await db.execute(
        "INSERT INTO deliveries(tg_id, kind, key, status, error, created_at) "
        "VALUES(:tg_id, :kind, :key, 'sending', :token, :created_at) "
        "ON CONFLICT (tg_id, kind, key) DO NOTHING",
        {"tg_id": 3101, "kind": "winback2", "key": "crash1",
         "token": "deadbeef", "created_at": past})

    reclaimed = await comms.reclaim_stale_sending(db)
    assert reclaimed == 1, f"ожидали 1 reclaim, получили {reclaimed}"

    cur = await db.execute(
        "SELECT status, error FROM deliveries "
        "WHERE tg_id=3101 AND kind='winback2' AND key='crash1'")
    row = await cur.fetchone()
    assert row["status"] == "failed", \
        f"sending не возвращён в retry: статус {row['status']!r}"
    assert row["error"] == "reclaimed"

    # Retry: claim пере-занимает failed → отправка уходит (dedup не дублирует).
    assert await comms.claim(db, 3101, "winback2", "crash1"), \
        "claim не пере-занял reclaimed-строку"
    assert not await comms.claim(db, 3101, "winback2", "crash1"), \
        "дубль claim прошёл: дедуп сломан после reclaim"


async def test_reclaim_fresh_sending_not_touched(db):
    """Sending младше CLAIM_TIMEOUT_S — живёт, следующий тик не трогает."""
    fresh = utcnow()
    await db.execute(
        "INSERT INTO deliveries(tg_id, kind, key, status, error, created_at) "
        "VALUES(:tg_id, :kind, :key, 'sending', :token, :created_at) "
        "ON CONFLICT (tg_id, kind, key) DO NOTHING",
        {"tg_id": 3102, "kind": "winback2", "key": "fresh1",
         "token": "deadbeef", "created_at": fresh})

    reclaimed = await comms.reclaim_stale_sending(db)
    assert reclaimed == 0, f"свежая строка не должна быть reclaimed: {reclaimed}"

    cur = await db.execute(
        "SELECT status FROM deliveries "
        "WHERE tg_id=3102 AND kind='winback2' AND key='fresh1'")
    assert (await cur.fetchone())["status"] == "sending", \
        "свежая sending-строка была затронута"


async def test_reclaim_does_not_touch_sent_or_forbidden(db):
    """Reclaim затронет только sending: sent и forbidden — терминальные."""
    for status in ("sent", "forbidden"):
        past = (datetime.now(timezone.utc)
                - timedelta(seconds=CLAIM_TIMEOUT_S + 60)).isoformat()
        await db.execute(
            "INSERT INTO deliveries(tg_id, kind, key, status, created_at) "
            "VALUES(:tg_id, :kind, :key, :status, :created_at) "
            "ON CONFLICT (tg_id, kind, key) DO NOTHING",
            {"tg_id": 3103, "kind": "winback2", "key": status,
             "status": status, "created_at": past})

    reclaimed = await comms.reclaim_stale_sending(db)
    assert reclaimed == 0, f"терминальные строки не должны быть reclaimed: {reclaimed}"


async def test_claim_writes_claimed_at(db):
    """BUS-313 F1: claim() пишет claimed_at — основа reclaim по времени."""
    assert await comms.claim(db, 3111, "winback2", "ck1")
    cur = await db.execute(
        "SELECT claimed_at FROM deliveries "
        "WHERE tg_id=3111 AND kind='winback2' AND key='ck1'")
    row = await cur.fetchone()
    assert row["claimed_at"] is not None, "claim не записал claimed_at"
    # Пере-claim failed-строки: claimed_at обновляется.
    await db.execute(
        "UPDATE deliveries SET status='failed' WHERE tg_id=3111 "
        "  AND kind='winback2' AND key='ck1'")
    assert await comms.claim(db, 3111, "winback2", "ck1")
    cur = await db.execute(
        "SELECT claimed_at FROM deliveries "
        "WHERE tg_id=3111 AND kind='winback2' AND key='ck1'")
    new_ts = await cur.fetchone()
    assert new_ts["claimed_at"] != row["claimed_at"], \
        "пере-claim не обновил claimed_at — reclaim будет неверным"


async def test_reclaim_without_claimed_at_uses_created_at(db):
    """Строки, занятые до BUS-313 F1 (без claimed_at): reclaim по created_at.

    Консервативный фолбэк: строка без claimed_at считается старой, если
    created_at старше cutoff — иначе мы пропустим зависшую отправку.
    """
    very_old = (datetime.now(timezone.utc)
                - timedelta(seconds=CLAIM_TIMEOUT_S + 120)).isoformat()
    await db.execute(
        "INSERT INTO deliveries(tg_id, kind, key, status, error, created_at) "
        "VALUES(:tg_id, :kind, :key, 'sending', :token, :created_at) "
        "ON CONFLICT (tg_id, kind, key) DO NOTHING",
        {"tg_id": 3112, "kind": "winback2", "key": "legacy1",
         "token": "deadbeef", "created_at": very_old})

    reclaimed = await comms.reclaim_stale_sending(db)
    assert reclaimed == 1, f"legacy-строка без claimed_at не reclaimed: {reclaimed}"
