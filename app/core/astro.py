"""Астро-расчёты.

Полный режим: kerykeion (Swiss Ephemeris) — планеты, дома, аспекты.
Лайт-режим (библиотека не установлена): знак Солнца + стихия, честно помеченный.
LLM никогда не считает карту — только трактует результат этого модуля.
"""
from __future__ import annotations

import asyncio
import logging
import math
from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .astrology_engine import (
    ENGINE,
    ENGINE_ADAPTER_VERSION,
    ChartRequest,
    validate_chart_result,
)
from .chart_contract import ASPECT_ORBS, build_calculation_metadata

log = logging.getLogger("oracle.astro")

SIGNS = [
    ("Овен", "♈", "огонь"), ("Телец", "♉", "земля"), ("Близнецы", "♊", "воздух"),
    ("Рак", "♋", "вода"), ("Лев", "♌", "огонь"), ("Дева", "♍", "земля"),
    ("Весы", "♎", "воздух"), ("Скорпион", "♏", "вода"), ("Стрелец", "♐", "огонь"),
    ("Козерог", "♑", "земля"), ("Водолей", "♒", "воздух"), ("Рыбы", "♓", "вода"),
]

# границы знаков по дням (приближённо, для лайт-режима)
_SUN_BOUNDS = [(1, 20), (2, 19), (3, 21), (4, 20), (5, 21), (6, 21),
               (7, 23), (8, 23), (9, 23), (10, 23), (11, 22), (12, 22)]

PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн",
    "Uranus": "Уран", "Neptune": "Нептун", "Pluto": "Плутон",
}
SIGN_EN2RU = {
    "Ari": "Овен", "Tau": "Телец", "Gem": "Близнецы", "Can": "Рак", "Leo": "Лев",
    "Vir": "Дева", "Lib": "Весы", "Sco": "Скорпион", "Sag": "Стрелец",
    "Cap": "Козерог", "Aqu": "Водолей", "Pis": "Рыбы",
}

# kerykeion отдаёт дом строкой вида "Ninth_House"
HOUSE_ORDER = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth",
               "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth"]
HOUSE_NUM = {f"{n}_House": i + 1 for i, n in enumerate(HOUSE_ORDER)}

ASPECT_RU = {
    "conjunction": ("соединение", "☌"), "opposition": ("оппозиция", "☍"),
    "trine": ("трин", "△"), "square": ("квадрат", "□"), "sextile": ("секстиль", "⚹"),
}
# только мажорные аспекты между «настоящими» планетами — иначе шум из 55 строк
POINT_RU = {**PLANET_RU, "Ascendant": "Асцендент", "Medium_Coeli": "Середина неба"}
ASPECT_PLANETS = set(POINT_RU)

# Keep calculation conventions explicit instead of inheriting silent library defaults.
# These are the current product conventions and are returned in chart metadata.
ZODIAC_TYPE = "Tropical"
HOUSE_SYSTEM_IDENTIFIER = "P"  # Placidus
HOUSE_SYSTEM_NAME = "Placidus"
PERSPECTIVE_TYPE = "Apparent Geocentric"
EPHEMERIS_ENGINE = "Swiss Ephemeris via Kerykeion"
NODE_MODE = "true"
ACTIVE_POINTS = [
    "Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn",
    "Uranus", "Neptune", "Pluto", "Chiron", "Juno", "Ceres", "Vesta", "Pallas",
    "True_North_Lunar_Node", "True_South_Lunar_Node", "True_Lilith",
    "Ascendant", "Medium_Coeli", "Descendant", "Imum_Coeli",
]
ADDITIONAL_POINT_RU = {
    "Chiron": "Хирон", "Juno": "Джуно", "Ceres": "Церера",
    "Vesta": "Веста", "Pallas": "Паллада",
}
EXPANDED_POINT_NAMES = tuple(ADDITIONAL_POINT_RU)


def sun_sign(d: date) -> tuple[str, str, str]:
    """(знак, символ, стихия) по дате — без эфемерид."""
    m, day = d.month, d.day
    bm, bd = _SUN_BOUNDS[m - 1]
    idx = (m - 1) if day >= bd else (m - 2)
    # индекс знака: 21 марта = Овен (0). Сдвиг: март -> 0
    return SIGNS[(idx - 2) % 12]


# ───────────────────────── эфемеридные знаки без времени ─────────────────────
#
# Для знаков планет точное время и место рождения не нужны — планеты находятся
# в одном знаке круглые сутки. kerykeion строит карту на дату в 12:00 и с
# координатами, не влияющими на знаки; кеш по дате экономит повторные расчёты,
# потому что прогноз дня, гороскопы и спидометр зовут их часто.
_LIGHT_CACHE: dict[str, dict] = {}


