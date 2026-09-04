"""Deterministic Vedic/Jyotish calculations with explicit evidence contracts.

This module is intentionally separate from ``astro.py``.  The existing product
uses a Western tropical/Placidus contract; this module uses sidereal Lahiri and
never silently mixes the two traditions.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import swisseph as swe
except ImportError:  # lazy import guard: tests/dev envs without pyswisseph
    swe = None

SIGNS_EN = (
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
)
SIGNS_RU = (
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы",
)
PLANETS = (
    {
        "Sun": swe.SUN, "Moon": swe.MOON, "Mercury": swe.MERCURY,
        "Venus": swe.VENUS, "Mars": swe.MARS, "Jupiter": swe.JUPITER,
        "Saturn": swe.SATURN, "Rahu": swe.TRUE_NODE,
    }
    if swe is not None
    else {}
)
PLANET_RU = {
    "Sun": "Солнце", "Moon": "Луна", "Mercury": "Меркурий", "Venus": "Венера",
    "Mars": "Марс", "Jupiter": "Юпитер", "Saturn": "Сатурн", "Rahu": "Раху",
    "Ketu": "Кету",
}
NAKSHATRAS = (
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
)
NAKSHATRA_RU = (
    "Ашвини", "Бхарани", "Криттика", "Рохини", "Мригашира", "Ардра",
    "Пунарвасу", "Пушья", "Ашлеша", "Магха", "Пурва-Пхалгуни",
    "Уттара-Пхалгуни", "Хаста", "Читра", "Свати", "Вишакха", "Анурадха",
    "Джйештха", "Мула", "Пурва-Ашадха", "Уттара-Ашадха", "Шравана",
    "Дхаништха", "Шатабхиша", "Пурва-Бхадрапада", "Уттара-Бхадрапада", "Ревати",
)
NAKSHATRA_LORDS = (
    "Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury",
) * 3
DASHA_YEARS = {
    "Ketu": 7, "Venus": 20, "Sun": 6, "Moon": 10, "Mars": 7,
    "Rahu": 18, "Jupiter": 16, "Saturn": 19, "Mercury": 17,
}
DASHA_ORDER = ("Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury")

AYANAMSA_NAME = "Lahiri"
ENGINE = f"Swiss Ephemeris via pyswisseph {getattr(swe, '__version__', 'unknown')}"
NAKSHATRA_SPAN = 360.0 / 27.0
PADA_SPAN = NAKSHATRA_SPAN / 4.0


def _evidence(tool: str, *, inputs: dict, result, limitations: list[str] | None = None) -> dict:
    return {
        "tool": tool,
        "calculation_mode": "deterministic",
        "tradition": "Vedic/Jyotish",
        "ayanamsa": AYANAMSA_NAME,
        "ephemeris": ENGINE,
        "inputs": inputs,
        "result": result,
        "limitations": limitations or [],
        "calculated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def _check_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("date must use YYYY-MM-DD") from exc


def _zone(value: str | None) -> ZoneInfo:
    if not value:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("timezone must be a valid IANA identifier") from exc


def _coords(lat: float | None, lon: float | None) -> tuple[float, float]:
    if lat is None or lon is None:
        raise ValueError("latitude and longitude are required for local Vedic calculations")
    lat_f, lon_f = float(lat), float(lon)
    if not (-90 <= lat_f <= 90 and -180 <= lon_f <= 180):
        raise ValueError("latitude/longitude are outside physical bounds")
    return lat_f, lon_f


def _local_dt(birth_date: str, birth_time: str | None, tz: str | None, *, default_noon: bool = True) -> datetime:
    d = _check_date(birth_date)
    zone = _zone(tz)
    if birth_time:
        try:
            clock = datetime.strptime(birth_time, "%H:%M").time()
        except (TypeError, ValueError) as exc:
            raise ValueError("birth_time must use HH:MM") from exc
    elif default_noon:
        clock = time(12, 0)
    else:
        raise ValueError("birth_time is required")
    return datetime.combine(d, clock, tzinfo=zone)


def _julian(dt: datetime) -> float:
    utc = dt.astimezone(timezone.utc)
    return swe.julday(utc.year, utc.month, utc.day,
                      utc.hour + utc.minute / 60 + utc.second / 3600)


def _sidereal_longitudes(jd: float) -> dict[str, dict]:
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    flags = swe.FLG_SWIEPH | swe.FLG_SIDEREAL | swe.FLG_SPEED
    output: dict[str, dict] = {}
    for name, body in PLANETS.items():
        values, _ = swe.calc_ut(jd, body, flags)
        longitude = float(values[0]) % 360.0
        speed = float(values[3])
        output[name] = {
            "name": PLANET_RU[name],
            "planet": name,
            "longitude": round(longitude, 6),
            "sign": SIGNS_RU[int(longitude // 30) % 12],
            "sign_index": int(longitude // 30) % 12,
            "degree": round(longitude % 30, 6),
            "retrograde": speed < 0,
        }
    output["Ketu"] = {
        **output["Rahu"], "name": PLANET_RU["Ketu"], "planet": "Ketu",
        "longitude": round((output["Rahu"]["longitude"] + 180) % 360, 6),
    }
    output["Ketu"]["sign_index"] = int(output["Ketu"]["longitude"] // 30) % 12
    output["Ketu"]["sign"] = SIGNS_RU[output["Ketu"]["sign_index"]]
    output["Ketu"]["degree"] = round(output["Ketu"]["longitude"] % 30, 6)
    output["Ketu"]["retrograde"] = output["Rahu"]["retrograde"]
    return output


def _nakshatra(longitude: float) -> dict:
    value = float(longitude) % 360.0
    index = min(26, int(value / NAKSHATRA_SPAN))
    within = value - index * NAKSHATRA_SPAN
    pada = min(4, int(within / PADA_SPAN) + 1)
    return {
        "longitude": round(value, 6), "index": index + 1,
        "name": NAKSHATRAS[index], "name_ru": NAKSHATRA_RU[index],
        "pada": pada, "lord": NAKSHATRA_LORDS[index],
        "span_start": round(index * NAKSHATRA_SPAN, 6),
        "span_end": round((index + 1) * NAKSHATRA_SPAN, 6),
    }


def get_nakshatra(longitude: float) -> dict:
    try:
        value = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("longitude must be numeric") from exc
    if not 0 <= value <= 360:
        raise ValueError("longitude must be between 0 and 360 degrees")
    return _evidence("get_nakshatra", inputs={"longitude": value}, result=_nakshatra(value))


def _whole_sign_houses(lagna: float) -> tuple[dict, list[dict]]:
    lagna_index = int(lagna // 30) % 12
    asc = {"longitude": round(lagna % 360, 6), "sign": SIGNS_RU[lagna_index],
           "sign_index": lagna_index, "degree": round(lagna % 30, 6)}
    houses = [{"house": house, "sign": SIGNS_RU[(lagna_index + house - 1) % 12],
               "sign_index": (lagna_index + house - 1) % 12}
              for house in range(1, 13)]
    return asc, houses


def compute_vedic_chart(birth_date: str, birth_time: str | None, city: str | None,
                        lat: float | None, lon: float | None, tz: str | None = None,
                        *, time_known: bool | None = None) -> dict:
    d = _check_date(birth_date)
    local = _local_dt(birth_date, birth_time, tz)
    coordinates = _coords(lat, lon)
    jd = _julian(local)
    planets = _sidereal_longitudes(jd)
    exact = bool(birth_time and time_known is not False)
    asc = None
    houses = []
    if exact:
        _, lon_f = coordinates
        lat_f, _ = coordinates
        swe.set_sid_mode(swe.SIDM_LAHIRI)
        _, ascmc = swe.houses_ex(jd, lat_f, lon_f, b'W', swe.FLG_SIDEREAL)
        asc, houses = _whole_sign_houses(float(ascmc[0]))
    limitations = []
    if not exact:
        limitations.append("birth time is unknown or unconfirmed; lagna and houses are omitted")
    if not tz:
        limitations.append("timezone was not supplied; UTC was used for the date snapshot")
    node_data = {key: planets[key] for key in ("Rahu", "Ketu")}
    for item in planets.values():
        item["nakshatra"] = _nakshatra(item["longitude"])
    return _evidence(
        "get_vedic_chart",
        inputs={"birth_date": d.isoformat(), "birth_time": birth_time,
                "city": city, "latitude": coordinates[0], "longitude": coordinates[1],
                "timezone": tz or "UTC", "time_known": exact},
        result={"precision": "exact" if exact else "date_only", "zodiac": "sidereal",
                "ayanamsa": AYANAMSA_NAME, "city": city, "planets": list(planets.values()),
                "lunar_nodes": node_data, "lagna": asc, "houses": houses},
        limitations=limitations,
    )


def _moon_snapshot(birth_date: str, birth_time: str | None, tz: str | None,
                   lat: float | None = None, lon: float | None = None) -> tuple[dict, datetime]:
    local = _local_dt(birth_date, birth_time, tz, default_noon=not bool(birth_time))
    planets = _sidereal_longitudes(_julian(local))
    planets["Moon"]["nakshatra"] = _nakshatra(planets["Moon"]["longitude"])
    return planets["Moon"], local


def _antardasha_periods(start: datetime, mahadasha_lord: str, duration_days: float) -> list[dict]:
    idx = DASHA_ORDER.index(mahadasha_lord)
    cursor = start
    rows = []
    for n in range(len(DASHA_ORDER)):
        lord = DASHA_ORDER[(idx + n) % len(DASHA_ORDER)]
        span = duration_days * DASHA_YEARS[lord] / 120
        end = cursor + timedelta(days=span)
        rows.append({"lord": lord, "lord_ru": PLANET_RU[lord],
                     "start": cursor.date().isoformat(), "end": end.date().isoformat(),
                     "years": DASHA_YEARS[lord]})
        cursor = end
    return rows


def _dasha_periods(start: datetime, first_lord: str, *, years: float = 120) -> list[dict]:
    idx = DASHA_ORDER.index(first_lord)
    periods: list[dict] = []
    cursor = start
    total_days = years * 365.2425
    elapsed = 0.0
    for n in range(len(DASHA_ORDER) + 1):
        lord = DASHA_ORDER[(idx + n) % len(DASHA_ORDER)]
        duration_days = total_days * DASHA_YEARS[lord] / 120
        end = cursor + timedelta(days=duration_days)
        periods.append({"lord": lord, "lord_ru": PLANET_RU[lord],
                        "start": cursor.date().isoformat(), "end": end.date().isoformat(),
                        "years": DASHA_YEARS[lord],
                        "antardasha": _antardasha_periods(cursor, lord, duration_days)})
        cursor = end
        elapsed += duration_days
        if elapsed >= total_days - 0.01:
            break
    return periods


def get_vimshottari_dasha(birth_date: str, birth_time: str | None, tz: str | None,
                          *, as_of: str | None = None) -> dict:
    if not birth_time:
        raise ValueError("birth_time is required for a precise Vimshottari timeline")
    moon, local = _moon_snapshot(birth_date, birth_time, tz)
    nak = moon["nakshatra"]
    lord = nak["lord"]
    traversed = (moon["longitude"] % NAKSHATRA_SPAN) / NAKSHATRA_SPAN
    remaining_fraction = 1.0 - traversed
    first_duration_days = 365.2425 * DASHA_YEARS[lord] * remaining_fraction
    start = local - timedelta(days=365.2425 * DASHA_YEARS[lord] * traversed)
    periods = _dasha_periods(start, lord)
    if periods:
        periods[0]["balance_fraction_at_birth"] = round(remaining_fraction, 8)
        periods[0]["balance_days_at_birth"] = round(first_duration_days, 2)
    target = _check_date(as_of) if as_of else date.today()
    current = next((p for p in periods if p["start"] <= target.isoformat() < p["end"]), None)
    result = {"system": "Vimshottari", "cycle_years": 120, "moon": moon,
              "starting_lord": lord, "periods": periods, "as_of": target.isoformat(),
              "current": current}
    return _evidence("get_vimshottari_dasha",
                     inputs={"birth_date": birth_date, "birth_time": birth_time,
                             "timezone": tz or "UTC", "as_of": target.isoformat()},
                     result=result,
                     limitations=["interpretation uses traditional timing language; do not assert events absent from the calculated periods"])


def _sun_moon(jd: float) -> tuple[dict, dict]:
    all_pos = _sidereal_longitudes(jd)
    return all_pos["Sun"], all_pos["Moon"]


def _panchang_at(local: datetime, lat: float, lon: float) -> dict:
    jd = _julian(local)
    sun, moon = _sun_moon(jd)
    elongation = (moon["longitude"] - sun["longitude"]) % 360
    tithi_index = min(29, int(elongation // 12))
    yoga_index = min(26, int(((moon["longitude"] + sun["longitude"]) % 360) // NAKSHATRA_SPAN))
    half = min(59, int(elongation // 6))
    if half == 0:
        karana = "Kimstughna"
    elif half >= 57:
        karana = ("Shakuni", "Chatushpada", "Naga")[half - 57]
    else:
        karana = ("Bava", "Balava", "Kaulava", "Taitila", "Garaja", "Vanija", "Vishti")[(half - 1) % 7]
    sunrise = _rise_set(local, lat, lon, rise=True)
    sunset = _rise_set(local, lat, lon, rise=False)
    return {
        "date": local.date().isoformat(), "vara": local.strftime("%A"),
        "tithi": {"number": tithi_index + 1, "paksha": "Shukla" if tithi_index < 15 else "Krishna",
                   "name": f"Tithi {tithi_index + 1}"},
        "nakshatra": _nakshatra(moon["longitude"]),
        "yoga": {"number": yoga_index + 1, "name": f"Yoga {yoga_index + 1}"},
        "karana": {"half_tithi_index": half + 1, "name": karana},
        "sunrise": sunrise, "sunset": sunset,
        "solar_longitude": sun["longitude"], "lunar_longitude": moon["longitude"],
    }


def _rise_set(local: datetime, lat: float, lon: float, *, rise: bool) -> str | None:
    start = datetime.combine(local.date(), time(0), tzinfo=local.tzinfo)
    rsmi = swe.CALC_RISE if rise else swe.CALC_SET
    try:
        _, result = swe.rise_trans(_julian(start), swe.SUN, rsmi, (lon, lat, 0), flags=swe.FLG_SWIEPH)
        utc_jd = result[0]
        year, month, day, hour = swe.revjul(utc_jd, swe.GREG_CAL)
        whole_hours = int(hour)
        minutes = int(round((hour - whole_hours) * 60))
        event = datetime(year, month, day, tzinfo=timezone.utc) + timedelta(hours=whole_hours, minutes=minutes)
        return event.astimezone(local.tzinfo).isoformat()
    except (swe.Error, ValueError, OverflowError):
        return None


def get_panchang(calendar_date: str, lat: float, lon: float, tz: str | None = None) -> dict:
    d = _check_date(calendar_date)
    lat_f, lon_f = _coords(lat, lon)
    local = datetime.combine(d, time(12), tzinfo=_zone(tz))
    result = _panchang_at(local, lat_f, lon_f)
    return _evidence("get_panchang", inputs={"date": calendar_date, "latitude": lat_f,
                                               "longitude": lon_f, "timezone": tz or "UTC"},
                     result=result,
                     limitations=["tithi/yoga/karana are evaluated at local noon; event-boundary precision requires an interval ephemeris"])


def get_rahu_kaal(calendar_date: str, lat: float, lon: float, tz: str | None = None) -> dict:
    d = _check_date(calendar_date)
    lat_f, lon_f = _coords(lat, lon)
    local = datetime.combine(d, time(12), tzinfo=_zone(tz))
    panchang = _panchang_at(local, lat_f, lon_f)
    if not panchang["sunrise"] or not panchang["sunset"]:
        raise ValueError("sunrise/sunset could not be calculated for this location")
    sunrise = datetime.fromisoformat(panchang["sunrise"])
    sunset = datetime.fromisoformat(panchang["sunset"])
    segment = (sunset - sunrise) / 8
    # Monday=0 ... Sunday=6.  Segment number is 1-based.
    rahu_segment = (2, 7, 5, 6, 4, 3, 8)[d.weekday()]
    start = sunrise + segment * (rahu_segment - 1)
    end = start + segment
    result = {"date": calendar_date, "weekday": d.strftime("%A"),
              "segment": rahu_segment, "start": start.isoformat(), "end": end.isoformat(),
              "sunrise": panchang["sunrise"], "sunset": panchang["sunset"]}
    return _evidence("get_rahu_kaal", inputs={"date": calendar_date, "latitude": lat_f,
                                                 "longitude": lon_f, "timezone": tz or "UTC"},
                     result=result,
                     limitations=["Rahu Kaal is a traditional planning convention, not a prediction or prohibition"])


def _varga_sign(longitude: float, divisions: int) -> int:
    sign = int((longitude % 360) // 30)
    part = min(divisions - 1, int((longitude % 30) / (30 / divisions)))
    if divisions == 1:
        return sign
    if sign % 3 == 0:  # movable
        start = sign
    elif sign % 3 == 1:  # fixed
        start = sign + 8
    else:  # dual
        start = sign + 4
    return (start + part) % 12


def get_varga_chart(chart: dict, varga: str = "D1") -> dict:
    key = str(varga or "D1").upper().strip()
    divisions = {"D1": 1, "D9": 9, "D10": 10}.get(key)
    if divisions is None:
        raise ValueError("supported vargas are D1, D9 and D10")
    items = []
    for planet in chart.get("planets") or []:
        longitude = planet.get("longitude")
        if longitude is None:
            continue
        sign_index = _varga_sign(float(longitude), divisions)
        items.append({"planet": planet.get("planet"), "name": planet.get("name"),
                      "source_longitude": longitude, "sign": SIGNS_RU[sign_index],
                      "sign_index": sign_index})
    result = {"varga": key, "divisions": divisions, "method": "parashara-sign-division-v1",
              "planets": items}
    return _evidence("get_varga_chart", inputs={"varga": key}, result=result,
                     limitations=["D9/D10 use a documented sign-division rule; school variants may differ"])


_RASHI_LORD = ("Mars", "Venus", "Mercury", "Moon", "Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Saturn", "Jupiter")
_VARNA = ("Kshatriya", "Shudra", "Vaishya", "Brahmin", "Kshatriya", "Vaishya", "Vaishya", "Brahmin", "Kshatriya", "Shudra", "Vaishya", "Brahmin")
_GANA = ("Deva", "Manushya", "Manushya", "Manushya", "Deva", "Manushya", "Rakshasa", "Deva", "Rakshasa", "Rakshasa", "Manushya", "Manushya", "Deva", "Rakshasa", "Deva", "Rakshasa", "Deva", "Rakshasa", "Rakshasa", "Manushya", "Manushya", "Deva", "Rakshasa", "Rakshasa", "Manushya", "Manushya", "Deva")
_NADI = tuple((i % 3) for i in range(27))
_YONI = ("Horse", "Elephant", "Sheep", "Serpent", "Serpent", "Dog", "Cat", "Sheep", "Cat", "Rat", "Rat", "Cow", "Buffalo", "Tiger", "Buffalo", "Tiger", "Deer", "Deer", "Dog", "Monkey", "Mongoose", "Monkey", "Lion", "Horse", "Lion", "Cow", "Elephant")


def _moon_profile(chart: dict) -> tuple[dict, int, int]:
    moon = next((p for p in chart.get("planets") or [] if p.get("planet") == "Moon" or p.get("name") == "Луна"), None)
    if not moon:
        raise ValueError("chart must contain Moon longitude")
    nak = _nakshatra(float(moon["longitude"]))
    return moon, nak["index"] - 1, int(moon["sign_index"])


def _score_guna(index_a: int, sign_a: int, index_b: int, sign_b: int) -> list[dict]:
    varna = 1 if _VARNA[sign_a] == _VARNA[sign_b] or abs((sign_a % 4) - (sign_b % 4)) <= 1 else 0
    vashya = 2 if sign_a == sign_b or sign_a % 4 == sign_b % 4 else 1
    tara_a = ((index_b - index_a) % 27) % 9
    tara_b = ((index_a - index_b) % 27) % 9
    tara = 3 if tara_a in {1, 2, 4, 6, 8} and tara_b in {1, 2, 4, 6, 8} else 1
    yoni = 4 if _YONI[index_a] == _YONI[index_b] else (2 if _YONI[index_a] != _YONI[index_b] else 0)
    graha = 5 if _RASHI_LORD[sign_a] == _RASHI_LORD[sign_b] else 3
    gana = 6 if _GANA[index_a] == _GANA[index_b] else 1
    bhakoot = 7 if abs(sign_a - sign_b) not in {2, 3, 7, 8, 5, 9} else 0
    nadi = 0 if _NADI[index_a] == _NADI[index_b] else 8
    rows = [("Varna", varna, 1), ("Vashya", vashya, 2), ("Tara", tara, 3),
            ("Yoni", yoni, 4), ("Graha Maitri", graha, 5), ("Gana", gana, 6),
            ("Bhakoot", bhakoot, 7), ("Nadi", nadi, 8)]
    return [{"koota": name, "score": score, "max": maximum} for name, score, maximum in rows]


def get_guna_milan(chart_a: dict, chart_b: dict) -> dict:
    _, idx_a, sign_a = _moon_profile(chart_a)
    _, idx_b, sign_b = _moon_profile(chart_b)
    components = _score_guna(idx_a, sign_a, idx_b, sign_b)
    total = sum(row["score"] for row in components)
    return _evidence("get_guna_milan", inputs={"method": "ashtakoot-balanced-v1"},
                     result={"method": "ashtakoot-balanced-v1", "total": total, "maximum": 36,
                             "components": components, "symmetric": True},
                     limitations=["component rules are an explicit balanced implementation; schools differ",
                                  "score is a reflection aid, not a verdict about a relationship"])


def get_vedic_transits(as_of: str | None = None) -> dict:
    d = _check_date(as_of) if as_of else date.today()
    local = datetime.combine(d, time(12), tzinfo=timezone.utc)
    planets = _sidereal_longitudes(_julian(local))
    result = {"date": d.isoformat(), "positions": list(planets.values())}
    return _evidence("get_vedic_transits", inputs={"date": d.isoformat()}, result=result,
                     limitations=["transits provide traditional timing context; use calculated windows for observation and preparation"])


_EXALTATION = {"Sun": 0, "Moon": 1, "Mars": 9, "Mercury": 5, "Jupiter": 3, "Venus": 11, "Saturn": 6}
_DEBILITATION = {planet: (sign + 6) % 12 for planet, sign in _EXALTATION.items()}
_OWN_SIGNS = {"Sun": {4}, "Moon": {3}, "Mars": {0, 7}, "Mercury": {2, 5},
              "Jupiter": {8, 11}, "Venus": {1, 6}, "Saturn": {9, 10}}


def get_graha_strengths(chart: dict) -> dict:
    rows = []
    for planet in chart.get("planets") or []:
        key = planet.get("planet")
        sign = int(planet.get("sign_index", -1))
        if key not in _EXALTATION or sign < 0:
            continue
        if sign == _EXALTATION[key]:
            status, score = "exalted", 100
        elif sign == _DEBILITATION[key]:
            status, score = "debilitated", 20
        elif sign in _OWN_SIGNS[key]:
            status, score = "own_sign", 80
        else:
            status, score = "neutral", 50
        rows.append({"planet": key, "name": planet.get("name"), "sign": planet.get("sign"),
                     "status": status, "score": score})
    return _evidence("get_graha_strengths", inputs={"formula": "dignity-lite-v1"},
                     result={"method": "dignity-lite-v1", "planets": rows},
                     limitations=["this is bounded sign-dignity evidence, not a full Shadbala calculation"])


def get_muhurta(date_a: str, date_b: str, lat: float, lon: float, tz: str | None = None,
                criteria: str | None = None) -> dict:
    p_a = get_panchang(date_a, lat, lon, tz)["result"]
    p_b = get_panchang(date_b, lat, lon, tz)["result"]
    # This is intentionally transparent and criteria-led rather than a hidden auspiciousness claim.
    def score(p: dict) -> int:
        score_value = 0
        if criteria and any(word in criteria.lower() for word in ("start", "начать", "launch", "запуск")):
            score_value += 1 if p["tithi"]["paksha"] == "Shukla" else 0
        if criteria and any(word in criteria.lower() for word in ("finish", "заверш", "close", "закры")):
            score_value += 1 if p["tithi"]["paksha"] == "Krishna" else 0
        return score_value
    sa, sb = score(p_a), score(p_b)
    winner = date_a if sa > sb else date_b if sb > sa else None
    result = {"criteria": criteria or "none supplied", "candidates": [
        {"date": date_a, "score": sa, "panchang": p_a},
        {"date": date_b, "score": sb, "panchang": p_b}], "preferred": winner}
    return _evidence("get_muhurta", inputs={"date_a": date_a, "date_b": date_b,
                                             "latitude": lat, "longitude": lon,
                                             "timezone": tz or "UTC", "criteria": criteria},
                     result=result,
                     limitations=["criteria comparison is not a guarantee and does not replace practical planning"])
