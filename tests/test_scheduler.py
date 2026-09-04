"""Планировщик: преген утренних прогнозов (G8).

Преген — за час до рассылки по таймзоне: текст прогноза уже лежит в forecasts,
когда наступает час клиентки. Проверяем окно, идемпотентность кеша и фильтр
аудитории. LLM в тестах выключен, поэтому генерация уходит в офлайн-шаблон —
это заодно проверяет запасной путь.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.scenarios import _impl as forecast_impl
from app.repo import readings, users
from app.services import scheduler


async def _moscow_at_8(db):
    """Клиентка, у которой в выбранный момент местные 8:00."""
    await users.ensure(db, 1001, "Тестовая")
    await users.update(db, 1001, onboarded=1, tz="Europe/Moscow", sub_level="vip")
    return 1001


async def test_pregen_fills_forecast_before_push(db):
    """За час до рассылки преген кладёт текст в forecasts — к часу он готов."""
    tg_id = await _moscow_at_8(db)
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)   # 5:00 UTC = 8:00 МСК

    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 9})

    day = users.user_today(await users.get(db, tg_id))
    text = await readings.get_forecast(db, tg_id, day)
    assert text and text.startswith("🌅"), "прогноз не прегенерирован или пуст"


async def test_pregen_is_idempotent(db, monkeypatch):
    """Второй проход не генерирует заново: текст уже в кеше forecasts."""
    tg_id = await _moscow_at_8(db)
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)

    calls = []
    orig = forecast_impl.daily_forecast

    async def counting(db_, user, chart):
        calls.append(user["tg_id"])
        return await orig(db_, user, chart)

    monkeypatch.setattr(forecast_impl, "daily_forecast", counting)
    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 9})
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 9})

    assert calls.count(tg_id) == 1, "второй проход сгенерировал прогноз заново"


async def test_pregen_skips_off_audience(db):
    """Без рассылки (morning_push=0) прогноз не тратится."""
    await _moscow_at_8(db)
    await users.ensure(db, 9002, "Без рассылки")
    await users.update(db, 9002, onboarded=1, tz="Europe/Moscow",
                       sub_level="vip", morning_push=0)
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)

    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 9})

    day = users.user_today(await users.get(db, 9002))
    assert await readings.get_forecast(db, 9002, day) is None


async def test_pregen_noop_outside_window(db, monkeypatch):
    """В другие часы преген ничего не генерирует."""
    await _moscow_at_8(db)
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)

    called = []

    async def counting(db_, user):
        called.append(user["tg_id"])
        return "🌅"

    monkeypatch.setattr(forecast_impl, "daily_forecast_cached", counting)
    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    # окно прегена = 8:00 МСК, а тут morning_hour=11 → преген должен молчать
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 11})

    assert called == []


async def _bulk_users(db, base: int, count: int, *, sub_until: str | None = None):
    """Прямая вставка пачкой — быстрее, чем 6000× users.ensure."""
    ids = range(base, base + count)
    if sub_until is None:
        await db.executemany(
            "INSERT INTO users(tg_id, onboarded, status, tz) "
            "VALUES(?,1,'active','Europe/Moscow')", [(i,) for i in ids])
    else:
        await db.executemany(
            "INSERT INTO users(tg_id, onboarded, status, tz, sub_until) "
            "VALUES(?,1,'active','Europe/Moscow',?)", [(i, sub_until) for i in ids])
    await db.commit()


async def test_audience_scales_beyond_cap(db):
    """10-тысячная аудитория не режется лимитом 5000: приходит целиком."""
    await _bulk_users(db, 100_000, 6000)

    audience = await scheduler._audience(db, {"Europe/Moscow"})

    assert len(audience) == 6000, "курсорная пагинация обрезала аудиторию"
    ids = [u["tg_id"] for u in audience]
    assert ids == sorted(ids), "аудитория не упорядочена по tg_id"
    assert len(set(ids)) == 6000, "есть дубли между пачками"


async def test_expiring_audience_scales_beyond_cap(db):
    """Кандидаты на продление выбираются тоже без отсечки в 5000."""
    soon = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    await _bulk_users(db, 200_000, 6000, sub_until=soon)

    audience = await scheduler._expiring_audience(db, datetime.now(timezone.utc))

    assert len(audience) == 6000, "курсор обрезал expiring-аудиторию"
    ids = [u["tg_id"] for u in audience]
    assert ids == sorted(ids) and len(set(ids)) == 6000


async def test_pregen_caches_ru_and_en_independently(db, monkeypatch):
    """Смена языка создаёт отдельный прогноз, не подменяя уже готовую локаль."""
    tg_id = await _moscow_at_8(db)
    now = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    calls: list[str] = []

    async def localized_forecast(db_, user, chart):
        calls.append(user["lang"])
        return f"forecast-{user['lang']}"

    monkeypatch.setattr(forecast_impl, "daily_forecast", localized_forecast)
    scheduler._KNOWN_ZONES = ["Europe/Moscow"]
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 9})

    await users.update(db, tg_id, lang="en")
    await scheduler._pregen_forecasts(db, now, {"morning_hour": 9})
    day = users.user_today(await users.get(db, tg_id))

    assert await readings.get_forecast(db, tg_id, day, lang="ru") == "forecast-ru"
    assert await readings.get_forecast(db, tg_id, day, lang="en") == "forecast-en"
    assert calls == ["ru", "en"], "кэш не должен повторно собирать одну и ту же локаль"


async def test_voice_forecast_updates_only_current_language(db, monkeypatch):
    """Аудиоверсия EN-прогноза не должна перезаписывать file_id версии RU."""
    from app.core import llm
    from app.repo import billing, content

    tg_id = await _moscow_at_8(db)
    await users.update(db, tg_id, lang="en")
    user = await users.get(db, tg_id)
    day = users.user_today(user)
    await readings.save_forecast(db, tg_id, day, "ru-text", lang="ru")
    await readings.save_forecast(db, tg_id, day, "en-text", lang="en")

    async def enabled_content(*_args, **_kwargs):
        return True

    async def enabled_plan(*_args, **_kwargs):
        return {"features": ["Аудио"]}

    async def voice_bytes(*_args, **_kwargs):
        return b"ogg"

    class FakeVoice:
        file_id = "en-file-id"

    class FakeMessage:
        voice = FakeVoice()

    class FakeBot:
        async def send_voice(self, *_args, **_kwargs):
            return FakeMessage()

    monkeypatch.setattr(llm, "tts_enabled", lambda: True)
    monkeypatch.setattr(llm, "speak", voice_bytes)
    monkeypatch.setattr(content, "is_on", enabled_content)
    monkeypatch.setattr(billing, "get_plan", enabled_plan)

    await scheduler._voice_forecast(FakeBot(), db, user, "en-text", day)

    cur = await db.execute(
        "SELECT lang, audio_file_id FROM forecasts WHERE tg_id=? AND day=? ORDER BY lang",
        (tg_id, day))
    versions = {row["lang"]: row["audio_file_id"] for row in await cur.fetchall()}
    assert versions == {"en": "en-file-id", "ru": None}


async def test_scheduler_lease_allows_one_owner_across_connections(db):
    """Two bot processes sharing one PostgreSQL DB cannot both own the tick.

    `session.connect` creates a fresh engine per call — not two isolated handles
    on one DB. Здесь обе стороны читают один и тот же DATABASE_URL через отдельные
    `PostgresDatabase`, схема уже существует (её применил `db`-фикстур).
    """
    from asyncio import gather

    from app.config import settings
    from app.data.postgres import PostgresDatabase

    db_a = PostgresDatabase(settings.database_url)
    db_b = PostgresDatabase(settings.database_url)
    try:
        results = await gather(
            scheduler.acquire_scheduler_lease(
                db_a, "owner-a", now=datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
            ),
            scheduler.acquire_scheduler_lease(
                db_b, "owner-b", now=datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
            ),
        )
        assert sorted(results) == [False, True]
        status = await scheduler.scheduler_status(db_a)
        assert status["status"] == "running"
        assert status["run_count"] == 1
    finally:
        await db_a.close()
        await db_b.close()


async def test_scheduler_lease_recovers_after_expiry_and_records_failure(db):
    """A crashed owner can be replaced after the lease deadline."""
    first = datetime(2026, 8, 3, 5, 0, tzinfo=timezone.utc)
    expired = first + timedelta(seconds=scheduler.LEASE_SECONDS + 1)
    assert await scheduler.acquire_scheduler_lease(db, "owner-a", now=first)
    assert not await scheduler.acquire_scheduler_lease(db, "owner-b", now=first)
    assert await scheduler.acquire_scheduler_lease(db, "owner-b", now=expired)
    assert await scheduler.finish_scheduler_lease(
        db, "owner-b", status="error", error="fixture failure", now=expired
    )
    status = await scheduler.scheduler_status(db)
    assert status["status"] == "error"
    assert status["failure_count"] == 1
    assert status["last_error"] == "fixture failure"