def _light_sky(d: date) -> dict:
    """Знаки Солнца/Луны/Венеры на дату: эфемериды → календарный фолбэк."""
    key = d.isoformat()
    cached = _LIGHT_CACHE.get(key)
    if cached:
        return cached
    try:
        from kerykeion import AstrologicalSubjectFactory
        subj = AstrologicalSubjectFactory.from_birth_data(
            name="sky", year=d.year, month=d.month, day=d.day,
            hour=12, minute=0, city="-", lat=52.5, lng=13.4, tz_str="UTC", online=False,
            zodiac_type=ZODIAC_TYPE,
            houses_system_identifier=HOUSE_SYSTEM_IDENTIFIER,
            perspective_type=PERSPECTIVE_TYPE,
            active_points=ACTIVE_POINTS)
        m = subj

        def sign_of(p) -> tuple[str, str]:
            s = SIGN_EN2RU.get(p.sign, p.sign)
            el = next((x[2] for x in SIGNS if x[0] == s), "")
            return s, el

        # Точный знак Солнца: момент входа по эфемеридам, а не по календарю.
        s, el = sign_of(m.sun)
        sym = next((x[1] for x in SIGNS if x[0] == s), "☉")
        out = {"sun": (s, sym, el),
               "moon": sign_of(m.moon), "venus": sign_of(m.venus)}
    except Exception as e:  # noqa: BLE001
        log.debug("эфемеридные знаки недоступны (%s), фолбэк на календарь", e)
        out = {"sun": sun_sign(d), "moon": None, "venus": None}
    if len(_LIGHT_CACHE) > 800:
        _LIGHT_CACHE.clear()
    _LIGHT_CACHE[key] = out
    return out


def sun_sign_precise(d: date) -> tuple[str, str, str]:
    """Точный знак Солнца (эфемериды): переход на годы, а не статичная таблица.

    Рождённый 21 марта в одном году уже Телец, в другом ещё Овен — календарные
    границы грешат на ±1–2 дня. При недоступных эфемеридах — календарный знак.
    """
    return _light_sky(d)["sun"]


def moon_venus_signs(d: date) -> tuple[tuple[str, str] | None,
                                       tuple[str, str] | None]:
    """(знак, стихия) Луны и Венеры на дату; кортежи None — эфемериды недоступны."""
    sky = _light_sky(d)
    return sky["moon"], sky["venus"]


# ─────────────────────────────── синастрия ────────────────────────────────────

# Орбы синастрии используют ту же явную major-aspect policy.
_SYNASTRY_ORBS = ASPECT_ORBS
_ASPECT_ANGLE = {"conjunction": 0.0, "opposition": 180.0, "trine": 120.0,
                 "square": 90.0, "sextile": 60.0}
_LUMINARY = {"Солнце", "Луна"}


def _delta360(a: float, b: float) -> float:
    delta = abs(a - b) % 360
    return min(delta, 360 - delta)


def synastry_aspects(planets_a: list[dict], planets_b: list[dict],
                     limit: int = 10) -> list[dict]:
    """Мажорные аспекты между планетами двух карт, точные первыми.

    Одноимённые точки (Солнце—Солнце и т.п.) пропускаем: это не аспект «между»,
    а две стороны одного качества — в классике синастрии их не читают орбно.
    """
    out = []
    for pa in planets_a:
        if pa.get("abs_deg") is None:   # 0° — легитимная долгота
            continue
        for pb in planets_b:
            if pa["name"] == pb["name"] or pb.get("abs_deg") is None:
                continue
            delta = _delta360(pa["abs_deg"], pb["abs_deg"])
            orb = 10 if (pa["name"] in _LUMINARY or pb["name"] in _LUMINARY) else 8
            for aspect, good in _ASPECT_ANGLE.items():
                if abs(delta - good) <= _SYNASTRY_ORBS.get(aspect, orb):
                    glyph = ASPECT_RU[aspect][1]
                    out.append({"p1": pa["name"], "p2": pb["name"],
                                "aspect": ASPECT_RU[aspect][0], "glyph": glyph,
                                "orb": round(abs(delta - good), 1), "code": aspect})
                    break
    out.sort(key=lambda x: x["orb"])
    return out[:limit]


def synastry_aspects_text(aspects: list[dict]) -> str:
    if not aspects:
        return "аспектов между картами не найдено"
    return "; ".join(f"{a['p1']} {a['glyph']} {a['p2']} (орб {a['orb']}°)"
                     for a in aspects[:8])


def _parse_birth_time(value: str | None) -> tuple[int, int] | None:
    """Возвращает проверенное локальное время или `None`, не подменяя его полднем."""
    if value in (None, ""):
        return None
    try:
        parsed = datetime.strptime(value, "%H:%M")
    except (TypeError, ValueError) as exc:
        raise ValueError("Время рождения указывается в формате ЧЧ:ММ") from exc
    return parsed.hour, parsed.minute


def _has_valid_timezone(tz: str | None) -> bool:
    """Return whether a supplied IANA timezone identifier is valid."""
    if not tz:
        return False
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError):
        return False
    return True


def _has_valid_coordinates(lat: float | None, lon: float | None) -> bool:
    """Проверяет полноту и физически допустимый диапазон координат."""
    if lat is None or lon is None:
        return False
    try:
        return (math.isfinite(float(lat)) and math.isfinite(float(lon))
                and -90 <= float(lat) <= 90 and -180 <= float(lon) <= 180)
    except (TypeError, ValueError):
        return False


