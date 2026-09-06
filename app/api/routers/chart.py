"""Натальная карта, Матрица Судьбы, совместимость, партнёры, разборы."""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from ...core import agent as agent_core
from ...core import product_cost
from ...core import astro, chart_rendering, geo, memory
from ...pdfgen import builder, render
from ...core.chart_contract import (
    EPHEMERIS_BACKEND,
    EPHEMERIS_NAME,
    KERYKEION_VERSION,
    ORACLE_ENGINE_ADAPTER_VERSION,
    ORACLE_ENGINE_NAME,
    public_calculation_contract,
)
from ...core.matrix import compute_matrix
from ...core.observability import log_event
from ...services.repo_gateway import billing, readings, users
from ...services import analytics, compatibility as compatibility_svc
from ..common.validation import parse_birth_date
from ..contracts.compatibility import CompatIn
from ..deps import confirmed_age_user, active_user, get_db, rate_limit

router = APIRouter(prefix="/api", tags=["chart"])
astro_log = logging.getLogger("oracle.astro")


def _astro_counts(chart: dict | None) -> dict[str, int]:
    chart = chart or {}
    return {
        "planet_count": len(chart.get("planets") or []),
        "house_count": len(chart.get("houses") or []),
        "aspect_count": len(chart.get("aspects") or []),
        "section_count": len((astro.chart_sections(chart, time_known=True).get("sections") or {})),
    }


def _log_astro(level: int, event: str, message: str, started: float,
               chart: dict | None = None, **fields) -> None:
    """Operational astrology log without birth data, prompt text or Telegram ID."""
    meta = _astro_counts(chart)
    meta["duration_ms"] = round((time.monotonic() - started) * 1000)
    log_event(astro_log, level, event, message, **meta, **fields)


# В публичном контракте None — валидное значение «время неизвестно».
# Отдельный sentinel нужен, чтобы отличать его от отсутствующего override.
_UNSET = object()


def _canonical_lunar_nodes(data: dict) -> dict:
    """Return the stable Rahu/Ketu contract, including legacy cached charts."""
    nodes = data.get("nodes") or []
    current = data.get("lunar_nodes")
    if isinstance(current, dict):
        return current
    return {
        "mode": "true",
        "mode_label": "True Node",
        "rahu": next((node for node in nodes if node.get("name", "").startswith("Раху")), None),
        "ketu": next((node for node in nodes if node.get("name", "").startswith("Кету")), None),
    }


def _chart_payload(data: dict, user, *, birth_date=_UNSET,
                   birth_time=_UNSET,
                   birth_city=_UNSET,
                   time_known: bool | None = None, **meta) -> dict:
    """Единый публичный контракт карты для GET, кэша и свежего расчёта.

    Точность — продуктовый факт, а не деталь UI: Mini App и другие клиенты должны
    одинаково понимать, можно ли показывать дома, ASC и MC.
    """
    known = bool(user["birth_time_known"]) if time_known is None else bool(time_known)
    calculation_contract = public_calculation_contract(data)
    payload = {
        "natal_schema_version": 2,
        "mode": data.get("mode", "lite"),
        "precision": data.get("precision", "sun_only"),
        "engine": data.get("engine", astro.EPHEMERIS_ENGINE),
        "engine_provenance": {
            "product_engine": ORACLE_ENGINE_NAME,
            "adapter_version": ((calculation_contract.get("input") or {}).get("adapter_version")
                                 or ORACLE_ENGINE_ADAPTER_VERSION),
            "backend": EPHEMERIS_BACKEND,
            "backend_version": KERYKEION_VERSION,
            "ephemeris": EPHEMERIS_NAME,
            "license_notice": "AGPL-3.0/commercial licensing obligations apply to the selected distribution model.",
        },
        "zodiac_type": data.get("zodiac_type", astro.ZODIAC_TYPE),
        "house_system": data.get("house_system", astro.HOUSE_SYSTEM_IDENTIFIER),
        "house_system_name": data.get("house_system_name", astro.HOUSE_SYSTEM_NAME),
        "perspective_type": data.get("perspective_type", astro.PERSPECTIVE_TYPE),
        "sun": data.get("sun"),
        "ascendant": data.get("ascendant"),
        "mc": data.get("mc"),
        "planets": data.get("planets", []),
        "houses": data.get("houses", []),
        "aspects": data.get("aspects", []),
        "nodes": data.get("nodes", []),
        "lunar_nodes": _canonical_lunar_nodes(data),
        "additional_points": data.get("additional_points", []),
        "note": data.get("note"),
        "calculation": calculation_contract,
        "sections": astro.chart_sections(data, time_known=known),
        "birth": {
            "date": user["birth_date"] if birth_date is _UNSET else birth_date,
            "time": user["birth_time"] if birth_time is _UNSET else birth_time,
            "city": user["birth_city"] if birth_city is _UNSET else birth_city,
            "time_known": known,
        },
    }
    return {**meta, **payload}


