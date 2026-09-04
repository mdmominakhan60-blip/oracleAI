"""Гороскопы по знакам, память по смыслу, карточки и вебхук web-оплаты.

Всё это — механики роста и монетизации: канал трафика, крючок удержания,
виральность и основной чек мимо комиссии Stars.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app.api.routers.webhooks import _already_seen, verify_paddle
from app.core import cards, memory, tarot
from app.core.scenarios import _impl as forecast_impl
from app.services import horoscopes


# ──────────────────────────── гороскопы по знакам ─────────────────────────────

def test_twelve_signs_with_codes():
    assert len(horoscopes.SIGNS) == 12
    assert len(horoscopes.SIGN_CODE) == 12
    assert set(horoscopes.SIGN_CODE) == set(horoscopes.SIGNS)


async def test_horoscope_is_cached(db):
    """Двенадцать текстов в сутки на весь сервис, а не по тексту на клиентку."""
    first = await horoscopes.get_or_build(db, "Овен")
    second = await horoscopes.get_or_build(db, "Овен")
    assert first == second, "гороскоп сгенерировался дважды — платим два раза"
    assert len(first) > 60


async def test_horoscope_builds_once_under_concurrency(db, monkeypatch):
    """Утренний пик: пять одновременных запросов одного знака — одна генерация.

    Замок на (день, знак) + атомарная проверка кеша после захвата (G17): первый
    билдит, остальные ждут и читают уже готовое.
    """
    import asyncio

    calls = []

    async def fake_generate(db_, sign, day):
        calls.append(sign)
        await asyncio.sleep(0.02)     # даём остальным пройти проверку кеша до замка
        return "Гороскоп на сегодня"

    monkeypatch.setattr(horoscopes, "_generate", fake_generate)
    results = await asyncio.gather(
        *[horoscopes.get_or_build(db, "Лев") for _ in range(5)])

    assert calls == ["Лев"], f"генераций {len(calls)}, а должна быть одна"
    assert all(r == "Гороскоп на сегодня" for r in results)


@pytest.mark.parametrize(
    ("sign", "expected"),
    [
        ("Овен", "Овна"), ("Телец", "Тельца"), ("Близнецы", "Близнецов"),
        ("Рак", "Рака"), ("Лев", "Льва"), ("Дева", "Девы"),
        ("Весы", "Весов"), ("Скорпион", "Скорпиона"),
        ("Стрелец", "Стрельца"), ("Козерог", "Козерога"),
        ("Водолей", "Водолея"), ("Рыбы", "Рыб"),
    ],
)
def test_offline_daily_forecast_uses_correct_ru_sign_case(sign, expected):
    from app.core import agent as agent_core, astro

    user = {"name": "", "tg_id": 91000, "tz": "UTC", "lang": "ru"}
    chart = {"sun": {"sign": sign}}
    text = agent_core._forecast_offline(user, chart, astro.today_sky())
    assert f"Сегодня для {expected} —" in text


async def test_daily_forecast_builds_once_under_concurrency(db, user, monkeypatch):
    """Mini App и бот в одно утро: пять параллельных запросов — одна генерация
    (G17, атомарная проверка кеша в daily_forecast_cached)."""
    import asyncio

    from app.core import agent as agent_core

    calls = []

    async def fake_forecast(db_, user_, chart):
        calls.append(user_["tg_id"])
        await asyncio.sleep(0.02)
        return "🌅 Прогноз на сегодня"

    monkeypatch.setattr(forecast_impl, "daily_forecast", fake_forecast)
    results = await asyncio.gather(
        *[agent_core.daily_forecast_cached(db, user) for _ in range(5)])

    assert calls == [user["tg_id"]], f"генераций {len(calls)}, а должна быть одна"
    assert all(r == "🌅 Прогноз на сегодня" for r in results)


async def test_build_day_fills_all_signs(db):
    result = await horoscopes.build_day(db)
    assert result["built"] == 12
    again = await horoscopes.build_day(db)
    assert again["built"] == 0, "повторная сборка перегенерировала всё"

    items = await horoscopes.all_for_day(db)
    assert len(items) == 12
    assert all(i["text"] for i in items)
    assert all(i["posted_at"] is None for i in items), "ничего не публиковали"


async def test_build_day_does_not_overwrite_existing(db, monkeypatch):
    """Готовый гороскоп (ручная правка / гонка процессов) сборка не затирает (G26)."""
    day = horoscopes.date.today().isoformat()
    await horoscopes.save(db, "Лев", day, "Ручной текст админа")

    calls = []

    async def fake_generate(db_, sign, day_):
        calls.append(sign)
        return "сгенерировано заново"

    monkeypatch.setattr(horoscopes, "_generate", fake_generate)
    result = await horoscopes.build_day(db, day)
    assert "Лев" not in calls, "сборка перегенерировала готовый знак"
    assert result["built"] == 11
    assert await horoscopes.get(db, "Лев", day) == "Ручной текст админа"


async def test_offline_horoscope_is_stable(db):
    """Один и тот же день и знак — один и тот же текст после перезапуска."""
    from app.core import astro
    sky = astro.today_sky()
    a = horoscopes._offline("Лев", "2026-07-26", sky)
    b = horoscopes._offline("Лев", "2026-07-26", sky)
    assert a == b


def test_channel_map_parses_env(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "horoscope_channels",
                        "aries:@ora_aries, taurus:@ora_taurus, мусор", False)
    mapping = horoscopes.channel_map()
    assert mapping == {"Овен": "@ora_aries", "Телец": "@ora_taurus"}


# ────────────────────────────── память по смыслу ──────────────────────────────

def test_vector_survives_roundtrip():
    vector = [0.5, -0.25, 0.125, 1.0]
    restored = memory.unpack(memory.pack(vector))
    assert len(restored) == len(vector)
    assert all(abs(a - b) < 1e-6 for a, b in zip(vector, restored))


def test_cosine_bounds():
    assert memory.cosine([1, 0], [1, 0]) == pytest.approx(1.0, abs=1e-6)
    assert memory.cosine([1, 0], [0, 1]) == pytest.approx(0.0, abs=1e-6)
    assert memory.cosine([], [1, 0]) == 0.0
    assert memory.cosine([1, 0, 0], [1, 0]) == 0.0, "разная длина — не сравниваем"


def test_unpack_handles_garbage():
    assert memory.unpack(None) == []
    assert memory.unpack(b"\x01") == []


async def test_remember_deduplicates_exact(db, user):
    assert await memory.remember(db, user["tg_id"], "Работает дизайнером")
    assert not await memory.remember(db, user["tg_id"], "работает дизайнером  ")
    cur = await db.execute("SELECT COUNT(*) c, MAX(weight) w FROM memories "
                           "WHERE tg_id=?", (user["tg_id"],))
    row = await cur.fetchone()
    assert row["c"] == 1, "дубликат попал в память"
    assert row["w"] == 2, "вес повтора не вырос"


async def test_remember_rejects_noise(db, user):
    assert not await memory.remember(db, user["tg_id"], "ок")
    assert not await memory.remember(db, user["tg_id"], "  ")


async def test_recall_returns_anchors_without_query(db, user):
    for fact in ("Её парня зовут Дима", "Работает в найме", "Боится летать"):
        await memory.remember(db, user["tg_id"], fact)
    recalled = await memory.recall(db, user["tg_id"], "", limit=10)
    assert len(recalled) == 3


async def test_recall_prefers_relevant(db, user):
    """Без эмбеддингов работает поиск по словам — но релевантное всё равно всплывает."""
    await memory.remember(db, user["tg_id"], "Её парня зовут Дима")
    await memory.remember(db, user["tg_id"], "Хочет сменить работу на удалённую")
    recalled = await memory.recall(db, user["tg_id"], "что там с работой", limit=2)
    assert any("работ" in fact.lower() for fact in recalled)


async def test_remember_many_batches_embeddings(db, user, monkeypatch):
    """Бач-запись: один эмбеддинг-запрос на все факты, а не по одному (G23)."""
    calls: list[int] = []

    async def fake_embed(texts):
        calls.append(len(texts))
        return None              # офлайн: без векторов, дедупликация по словам

    monkeypatch.setattr(memory, "embed", fake_embed)
    saved = await memory.remember_many(
        db, user["tg_id"], ["Любит кофе", "Её парня зовут Дима", "Боится летать"])
    assert saved == 3
    assert calls == [3], "эмбеддинги не сгруппированы в один запрос"


async def test_remember_many_deduplicates(db, user):
    await memory.remember(db, user["tg_id"], "Любит кофе")
    assert await memory.remember_many(
        db, user["tg_id"], ["Любит кофе", "Её парня зовут Дима"]) == 1
    cur = await db.execute("SELECT COUNT(*) c FROM memories WHERE tg_id=?",
                           (user["tg_id"],))
    assert (await cur.fetchone())["c"] == 2, "повтор попал в память"


async def test_summary_absent_until_enough_facts(db, user):
    assert await memory.get_summary(db, user["tg_id"]) == ""
    assert not await memory.needs_summary(db, user["tg_id"])


# ──────────────────────────── карточки для сторис ─────────────────────────────

@pytest.mark.skipif(not cards.available(), reason="Pillow не установлен")
def test_reading_card_is_png():
    png = cards.reading_card("Прошлое · Настоящее · Будущее", tarot.draw(3),
                             ["Прошлое", "Настоящее", "Будущее"],
                             name="Аня", bot_username="oracle_bot", seed=7)
    assert png and png.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(png) > 10_000, "картинка подозрительно пустая"


@pytest.mark.skipif(not cards.available(), reason="Pillow не установлен")
def test_forecast_card_is_png():
    png = cards.forecast_card("Сегодня день тихой силы.\nНе торопи события.",
                              sign="Лев", symbol="♌", card_name="Звезда",
                              name="Аня", bot_username="oracle_bot")
    assert png and png.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.skipif(not cards.available(), reason="Pillow не установлен")
def test_card_without_cards_returns_none():
    assert cards.reading_card("Пусто", [], []) is None
    assert cards.forecast_card("") is None


# ──────────────────────────── вебхук web-оплаты ───────────────────────────────

SECRET = "whsec_test"


def _signed(body: bytes, *, secret: str = SECRET, age: int = 0) -> str:
    ts = str(int(time.time()) - age)
    digest = hmac.new(secret.encode(), f"{ts}:".encode() + body,
                      hashlib.sha256).hexdigest()
    return f"ts={ts};h1={digest}"


def test_valid_signature_accepted():
    body = json.dumps({"event_id": "evt_1"}).encode()
    assert verify_paddle(body, _signed(body), SECRET)


def test_tampered_body_rejected():
    body = json.dumps({"event_id": "evt_1"}).encode()
    header = _signed(body)
    assert not verify_paddle(b'{"event_id":"evt_hacked"}', header, SECRET)


def test_wrong_secret_rejected():
    body = b"{}"
    assert not verify_paddle(body, _signed(body), "whsec_other")


def test_old_signature_rejected():
    """Подпись бессрочна сама по себе — перехваченный запрос иначе работал бы вечно."""
    body = b"{}"
    assert not verify_paddle(body, _signed(body, age=3600), SECRET)


def test_malformed_header_rejected():
    assert not verify_paddle(b"{}", "", SECRET)
    assert not verify_paddle(b"{}", "мусор", SECRET)
    assert not verify_paddle(b"{}", "ts=abc;h1=def", SECRET)


def test_no_secret_rejects_everything():
    body = b"{}"
    assert not verify_paddle(body, _signed(body), "")


async def test_webhook_event_is_processed_once(db):
    """Повтор доставки не должен выдавать подписку второй раз."""
    assert not await _already_seen(db, "evt_42", "paddle", "test", "{}")
    assert await _already_seen(db, "evt_42", "paddle", "test", "{}")


async def test_daily_forecast_separates_languages_under_concurrency(db, user, monkeypatch):
    """Одна учётная запись может параллельно открыть RU и EN без смешивания кэша."""
    import asyncio

    from app.core import agent as agent_core
    from app.repo import readings, users

    await users.update(db, user["tg_id"], lang="ru")
    ru_user = await users.get(db, user["tg_id"])
    await users.update(db, user["tg_id"], lang="en")
    en_user = await users.get(db, user["tg_id"])
    calls: list[str] = []

    async def fake_forecast(db_, user_, chart):
        calls.append(user_["lang"])
        await asyncio.sleep(0.02)
        return f"🌅 forecast-{user_['lang']}"

    monkeypatch.setattr(forecast_impl, "daily_forecast", fake_forecast)
    results = await asyncio.gather(
        *[agent_core.daily_forecast_cached(db, ru_user) for _ in range(5)],
        *[agent_core.daily_forecast_cached(db, en_user) for _ in range(5)])

    day = users.user_today(ru_user)
    assert calls.count("ru") == 1 and calls.count("en") == 1
    assert results.count("🌅 forecast-ru") == 5
    assert results.count("🌅 forecast-en") == 5
    assert await readings.get_forecast(db, user["tg_id"], day, lang="ru") == "🌅 forecast-ru"
    assert await readings.get_forecast(db, user["tg_id"], day, lang="en") == "🌅 forecast-en"


def test_signature_rotation_accepts_any_h1():
    body = b'{"event_id":"evt_rotation"}'
    valid = _signed(body).split(";", 1)[1].split("=", 1)[1]
    ts = str(int(time.time()))
    assert verify_paddle(
        body, f"ts={ts};h1=deadbeef;h1={valid}", SECRET)


# ───────────────────── dashboard referral aggregation regression ───────────────

async def test_top_referrers_returns_grouped_user_fields(db):
    from app.repo import growth, users

    await users.ensure(db, 2001, "Реферер", "referrer")
    await users.ensure(db, 2002, "Приглашённая", "invitee")
    await users.ensure(db, 2003, "Ещё одна", "invitee2")

    assert await growth.record_referral(db, 2001, 2002)
    assert await growth.record_referral(db, 2001, 2003)

    rows = await growth.top_referrers(db)

    assert rows[0]["tg_id"] == 2001
    assert rows[0]["name"] == "Реферер"
    assert rows[0]["username"] == "referrer"
    assert rows[0]["invited"] == 2
    assert rows[0]["bonus"] == 0


async def test_top_referrers_keeps_referrers_with_missing_profile(db):
    from app.repo import growth, users

    await users.ensure(db, 2004, "Known")
    assert await growth.record_referral(db, 2004, 2005)

    rows = await growth.top_referrers(db)

    assert rows[0]["tg_id"] == 2004
    assert rows[0]["name"] == "Known"
    assert rows[0]["username"] is None
    assert rows[0]["invited"] == 1