def compute_chart(birth_date: str, birth_time: str | None, city: str | None,
                  lat: float | None, lon: float | None,
                  tz: str | None = None, *, time_known: bool | None = None,
                  coordinate_source: str | None = None,
                  coordinate_confidence: float | None = None,
                  timezone_source: str | None = None,
                  ambiguity_mode: str = "safe_date_only") -> dict:
    """Calculate a chart through the improved Kerykeion engine boundary.

    The boundary normalizes input, derives the truth state and fingerprints the
    request before the Kerykeion/Swiss Ephemeris backend is called. It also
    caches only defensive copies, so callers cannot mutate future results.
    """
    request = ENGINE.normalize(
        birth_date, birth_time, city, lat, lon, tz, time_known=time_known,
        coordinate_source=coordinate_source,
        coordinate_confidence=coordinate_confidence,
        timezone_source=timezone_source,
        ambiguity_mode=ambiguity_mode,
        active_points=tuple(ACTIVE_POINTS),
    )

    def calculate(normalized: ChartRequest) -> dict:
        return _full_chart(
            normalized.birth_date,
            normalized.birth_time,
            normalized.city,
            normalized.lat,
            normalized.lon,
            normalized.tz,
            coordinates_known=normalized.coordinates_known,
            time_confirmed=normalized.time_confirmed,
            precision_reason=normalized.precision_reason,
            precision=normalized.precision,
            request_metadata=normalized.metadata(),
        )

    try:
        return ENGINE.calculate(request, calculate, validator=validate_chart_result)
    except Exception as exc:  # noqa: BLE001
        log.warning("полная карта недоступна (%s), считаю упрощённо", exc)
        sign, sym, element = sun_sign_precise(request.birth_date)
        return {
            "mode": "lite",
            "precision": "sun_only",
            "engine": EPHEMERIS_ENGINE,
            "zodiac_type": ZODIAC_TYPE,
            "house_system": HOUSE_SYSTEM_IDENTIFIER,
            "house_system_name": HOUSE_SYSTEM_NAME,
            "perspective_type": PERSPECTIVE_TYPE,
            "sun": {"sign": sign, "symbol": sym, "element": element},
            "planets": [],
            "houses": [],
            "aspects": [],
            "note": "Упрощённый расчёт: доступны только данные Солнца; "
                    "дома, ASC, MC и аспекты не определяются.",
            "calculation": build_calculation_metadata(
                active_points=ACTIVE_POINTS,
                input_data={
                    "birth_date": request.birth_date.isoformat(),
                    "birth_time": (f"{request.birth_time[0]:02d}:{request.birth_time[1]:02d}"
                                   if request.birth_time else None),
                    "city": request.city,
                    "lat": request.lat,
                    "lon": request.lon,
                    "tz": request.tz,
                    "time_known": request.time_confirmed,
                    "precision_reason": request.precision_reason,
                    **request.metadata(),
                },
                precision="sun_only", angular_data_available=False),
        }


async def compute_chart_async(birth_date: str, birth_time: str | None,
                              city: str | None, lat: float | None,
                              lon: float | None, tz: str | None = None,
                              *, time_known: bool | None = None,
                              coordinate_source: str | None = None,
                              coordinate_confidence: float | None = None,
                              timezone_source: str | None = None,
                              ambiguity_mode: str = "safe_date_only") -> dict:
    """`compute_chart` в отдельном потоке.

    Расчёт эфемерид занимает сотни миллисекунд и держит GIL: из async-хендлера
    это означало, что на время построения карты бот не отвечал никому.
    """
    return await asyncio.to_thread(compute_chart, birth_date, birth_time, city,
                                   lat, lon, tz, time_known=time_known,
                                   coordinate_source=coordinate_source,
                                   coordinate_confidence=coordinate_confidence,
                                   timezone_source=timezone_source,
                                   ambiguity_mode=ambiguity_mode)


def _aspects(subject) -> list[dict]:
    """Мажорные аспекты между планетами, самые точные — первыми."""
    from kerykeion import NatalAspects  # type: ignore

    out = []
    for a in NatalAspects(subject).relevant_aspects:
        if a.aspect not in ASPECT_RU:
            continue
        if a.p1_name not in ASPECT_PLANETS or a.p2_name not in ASPECT_PLANETS:
            continue
        orbit = abs(float(a.orbit))
        if orbit > ASPECT_ORBS.get(a.aspect, 0.0):
            continue
        name, glyph = ASPECT_RU[a.aspect]
        out.append({
            "p1": POINT_RU.get(a.p1_name, a.p1_name),
            "p2": POINT_RU.get(a.p2_name, a.p2_name),
            "aspect": name, "glyph": glyph,
            "orb": round(orbit, 1), "orb_exact": orbit,
        })
    out.sort(key=lambda x: x["orb"])
    return out[:12]


