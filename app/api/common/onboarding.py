"""Validated Mini App onboarding; no writes until all inputs and chart succeed."""
from __future__ import annotations

import json
import re
from datetime import date

from fastapi import HTTPException

from ...core import astro, geo
from .validation import parse_birth_date


def normalize_birth_time(value: str | None, precision: str) -> tuple[str | None, bool]:
    if precision == "unknown":
        return None, False
    raw = (value or "").strip()
    if precision not in {"exact", "approx"} or not re.fullmatch(r"\d{1,2}:\d{2}", raw):
        raise HTTPException(400, "Укажи часы и минуты или выбери «Не знаю время».")
    hour, minute = map(int, raw.split(":"))
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise HTTPException(400, "Часы должны быть от 0 до 23, минуты — от 0 до 59.")
    return f"{hour:02d}:{minute:02d}", precision == "exact"


async def onboarding_fields(item, user, db) -> dict:
    """Return an atomic update for explicit completion, never infer completion.

    The selected city is a server-known suggestion key, not client coordinates.
    Existing identity, subscriptions, persona and notification preferences stay intact.
    """
    if not item.onboarding_complete:
        return {}
    required = {"name", "birth_date", "birth_time_precision", "city", "intent"}
    if not required.issubset(item.model_fields_set):
        raise HTTPException(400, "Проверь имя, дату, время и город перед сохранением.")
    name = (item.name or "").strip()
    if not 2 <= len(name) <= 60:
        raise HTTPException(400, "Имя должно содержать от 2 до 60 символов.")
    birth_date = parse_birth_date(item.birth_date)
    if not date(1900, 1, 1) <= date.fromisoformat(birth_date) <= date.today():
        raise HTTPException(400, "Укажи дату рождения с 1900 года, не позднее сегодняшнего дня.")
    precision = item.birth_time_precision
    stored_time, known = normalize_birth_time(item.birth_time, precision)
    city_key = geo.normalize(item.city)
    # Deliberately exact: geo's legacy fuzzy fallback may match a different city.
    coordinates = geo.FALLBACK.get(city_key)
    if not coordinates:
        raise HTTPException(400, "Выбери город из предложенных подсказок.")
    if item.intent not in {"oracle", "astro", "tarot", "chiromant"}:
        raise HTTPException(400, "Выбери направление знакомства.")
    lat, lon, tz = coordinates
    chart = await astro.compute_chart_async(
        birth_date, stored_time or "12:00", city_key.title(), lat, lon, tz,
        time_known=known, coordinate_source="builtin",
        coordinate_confidence=0.8, timezone_source="builtin",
    )
    chart["time_precision"] = precision
    return {
        "name": name, "birth_date": birth_date,
        "birth_time": stored_time, "birth_time_known": int(known),
        "birth_time_precision": precision, "birth_city": city_key.title(),
        "birth_lat": lat, "birth_lon": lon, "tz": tz,
        "chart_json": json.dumps(chart, ensure_ascii=False),
        "goal": item.intent, "onboarded": 1, "onboarding_step": None,
    }
