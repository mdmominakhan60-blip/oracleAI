"""API административной панели.

Права проверяются на каждом эндпоинте (`Depends(require(...))`), а изменяющие
действия пишутся в аудит. Причина: панель умеет дарить подписки, начислять
Кристаллы и писать всей базе — такие операции должны быть объяснимы задним числом.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator

from ...config import settings
from ...core import product_cost
from ...data.session import healthcheck
from ...services import analytics as analytics_svc
from ...services import billing as billing_svc
from ...services import broadcast as broadcast_svc
from ...services import payment_monitor
from ...services import telegram
from ...services.admin import (analytics_repo, billing, comms, content, crm,
                               growth, ltv_tier, users)
from ...services.admin import admin_repo, feedback_admin
from ..deps import current_admin, get_db, rate_limit, require

log = logging.getLogger("oracle.api.admin")


def _validate_json_budget(value, *, label: str, max_bytes: int = 64 * 1024,
                          max_depth: int = 8) -> None:
    """Reject oversized/deep admin JSON before persisting or auditing it."""
    def depth(item, level: int = 0) -> int:
        if level > max_depth:
            raise HTTPException(422, f"{label}: слишком глубокая структура")
        if isinstance(item, dict):
            return max([level] + [depth(v, level + 1) for v in item.values()])
        if isinstance(item, list):
            return max([level] + [depth(v, level + 1) for v in item])
        return level

    depth(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, f"{label}: невалидный JSON") from exc
    if len(encoded.encode("utf-8")) > max_bytes:
        raise HTTPException(413, f"{label}: значение слишком большое")


# rate-limit на весь роутер (G24): панель умеет дарить подписки и писать базе —
# 60 запросов в минуту на админа отсекают перебор и последствия утёкшего ключа
router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(rate_limit("admin"))])


# ─────────────────────────────── доступ ───────────────────────────────────────

@router.get("/me")
async def whoami(ctx=Depends(current_admin), db=Depends(get_db)):
    user = await users.get(db, ctx.tg_id)
    return {
        "tg_id": ctx.tg_id,
        "role": ctx.role,
        "name": (user["name"] if user else None) or "Администратор",
        "permissions": sorted(admin_repo.PERMISSIONS.get(ctx.role, set())),
    }


@router.get("/health")
async def health(ctx=Depends(require("dashboard")), db=Depends(get_db)):
    result = await healthcheck(db)
    # Не раскрываем URL или секреты, но владелец сразу видит, доступна ли
    # панель через кнопку Telegram, а не только на локальном адресе.
    result["telegram_webapp_ready"] = settings.webapp_url.startswith("https://")
    return result


# ────────────────────────────── аналитика ─────────────────────────────────────

@router.get("/dashboard")
async def dashboard(days: int = Query(default=30, ge=1, le=365),
                    ctx=Depends(require("dashboard")), db=Depends(get_db)):
    return await analytics_svc.dashboard(db, days=days)


@router.get("/dashboard/demo")
async def demo_dashboard(days: int = Query(default=30, ge=1, le=365),
                         ctx=Depends(current_admin)):
    """Owner-only synthetic preview; it never reads or writes operational data."""
    if ctx.role != "owner":
        raise HTTPException(403, "демо-режим доступен только владельцу")
    return await analytics_svc.demo_dashboard(days=days)


# ────────────── аналитика владельца (BUS-176 §4, BUS-229) ─────────────────────

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MIN_PERIOD = date(2024, 1, 1)


def _owner_period(from_: str | None, to: str | None) -> tuple[date, date]:
    """Валидация окна периода (§4.5): ISO-формат, from ≤ to, ≤ 365 дней.

    from/to опциональны: без них — последние 30 дней. Дата-нижняя граница
    отсекает опечатки вида 0024-09-01, которые лексикографика бы пропустила.
    """
    today = datetime.now(timezone.utc).date()
    try:
        d_from = date.fromisoformat(from_) if from_ else today - timedelta(days=29)
        d_to = date.fromisoformat(to) if to else today
    except ValueError as exc:
        raise HTTPException(422, "период ожидается в формате YYYY-MM-DD") from exc
    if d_from < _MIN_PERIOD or d_to < _MIN_PERIOD:
        raise HTTPException(422, "период вне допустимого диапазона")
    if d_from > d_to:
        raise HTTPException(422, "from должен быть не позже to")
    if (d_to - d_from).days > 365:
        raise HTTPException(422, "окно анализа не может превышать 365 дней")
    return d_from, d_to


def _no_store(payload) -> Response:
    return Response(content=json.dumps(payload, ensure_ascii=False),
                    media_type="application/json",
                    headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@router.get("/analytics/funnel")
async def analytics_funnel(from_: str | None = Query(default=None, alias="from"),
                           to: str | None = None,
                           source: str | None = Query(default=None, max_length=48),
                           surface: str | None = Query(default=None, max_length=16),
                           campaign: str | None = Query(default=None, max_length=64),
                           ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Visit-based воронка (§4.1): сессии сверху, пользователи снизу."""
    d_from, d_to = _owner_period(from_, to)
    if source and source not in analytics_repo._FUNNEL_SOURCES:
        raise HTTPException(422, f"неизвестный источник: {source}")
    if surface and surface not in analytics_repo._FUNNEL_SURFACES:
        raise HTTPException(422, f"неизвестная поверхность: {surface}")
    if campaign and not re.fullmatch(r"[A-Za-z0-9_\-.]{1,64}", campaign):
        raise HTTPException(422, "campaign — ascii-токен до 64 символов")
    payload = await analytics_repo.owner_funnel(
        db, date_from=d_from.isoformat(), date_to=d_to.isoformat(),
        source=source, surface=surface, campaign=campaign)
    return _no_store(payload)