def _full_chart(d: date, birth_time: tuple[int, int] | None, city, lat, lon, tz,
                *, coordinates_known: bool, time_confirmed: bool,
                precision_reason: str = "date_only", precision: str | None = None,
                request_metadata: dict | None = None) -> dict:
    from kerykeion import AstrologicalSubjectFactory  # type: ignore

    hour, minute = birth_time or (12, 0)
    # Использовать углы и дома корректно можно только при локальном времени,
    # координатах и таймзоне. В остальных случаях полдень — техническая опора для
    # положений планет, а не подставное время рождения.
    angular_data_available = bool(time_confirmed and coordinates_known and tz)

    kwargs = dict(name="user", year=d.year, month=d.month, day=d.day,
                  hour=hour, minute=minute, city=city or "-",
                  zodiac_type=ZODIAC_TYPE,
                  houses_system_identifier=HOUSE_SYSTEM_IDENTIFIER,
                  perspective_type=PERSPECTIVE_TYPE,
                  active_points=ACTIVE_POINTS)
    if coordinates_known:
        subject = AstrologicalSubjectFactory.from_birth_data(
            **kwargs, lat=float(lat), lng=float(lon),
            tz_str=tz or "UTC", online=False)
    else:
        # Без координат используем нейтральную 0°/0° reference point только для
        # гео-независимых планетных долгот; углы и дома всё равно отключены.
        subject = AstrologicalSubjectFactory.from_birth_data(
            **{**kwargs, "city": "UTC reference"}, lat=0.0, lng=0.0,
            tz_str=tz or "UTC", online=False)

    m = subject

    planets = []
    for attr in ["sun", "moon", "mercury", "venus", "mars", "jupiter",
                 "saturn", "uranus", "neptune", "pluto"]:
        p = getattr(m, attr)
        planets.append({
            "name": PLANET_RU.get(p.name, p.name),
            "sign": SIGN_EN2RU.get(p.sign, p.sign),
            "deg": round(p.position, 1),
            "deg_exact": float(p.position),
            "abs_deg": round(p.abs_pos, 1),
            "abs_deg_exact": float(p.abs_pos),
            "house": HOUSE_NUM.get(str(p.house), None) if angular_data_available else None,
            "retro": bool(getattr(p, "retrograde", False)),
        })

    houses = []
    if angular_data_available:
        for i, name in enumerate(HOUSE_ORDER, start=1):
            h = getattr(m, f"{name.lower()}_house")
            houses.append({"n": i, "sign": SIGN_EN2RU.get(h.sign, h.sign),
                           "deg": round(h.position, 1), "deg_exact": float(h.position),
                           "abs_deg": round(h.abs_pos, 1), "abs_deg_exact": float(h.abs_pos)})

    asc = m.ascendant if angular_data_available else None
    mc = m.medium_coeli if angular_data_available else None
    sun = planets[0]
    sym = next((s[1] for s in SIGNS if s[0] == sun["sign"]), "☉")
    element = next((s[2] for s in SIGNS if s[0] == sun["sign"]), "")
    # Лунные узлы (Раху — северный, Кету — южный) и Чёрная Луна — часть карты,
    # без них «полная карта» выглядит неполной.
    nodes = []
    for attr, ru in [("true_north_lunar_node", "Раху (Северный узел)"),
                     ("true_south_lunar_node", "Кету (Южный узел)"),
                     ("true_lilith", "Лилит (Чёрная Луна)")]:
        try:
            n = getattr(m, attr)
        except AttributeError:
            continue
        if n is None or getattr(n, "sign", None) is None:
            continue
        nodes.append({
            "name": ru,
            "sign": SIGN_EN2RU.get(n.sign, n.sign),
            "deg": round(n.position, 1),
            "deg_exact": float(n.position),
            "abs_deg": round(n.abs_pos, 1),
            "abs_deg_exact": float(n.abs_pos),
            "house": HOUSE_NUM.get(str(getattr(n, "house", "")), None)
                     if angular_data_available else None,
            "retro": bool(getattr(n, "retrograde", False)),
        })
    additional_points = []
    for attr in EXPANDED_POINT_NAMES:
        point = getattr(m, attr.lower(), None)
        if point is None or getattr(point, "sign", None) is None:
            continue
        additional_points.append({
            "name": ADDITIONAL_POINT_RU[attr],
            "point": attr,
            "sign": SIGN_EN2RU.get(point.sign, point.sign),
            "deg": round(point.position, 1),
            "deg_exact": float(point.position),
            "abs_deg": round(point.abs_pos, 1),
            "abs_deg_exact": float(point.abs_pos),
            "house": HOUSE_NUM.get(str(getattr(point, "house", "")), None)
                     if angular_data_available else None,
            "retro": bool(getattr(point, "retrograde", False)),
        })
    rahu = next((point for point in nodes if point["name"].startswith("Раху")), None)
    ketu = next((point for point in nodes if point["name"].startswith("Кету")), None)
    precision = precision or ("exact" if angular_data_available else (
        "time_without_location" if time_confirmed else "date_only"
    ))
    note = ""
    if precision == "date_only":
        note = ("Время рождения не указано: показаны эфемеридные положения планет; "
                "дома, ASC и MC намеренно скрыты.")
    elif precision == "interval":
        note = ("Локальное время неоднозначно из-за перехода часового пояса: "
                "углы и дома скрыты, а time-specific выводы требуют подтверждения fold.")
    elif precision == "time_without_location":
        note = ("Время рождения указано, но координаты или таймзона не подтверждены: "
                "дома, ASC и MC намеренно скрыты.")
    aspects = _aspects(subject)
    if not angular_data_available:
        aspects = [a for a in aspects if a["p1"] not in {"Асцендент", "Середина неба"}
                   and a["p2"] not in {"Асцендент", "Середина неба"}]
    return {
        "mode": "full",
        "precision": precision,
        "engine": EPHEMERIS_ENGINE,
        "zodiac_type": ZODIAC_TYPE,
        "house_system": HOUSE_SYSTEM_IDENTIFIER,
        "house_system_name": HOUSE_SYSTEM_NAME,
        "perspective_type": PERSPECTIVE_TYPE,
        "sun": {"sign": sun["sign"], "symbol": sym, "element": element},
        "ascendant": ({"sign": SIGN_EN2RU.get(asc.sign, asc.sign),
                       "deg": round(asc.position, 1), "deg_exact": float(asc.position),
                       "abs_deg": round(asc.abs_pos, 1), "abs_deg_exact": float(asc.abs_pos)}
                      if asc else None),
        "mc": ({"sign": SIGN_EN2RU.get(mc.sign, mc.sign),
                "deg": round(mc.position, 1), "deg_exact": float(mc.position),
                "abs_deg": round(mc.abs_pos, 1), "abs_deg_exact": float(mc.abs_pos)}
               if mc else None),
        "planets": planets,
        "houses": houses,
        "aspects": aspects,
        "nodes": nodes,
        "lunar_nodes": {
            "mode": NODE_MODE,
            "mode_label": "True Node",
            "rahu": rahu,
            "ketu": ketu,
        },
        "additional_points": additional_points,
        "note": note,
        "calculation": build_calculation_metadata(
            active_points=ACTIVE_POINTS,
            input_data={"birth_date": d.isoformat(),
                        "birth_time": (f"{hour:02d}:{minute:02d}" if birth_time and time_confirmed else None),
                        "city": city, "lat": lat, "lon": lon, "tz": tz,
                        "time_known": time_confirmed,
                        "precision_reason": precision_reason,
                        "adapter_version": ENGINE_ADAPTER_VERSION,
                        **(request_metadata or {})},
            precision=precision, angular_data_available=angular_data_available),
    }


