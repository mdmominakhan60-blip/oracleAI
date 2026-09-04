"""API административной панели.

Права проверяются на каждом эндпоинте (`Depends(require(...))`), а изменяющие
действия пишутся в аудит. Причина: панель умеет дарить подписки, начислять
Кристаллы и писать всей базе — такие операции должны быть объяснимы задним числом.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from ...config import settings
from ...core import product_cost
from ...data.session import healthcheck
from ...services import analytics as analytics_svc
from ...services import billing as billing_svc
from ...services import broadcast as broadcast_svc
from ...services import payment_monitor
from ...services import telegram
from ...services.admin import (analytics_repo, billing, comms, content, crm,
                               growth, users)
from ...services.admin import admin_repo
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
    """Подарок, компенсация или тест. Всё пишется в аудит."""
    if item.kind not in billing_svc.GRANT_KINDS:
        raise HTTPException(400, f"неизвестный вид: {item.kind}")
    if not await users.get(db, tg_id):
        raise HTTPException(404, "пользователь не найден")
    granted = await billing_svc.grant_manually(
        db, tg_id, item.kind, item.code, qty=item.qty, days=item.days,
        admin_id=ctx.tg_id)
    await admin_repo.audit(db, ctx.tg_id, "user.grant", target=str(tg_id),
                           payload={"kind": item.kind, "code": item.code,
                                    "qty": item.qty, "days": item.days,
                                    "reason": item.reason})
    return granted


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
                     ctx=Depends(require("promo")), db=Depends(get_db)):
    return {"batches": await growth.batch_stats(db),
            "codes": await growth.list_codes(db, batch=batch, unused_only=unused)}


@router.get("/promo/redemptions")
async def promo_redemptions(batch: str | None = None,
                            limit: int = Query(default=200, ge=1, le=1000),
                            ctx=Depends(require("promo")), db=Depends(get_db)):
    """Кто и когда активировал купоны."""
    return await growth.list_redemptions(db, batch=batch, limit=limit)


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