@router.get("/chart/image")
async def chart_image(
    request: Request,
    variant: str = Query(default="compact", min_length=1, max_length=16),
    format: str = Query(default="png", min_length=1, max_length=8),
    locale: str = Query(default="ru", min_length=2, max_length=2),
    user=Depends(confirmed_age_user),
):
    """Private raster chart image; the SVG engine output never crosses this boundary."""
    started = time.monotonic()
    data = users.chart_of(user)
    if not data:
        raise HTTPException(400, "карта ещё не построена")
    calculation_input = (data.get("calculation") or {}).get("input") or {}
    # A rendered image must describe the immutable chart snapshot. Prefer the
    # calculation input captured with that snapshot; profile edits are applied
    # only after a new chart calculation, not implicitly during rendering.
    birth_date = calculation_input.get("birth_date") or user["birth_date"]
    birth_time = calculation_input.get("birth_time") or user["birth_time"]
    lat = calculation_input.get("lat") if calculation_input.get("lat") is not None else user["birth_lat"]
    lon = calculation_input.get("lon") if calculation_input.get("lon") is not None else user["birth_lon"]
    tz = calculation_input.get("tz") or user["tz"]
    try:
        image, spec, cache_hit, etag = await asyncio.to_thread(
            chart_rendering.render_chart_image,
            data,
            birth_date=birth_date, birth_time=birth_time,
            lat=lat, lon=lon, tz=tz,
            variant=variant, image_format=format, locale=locale,
        )
    except chart_rendering.InsufficientPrecisionError as exc:
        raise HTTPException(409, {"code": exc.code, "message": str(exc)}) from exc
    except chart_rendering.UnsupportedRenderError as exc:
        raise HTTPException(422, {"code": exc.code, "message": str(exc)}) from exc
    except chart_rendering.RasterizerUnavailableError as exc:
        raise HTTPException(503, {"code": exc.code, "message": "картинка временно недоступна"}) from exc
    except chart_rendering.ChartRenderError as exc:
        _log_astro(logging.ERROR, "astro_chart_image_failed", "отрисовка натальной карты завершилась ошибкой", started,
                   data, variant=variant, format=format, locale=locale,
                   cache_hit=False, status="error", error_type=type(exc).__name__)
        raise HTTPException(503, {"code": getattr(exc, "code", "chart_image_failed"),
                                  "message": "картинка временно недоступна"}) from exc

    quoted = f'"{etag}"'
    headers = {
        "Cache-Control": "private, max-age=3600, must-revalidate",
        "Vary": "X-Init-Data",
        "ETag": quoted,
        "Content-Length": str(len(image)),
        "Content-Disposition": f'inline; filename="oracle-natal-{spec.variant}.{spec.image_format}"',
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == quoted:
        return Response(status_code=304, headers=headers)
    media_type = "image/webp" if spec.image_format == "webp" else "image/png"
    _log_astro(logging.INFO, "astro_chart_image_served", "растровая натальная карта отдана клиенту", started,
               data, variant=spec.variant, format=spec.image_format, locale=spec.locale,
               cache_hit=cache_hit, live=False, status="ok")
    return Response(content=image, media_type=media_type, headers=headers)


@router.get("/city/suggest", dependencies=[Depends(rate_limit("read"))])
async def city_suggest(q: str = Query(default="", min_length=0, max_length=60),
                       user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Подсказки города для кнопочного ввода: встроенный словарь + кеш геокода.

    Цель — исключить опечатки: клиентка тапает готовый город вместо ручного
    ввода. Источник — те же данные, что резолвит `geo.resolve_city_async`,
    поэтому подсказка всегда геокодируема. Сеть не трогаем: подсказки
    мгновенны и не зависят от Nominatim.
    """
    from ...core.geo import FALLBACK, normalize
    query = normalize(q)
    if len(query) < 2:
        return {"items": []}
    titles = {"москва": "Москва", "санкт-петербург": "Санкт-Петербург", "петербург": "Санкт-Петербург",
              "питер": "Санкт-Петербург", "казань": "Казань", "новосибирск": "Новосибирск",
              "екатеринбург": "Екатеринбург", "нижний новгород": "Нижний Новгород",
              "самара": "Самара", "омск": "Омск", "челябинск": "Челябинск",
              "ростов-на-дону": "Ростов-на-Дону", "уфа": "Уфа", "красноярск": "Красноярск",
              "воронеж": "Воронеж", "пермь": "Пермь", "волгоград": "Волгоград",
              "краснодар": "Краснодар", "саратов": "Саратов", "тюмень": "Тюмень",
              "владивосток": "Владивосток", "иркутск": "Иркутск", "сочи": "Сочи",
              "калининград": "Калининград", "минск": "Минск", "гомель": "Гомель",
              "киев": "Киев", "київ": "Київ", "харьков": "Харьков", "одесса": "Одесса",
              "львов": "Львов", "алматы": "Алматы", "астана": "Астана",
              "нур-султан": "Астана", "шымкент": "Шымкент", "ташкент": "Ташкент",
              "бишкек": "Бишкек", "душанбе": "Душанбе", "баку": "Баку", "ереван": "Ереван",
              "тбилиси": "Тбилиси", "кишинёв": "Кишинёв", "кишинев": "Кишинёв",
              "рига": "Рига", "вильнюс": "Вильнюс", "таллин": "Таллин", "варшава": "Варшава",
              "берлин": "Берлин", "прага": "Прага", "лондон": "London", "париж": "Paris",
              "рим": "Rome", "мадрид": "Madrid", "лиссабон": "Lisbon", "стамбул": "Istanbul",
              "тель-авив": "Тель-Авив", "дубай": "Dubai", "нью-йорк": "New York",
              "лос-анджелес": "Los Angeles", "чикаго": "Chicago", "торонто": "Toronto",
              "майами": "Miami", "бангкок": "Bangkok", "пекин": "Beijing", "токио": "Tokyo"}
    items, seen = [], set()
    query_words = query.replace(",", " ").split()
    # «Масква» и другие опечатки — нечёткое совпадение по встроенному словарю
    typo_keys = set(difflib.get_close_matches(query, FALLBACK, n=4, cutoff=0.6))
    for w in query_words:
        typo_keys.update(difflib.get_close_matches(w, FALLBACK, n=4, cutoff=0.75))
    # точное совпадение и «начинается с» — сначала, потом «встречается в слове», затем опечатки
    def rank(key: str) -> tuple:
        if key == query or key.startswith(query):
            return (0, key)
        if any(key in w or w in key for w in query_words):
            return (1, key)
        if key in typo_keys:
            return (2, key)
        return (3, key)
    for key in sorted(FALLBACK, key=rank):
        if rank(key)[0] < 3 and key not in seen:
            seen.add(key)
            items.append({"key": key, "label": titles.get(key, key.title())})
        if len(items) >= 8:
            break
    return {"items": items}


@router.get("/chart")
async def chart(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Карта целиком: планеты, дома, аспекты и честно указанная точность."""
    started = time.monotonic()
    data = users.chart_of(user)
    if not data:
        _log_astro(logging.WARNING, "astro_chart_missing", "натальная карта отсутствует", started,
                   status="missing", user_state="no_saved_chart")
        raise HTTPException(400, "карта ещё не построена — пройди знакомство в боте")
    payload = _chart_payload(data, user)
    _log_astro(logging.INFO, "astro_chart_served", "натальная карта отдана клиенту", started,
               data, mode=data.get("mode", "lite"), precision=data.get("precision", "sun_only"),
               time_known=bool(user["birth_time_known"]), cache_hit=True, live=False,
               status="ok", user_state="saved_chart")
    return payload


_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


class ChartBuildIn(BaseModel):
    birth_date: str | None = None
    birth_time: str | None = None
    birth_city: str | None = Field(default=None, max_length=60)


@router.post("/chart", dependencies=[Depends(rate_limit("write"))])
async def build_chart(item: ChartBuildIn | None = None, user=Depends(confirmed_age_user),
                      db=Depends(get_db)):
    """Строит и сохраняет натальную карту — тот же путь, что в онбординге бота.

    Нужно для сценария «собери карту прямо здесь»: у астролога в чате клиентка
    может заполнить/уточнить время и город, не заходя в бота. Если карта уже
    построена — возвращает её без пересчёта.
    """
    started = time.monotonic()
    item = item or ChartBuildIn()
    # В body важно различать «поле отсутствует» и «пользовательница очистила поле».
    # Второй вариант — осознанный date-only выбор, а не повод молча вернуть старое
    # время профиля и показать ложные ASC/MC/дома.
    supplied = item.model_fields_set
    date_supplied = "birth_date" in supplied
    time_supplied = "birth_time" in supplied
    city_supplied = "birth_city" in supplied

    birth_date = parse_birth_date(item.birth_date) if date_supplied and item.birth_date else user["birth_date"]
    if not birth_date:
        raise HTTPException(400, "укажи дату рождения — она нужна для расчёта карты")

    existing = users.chart_of(user)
    if existing and not supplied:
        payload = _chart_payload(existing, user, ok=True, cached=True)
        _log_astro(logging.INFO, "astro_chart_build_cached", "расчёт карты взят из кэша", started,
                   existing, mode=existing.get("mode", "lite"),
                   precision=existing.get("precision", "sun_only"),
                   time_known=bool(user["birth_time_known"]), cache_hit=True, live=False,
                   status="ok", user_state="saved_chart")
        return payload

    city = ((item.birth_city if city_supplied else user["birth_city"]) or "").strip()
    if not city:
        raise HTTPException(400, "укажи город рождения")

    raw_time = ((item.birth_time or "").strip() if time_supplied else (user["birth_time"] or "").strip())
    if raw_time and not _TIME_RE.match(raw_time):
        raise HTTPException(400, "время в формате ЧЧ:ММ, например 14:30")
    time_known = bool(raw_time) if time_supplied else bool(user["birth_time_known"])
    compute_time = raw_time or "12:00"
    stored_time = raw_time or None

    _log_astro(logging.INFO, "astro_chart_compute_started", "начат расчёт натальной карты", started,
               mode="full", precision="exact" if time_known else "date_only",
               time_known=time_known, cache_hit=False, live=True, status="started",
               user_state="recompute")
    geo_info = await geo.resolve_city_info_async(city, db)
    lat, lon, tz = geo_info["lat"], geo_info["lon"], geo_info["tz"]
    try:
        chart = await astro.compute_chart_async(
            birth_date, compute_time, city, lat, lon, tz, time_known=time_known,
            coordinate_source=geo_info["coordinate_source"],
            coordinate_confidence=geo_info["coordinate_confidence"],
            timezone_source=geo_info["timezone_source"],
        )
    except Exception as exc:  # noqa: BLE001
        _log_astro(logging.ERROR, "astro_chart_compute_failed", "расчёт натальной карты завершился ошибкой", started,
                   mode="full", precision="exact" if time_known else "date_only",
                   time_known=time_known, cache_hit=False, live=True, status="error",
                   error_type=type(exc).__name__, user_state="recompute")
        raise
    await users.update(db, user["tg_id"], birth_date=birth_date, birth_city=city,
                       birth_lat=lat, birth_lon=lon, tz=tz, birth_time=stored_time,
                       birth_time_known=1 if time_known else 0,
                       chart_json=json.dumps(chart, ensure_ascii=False))
    payload = _chart_payload(chart, user, birth_date=birth_date, birth_time=stored_time,
                             birth_city=city, time_known=time_known, ok=True, cached=False)
    _log_astro(logging.INFO, "astro_chart_computed", "натальная карта рассчитана и сохранена", started,
               chart, mode=chart.get("mode", "full"), precision=chart.get("precision", "exact"),
               time_known=time_known, cache_hit=False, live=True, status="ok", user_state="recompute")
    return payload


@router.post("/chart/interpret", dependencies=[Depends(rate_limit("write"))])
async def chart_interpret(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Бесплатный ИИ-разбор построенной карты простыми словами (кэш в chart_json).

    Для людей без астрологических знаний: кто ты, характер, сильные/слабые
    стороны, страхи, предназначение (Раху) и кармический багаж (Кету).
    """
    started = time.monotonic()
    if not user["birth_date"]:
        _log_astro(logging.WARNING, "astro_interpret_missing_birth_date", "нет даты для интерпретации карты", started,
                   status="missing", user_state="no_birth_date")
        raise HTTPException(400, "нет даты рождения")
    chart = users.chart_of(user)
    if not chart:
        _log_astro(logging.WARNING, "astro_interpret_missing_chart", "нет карты для интерпретации", started,
                   status="missing", user_state="no_saved_chart")
        raise HTTPException(400, "карта ещё не построена")
    text = chart.get("interpretation")
    if text:
        _log_astro(logging.INFO, "astro_interpret_cached", "разбор карты отдан из кэша", started,
                   chart, mode=chart.get("mode", "full"), precision=chart.get("precision", "exact"),
                   time_known=bool(user["birth_time_known"]), cache_hit=True, live=False,
                   status="ok", user_state="saved_interpretation")
    else:
        try:
            text, live = await agent_core.interpret_chart(db, user, chart)
        except Exception as exc:  # noqa: BLE001
            _log_astro(logging.ERROR, "astro_interpret_failed", "LLM-разбор карты завершился ошибкой", started,
                       chart, mode=chart.get("mode", "full"), precision=chart.get("precision", "exact"),
                       time_known=bool(user["birth_time_known"]), cache_hit=False, live=True,
                       status="error", error_type=type(exc).__name__, user_state="live_interpretation")
            raise
        # Кэшируем только LLM-генерацию: офлайн-заглушка не должна «залипать».
        if live:
            chart["interpretation"] = text
            await users.update(db, user["tg_id"],
                               chart_json=json.dumps(chart, ensure_ascii=False))
        _log_astro(logging.INFO, "astro_interpret_completed", "разбор карты подготовлен", started,
                   chart, mode=chart.get("mode", "full"), precision=chart.get("precision", "exact"),
                   time_known=bool(user["birth_time_known"]), cache_hit=False, live=bool(live),
                   status="ok", user_state="live_interpretation")
    return {"text": text, "structured": chart.get("interpretation_structured")}


@router.get("/matrix")
async def matrix(user=Depends(confirmed_age_user)):
    if not user["birth_date"]:
        raise HTTPException(400, "нет даты рождения")
    return compute_matrix(user["birth_date"])


@router.get("/chart/pdf", dependencies=[Depends(rate_limit("llm"))])
async def chart_pdf(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Полный PDF-разбор натальной карты через pdfgen."""
    if not user["birth_date"]:
        raise HTTPException(400, "сначала укажи дату рождения в профиле")
    try:
        pdf = await builder.build_natal_pdf_bytes(db, user)
    except render.PdfUnavailable:
        raise HTTPException(503, "PDF-генератор временно недоступен: установите WeasyPrint")
    except Exception as exc:
        raise HTTPException(500, "не удалось собрать PDF-разбор") from exc
    filename = f"oracle-natal-{user['tg_id']}.pdf"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=pdf, media_type="application/pdf", headers=headers)


# ─────────────────────────────── совместимость ────────────────────────────────

@router.post("/compat", dependencies=[Depends(rate_limit("write"))])
async def compat(item: CompatIn, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """«Спидометр любви»: балл и его разбор считает сервер.

    Формула живёт в одном месте специально: раньше у клиента была своя копия, и
    Mini App показывал балл, не совпадающий с ответом Оракула в чате.
    """
    if not user["birth_date"]:
        raise HTTPException(400, "нет даты рождения")
    partner_date = parse_birth_date(item.partner_date)
    return await compatibility_svc.calculate(
        db, user, partner_date, relation=item.relation,
        partner_name=item.partner_name, save=item.save)


@router.post("/compat/full", dependencies=[Depends(rate_limit("llm"))])
async def compat_full(item: CompatIn, user=Depends(active_user), db=Depends(get_db)):
    """Разбор пары Астрологом — расходует вопрос дня."""
    partner_date = parse_birth_date(item.partner_date)
    try:
        return await compatibility_svc.explain(
            db, user, partner_date, partner_name=item.partner_name,
            relation=item.relation, save=item.save)
    except compatibility_svc.CompatibilityDenied as exc:
        from ..common.errors import access_denied
        raise access_denied(exc.verdict, lang=user["lang"] or "ru") from exc


# ──────────────────────────────── партнёры ────────────────────────────────────

class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    birth_date: str
    relation: str = Field(default="partner", max_length=20)
    birth_time: str | None = None
    birth_city: str | None = Field(default=None, max_length=60)


@router.get("/partners")
async def partners(user=Depends(confirmed_age_user), db=Depends(get_db)):
    return await readings.list_partners(db, user["tg_id"])


@router.post("/partners", dependencies=[Depends(rate_limit("write"))])
async def add_partner(item: PartnerIn, user=Depends(confirmed_age_user),
                      db=Depends(get_db)):
    """Сохраняет человека из окружения — чтобы агент понимал «он»/«она»."""
    birth_date = parse_birth_date(item.birth_date)
    lat = lon = tz = None
    chart_data = None
    if item.birth_city:
        lat, lon, tz = await geo.resolve_city_async(item.birth_city, db)
        chart_data = await astro.compute_chart_async(
            birth_date, item.birth_time, item.birth_city, lat, lon, tz,
            time_known=bool(item.birth_time),
        )
    partner_id = await readings.add_partner(
        db, user["tg_id"], item.name.strip(), birth_date,
        relation=item.relation, birth_time=item.birth_time,
        birth_city=item.birth_city, lat=lat, lon=lon, tz=tz, chart=chart_data)
    if bool(user["memory_enabled"]):
        await memory.remember(db, user["tg_id"],
                              f"{item.relation}: {item.name} ({birth_date})",
                              kind="person")
    return {"id": partner_id, "ok": True}


@router.delete("/partners/{partner_id}", dependencies=[Depends(rate_limit("write"))])
async def delete_partner(partner_id: int, user=Depends(confirmed_age_user),
                         db=Depends(get_db)):
    await readings.delete_partner(db, partner_id, user["tg_id"])
    return {"ok": True}


# ───────────────────────────── купленные разборы ──────────────────────────────

class ReportIn(BaseModel):
    partner_date: str | None = None
    partner_name: str = Field(default="", max_length=30)


@router.get("/reports")
async def reports(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Список готовых разборов + права на ещё не собранные."""
    return {
        "ready": await readings.list_reports(db, user["tg_id"]),
        "available": [e for e in await billing.list_entitlements(db, user["tg_id"])
                      if e["kind"] == "report"],
    }


@router.get("/reports/{kind}")
async def get_report(kind: str, period: str | None = None,
                     report_id: int | None = Query(default=None, ge=1),
                     user=Depends(confirmed_age_user), db=Depends(get_db)):
    row = (
        await readings.get_report_by_id(db, user["tg_id"], kind, report_id)
        if report_id is not None
        else await readings.get_report(db, user["tg_id"], kind, period)
    )
    if not row:
        raise HTTPException(404, "такого разбора пока нет")
    return {"report_id": row["id"], "kind": row["kind"], "title": row["title"],
            "body": row["body"], "period": row["period"], "created_at": row["created_at"]}


@router.post("/reports/{kind}", dependencies=[Depends(rate_limit("llm"))])
async def build_report(kind: str, item: ReportIn | None = None,
                       refresh: bool = Query(default=False),
                       user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Собирает купленный разбор. Право списывается только после успеха."""
    if kind not in agent_core.REPORTS:
        raise HTTPException(404, "неизвестный разбор")
    item = item or ReportIn()

    existing = await readings.get_report(db, user["tg_id"], kind,
                                        item.partner_date if kind == "synastry" else None)
    if existing and existing["body"] and not refresh:
        await product_cost.record_event(
            db, event_kind="delivery", tg_id=user["tg_id"], sku=f"report:{kind}",
            channel="miniapp", result_category="report", status="delivered", units=1,
            reference_id=f"report:{existing['id']}")
        return {"kind": kind, "title": existing["title"], "body": existing["body"],
                "cached": True, "report_id": existing["id"]}

    if not await billing.available_entitlements(db, user["tg_id"], "report", kind):
        raise HTTPException(402, "этот разбор нужно открыть в лавке 💎")

    partner_date = parse_birth_date(item.partner_date) if item.partner_date else None
    if kind == "synastry" and not partner_date:
        raise HTTPException(400, "для синастрии нужна дата партнёра")

    with product_cost.context(
            sku=f"report:{kind}", channel="miniapp", result_category="report"):
        result = await agent_core.build_report(
            db, user, kind, partner_date=partner_date,
            partner_name=item.partner_name, force=refresh)
    if not await billing.consume_entitlement(db, user["tg_id"], "report", kind):
        # право исчезло между проверкой и списанием (второе устройство) —
        # отчёт уже сохранён, отдаём его, повторно не спишем
        pass
    await analytics.track(db, "report_built", user["tg_id"],
                          props={"kind": kind}, surface="miniapp")
    await product_cost.record_event(
        db, event_kind="delivery", tg_id=user["tg_id"], sku=f"report:{kind}",
        channel="miniapp", result_category="report", status="delivered", units=1,
        reference_id=f"report:{result.get('report_id') or 'cached'}")
    return result