def _chart_planet(chart: dict, name: str) -> dict | None:
    return next((p for p in chart.get("planets") or [] if p.get("name") == name), None)


def _chart_house(chart: dict, number: int) -> dict | None:
    return next((h for h in chart.get("houses") or [] if h.get("n") == number), None)


def _chart_point_value(point: dict | None, *, include_house: bool = True) -> str:
    if not point or not point.get("sign"):
        return "нет данных"
    value = str(point["sign"])
    if point.get("deg") is not None:
        value += f" · {point['deg']}°"
    if include_house and point.get("house"):
        value += f" · {point['house']}-й дом"
    return value


def chart_sections(chart: dict, *, time_known: bool | None = None) -> dict:
    """Понятная карта смыслов, собранная поверх фактических положений.

    Этот слой отдаёт клиенту проверяемые placements и короткие определения тем,
    чтобы UI и LLM использовали один и тот же источник правды.
    """
    exact = bool(time_known is True and chart.get("precision", "exact") == "exact")
    sun = chart.get("sun") or _chart_planet(chart, "Солнце") or {}
    moon = _chart_planet(chart, "Луна")
    mercury = _chart_planet(chart, "Меркурий")
    mars = _chart_planet(chart, "Марс")
    venus = _chart_planet(chart, "Венера")
    asc = chart.get("ascendant") or {}
    mc = chart.get("mc") or {}
    seventh = _chart_house(chart, 7)
    second = _chart_house(chart, 2)
    sixth = _chart_house(chart, 6)
    tenth = _chart_house(chart, 10)
    nodes = {n.get("name", ""): n for n in chart.get("nodes") or []}
    ketu = nodes.get("Кету (Южный узел)")
    rahu = nodes.get("Раху (Северный узел)")

    def item(key: str, label: str, point: dict | None, meaning: str, *, available: bool = True) -> dict:
        return {"key": key, "label": label, "value": _chart_point_value(point),
                "sign": (point or {}).get("sign"), "house": (point or {}).get("house"),
                "meaning": meaning, "available": bool(available and point and point.get("sign"))}

    sections = {
        "identity": {
            "title": "Ядро личности и маска",
            "intro": "Три точки показывают внутренний центр, эмоциональную настройку и первое впечатление — это ясный язык наблюдения и самопонимания.",
            "items": [
                item("ascendant", "Асцендент", asc, "Как человек входит в контакт с миром и какое первое впечатление создаёт.", available=exact),
                item("sun", "Солнце", sun, "Центр воли, самоощущение, жизненная энергия и то, как человек собирает образ себя."),
                item("moon", "Луна", moon, "Эмоциональные привычки, потребность в безопасности и внутренний мир, который проявляется наедине с собой."),
            ],
            "note": "Для точного Асцендента нужно подтверждённое время, координаты и часовой пояс рождения." if not exact else "",
        },
        "mind_career": {
            "title": "Интеллект, общение, карьера и деньги",
            "intro": "Планеты описывают стиль мышления и действия; дома — сферы жизни. Финансовый блок показывает отношение к ресурсам, устойчивости и способу строить доход через конкретные навыки и решения.",
            "items": [
                item("mercury", "Меркурий", mercury, "Как человек думает, объясняет, шутит, учится и обрабатывает информацию."),
                item("mars", "Марс", mars, "Как человек действует, защищает границы, проходит препятствия и переживает конфликт."),
                {"key": "career", "label": "Карьера", "value": (f"MC в {mc.get('sign')} · 10-й дом {tenth.get('sign')}" if exact and mc.get("sign") and tenth else "нужны точные дома"), "sign": (mc.get("sign") if exact else None), "house": 10 if exact and tenth else None, "meaning": "Профессиональная среда, амбиции и способ строить видимый результат.", "available": bool(exact and (mc.get("sign") or tenth))},
                {"key": "finance", "label": "Финансы", "value": (f"2-й дом {second.get('sign')} · 6-й дом {sixth.get('sign')}" if exact and (second or sixth) else "нужны точные дома"), "sign": (second or {}).get("sign") if exact else None, "house": 2 if exact and second else None, "meaning": "Ресурсы, привычки труда, отношение к ценности и устойчивому заработку  — для практических решений опирайся на факты, навыки и обстоятельства.", "available": bool(exact and (second or sixth))},
            ],
            "note": "Без подтверждённого времени показываем планеты в знаках. Карьерные и финансовые дома пока недоступны: нужны точные дома." if not exact else "",
        },
        "relationships": {
            "title": "Любовь, отношения и партнёрство",
            "intro": "Венера показывает язык симпатии и удовольствия, а 7-й дом — стиль серьёзного партнёрства, если время рождения достаточно точное.",
            "items": [
                item("venus", "Венера", venus, "Как человек проявляет нежность, что считает красивым и какой формат близости приносит удовольствие."),
                {"key": "seventh_house", "label": "7-й дом", "value": (_chart_point_value(seventh, include_house=False) if exact else "нужны точные дома"), "sign": (seventh or {}).get("sign") if exact else None, "house": 7 if exact and seventh else None, "meaning": "Какие качества человек ищет в серьёзном союзе и где в паре могут возникать повторяющиеся задачи.", "available": bool(exact and seventh)},
            ],
            "note": "Без точного времени можно говорить о Венере, но не делать выводы по 7-му дому." if not exact else "",
        },
        "nodes": {
            "title": "Кармические узлы: привычное и направление роста",
            "intro": "Узлы показывают привычную силу и направление роста: Кету — накопленный сценарий, Раху — новый опыт, который раскрывает следующий уровень карты.",
            "items": [
                item("ketu", "Кету · Южный узел", ketu, "Накопленный опыт, знакомые стратегии и зона опоры, которую важно использовать осознанно."),
                item("rahu", "Раху · Северный узел", rahu, "Направление любопытства и развития: навык, который раскрывается через конкретные действия в настоящем."),
            ],
            "note": "Соедини привычную силу Кету с новым опытом Раху через один конкретный шаг." if ketu or rahu else "Узлы пока не рассчитаны.",
        },
    }
    return {"version": 1, "exact": exact, "sections": sections}