@router.get("/analytics/retention")
async def analytics_retention(from_: str | None = Query(default=None, alias="from"),
                              to: str | None = None,
                              granularity: str = Query(default="day"),
                              ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Milestone-когорты по первому miniapp_open (§4.2); d30 — activity_fallback."""
    d_from, d_to = _owner_period(from_, to)
    if granularity not in ("day", "week"):
        raise HTTPException(422, "granularity — day или week")
    payload = await analytics_repo.owner_retention(
        db, date_from=d_from.isoformat(), date_to=d_to.isoformat(),
        granularity=granularity)
    return _no_store(payload)


@router.get("/analytics/revenue")
async def analytics_revenue(from_: str | None = Query(default=None, alias="from"),
                            to: str | None = None,
                            sku: str | None = Query(default=None, max_length=40),
                            ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Gross-деньги в Stars (§4.3); net остаётся null до settlement-входов."""
    d_from, d_to = _owner_period(from_, to)
    if sku and not re.fullmatch(r"[A-Za-z0-9_\-.]{1,40}", sku):
        raise HTTPException(422, "sku — ascii-токен до 40 символов")
    payload = await analytics_repo.owner_revenue(
        db, date_from=d_from.isoformat(), date_to=d_to.isoformat(), sku=sku)
    return _no_store(payload)


@router.get("/analytics/segments")
async def analytics_segments(by: str = Query(default="source"),
                             from_: str | None = Query(default=None, alias="from"),
                             to: str | None = None,
                             ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Сегменты аудитории (§4.4); сегменты <5 users агрегируются в other."""
    d_from, d_to = _owner_period(from_, to)
    if by not in ("source", "tier", "surface", "lifecycle"):
        raise HTTPException(422, "by — один из source|tier|surface|lifecycle")
    payload = await analytics_repo.owner_segments(
        db, by=by, date_from=d_from.isoformat(), date_to=d_to.isoformat())
    return _no_store(payload)


@router.get("/analytics/scenarios")
async def analytics_scenarios(from_: str | None = Query(default=None, alias="from"),
                              to: str | None = None,
                              scenario: str | None = None,
                              ctx=Depends(require("dashboard")),
                              db=Depends(get_db)):
    """Карточки CRM-сценариев R7 (BUS-264): вошло/дошло/конверсия/стопы.

    R9-gap-поведение: неснятый гэп конверсионной части — no_data с подписью
    причины и null-метриками, не ноль. Только агрегаты (privacy §2.3).
    """
    d_from, d_to = _owner_period(from_, to)
    if scenario is not None and scenario not in analytics_repo.SCENARIO_KEYS:
        raise HTTPException(
            422, "scenario — один из " + "|".join(analytics_repo.SCENARIO_KEYS))
    payload = await analytics_repo.owner_scenarios(
        db, date_from=d_from.isoformat(), date_to=d_to.isoformat(),
        scenario=scenario)
    return _no_store(payload)


@router.get("/payment-health")
async def payment_health(ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Aggregated payment/webhook health; no IDs, payloads or user PII."""
    return await payment_monitor.admin_snapshot(db)


@router.get("/reconciliation")
async def reconciliation(ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "сверка доступна только владельцу")
    return await payment_monitor.reconciliation(db)


@router.get("/reconciliation/{order_id}")
async def reconciliation_order(order_id: int = Path(..., ge=1, le=2_147_483_647),
                                  ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "сверка доступна только владельцу")
    return await payment_monitor.recheck_order(db, order_id)


@router.post("/reconciliation/{order_id}/review")
async def reconciliation_review(order_id: int = Path(..., ge=1, le=2_147_483_647),
                                  ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "сверка доступна только владельцу")
    result = await payment_monitor.mark_for_review(db, order_id, ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "payment.mark_for_review",
                           target=str(order_id), payload={"changed": result.get("marked_for_review", False)})
    return result


@router.get("/reconciliation/export")
async def reconciliation_export(ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "экспорт сверки доступен только владельцу")
    snapshot = await payment_monitor.admin_snapshot(db)
    recon = await payment_monitor.reconciliation(db)
    payload = {
        "export_version": 1,
        "checked_at": snapshot.get("checked_at"),
        "status": snapshot.get("status"),
        "provider_statuses": {key: value.get("status") for key, value in (snapshot.get("providers") or {}).items()},
        "reconciliation": {"anomaly_count": recon.get("count", 0),
                            "ledger_mismatches": recon.get("ledger_mismatches", 0)},
        "timeline_events": len((snapshot.get("checks") or {}).get("webhook_timeline") or []),
    }
    await admin_repo.audit(db, ctx.tg_id, "payment.reconciliation_export",
                           target="aggregate", payload={"status": payload["status"]})
    return Response(content=json.dumps(payload, ensure_ascii=False), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="payment-reconciliation.json"',
                             "Cache-Control": "no-store", "Pragma": "no-cache",
                             "X-Content-Type-Options": "nosniff"})


class NotificationPreferencesIn(BaseModel):
    degraded_cooldown_hours: int = Field(default=6, ge=1, le=168)
    critical_cooldown_hours: int = Field(default=1, ge=1, le=168)
    quiet_hours_start: str = Field(default="23:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    quiet_hours_end: str = Field(default="07:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    secondary_enabled: bool = False


@router.get("/payment-notifications")
async def payment_notifications(ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "настройки уведомлений доступны только владельцу")
    return await payment_monitor.notification_preferences(db)


@router.patch("/payment-notifications")
async def update_payment_notifications(item: NotificationPreferencesIn,
                                        ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "настройки уведомлений доступны только владельцу")
    result = await payment_monitor.save_notification_preferences(db, item.model_dump())
    await admin_repo.audit(db, ctx.tg_id, "payment.notifications.update",
                           target="payment_monitor", payload={key: result[key] for key in item.model_fields})
    return result


@router.get("/events")
async def events(days: int = Query(default=7, ge=1, le=90),
                 ctx=Depends(require("dashboard")), db=Depends(get_db)):
    return await analytics_repo.top_events(db, days=days, limit=40)


@router.get("/costs")
async def costs(days: int = Query(default=30, ge=1, le=365),
                ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Себестоимость LLM: сколько ушло токенов, на что и почём."""
    return await analytics_repo.llm_costs(db, days=days)


@router.get("/safety")
async def safety(days: int = Query(default=30, ge=1, le=365),
                 ctx=Depends(require("users:read")), db=Depends(get_db)):
    """Aggregate safety telemetry without crisis text or user identity."""
    return await analytics_repo.safety_summary(db, days=days)


@router.get("/safety/incidents")
async def safety_incidents(days: int = Query(default=30, ge=1, le=365),
                           limit: int = Query(default=100, ge=1, le=200),
                           ctx=Depends(require("safety:read")), db=Depends(get_db)):
    """Raw crisis excerpts for explicitly authorized safety reviewers only."""
    return await analytics_repo.safety_events(db, days=days, limit=limit)


# ─────────────── отзывы day-7 опроса (R6, BUS-237) ────────────────────────────

def _feedback_params(days: int, nps_min: int | None, nps_max: int | None,
                     question: str | None, choice: str | None,
                     moderation: str | None, text_query: str | None) -> dict:
    """Валидация фильтров R6: коды вопросов/вариантов — по allowlist day7_v1,
    модерация — только известные статусы. Невалидное значение → 422."""
    if question is not None:
        question = question[:32]
        allowed_choices = feedback_admin.CHOICES.get(question)
        if allowed_choices is None and question not in (
                *feedback_admin.SCORE_QUESTIONS, *feedback_admin.TEXT_QUESTIONS):
            raise HTTPException(422, f"неизвестный вопрос: {question}")
        if choice is not None:
            if question not in feedback_admin.CHOICES:
                raise HTTPException(422, "вариант выбирается для категориального вопроса")
            if choice not in allowed_choices:
                raise HTTPException(422, f"неизвестный вариант: {choice}")
    if moderation is not None and moderation not in feedback_admin.MODERATION_MAP.values():
        raise HTTPException(422, f"неизвестный статус модерации: {moderation}")
    if (nps_min is None) != (nps_max is None):
        raise HTTPException(422, "NPS-диапазон задаётся обеими границами")
    if nps_min is not None and nps_min > nps_max:
        raise HTTPException(422, "nps_min должен быть не больше nps_max")
    return {}


@router.get("/feedback/summary")
async def feedback_summary(days: int = Query(default=90, ge=1, le=365),
                           ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """NPS-сводка и распределения Q1/Q2/Q5 + response rate (R6)."""
    return await feedback_admin.summary(db, days=days)


@router.get("/feedback/responses")
async def feedback_responses(days: int = Query(default=90, ge=1, le=365),
                             nps_min: int | None = Query(default=None, ge=0, le=10),
                             nps_max: int | None = Query(default=None, ge=0, le=10),
                             question: str | None = Query(default=None, max_length=32),
                             choice: str | None = Query(default=None, max_length=32),
                             moderation: str | None = Query(default=None, max_length=16),
                             text_query: str | None = Query(default=None, max_length=100),
                             limit: int = Query(default=50, ge=1, le=200),
                             offset: int = Query(default=0, ge=0),
                             ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Список отзывов с фильтрами (дата, NPS-диапазон, вопрос+вариант,
    модерация, поиск по free text). Free text — только здесь, не в CSV."""
    _feedback_params(days, nps_min, nps_max, question, choice, moderation, text_query)
    items, total = await feedback_admin.list_responses(
        db, days=days, nps_min=nps_min, nps_max=nps_max, question=question,
        choice=choice, moderation=moderation, text_query=text_query,
        limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/feedback/export")
async def feedback_export(days: int = Query(default=90, ge=1, le=365),
                          ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """CSV-экспорт отзывов (R8-срез): категориальные ответы и NPS, free text
    НЕ выгружается (только по явному разрешению владельца — вне MVP+).
    Экспорт owner/admin + audit trail (финальные права analyst — волна 2)."""
    if ctx.role not in ("owner", "admin"):
        raise HTTPException(403, "экспорт отзывов доступен владельцу и админу")
    rows = await feedback_admin.export_rows(db, days=days)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["tg_id", "created_at", "nps", "like", "blocker", "next",
                     "moderation", "bonus_granted"])
    for row in rows:
        writer.writerow([row["tg_id"], row["created_at"], row["nps"],
                         row["like"], row["blocker"], row["next"],
                         row["moderation"], row["bonus_granted"]])
    await admin_repo.audit(db, ctx.tg_id, "feedback.export",
                           target=feedback_admin.SURVEY_CODE,
                           payload={"count": len(rows), "days": days})
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="feedback-day7.csv"',
                             "Cache-Control": "no-store", "Pragma": "no-cache",
                             "X-Content-Type-Options": "nosniff"})


@router.get("/horoscopes")
async def horoscopes_day(day: str | None = None,
                         ctx=Depends(require("content:read")), db=Depends(get_db)):
    """Гороскопы на день: что сгенерировано и что уже ушло в каналы."""
    from ...services import horoscopes as horoscopes_svc
    return {"items": await horoscopes_svc.all_for_day(db, day),
            "channels": horoscopes_svc.channel_map()}


@router.post("/horoscopes/build")
async def horoscopes_build(day: str | None = None,
                           ctx=Depends(require("content:write")),
                           db=Depends(get_db)):
    """Собрать гороскопы вручную — не дожидаясь ночного тика планировщика."""
    from ...services import horoscopes as horoscopes_svc
    result = await horoscopes_svc.build_day(db, day)
    await admin_repo.audit(db, ctx.tg_id, "horoscopes.build",
                           target=result["day"], payload=result)
    return result


# ──────────────────────────────── CRM ─────────────────────────────────────────

@router.get("/users")
async def user_list(q: str = "", segment: str = "all",
                    limit: int = Query(default=50, ge=1, le=200),
                    offset: int = Query(default=0, ge=0),
                    order: str = "created_at",
                    ctx=Depends(require("users:read")), db=Depends(get_db)):
    rows = await users.search(db, q, segment, limit=limit, offset=offset, order=order)
    for row in rows:
        row["sub_active"] = users.sub_active(row)
        row["tags"] = await crm.tags_of(db, row["tg_id"])
    return {
        "items": rows,
        "total": await users.count(db, q, segment),
        "segments": sorted(users.SEGMENTS),
    }


# ────────────────────────── Аудитория (BUS-230, волна 1) ──────────────────────

@router.get("/audience/segments")
async def audience_segments(ctx=Depends(require("dashboard")),
                            db=Depends(get_db)):
    """Таблица сегментов crm-frame §1: размер и Δ7д.

    Счётчики идут через users.segment_count — равенство broadcast preview
    (§3.3 BUS-168) соблюдается конструкцией. Сегменты — фиксированный
    allowlist SEGMENTS, а не произвольные ключи: анти-reid разрез <5→other
    (BUS-176 §4.4) здесь не нужен, доступ уже под permission.
    """
    return await analytics_svc.audience_segments(db)


@router.get("/audience/segments/{segment}/users")
async def audience_segment_users(segment: str,
                                 limit: int = Query(default=50, ge=1, le=200),
                                 offset: int = Query(default=0, ge=0),
                                 ctx=Depends(require("users:read")),
                                 db=Depends(get_db)):
    """Детализация сегмента до списка клиенток (клик с таблицы → 360°).

    users:read — жёстче, чем у таблицы (dashboard): список tg_id — уже
    персональные данные. Неизвестный сегмент — 404, а не пустой список:
    «сегмента нет» и «сегмент пуст» — разные состояния для UI.
    """
    if segment not in users.SEGMENTS:
        raise HTTPException(404, f"неизвестный сегмент: {segment}")
    rows = await users.search(db, "", segment, limit=limit, offset=offset)
    for row in rows:
        row["sub_active"] = users.sub_active(row)
        row["tags"] = await crm.tags_of(db, row["tg_id"])
    return {
        "segment": segment,
        "items": rows,
        "total": await users.count(db, "", segment),
    }


@router.get("/audience/churn")
async def audience_churn(ctx=Depends(require("dashboard")),
                         db=Depends(get_db)):
    """Churn-карточки R3 BUS-168: expiring_3d/sleeping_14d со сплитом payer/free."""
    return await analytics_svc.audience_churn(db)


@router.get("/audience/goals")
async def audience_goals(ctx=Depends(require("dashboard")),
                         db=Depends(get_db)):
    """Разбивка аудитории по мотивации (G-11 BUS-175): GROUP BY goal."""
    return await analytics_repo.goal_split(db)


@router.get("/attention-queue")
async def attention_queue(ctx=Depends(require("dashboard")),
                          db=Depends(get_db)):
    """Очередь внимания оператора: 7 правил, on-demand (BUS-309).

    Счётчики counts/overdue — по всей очереди, не по лимиту 50.
    """
    return await ltv_tier.attention_queue(db, limit=50)


@router.get("/users/{tg_id}")
async def user_card(tg_id: int, ctx=Depends(require("users:read")),
                    db=Depends(get_db)):
    card = await crm.user_card(db, tg_id)
    if not card:
        raise HTTPException(404, "пользователь не найден")
    return card


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/users/{tg_id}/notes")
async def add_note(tg_id: int, item: NoteIn, ctx=Depends(require("crm:write")),
                   db=Depends(get_db)):
    note_id = await crm.add_note(db, tg_id, item.text, ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "note.add", target=str(tg_id))
    return {"id": note_id}


@router.delete("/notes/{note_id}")
async def delete_note(note_id: int, ctx=Depends(require("crm:write")),
                      db=Depends(get_db)):
    await crm.delete_note(db, note_id)
    await admin_repo.audit(db, ctx.tg_id, "note.delete", target=str(note_id))
    return {"ok": True}


class TagIn(BaseModel):
    tag: str = Field(min_length=1, max_length=40)


@router.post("/users/{tg_id}/tags")
async def add_tag(tg_id: int, item: TagIn, ctx=Depends(require("crm:write")),
                  db=Depends(get_db)):
    await crm.add_tag(db, tg_id, item.tag, ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "tag.add", target=str(tg_id),
                           payload={"tag": item.tag.strip().lower()})
    return {"tags": await crm.tags_of(db, tg_id)}


@router.delete("/users/{tg_id}/tags/{tag}")
async def remove_tag(tg_id: int, tag: str, ctx=Depends(require("crm:write")),
                     db=Depends(get_db)):
    await crm.remove_tag(db, tg_id, tag)
    await admin_repo.audit(db, ctx.tg_id, "tag.delete", target=str(tg_id),
                           payload={"tag": tag.strip().lower()})
    return {"tags": await crm.tags_of(db, tg_id)}


@router.get("/tags")
async def tags(ctx=Depends(require("users:read")), db=Depends(get_db)):
    return await crm.all_tags(db)


class GrantIn(BaseModel):
    kind: str                      # plan | crystals | spread | report | question
    code: str | None = None
    qty: int = Field(default=1, ge=1, le=10000)
    days: int | None = Field(default=None, ge=1, le=3650)
    reason: str = Field(default="", max_length=200)


@router.post("/users/{tg_id}/grant")
async def grant(tg_id: int, item: GrantIn, ctx=Depends(require("grants")),
                db=Depends(get_db)):
    """Подарок, компенсация или тест. Всё пишется в аудит.

    Каппинг по роли — матрица компенсаций BUS-284 §4.2: прямой grant подписки
    admin ≤7 дней, owner ≤30; кристаллы admin/owner ≤30✦ (сверх — owner).
    Проверка на уровне endpoint, до billing_svc.grant_manually.
    """
    if item.kind not in billing_svc.GRANT_KINDS:
        raise HTTPException(400, f"неизвестный вид: {item.kind}")
    if not await users.get(db, tg_id):
        raise HTTPException(404, "пользователь не найден")
    if item.kind == "plan" and ctx.role == "admin" and (item.days or 0) > 7:
        raise HTTPException(403, {
            "code": "grant_days_cap", "role": ctx.role, "max_days": 7})
    if item.kind == "plan" and ctx.role == "owner" and (item.days or 0) > 30:
        raise HTTPException(403, {
            "code": "grant_days_cap", "role": ctx.role, "max_days": 30})
    if item.kind == "crystals" and ctx.role == "admin" and item.qty > 30:
        raise HTTPException(403, {
            "code": "grant_crystals_cap", "role": ctx.role, "max_qty": 30})
    granted = await billing_svc.grant_manually(
        db, tg_id, item.kind, item.code, qty=item.qty, days=item.days,
        admin_id=ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "user.grant", target=str(tg_id),
                           payload={"kind": item.kind, "code": item.code,
                                    "qty": item.qty, "days": item.days,
                                    "reason": item.reason})
    return granted


# ─────────────── операторские подарки (BUS-310, BUS-284 §4) ──────────────────

#: Сколько дней trial доступно роли (матрица §4.2): support — 3; admin — 3/7/10;
#: owner — 3/7/10/14 (усиление PB-3).
OP_GIFT_DAYS = {"support": (3,), "admin": (3, 7, 10), "owner": (3, 7, 10, 14)}

#: Анти-абьюз: 3/7-дневные подарки — окно 60 дней; усиление 10/14 — 90 (PB-3).
OP_GIFT_COOLDOWN_DAYS = {3: 60, 7: 60, 10: 90, 14: 90}


class GiftIn(BaseModel):
    days: int
    reason: str = Field(min_length=1, max_length=500)


def _gift_error(code: str, status: int = 400, **extra) -> HTTPException:
    """Machine-readable ошибка подарка: FE рендерит по code, не по тексту."""
    return HTTPException(status, {"error": {"code": code, **extra}})


async def _gift_state(db, tg_id: int) -> dict:
    """Доступность подарков клиентке: окно анти-абьюза по последней выдаче.

    Окно определяется размером последнего подарка: 60д для 3/7-дневных,
    90д для усиления 10/14 (PB-3).
    """
    last_at = await growth.last_op_gift_at(db, tg_id)
    last_days = await growth.last_op_gift_days(db, tg_id)
    next_at = None
    if last_at:
        last = datetime.fromisoformat(last_at)
        window = OP_GIFT_COOLDOWN_DAYS.get(last_days, 60)
        next_at = last + timedelta(days=window)
    return {"last_at": last_at, "next_at": next_at}


@router.get("/users/{tg_id}/gift/eligibility")
async def gift_eligibility(tg_id: int, ctx=Depends(require("crm:write")),
                           db=Depends(get_db)):
    """Машин-readable готовность клиентки к подарку — для серых кнопок формы.

    FE строит форму по can() и этому статусу заранее (тред BUS-312 LTV3):
    не текстовое сообщение после submit, а окно/доступность до него.
    """
    if not await users.get(db, tg_id):
        raise HTTPException(404, "пользователь не найден")
    state = await _gift_state(db, tg_id)
    now = datetime.now(timezone.utc)
    ok = state["next_at"] is None or now >= state["next_at"]
    return {
        "allowed_days": list(OP_GIFT_DAYS.get(ctx.role, ())),
        "eligible": bool(OP_GIFT_DAYS.get(ctx.role)) and ok,
        "cooldown": not ok,
        "next_available_at": state["next_at"].isoformat() if not ok else None,
        "last_gift_at": state["last_at"],
    }


@router.post("/users/{tg_id}/gift")
async def gift(tg_id: int, item: GiftIn, ctx=Depends(require("crm:write")),
               db=Depends(get_db)):
    """Выдать операторский подарок: промокод из партии op_* (BUS-284 §4.1).

    Роль-гейтинг: support — 3д, admin — до 10, owner — до 14. Причина
    обязательна и пишется в аудит (user.gift) — объяснимость задним числом.
    Анти-абьюз §4.1.3: окно 60д (усиление — 90д) с последнего подарка.
    """
    allowed = OP_GIFT_DAYS.get(ctx.role, ())
    if item.days not in allowed:
        raise _gift_error("gift_days_not_allowed", 403,
                          role=ctx.role, allowed_days=list(allowed))
    if not await users.get(db, tg_id):
        raise HTTPException(404, "пользователь не найден")
    state = await _gift_state(db, tg_id)
    now = datetime.now(timezone.utc)
    if state["next_at"] and now < state["next_at"]:
        raise _gift_error("gift_cooldown", 409,
                          next_available_at=state["next_at"].isoformat())
    code = await growth.reserve_op_gift(db, item.days)
    if not code:
        raise _gift_error("gift_batch_empty", 409)
    # Факт выдачи конкретной клиентке — под её tg_id (анти-абьюз, таймлайн),
    # статус sent: код оператор передаёт в личном сообщении, не через бота.
    await comms.mark_sent(db, tg_id, "op_gift", code)
    await admin_repo.audit(db, ctx.tg_id, "user.gift", target=str(tg_id),
                           payload={"code": code, "days": item.days,
                                    "reason": item.reason})
    return {"code": code, "days": item.days, "reason": item.reason}


class StatusIn(BaseModel):
    status: str                    # active | blocked


@router.post("/users/{tg_id}/status")
async def set_status(tg_id: int, item: StatusIn, ctx=Depends(require("users:write")),
                     db=Depends(get_db)):
    if item.status not in ("active", "blocked"):
        raise HTTPException(400, "статус может быть active или blocked")
    await users.set_status(db, tg_id, item.status)
    await admin_repo.audit(db, ctx.tg_id, "user.status", target=str(tg_id),
                           payload={"status": item.status})
    return {"ok": True}


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=3500)


@router.post("/users/{tg_id}/message")
async def message_user(tg_id: int, item: MessageIn,
                       ctx=Depends(require("crm:write")), db=Depends(get_db)):
    """Личный ответ поддержки — прямо из карточки клиентки."""
    ok = await telegram.send_message(tg_id, item.text)
    await admin_repo.audit(db, ctx.tg_id, "user.message", target=str(tg_id),
                           payload={"ok": ok, "len": len(item.text)})
    if not ok:
        raise HTTPException(502, "Telegram не принял сообщение (возможно, бот заблокирован)")
    await crm.add_note(db, tg_id, f"[ответ поддержки] {item.text[:500]}", ctx.tg_id)
    return {"ok": True}


@router.post("/users/{tg_id}/anonymize")
async def anonymize(tg_id: int, ctx=Depends(require("users:write")),
                    db=Depends(get_db)):
    """«Удали мои данные»: PII и история стираются, финансовый след остаётся."""
    if ctx.role != "owner":
        raise HTTPException(403, "удаление данных доступно только владельцу")
    await users.anonymize(db, tg_id)
    await admin_repo.audit(db, ctx.tg_id, "user.anonymize", target=str(tg_id))
    return {"ok": True}


# ─────────────────────────── контент и настройки ──────────────────────────────

@router.get("/content")
async def content_list(kind: str | None = None,
                       ctx=Depends(require("content:read")), db=Depends(get_db)):
    return await content.list_content(db, kind)


class ContentIn(BaseModel):
    kind: str = Field(min_length=1, max_length=30)
    code: str = Field(min_length=1, max_length=60)
    title: str | None = None
    body: str | None = None
    meta: dict | None = None
    is_active: bool | None = None
    sort: int | None = None


@router.post("/content")
async def content_save(item: ContentIn, ctx=Depends(require("content:write")),
                       db=Depends(get_db)):
    _validate_json_budget(item.meta, label="meta")
    await content.upsert_content(
        db, item.kind, item.code, title=item.title, body=item.body,
        meta=item.meta, is_active=item.is_active, sort=item.sort,
        admin_id=ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "content.save",
                           target=f"{item.kind}/{item.code}")
    return {"ok": True}


@router.delete("/content/{kind}/{code}")
async def content_delete(kind: str, code: str,
                        ctx=Depends(require("content:write")), db=Depends(get_db)):
    await content.delete_content(db, kind, code)
    await admin_repo.audit(db, ctx.tg_id, "content.delete", target=f"{kind}/{code}")
    return {"ok": True}


@router.get("/settings")
async def settings_list(ctx=Depends(require("settings:read")), db=Depends(get_db)):
    return await content.all_settings(db)


class SettingIn(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: object = None


@router.post("/settings")
async def setting_save(item: SettingIn, ctx=Depends(require("settings:write")),
                       db=Depends(get_db)):
    _validate_json_budget(item.value, label="setting")
    await content.set_setting(db, item.key, item.value, ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "setting.save", target=item.key,
                           payload={"value": item.value})
    return {"ok": True}


@router.get("/flags")
async def flags(ctx=Depends(require("settings:read")), db=Depends(get_db)):
    return await content.list_flags(db)


class FlagIn(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    is_on: bool | None = None
    rollout_pct: int | None = Field(default=None, ge=0, le=100)
    description: str | None = None


@router.post("/flags")
async def flag_save(item: FlagIn, ctx=Depends(require("settings:write")),
                    db=Depends(get_db)):
    await content.set_flag(db, item.code, is_on=item.is_on,
                           rollout_pct=item.rollout_pct,
                           description=item.description, admin_id=ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "flag.save", target=item.code,
                           payload={"is_on": item.is_on,
                                    "rollout": item.rollout_pct})
    return {"ok": True}


# ────────────────────────── тарифы, товары, заказы ────────────────────────────

@router.get("/plans")
async def plans(ctx=Depends(require("catalog")), db=Depends(get_db)):
    return await billing.list_plans(db, public_only=False)


class PlanIn(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    fields: dict


@router.post("/plans")
async def plan_save(item: PlanIn, ctx=Depends(require("catalog")),
                    db=Depends(get_db)):
    _validate_json_budget(item.fields, label="plan fields")
    await billing.upsert_plan(db, item.code, **item.fields)
    await admin_repo.audit(db, ctx.tg_id, "plan.save", target=item.code,
                           payload=item.fields)
    return {"ok": True}


@router.get("/products")
async def products(ctx=Depends(require("catalog")), db=Depends(get_db)):
    return await billing.list_products(db, active_only=False)


class ProductIn(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    fields: dict


@router.post("/products")
async def product_save(item: ProductIn, ctx=Depends(require("catalog")),
                       db=Depends(get_db)):
    _validate_json_budget(item.fields, label="product fields")
    await billing.upsert_product(db, item.sku, **item.fields)
    await admin_repo.audit(db, ctx.tg_id, "product.save", target=item.sku,
                           payload=item.fields)
    return {"ok": True}


@router.get("/orders")
async def orders(status: str | None = None,
                 limit: int = Query(default=100, ge=1, le=500),
                 ctx=Depends(require("dashboard")), db=Depends(get_db)):
    return await billing.recent_orders(db, status=status, limit=limit)


@router.post("/orders/{order_id}/refund")
async def refund(order_id: int, ctx=Depends(require("grants")), db=Depends(get_db)):
    """Возврат: сначала Telegram, потом наша отметка.

    Обратный порядок оставил бы заказ «возвращённым» при отказе Telegram, и
    деньги остались бы у нас при обещанном возврате.
    """
    order = await billing.get_order(db, order_id)
    if not order or order["status"] != "paid":
        raise HTTPException(400, "заказ не оплачен или не найден")
    charge_id = await billing.payment_charge_id(db, order_id)
    if charge_id and not await telegram.refund_star_payment(order["tg_id"], charge_id):
        raise HTTPException(502, "Telegram отказал в возврате")
    await billing.refund_order(db, order_id)
    await product_cost.record_event(
        db, event_kind="refund", tg_id=order["tg_id"],
        sku=order["sku"] or order["kind"],
        channel=order["surface"] if order["surface"] in {"bot", "miniapp", "web"} else "system",
        result_category=order["kind"], status="refunded", units=1,
        reference_id=f"order:{order_id}", order_id=order_id,
        reason="provider_refund")
    await admin_repo.audit(db, ctx.tg_id, "order.refund", target=str(order_id),
                           payload={"tg_id": order["tg_id"],
                                    "stars": order["amount_stars"]})
    return {"ok": True}


# ─────────────────────────────── промокоды ────────────────────────────────────

@router.get("/promo")
async def promo_list(batch: str | None = None, unused: bool = False,
                     code: str | None = None,
                     ctx=Depends(require("promo")), db=Depends(get_db)):
    """`code` — точный поиск кода (CS-сценарий BUS-317 G2), комбинируется с batch."""
    return {"batches": await growth.batch_stats(db),
            "codes": await growth.list_codes(db, batch=batch, unused_only=unused,
                                             code=code)}


@router.get("/promo/redemptions")
async def promo_redemptions(batch: str | None = None,
                            limit: int = Query(default=200, ge=1, le=1000),
                            ctx=Depends(require("promo")), db=Depends(get_db)):
    """Кто и когда активировал купоны."""
    return await growth.list_redemptions(db, batch=batch, limit=limit)


@router.get("/promo/op-report")
async def promo_op_report(months: int = Query(default=6, ge=1, le=24),
                          ctx=Depends(require("dashboard")), db=Depends(get_db)):
    """Месячный отчёт по партиям op_*: redemption rate + конверсия в оплату.

    Данные для KPI §5 плейбука (BUS-284): экономика операторских подарков
    видна без права promo — право dashboard, как у прочих отчётов панели.
    """
    return {"batches": await growth.op_batches_report(db, months=months)}


@router.get("/promo/export")
async def promo_export(batch: str = Query(min_length=1, max_length=40),
                       ctx=Depends(require("promo")), db=Depends(get_db)):
    """CSV партии для загрузки в карточку маркетплейса (BUS-317 G1).

    Одна строка = один код, колонки expires/sku — опциональные по аудиту
    BUS-289. Паттерн reconciliation/export: no-store + audit-лог.
    """
    codes = await growth.batch_codes(db, batch)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["code", "kind", "days", "plan_code", "crystals", "sku",
                     "batch", "max_uses", "used_count", "expires_at", "is_active"])
    for row in codes:
        writer.writerow([row["code"], row["kind"] or "", row["days"] or 0,
                         row["plan_code"] or "", row["crystals"] or 0,
                         row["sku"] or "", row["batch"] or "",
                         row["max_uses"] or 1, row["used_count"] or 0,
                         row["expires_at"] or "", row["is_active"] if
                         row["is_active"] is not None else 1])
    await admin_repo.audit(db, ctx.tg_id, "promo.export", target=batch,
                           payload={"count": len(codes)})
    filename = f"promo-{re.sub(r'[^A-Za-z0-9_.-]', '_', batch)}.csv"
    return Response(content=buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "Cache-Control": "no-store", "Pragma": "no-cache",
                             "X-Content-Type-Options": "nosniff"})


class PromoStateIn(BaseModel):
    batch: str | None = Field(default=None, max_length=40)
    code: str | None = Field(default=None, min_length=1, max_length=40)
    active: bool

    @model_validator(mode="after")
    def _one_target(self) -> "PromoStateIn":
        if (self.batch is None) == (self.code is None):
            raise ValueError("нужен ровно один таргет: batch или code")
        return self


@router.post("/promo/state")
async def promo_set_state(item: PromoStateIn, ctx=Depends(require("promo")),
                          db=Depends(get_db)):
    """Отзыв (is_active=0) или возврат в строй партии/кода — kill switch (G3)."""
    changed = await growth.set_codes_active(
        db, batch=item.batch, code=item.code, active=item.active)
    await admin_repo.audit(
        db, ctx.tg_id, "promo.set_state",
        target=item.batch or item.code or "",
        payload={"active": item.active, "changed": changed})
    if not changed:
        raise HTTPException(404, "партия или код не найдены")
    return {"changed": changed}


class PromoBatchIn(BaseModel):
    count: int = Field(ge=1, le=1000)
    kind: str = "plan_days"
    days: int = Field(default=30, ge=1, le=3650)
    plan_code: str = "vip"
    crystals: int = Field(default=0, ge=0, le=10000)
    sku: str | None = None
    batch: str = Field(default="manual", max_length=40)
    max_uses: int = Field(default=1, ge=1, le=100000)
    valid_days: int | None = Field(default=None, ge=1, le=3650)
    prefix: str = Field(default="ORA-", max_length=8)


@router.post("/promo")
async def promo_create(item: PromoBatchIn, ctx=Depends(require("promo")),
                       db=Depends(get_db)):
    codes = await growth.create_codes(
        db, item.count, kind=item.kind, days=item.days, plan_code=item.plan_code,
        crystals=item.crystals, sku=item.sku, batch=item.batch,
        max_uses=item.max_uses, valid_days=item.valid_days,
        created_by=ctx.tg_id, prefix=item.prefix)
    await admin_repo.audit(db, ctx.tg_id, "promo.create", target=item.batch,
                           payload={"count": len(codes), "kind": item.kind})
    return {"codes": codes}


# ─────────────────────────────── рассылки ─────────────────────────────────────

@router.get("/broadcasts")
async def broadcast_list(ctx=Depends(require("broadcast")), db=Depends(get_db)):
    items = await comms.list_broadcasts(db)
    for item in items:
        item["progress"] = await comms.broadcast_progress(db, item["id"])
    return items


class BroadcastIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=3500)
    segment: str = "all"
    button_text: str | None = Field(default=None, max_length=40)
    button_url: str | None = None
    scheduled_at: str | None = None
    send_now: bool = False


@router.post("/broadcasts/preview")
async def broadcast_preview(item: BroadcastIn, ctx=Depends(require("broadcast")),
                            db=Depends(get_db)):
    """Сколько человек попадёт в сегмент — до создания рассылки."""
    return await broadcast_svc.preview(db, item.segment)


@router.post("/broadcasts")
async def broadcast_create(item: BroadcastIn, ctx=Depends(require("broadcast")),
                           db=Depends(get_db)):
    """Создаёт рассылку. Отправляет её процесс бота — он владеет соединением.

    `send_now` ставит время отправки «сейчас»: бот подхватит очередь ближайшим
    проходом (до минуты) и продолжит с места обрыва, если его перезапустят.
    """
    if item.segment not in users.SEGMENTS:
        raise HTTPException(400, f"неизвестный сегмент: {item.segment}")
    scheduled = comms.utcnow() if item.send_now else item.scheduled_at
    result = await broadcast_svc.schedule(
        db, title=item.title, body=item.body, segment=item.segment,
        button_text=item.button_text, button_url=item.button_url,
        scheduled_at=scheduled, admin_id=ctx.tg_id)
    return result


@router.post("/broadcasts/{broadcast_id}/start")
async def broadcast_start(broadcast_id: int, ctx=Depends(require("broadcast")),
                          db=Depends(get_db)):
    await comms.set_broadcast_status(db, broadcast_id, "scheduled",
                                    scheduled_at=comms.utcnow())
    await admin_repo.audit(db, ctx.tg_id, "broadcast.start",
                           target=str(broadcast_id))
    return {"ok": True}


@router.post("/broadcasts/{broadcast_id}/cancel")
async def broadcast_cancel(broadcast_id: int, ctx=Depends(require("broadcast")),
                           db=Depends(get_db)):
    await broadcast_svc.cancel(db, broadcast_id, ctx.tg_id)
    return {"ok": True}


# ──────────────────────── администраторы и аудит ──────────────────────────────

@router.get("/admins")
async def admins(ctx=Depends(require("settings:read")), db=Depends(get_db)):
    return await admin_repo.list_admins(db)


class AdminIn(BaseModel):
    tg_id: int = Field(gt=0)
    role: str = "admin"
    title: str = Field(default="", max_length=60)


@router.post("/admins")
async def admin_add(item: AdminIn, ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "менять состав администраторов может только владелец")
    try:
        await admin_repo.add_admin(db, item.tg_id, item.role, title=item.title,
                                   added_by=ctx.tg_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    await admin_repo.audit(db, ctx.tg_id, "admin.add", target=str(item.tg_id),
                           payload={"role": item.role})
    return {"ok": True}


class AdminRoleIn(BaseModel):
    role: str
    title: str | None = Field(default=None, max_length=60)


@router.patch("/admins/{tg_id}")
async def admin_set_role(tg_id: int, item: AdminRoleIn,
                         ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "менять роли может только владелец")
    if tg_id == ctx.tg_id:
        raise HTTPException(400, "нельзя менять свою роль")
    try:
        changed = await admin_repo.update_admin_role(
            db, tg_id, item.role, title=item.title, changed_by=ctx.tg_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not changed:
        raise HTTPException(404, "администратор не найден")
    await admin_repo.audit(db, ctx.tg_id, "admin.role", target=str(tg_id),
                           payload={"role": item.role})
    return {"ok": True}


@router.delete("/admins/{tg_id}")
async def admin_remove(tg_id: int, ctx=Depends(current_admin), db=Depends(get_db)):
    if ctx.role != "owner":
        raise HTTPException(403, "менять состав администраторов может только владелец")
    if tg_id == ctx.tg_id:
        raise HTTPException(400, "нельзя разжаловать себя")
    await admin_repo.remove_admin(db, tg_id)
    await admin_repo.audit(db, ctx.tg_id, "admin.remove", target=str(tg_id))
    return {"ok": True}


@router.get("/audit")
async def audit_log(limit: int = Query(default=200, ge=1, le=1000),
                    ctx=Depends(require("dashboard")), db=Depends(get_db)):
    return await admin_repo.audit_log(db, limit=limit)
