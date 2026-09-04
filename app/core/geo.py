"""Город → координаты и таймзона.

Геокодирование — единственное место продукта, которое ходит в чужой интернет, и
делает это медленно (Nominatim, до 5 секунд). Поэтому здесь три уровня:

1. кеш в БД (`geocache`) — один и тот же город спрашивают сотни клиенток;
2. запрос к Nominatim + timezonefinder — в отдельном потоке, чтобы не держать
   event loop: синхронный вызов из async-хендлера вешал весь бот на время ответа;
3. встроенный словарь крупных городов и, в самом конце, Москва.

Синхронный `resolve_city` оставлен для скриптов и тестов; продуктовый код должен
звать `resolve_city_async`.
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata

log = logging.getLogger("oracle.geo")

DEFAULT_TZ = "Europe/Moscow"
NOMINATIM_TIMEOUT = 5

FALLBACK = {
    "москва": (55.75, 37.62, "Europe/Moscow"),
    "санкт-петербург": (59.94, 30.31, "Europe/Moscow"),
    "петербург": (59.94, 30.31, "Europe/Moscow"),
    "питер": (59.94, 30.31, "Europe/Moscow"),
    "казань": (55.79, 49.12, "Europe/Moscow"),
    "новосибирск": (55.03, 82.92, "Asia/Novosibirsk"),
    "екатеринбург": (56.84, 60.65, "Asia/Yekaterinburg"),
    "нижний новгород": (56.33, 44.00, "Europe/Moscow"),
    "самара": (53.20, 50.15, "Europe/Samara"),
    "омск": (54.99, 73.37, "Asia/Omsk"),
    "челябинск": (55.16, 61.40, "Asia/Yekaterinburg"),
    "ростов-на-дону": (47.23, 39.72, "Europe/Moscow"),
    "уфа": (54.74, 55.97, "Asia/Yekaterinburg"),
    "красноярск": (56.01, 92.87, "Asia/Krasnoyarsk"),
    "воронеж": (51.66, 39.20, "Europe/Moscow"),
    "пермь": (58.01, 56.25, "Asia/Yekaterinburg"),
    "волгоград": (48.71, 44.51, "Europe/Volgograd"),
    "краснодар": (45.04, 38.98, "Europe/Moscow"),
    "саратов": (51.53, 46.01, "Europe/Saratov"),
    "тюмень": (57.15, 65.53, "Asia/Yekaterinburg"),
    "владивосток": (43.12, 131.89, "Asia/Vladivostok"),
    "иркутск": (52.29, 104.30, "Asia/Irkutsk"),
    "сочи": (43.60, 39.73, "Europe/Moscow"),
    "калининград": (54.71, 20.51, "Europe/Kaliningrad"),
    "минск": (53.90, 27.57, "Europe/Minsk"),
    "гомель": (52.44, 30.98, "Europe/Minsk"),
    "киев": (50.45, 30.52, "Europe/Kyiv"),
    "київ": (50.45, 30.52, "Europe/Kyiv"),
    "харьков": (49.99, 36.23, "Europe/Kyiv"),
    "одесса": (46.48, 30.73, "Europe/Kyiv"),
    "львов": (49.84, 24.03, "Europe/Kyiv"),
    "алматы": (43.24, 76.89, "Asia/Almaty"),
    "астана": (51.17, 71.43, "Asia/Almaty"),
    "нур-султан": (51.17, 71.43, "Asia/Almaty"),
    "шымкент": (42.32, 69.59, "Asia/Almaty"),
    "ташкент": (41.30, 69.24, "Asia/Tashkent"),
    "бишкек": (42.87, 74.59, "Asia/Bishkek"),
    "душанбе": (38.56, 68.79, "Asia/Dushanbe"),
    "баку": (40.41, 49.87, "Asia/Baku"),
    "ереван": (40.18, 44.51, "Asia/Yerevan"),
    "тбилиси": (41.72, 44.79, "Asia/Tbilisi"),
    "кишинёв": (47.01, 28.86, "Europe/Chisinau"),
    "кишинев": (47.01, 28.86, "Europe/Chisinau"),
    "рига": (56.95, 24.11, "Europe/Riga"),
    "вильнюс": (54.69, 25.28, "Europe/Vilnius"),
    "таллин": (59.44, 24.75, "Europe/Tallinn"),
    "варшава": (52.23, 21.01, "Europe/Warsaw"),
    "берлин": (52.52, 13.40, "Europe/Berlin"),
    "прага": (50.08, 14.44, "Europe/Prague"),
    "лондон": (51.51, -0.13, "Europe/London"),
    "париж": (48.86, 2.35, "Europe/Paris"),
    "рим": (41.90, 12.50, "Europe/Rome"),
    "мадрид": (40.42, -3.70, "Europe/Madrid"),
    "лиссабон": (38.72, -9.14, "Europe/Lisbon"),
    "стамбул": (41.01, 28.98, "Europe/Istanbul"),
    "тель-авив": (32.08, 34.78, "Asia/Jerusalem"),
    "дубай": (25.20, 55.27, "Asia/Dubai"),
    "нью-йорк": (40.71, -74.01, "America/New_York"),
    "лос-анджелес": (34.05, -118.24, "America/Los_Angeles"),
    "чикаго": (41.88, -87.63, "America/Chicago"),
    "торонто": (43.65, -79.38, "America/Toronto"),
    "майами": (25.76, -80.19, "America/New_York"),
    "бангкок": (13.76, 100.50, "Asia/Bangkok"),
    "пекин": (39.90, 116.41, "Asia/Shanghai"),
    "токио": (35.68, 139.69, "Asia/Tokyo"),
}


def normalize(city: str) -> str:
    """Ключ кеша: без регистра, лишних пробелов и разницы «е/ё»."""
    key = unicodedata.normalize("NFKC", (city or "")).strip().lower()
    return " ".join(key.replace("ё", "е").split())


def _lookup_fallback(key: str) -> tuple[float, float, str] | None:
    if key in FALLBACK:
        return FALLBACK[key]
    # «г. Казань», «Казань, Россия» — берём первое узнаваемое слово
    for part in (p.strip() for p in key.replace(",", " ").split()):
        if part in FALLBACK:
            return FALLBACK[part]
    return None


def _geocode_online(city: str) -> tuple[float, float, str] | None:
    """Синхронный запрос к Nominatim. Вызывать только вне event loop."""
    try:
        from geopy.geocoders import Nominatim
        from timezonefinder import TimezoneFinder

        loc = Nominatim(user_agent="oracle-bot",
                        timeout=NOMINATIM_TIMEOUT).geocode(city)
        if not loc:
            return None
        tz = TimezoneFinder().timezone_at(lat=loc.latitude, lng=loc.longitude)
        return loc.latitude, loc.longitude, tz or DEFAULT_TZ
    except Exception as e:  # noqa: BLE001
        log.info("геокодирование не удалось: error_type=%s", type(e).__name__)
        return None


def resolve_city(city: str) -> tuple[float | None, float | None, str]:
    """(lat, lon, tz). Синхронная версия — для скриптов и тестов.

    Продуктовый код должен звать `resolve_city_async`: этот вызов блокирует
    поток на время сетевого запроса.
    """
    key = normalize(city)
    if not key:
        return None, None, DEFAULT_TZ
    hit = _lookup_fallback(key)
    if hit:
        return hit
    online = _geocode_online(city)
    if online:
        return online
    return None, None, DEFAULT_TZ


async def resolve_city_info_async(city: str, db=None) -> dict:
    """Resolve a city and return auditable coordinates/timezone provenance.

    The public tuple wrapper below remains for legacy callers. Confidence is a
    bounded product signal, not a claim of scientific geocoder accuracy.
    """
    key = normalize(city)
    if not key:
        return {"lat": None, "lon": None, "tz": DEFAULT_TZ,
                "coordinate_source": "unknown", "coordinate_confidence": 0.0,
                "timezone_source": "default_fallback"}

    if db is not None:
        cached = await _cache_get_record(db, key)
        if cached:
            source = cached.get("source") or "unknown"
            return {**cached, "coordinate_source": source,
                    "coordinate_confidence": 0.8 if source == "builtin" else 0.7,
                    "timezone_source": source}

    hit = _lookup_fallback(key)
    if hit:
        if db is not None:
            await _cache_put(db, key, *hit, source="builtin")
        return {"lat": hit[0], "lon": hit[1], "tz": hit[2],
                "coordinate_source": "builtin", "coordinate_confidence": 0.8,
                "timezone_source": "builtin"}

    online = await asyncio.to_thread(_geocode_online, city)
    if online:
        if db is not None:
            await _cache_put(db, key, *online, source="nominatim")
        return {"lat": online[0], "lon": online[1], "tz": online[2],
                "coordinate_source": "geocoder", "coordinate_confidence": 0.7,
                "timezone_source": "geocoder"}

    log.info("город не распознан — считаю карту без координат")
    return {"lat": None, "lon": None, "tz": DEFAULT_TZ,
            "coordinate_source": "unknown", "coordinate_confidence": 0.0,
            "timezone_source": "default_fallback"}


async def resolve_city_async(city: str, db=None) -> tuple[float | None, float | None, str]:
    """Legacy `(lat, lon, tz)` wrapper around :func:`resolve_city_info_async`."""
    info = await resolve_city_info_async(city, db)
    return info["lat"], info["lon"], info["tz"]


# ────────────────────────────────── кеш ───────────────────────────────────────

async def _cache_get_record(db, key: str) -> dict | None:
    try:
        cur = await db.execute(
            "SELECT lat, lon, tz, source FROM geocache WHERE city_key=:city_key",
            {"city_key": key})
        row = await cur.fetchone()
    except Exception as e:  # noqa: BLE001
        log.debug("кеш геокодирования недоступен: %s", e)
        return None
    if not row or row["lat"] is None:
        return None
    return {"lat": row["lat"], "lon": row["lon"], "tz": row["tz"] or DEFAULT_TZ,
            "source": row["source"] or "unknown"}


async def _cache_get(db, key: str) -> tuple[float, float, str] | None:
    record = await _cache_get_record(db, key)
    if not record:
        return None
    return record["lat"], record["lon"], record["tz"]


async def _cache_put(db, key: str, lat: float, lon: float, tz: str, *,
                     source: str = "nominatim") -> None:
    try:
        from ..data.session import transaction, utcnow
        async with transaction(db):
            await db.execute(
                "INSERT INTO geocache(city_key, lat, lon, tz, source, "
                "created_at) VALUES(:city_key, :lat, :lon, :tz, :source, :created_at) "
                "ON CONFLICT (city_key) DO UPDATE SET lat=excluded.lat, "
                "lon=excluded.lon, tz=excluded.tz, source=excluded.source, "
                "created_at=excluded.created_at",
                {"city_key": key, "lat": lat, "lon": lon, "tz": tz,
                 "source": source, "created_at": utcnow()})
    except Exception as e:  # noqa: BLE001
        log.debug("кеш геокодирования не записан: %s", e)