MOON_PHASES = [
    ("Новолуние", "🌑", "загадай намерение письменно и отпусти — Вселенная запомнит"),
    ("Растущий серп", "🌒", "первые шаги: знакомства, отклики, начало дела"),
    ("Первая четверть", "🌓", "пора решений: спорь с сомнениями, а не с миром"),
    ("Растущая Луна", "🌔", "сила растёт — запускай, проси, подписывай"),
    ("Полнолуние", "🌕", "эмоции громче фактов: будь мягче, не решай судьбоносно"),
    ("Убывающая Луна", "🌖", "закрывай хвосты и благодари — освобождаешь место"),
    ("Последняя четверть", "🌗", "отпускай лишнее: людей, привычки, старые долги"),
    ("Старый серп", "🌘", "тишина и восстановление: не начинай нового, выдыхай"),
]


def moon_phase(d: date | None = None) -> dict:
    """Фаза и лунный день по синодическому циклу (точность ±1 день).

    Считаем день от новолуния; классические лунные календари ведут сутки от
    восхода Луны, поэтому в начале цикла возможна разница в сутки. Название
    «лунный день» сохраняем — так это ищут женщины, а «~» в текстах честно
    помечает приближение. Канон по восходу требует эфемеридных итераций и
    вынесен из сферы прогнозов.
    """
    d = d or date.today()
    known_new_moon = date(2000, 1, 6)
    days = (d - known_new_moon).days % 29.530588
    idx = int((days / 29.530588) * 8 + 0.5) % 8
    name, emoji, advice = MOON_PHASES[idx]
    return {"name": name, "emoji": emoji, "advice": advice,
            "day": round(days) + 1}


def today_sky(d: date | None = None) -> dict:
    """«Небо сегодня»: знак сезона Солнца + фаза Луны."""
    d = d or date.today()
    sign, sym, element = sun_sign_precise(d)
    return {"sun_season": {"sign": sign, "symbol": sym, "element": element},
            "moon": moon_phase(d)}


