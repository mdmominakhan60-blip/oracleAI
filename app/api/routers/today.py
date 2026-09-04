"""Экран «Сегодня»: прогноз, карта дня, небо, лунная неделя."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException

from ...core import agent as agent_core
from ...core import astro
from ...services.repo_gateway import readings, users
from ...services import analytics, horoscopes
from ..deps import confirmed_age_user, active_user, get_db, rate_limit

router = APIRouter(prefix="/api", tags=["today"])


def _clean(text: str) -> str:
    """Прогноз хранится с HTML-разметкой для бота; интерфейсу нужен чистый текст."""
    return (text or "").replace("<b>", "").replace("</b>", "") \
                       .replace("<i>", "").replace("</i>", "")


@router.get("/today", dependencies=[Depends(rate_limit("llm"))])
async def today(user=Depends(active_user), db=Depends(get_db)):
    text = await agent_core.daily_forecast_cached(db, user)
    card = agent_core.card_of_day(user)
    sky = astro.today_sky()
    await analytics.track(db, analytics.E_FORECAST, user["tg_id"],
                          props={"channel": "miniapp"}, surface="miniapp")
    return {
        "forecast": _clean(text),
        "card": {"name": card["name"], "emoji": card["emoji"],
                 "meaning": card["meaning"], "num": card.get("num"),
                 "img": card.get("img")},
        "moon": sky["moon"],
        "sun_season": sky["sun_season"],
        "sphere": agent_core.daily_sphere(user),
        "day": users.user_today(user),
        "next_action": await _next_action(db, user),
    }


async def _next_action(db, user) -> dict:
    """Возвращает один локализованный следующий шаг для домашнего экрана."""
    lang = user["lang"] if user["lang"] in ("ru", "en") else "ru"
    copy = {
        "ru": {
            "chart": ("Собери натальную карту", "Планеты, дома и предназначение — по дате и времени рождения.", "Собрать карту ✨"),
            "compat": ("Проверь совместимость с партнёром", "Спидометр любви — балл и разбор пары по картам.", "Проверить 💞"),
            "spread": ("Расклад на твой вопрос", "Задай вопрос картам — колода Райдера-Уэйта ляжет в расклад.", "Вытянуть карты 🎴"),
            "tomorrow": ("Вернись завтра за картой дня", "Сегодня достаточно наблюдений. Завтра — новый прогноз и новая карта.", "Завтра снова ✨"),
        },
        "en": {
            "chart": ("Create your birth chart", "Planets, houses and themes based on your birth date and time.", "Create chart ✨"),
            "compat": ("Explore compatibility", "A connection score and an insightful reading for the two of you.", "Explore 💞"),
            "spread": ("A reading for your question", "Ask the cards a question and let the Rider–Waite deck reveal a spread.", "Draw cards 🎴"),
            "tomorrow": ("Return tomorrow for your card", "Today is complete. Tomorrow brings a fresh forecast and a new card.", "See you tomorrow ✨"),
        },
    }[lang]
    chart = users.chart_of(user)
    partners = await readings.list_partners(db, user["tg_id"])
    readings_done = bool(await readings.recent_readings(db, user["tg_id"], limit=1))
    if not chart:
        title, text, cta = copy["chart"]
        return {"kind": "chart", "emoji": "🌌", "title": title, "text": text,
                "cta": cta, "chat": "astro", "fn": "featureChart"}
    if not partners:
        title, text, cta = copy["compat"]
        return {"kind": "compat", "emoji": "💞", "title": title, "text": text,
                "cta": cta, "chat": "astro", "fn": "featureCompat"}
    if not readings_done:
        title, text, cta = copy["spread"]
        return {"kind": "spread", "emoji": "🎴", "title": title, "text": text,
                "cta": cta, "chat": "tarot", "fn": "featureTarot"}
    title, text, cta = copy["tomorrow"]
    return {"kind": "tomorrow", "emoji": "🌙", "title": title, "text": text,
            "cta": cta, "chat": "", "fn": ""}


@router.get("/moon/week")
async def moon_week(user=Depends(confirmed_age_user), days: int = 7):
    """Лунная лента: считаем на сервере, чтобы бот и приложение совпадали."""
    today_date = date.today()
    out = []
    for i in range(max(1, min(days, 30))):
        d = today_date + timedelta(days=i)
        phase = astro.moon_phase(d)
        out.append({"date": d.isoformat(), "weekday": d.weekday(),
                    "day_num": d.day, **phase})
    return out


@router.get("/sky")
async def sky(user=Depends(confirmed_age_user)):
    return astro.today_sky()


@router.get("/horoscope", dependencies=[Depends(rate_limit("read"))])
async def horoscope(sign: str | None = None, user=Depends(confirmed_age_user),
                    db=Depends(get_db)):
    """Гороскоп по знаку. Без параметра — по её знаку Солнца.

    Общий по знаку, в отличие от `/api/today`: он один на всех и потому
    бесплатен даже без подписки — это витрина, ведущая к персональному.
    """
    chart = users.chart_of(user)
    sign = sign or (chart.get("sun") or {}).get("sign")
    if not sign:
        from ...core.astro import sun_sign
        if not user["birth_date"]:
            raise HTTPException(400, "нет даты рождения")
        sign = sun_sign(date.fromisoformat(user["birth_date"]))[0]
    if sign not in horoscopes.SIGNS:
        raise HTTPException(404, "неизвестный знак")
    return {
        "sign": sign,
        "symbol": horoscopes.SIGN_SYMBOL[sign],
        "element": horoscopes.SIGN_ELEMENT[sign],
        "day": date.today().isoformat(),
        "text": await horoscopes.get_or_build(db, sign),
    }


@router.get("/horoscope/all", dependencies=[Depends(rate_limit("read"))])
async def horoscope_all(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Все двенадцать знаков на сегодня — витрина «а что у других»."""
    return await horoscopes.all_for_day(db)
