"""Картинки для сторис: расклад и прогноз дня.

Отдаём PNG прямо из API — в Mini App его достаточно открыть или сохранить.
Отдельный роутер, потому что это единственные ответы сервиса, которые не JSON.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response

from ...core import agent as agent_core
from ...core import astro, cards, tool_registry as skills
from ...services.repo_gateway import content, readings, users
from ...services import analytics, catalog
from ..common.validation import parse_birth_date
from ..deps import confirmed_age_user, get_db, rate_limit

log = logging.getLogger("oracle.api.share")

router = APIRouter(prefix="/api/share", tags=["share"])

PNG_HEADERS = {"Cache-Control": "private, max-age=3600"}


def _png(data: bytes | None, filename: str) -> Response:
    if not data:
        # Pillow не установлен или отрисовка не удалась — шеринг остаётся
        # текстовым, поэтому 503, а не 500: это временная недоступность фичи
        raise HTTPException(503, "картинка сейчас недоступна — поделись ссылкой 🌙")
    return Response(content=data, media_type="image/png",
                    headers={**PNG_HEADERS,
                             "Content-Disposition": f'inline; filename="{filename}"'})


async def _bot_username(db) -> str:
    return await content.get_setting(db, "brand.bot_username", "") or ""


@router.get("/reading/{reading_id}.png",
            dependencies=[Depends(rate_limit("write"))])
async def reading_png(reading_id: int, user=Depends(confirmed_age_user),
                      db=Depends(get_db)):
    """Карточка расклада. Доступна только владелице расклада."""
    row = await readings.get_reading(db, reading_id, user["tg_id"])
    if not row:
        raise HTTPException(404, "расклад не найден")
    try:
        drawn = json.loads(row["cards_json"] or "[]")
    except ValueError:
        drawn = []
    if not drawn:
        raise HTTPException(404, "в раскладе нет карт")

    spread = await catalog.get_spread(db, row["spread"] or "")
    # Отрисовка PNG — тяжёлая работа Pillow: держать событийный цикл, пока она
    # идёт, значит стопорить все остальные запросы API. Рендер уходит в поток.
    image = await asyncio.to_thread(
        cards.reading_card, spread["title"], drawn, spread["positions"],
        name=user["name"] or "", bot_username=await _bot_username(db),
        seed=reading_id)
    await analytics.track(db, "share_card", user["tg_id"],
                          props={"kind": "reading"}, surface="miniapp")
    return _png(image, f"oracle-reading-{reading_id}.png")


@router.get("/today.png", dependencies=[Depends(rate_limit("write"))])
async def today_png(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Карточка прогноза дня — то, что чаще всего уходит в сторис."""
    chart = users.chart_of(user)
    sun = chart.get("sun") or {}
    text = await agent_core.daily_forecast_cached(db, user, chart)
    card = agent_core.card_of_day(user)
    image = await asyncio.to_thread(
        cards.forecast_card, text, sign=sun.get("sign", ""),
        symbol=sun.get("symbol", ""), card_name=card["name"],
        name=user["name"] or "", bot_username=await _bot_username(db),
        day=users.user_today(user))
    await analytics.track(db, "share_card", user["tg_id"],
                          props={"kind": "today"}, surface="miniapp")
    return _png(image, "oracle-today.png")


@router.get("/compat.png", dependencies=[Depends(rate_limit("write"))])
async def compat_png(partner_date: str, partner_name: str = "", relation: str = "love",
                     user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Открытка совместимости: два знака, кольцо-шкала, вердикт, сферы.

    Балл считается ровно той же формулой, что в /api/compat, — иначе открытка и
    виджет спидометра показывали бы разные числа. LLM не зовём: данные пары уже
    посчитаны, рендер чисто по датам рождения.
    """
    if not user["birth_date"]:
        raise HTTPException(400, "нет даты рождения — заполни её в боте")
    pdate = parse_birth_date(partner_date)
    aspects = await skills.pair_aspects(db, user, pdate)
    data = skills.compatibility_score(user["birth_date"], pdate,
                                      relation=relation, aspects=aspects)
    symbol = {name: s for name, s, _ in astro.SIGNS}
    image = await asyncio.to_thread(
        cards.compat_card,
        you={"sign": data["you"]["sign"], "symbol": symbol.get(data["you"]["sign"], ""),
             "name": user["name"] or ""},
        partner={"sign": data["partner"]["sign"],
                 "symbol": symbol.get(data["partner"]["sign"], ""),
                 "name": partner_name.strip()[:30]},
        total=data["total"], verdict=data["verdict"], spheres=data["spheres"],
        relation=skills.relation_label(relation),
        bot_username=await _bot_username(db))
    await analytics.track(db, "share_card", user["tg_id"],
                          props={"kind": "compat"}, surface="miniapp")
    return _png(image, "oracle-compat.png")


@router.get("/enabled")
async def enabled(db=Depends(get_db)):
    """Есть ли чем рисовать — интерфейс прячет кнопку, если нет."""
    return {"cards": cards.available(),
            "flag": await content.is_on(db, "share_cards", default=True)}