# ──────────────── профессиональные акценты карты (для chart_brief) ──────────

# Стихия/крест по знаку и планета-управитель знака — таблицы фактов, без воли.
_SIGN_ELEMENT = {s[0]: s[2] for s in SIGNS}
_SIGN_CROSS = {
    "Овен": "кардинальный", "Рак": "кардинальный", "Весы": "кардинальный",
    "Козерог": "кардинальный", "Телец": "фиксированный", "Лев": "фиксированный",
    "Скорпион": "фиксированный", "Водолей": "фиксированный",
    "Близнецы": "мутабельный", "Дева": "мутабельный", "Стрелец": "мутабельный",
    "Рыбы": "мутабельный",
}
_SIGN_RULER = {
    "Овен": "Марс", "Телец": "Венера", "Близнецы": "Меркурий", "Рак": "Луна",
    "Лев": "Солнце", "Дева": "Меркурий", "Весы": "Венера", "Скорпион": "Плутон",
    "Стрелец": "Юпитер", "Козерог": "Сатурн", "Водолей": "Уран", "Рыбы": "Нептун",
}
_SIGN_IDX = {s[0]: i for i, s in enumerate(SIGNS)}
_ANGLE_ORB = 10.0  # орб близости к угловым куспидам: классика сильной планеты


def _planets_word(n: int) -> str:
    """Склонение слова «планеты» для числа: 4 планеты, 5 планет."""
    if 11 <= n % 100 <= 14:
        return "планет"
    last = n % 10
    if last == 1:
        return "планета"
    if last in (2, 3, 4):
        return "планеты"
    return "планет"


def _sign_abs(deg, sign_ru):
    """Абсолютная долгота (0–360) из позиции в знаке и его названия."""
    try:
        return _SIGN_IDX[sign_ru] * 30 + deg
    except (KeyError, TypeError):
        return None


def _chart_accents(chart: dict, time_known: bool | None) -> str:
    """Профессиональные акценты карты, выведенные из данных, без домыслов.

    Ничего не трактует за LLM — только факты (перевесы, стеллиумы, обиталища,
    угловые планеты, эмоциональный и любовный маркеры) с краткими пояснениями.
    Домовые факты зависят от точного времени рождения, поэтому при
    `time_known is not True` дома и углы не упоминаются.
    """
    planets = chart.get("planets") or []
    if not planets:
        return ""
    bits = []

    # Перевес стихий: сколько планет в какой.
    elements = {}
    for p in planets:
        el = _SIGN_ELEMENT.get(p.get("sign"))
        if el:
            elements[el] = elements.get(el, 0) + 1
    if elements:
        order = ["огонь", "земля", "воздух", "вода"]
        rows = [(el, elements[el]) for el in order if elements.get(el)]
        rows.sort(key=lambda x: (-x[1], order.index(x[0])))
        top = max(elements.values())
        bit = "стихии: " + ", ".join(f"{el} {n}" for el, n in rows)
        if top >= 3:
            lead = [el for el, n in rows if n == top]
            bit += f"; акцент: {', '.join(lead)} ({top} {_planets_word(top)})"
        bits.append(bit)

    # Кардинальность: кардинальные/фиксированные/мутабельные.
    crosses = {}
    for p in planets:
        cr = _SIGN_CROSS.get(p.get("sign"))
        if cr:
            crosses[cr] = crosses.get(cr, 0) + 1
    if crosses:
        rows = sorted(crosses.items(), key=lambda x: -x[1])
        top = max(crosses.values())
        bit = "кресты: " + ", ".join(f"{cr} {n}" for cr, n in rows)
        if top >= 3:
            lead = [cr for cr, n in rows if n == top]
            bit += f"; акцент: {', '.join(lead)} ({top} {_planets_word(top)})"
        bits.append(bit)

    # Стеллиумы: 3+ планет в одном знаке или доме.
    by_sign, by_house = {}, {}
    for p in planets:
        sign = p.get("sign")
        if sign:
            by_sign[sign] = by_sign.get(sign, 0) + 1
        if time_known is True:
            h = p.get("house")
            if h:
                by_house[h] = by_house.get(h, 0) + 1
    stell = [f"{s} ({n})" for s, n in sorted(by_sign.items(), key=lambda x: -x[1])
             if n >= 3]
    if time_known is True:
        stell += [f"{h} дом ({n})" for h, n in
                  sorted(by_house.items(), key=lambda x: -x[1]) if n >= 3]
    if stell:
        bits.append("стеллиумы: " + ", ".join(stell))

    # Планеты-акценты: обиталище (в своём знаке) и свой дом (управитель знака
    # естественного дома).
    dwell = []
    for p in planets:
        sign = p.get("sign")
        if sign and _SIGN_RULER.get(sign) == p.get("name"):
            dwell.append(f"{p['name']} в {sign} (обиталище)")
        if time_known is True:
            h = p.get("house")
            if h and 1 <= h <= 12:
                natural = SIGNS[h - 1][0]
                if _SIGN_RULER.get(natural) == p.get("name"):
                    dwell.append(f"{p['name']} в {h} доме (свой дом)")
    if dwell:
        bits.append("акценты: " + "; ".join(dwell))

    # Ретроградные планеты — профессиональный маркер: внутренняя работа вместо
    # внешнего действия, энергия, идущая внутрь.
    retros = [p.get("name", "?") for p in planets if p.get("retro")]
    if retros:
        bits.append("ретро: " + ", ".join(retros))

    # Самая близкая к угловым куспидам планета (ASC/MC).
    if time_known is True:
        asc = chart.get("ascendant") or {}
        mc = chart.get("mc") or {}
        a_deg = asc.get("abs_deg")
        m_deg = _sign_abs(mc.get("deg"), mc.get("sign"))
        best = None  # (расстояние, угол, планета)
        for p in planets:
            pd = p.get("abs_deg")
            if pd is None:
                continue
            for angle, ad in (("ASC", a_deg), ("MC", m_deg)):
                if ad is None:
                    continue
                d = _delta360(pd, ad)
                if best is None or d < best[0]:
                    best = (d, angle, p.get("name", "?"))
        if best and best[0] <= _ANGLE_ORB:
            bits.append(f"{best[2]} в {best[0]:.0f}° от {best[1]}")

    # Эмоции и любовь — маркеры по данным, трактовку делает LLM.
    by_name = {p.get("name"): p for p in planets}
    moon = by_name.get("Луна")
    if moon and moon.get("sign"):
        bits.append(f"Луна в {moon['sign']} — эмоциональная природа")
    venus, mars = by_name.get("Венера"), by_name.get("Марс")
    if venus and venus.get("sign"):
        love = [f"Венера в {venus['sign']}"]
        if mars and mars.get("sign"):
            love.append(f"Марс в {mars['sign']}")
        bits.append(", ".join(love) + " — любовный профиль")

    return "; ".join(bits)


