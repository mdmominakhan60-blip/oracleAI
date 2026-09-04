"""Ежедневные гороскопы по 12 знакам и каналы-спутники.

Зачем это в продукте. Общий гороскоп по знаку — не главная ценность (главная —
персональный прогноз к её карте), но это единственный бесплатный канал трафика,
доступный без бюджета: двенадцать телеграм-каналов, по одному на знак, каждый
день по посту, в конце поста — ссылка в бота. Так устроена воронка из бизнес-плана.

Экономика: двенадцать текстов в сутки на весь сервис, а не по тексту на клиентку.
Поэтому генерируем один раз, кладём в `horoscopes` и раздаём всем — и в канал, и
в бота, и в Mini App. Без кеша это была бы генерация на каждый показ.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date

from ..core import astro, llm
from ..core.stable import stable_seed
from ..data.session import transaction, utcnow
from ..repo import content

log = logging.getLogger("oracle.horoscopes")

SIGNS = [name for name, _, _ in astro.SIGNS]
SIGN_SYMBOL = {name: symbol for name, symbol, _ in astro.SIGNS}
SIGN_ELEMENT = {name: element for name, _, element in astro.SIGNS}

#: Латинские коды — для имён каналов и ссылок (`HOROSCOPE_CHANNELS`).
SIGN_CODE = {
    "Овен": "aries", "Телец": "taurus", "Близнецы": "gemini", "Рак": "cancer",
    "Лев": "leo", "Дева": "virgo", "Весы": "libra", "Скорпион": "scorpio",
    "Стрелец": "sagittarius", "Козерог": "capricorn", "Водолей": "aquarius",
    "Рыбы": "pisces",
}

MAX_LEN = 700

#: Single-flight на билд одного (день, знак): утром весь сегмент приходит разом,
#: и без замка каждая клиентка генерировала бы «свой» текст гороскопа.
_build_locks: dict[tuple[str, str], asyncio.Lock] = {}
_BUILD_LOCKS_MAX = 512


def _lock_for(sign: str, day: str) -> asyncio.Lock:
    key = (sign, day)
    lock = _build_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        if len(_build_locks) >= _BUILD_LOCKS_MAX:
            _build_locks.clear()
        _build_locks[key] = lock
    return lock


# ──────────────────────────────── чтение ──────────────────────────────────────

async def get(db, sign: str, day: str | None = None) -> str | None:
    day = day or date.today().isoformat()
    cur = await db.execute(
        "SELECT text FROM horoscopes WHERE day=:day AND sign=:sign",
        {"day": day, "sign": sign})
    row = await cur.fetchone()
    return row["text"] if row else None


async def get_or_build(db, sign: str, day: str | None = None) -> str:
    """Гороскоп знака на день. Если его ещё нет — собираем и сохраняем.

    Защита от лишней генерации двойная: лок в процессе (второй запрос достаёт
    готовый текст после первого) и атомарный INSERT OR IGNORE на случай, когда
    параллельно строит другой процесс (бот и API) — проигравший перечитывает
    чужой результат, а не пишет поверх.
    """
    day = day or date.today().isoformat()
    cached = await get(db, sign, day)
    if cached:
        return cached
    async with _lock_for(sign, day):
        # пока ждали замок, другой запрос мог уже сгенерировать и сохранить
        cached = await get(db, sign, day)
        if cached:
            return cached
        text = await _generate(db, sign, day)
        if not await _save_if_absent(db, sign, day, text):
            return await get(db, sign, day) or text
        return text


async def _save_if_absent(db, sign: str, day: str, text: str) -> bool:
    """True — сохранили мы; False — параллельный процесс успел раньше."""
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO horoscopes(day, sign, text, posted_at, created_at) "
            "VALUES(:day, :sign, :text, NULL, :created_at) "
            "ON CONFLICT (day, sign) DO NOTHING",
            {"day": day, "sign": sign, "text": text, "created_at": utcnow()})
        return bool(cur.rowcount)


async def all_for_day(db, day: str | None = None) -> list[dict]:
    day = day or date.today().isoformat()
    cur = await db.execute(
        "SELECT sign, text, posted_at FROM horoscopes WHERE day=:day", {"day": day})
    have = {r["sign"]: dict(r) for r in await cur.fetchall()}
    return [{"sign": s, "symbol": SIGN_SYMBOL[s], "element": SIGN_ELEMENT[s],
             "code": SIGN_CODE[s], "text": have.get(s, {}).get("text"),
             "posted_at": have.get(s, {}).get("posted_at")}
            for s in SIGNS]


async def save(db, sign: str, day: str, text: str) -> None:
    async with transaction(db):
        await db.execute(
            "INSERT INTO horoscopes(day, sign, text, posted_at, created_at) "
            "VALUES(:day, :sign, :text, "
            "(SELECT posted_at FROM horoscopes WHERE day=:day2 AND sign=:sign2), "
            ":created_at) "
            "ON CONFLICT(day, sign) DO UPDATE SET text=excluded.text, "
            "created_at=excluded.created_at",
            {"day": day, "sign": sign, "text": text, "day2": day, "sign2": sign,
             "created_at": utcnow()})


# ─────────────────────────────── генерация ────────────────────────────────────

async def _generate(db, sign: str, day: str) -> str:
    sky = astro.today_sky(date.fromisoformat(day))
    element = SIGN_ELEMENT[sign]
    if llm.enabled():
        try:
            system = (
                "Ты — астролог женского телеграм-канала. Пишешь короткий дневной "
                "гороскоп: тепло, конкретно, без страшилок и без воды. "
                "Никаких обещаний денег, свадеб и болезней — только настроение "
                "дня, одна сфера внимания и один выполнимый совет.")
            user_msg = (
                f"Дата: {day}. Знак: {sign} (стихия {element}).\n"
                f"Небо: Луна {sky['moon']['name']} ({sky['moon']['advice']}), "
                f"лунный день ~{sky['moon']['day']}, Солнце в "
                f"{sky['sun_season']['sign']}.\n\n"
                f"Напиши гороскоп для {sign} на этот день: 3-4 коротких абзаца, "
                f"начни с {SIGN_SYMBOL[sign]} и названия знака, закончи одной "
                f"строкой «Совет дня: …». Обращайся на «ты», как к женщине.")
            text = await llm.complete(system, user_msg, tier="lite",
                                      max_tokens=420, purpose="horoscope", db=db)
            text = (text or "").strip()
            if len(text) >= 120:
                return text[:MAX_LEN * 2]
        except Exception as e:  # noqa: BLE001
            log.warning("гороскоп для %s ушёл в офлайн: %s", sign, e)
    return _offline(sign, day, sky)


_MOODS = ["день ясности", "день тихой силы", "день знаков", "день выбора",
          "день отдачи", "день покоя", "день движения"]
_FOCUS = {
    "огонь": "Твоя стихия просит действия — начни с того, что откладывала.",
    "земля": "Твоя стихия просит опоры — сделай один практический шаг.",
    "воздух": "Твоя стихия просит слов — скажи то, что держишь в себе.",
    "вода": "Твоя стихия просит чувств — доверься первому ощущению.",
}


def _offline(sign: str, day: str, sky: dict) -> str:
    """Гороскоп без модели: реальная фаза Луны + устойчивый тон дня.

    Сид детерминирован датой и знаком: канал не должен показывать разный текст
    при каждом перезапуске процесса.
    """
    rnd_index = stable_seed(day, sign) % len(_MOODS)
    moon = sky["moon"]
    element = SIGN_ELEMENT[sign]
    return (
        f"{SIGN_SYMBOL[sign]} <b>{sign}</b> — {_MOODS[rnd_index]}.\n\n"
        f"{moon['emoji']} Луна: {moon['name']}. {moon['advice'].capitalize()}.\n\n"
        f"{_FOCUS.get(element, 'Слушай себя — ответ уже внутри.')}\n\n"
        f"Совет дня: не спорь с тем, что не в твоей власти, и займись тем, что в ней. ✨"
    )


async def build_day(db, day: str | None = None) -> dict:
    """Собирает все двенадцать гороскопов на день. Идемпотентно.

    Пишем через атомарный `_save_if_absent`, а не `save()`: у ночной сборки нет
    права перезаписать уже лежащий текст — гонка двух процессов (бот и API) не
    должна стоить двух генераций и затирания (G26).
    """
    day = day or date.today().isoformat()
    built = 0
    for sign in SIGNS:
        if await get(db, sign, day):
            continue
        if await _save_if_absent(db, sign, day, await _generate(db, sign, day)):
            built += 1
    if built:
        log.info("гороскопы на %s: собрано %d знаков", day, built)
    return {"day": day, "built": built, "total": len(SIGNS)}


# ─────────────────────────── каналы-спутники ──────────────────────────────────

def channel_map() -> dict[str, str]:
    """`HOROSCOPE_CHANNELS=aries:@ch_aries,taurus:@ch_taurus` → {знак: канал}."""
    from ..config import settings

    out: dict[str, str] = {}
    raw = settings.horoscope_channels or ""
    for chunk in raw.split(","):
        if ":" not in chunk:
            continue
        code, channel = (part.strip() for part in chunk.split(":", 1))
        sign = next((s for s, c in SIGN_CODE.items() if c == code.lower()), None)
        if sign and channel:
            out[sign] = channel
    return out


def _post_text(sign: str, text: str, bot_username: str) -> str:
    """Пост в канал = гороскоп + приглашение в бота. Канал существует ради этого."""
    link = f"https://t.me/{bot_username}?start=horo_{SIGN_CODE[sign]}" \
        if bot_username else ""
    tail = (f"\n\n🔮 <a href=\"{link}\">Личный прогноз по твоей натальной карте</a> — "
            f"не общий по знаку, а именно про тебя.") if link else ""
    return f"{text}{tail}"


async def post_day(bot, db, day: str | None = None) -> dict:
    """Публикует гороскопы дня в каналы-спутники. Повторно — не публикует."""
    day = day or date.today().isoformat()
    channels = channel_map()
    if not channels:
        return {"posted": 0, "skipped": "каналы не настроены"}
    if not await content.is_on(db, "horoscope_channels", default=False):
        return {"posted": 0, "skipped": "автопостинг выключен"}

    bot_username = await content.get_setting(db, "brand.bot_username", "") or ""
    posted = 0
    for sign, channel in channels.items():
        cur = await db.execute(
            "SELECT text, posted_at FROM horoscopes WHERE day=:day AND sign=:sign",
            {"day": day, "sign": sign})
        row = await cur.fetchone()
        if not row or not row["text"] or row["posted_at"]:
            continue
        try:
            await bot.send_message(channel,
                                   _post_text(sign, row["text"], bot_username))
        except Exception as e:  # noqa: BLE001
            # чаще всего это «бот не админ канала» — пост попробуем завтра
            log.warning("пост в %s не отправлен: %s", channel, e)
            continue
        async with transaction(db):
            await db.execute(
                "UPDATE horoscopes SET posted_at=:posted_at WHERE day=:day AND sign=:sign",
                {"posted_at": utcnow(), "day": day, "sign": sign})
        posted += 1
    if posted:
        log.info("гороскопы на %s: опубликовано %d постов", day, posted)
    return {"posted": posted, "channels": len(channels)}