def chart_brief(chart: dict, *, time_known: bool | None = None) -> str:
    """Краткая текстовая выжимка карты для промпта агента.

    `time_known=False` — время рождения неизвестно, дома посчитаны по полудню:
    их нельзя показывать и тем более нельзя давать LLM делать домовые выводы.
    """
    if chart.get("mode") == "full" and chart.get("planets"):
        parts = []
        conventions = (
            f"Методика: {chart.get('zodiac_type', ZODIAC_TYPE)}, "
            f"дома {chart.get('house_system_name', HOUSE_SYSTEM_NAME)}, "
            f"{chart.get('perspective_type', PERSPECTIVE_TYPE)}"
        )
        parts.append(conventions)
        contract = chart.get("calculation") or {}
        config = contract.get("config") or {}
        if contract:
            node_label = config.get("node_mode_label", "True Node")
            policy = config.get("aspect_policy") or {}
            orb_text = ", ".join(
                f"{name} {value}°" for name, value in (policy.get("orbs_deg") or {}).items()
            )
            parts.append(
                f"Канонический контракт v{contract.get('contract_version', 1)}; "
                f"узлы: {node_label}; орбы: {orb_text or 'major policy'}"
            )
        # Старые сохранённые карты не содержат `precision`; при известном времени
        # они считаются точными, а новые date-only карты явно блокируют углы.
        angular_data_available = time_known is True and chart.get("precision", "exact") == "exact"
        asc = chart.get("ascendant") if angular_data_available else None
        if asc:
            parts.append(f"Асцендент в {asc['sign']}")
        mc = chart.get("mc") if angular_data_available else None
        if mc and mc.get("sign"):
            parts.append(f"MC в {mc['sign']}")
        for p in chart["planets"]:
            house = f", {p['house']} дом" if (p.get("house") and angular_data_available) else ""
            parts.append(f"{p['name']} в {p['sign']}{house}"
                         + (" (R)" if p["retro"] else ""))
        brief = "; ".join(parts)
        if not angular_data_available:
            brief += (". ВНИМАНИЕ: время рождения неизвестно или недостаточно "
                      "подтверждено; используется только техническая точка полдня. "
                      "дома, ASC и MC отсутствуют — не выводи их и не заменяй предположением")
        aspects = chart.get("aspects") or []
        if aspects:
            brief += ". Ключевые аспекты: " + "; ".join(
                f"{a['p1']} {a['glyph']} {a['p2']} (орб {a['orb']}°)"
                for a in aspects[:6])
        nodes = chart.get("nodes") or []
        if nodes:
            brief += ". Узлы и Лилит: " + "; ".join(
                f"{n['name']} в {n['sign']}" for n in nodes if n.get("sign"))
        additional = chart.get("additional_points") or []
        if additional:
            brief += ". Дополнительные точки: " + "; ".join(
                f"{p['name']} в {p['sign']}" for p in additional if p.get("sign"))
        accents = _chart_accents(chart, angular_data_available)
        if accents:
            brief += ". АКЦЕНТЫ КАРТЫ: " + accents
        return brief
    s = chart.get("sun", {})
    return f"Солнце в {s.get('sign', '?')} (стихия: {s.get('element', '?')}); расчёт упрощённый"
