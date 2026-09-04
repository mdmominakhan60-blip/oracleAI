"""Профиль, настройки, рефералка, health."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...config import settings
from ...core import agents
from ...core.personas import persona_list
from ...data.session import healthcheck
from ...services.repo_gateway import billing, content, dialog, readings, users
from ...services.repo_gateway import monetization as monetization_repo
from ...services import analytics, chat, limits, referrals
from ...services.entitlements import entitlements
from ..deps import (
    confirmed_age_user,
    current_user,
    deletion_user,
    get_db,
    rate_limit,
    touched_user,
)

router = APIRouter(prefix="/api", tags=["profile"])


async def _global_streak(db, tg_id: int) -> int:
    """Дней подряд с любым действием — «день с Оракулом».

    Активным считается день, когда было хотя бы одно взаимодействие: запись в
    дневнике, сообщение в чате, расклад или отметка практики. Дни в UTC — как в
    `dialog.diary_streak`. Агрегат по существующим таблицам, без миграций.
    """
    cur = await db.execute(
        "SELECT d FROM ("
        " SELECT substr(created_at,1,10) d FROM diary WHERE tg_id=:tg_id"
        " UNION SELECT substr(created_at,1,10) FROM messages WHERE tg_id=:tg_id AND role='user'"
        " UNION SELECT substr(created_at,1,10) FROM tarot_readings WHERE tg_id=:tg_id"
        " UNION SELECT substr(last_done,1,10) FROM practices WHERE tg_id=:tg_id AND last_done IS NOT NULL"
        ") ORDER BY d DESC LIMIT 400",
        {"tg_id": tg_id})
    dayset = {r["d"] for r in await cur.fetchall()}
    if not dayset:
        return 0
    cursor = date.today()
    if cursor.isoformat() not in dayset:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor.isoformat() in dayset:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@router.get("/health")
async def health(db=Depends(get_db)):
    """Минимальный liveness для Caddy/Docker без внутренней телеметрии."""
    db_state = await healthcheck(db)
    if settings.dev_mode:
        return {
            "ok": db_state["ok"],
            "db": db_state,
            "llm": {"enabled": settings.llm_enabled,
                    "chain": list(settings.provider_chain)},
            "dev_mode": True,
        }
    if not db_state["ok"]:
        from fastapi.responses import JSONResponse
        return JSONResponse({"ok": False}, status_code=503)
    return {"ok": True}


@router.get("/public/config", dependencies=[Depends(rate_limit("read"))])
async def public_config(db=Depends(get_db)):
    """Неавторизованные параметры для первого касания (аудит UX-009).

    Экран «открой бота» в Mini App показывается ДО того, как /api/me может
    ответить (пользователь ещё не нажимал /start), поэтому username бота для
    deep-link нужен без подписи. Секретов здесь нет: username бота публичен.
    """
    return {
        "bot_username": await content.get_setting(db, "brand.bot_username", "") or "",
        "webapp_url": settings.webapp_url,
    }


@router.get("/me")
async def me(user=Depends(touched_user), db=Depends(get_db)):
    """Всё, что нужно интерфейсу на старте: профиль, лимиты, тариф, фичи."""
    chart = users.chart_of(user)
    allowance = await limits.allowance(db, user, check_followup=False)
    canonical_entitlements = await entitlements.snapshot(db, user)
    await chat.track_open(db, user)
    flags = {f["code"]: bool(f["is_on"]) for f in await content.list_flags(db)}
    return {
        "tg_id": user["tg_id"],
        "name": user["name"],
        "username": user["username"],
        "oracle_name": user["oracle_name"],
        "persona": user["persona"],
        "tz": user["tz"],
        "birth_date": user["birth_date"],
        "birth_city": user["birth_city"],
        "birth_time_known": bool(user["birth_time_known"]),
        "onboarded": bool(user["onboarded"]),
        "sun": chart.get("sun"),
        "ascendant": chart.get("ascendant"),
        "chart_mode": chart.get("mode"),
        "chart_precision": chart.get("precision", "sun_only"),
        "chart_note": chart.get("note"),
        "planets": chart.get("planets", []),
        "crystals": user["crystals"],
        "sub_active": users.sub_active(user),
        "sub_days_left": users.sub_days_left(user),
        "plan": allowance.plan,
        "allowance": allowance.as_dict(),
        # старые поля — интерфейс мог кешироваться у клиенток
        "questions_left": allowance.left,
        "questions_total": allowance.limit,
        "memories": (await dialog.get_memories(db, user["tg_id"], limit=8)
                     if bool(user["memory_enabled"]) else []),
        "diary_streak": await dialog.diary_streak(db, user["tg_id"]),
        "global_streak": await _global_streak(db, user["tg_id"]),
        "morning_push": bool(user["morning_push"]),
        "memory_enabled": bool(user["memory_enabled"]),
        "lang": user["lang"] or "ru",
        "gender": user["gender"],
        "entitlements": await billing.list_entitlements(db, user["tg_id"]),
        "reports": await readings.list_reports(db, user["tg_id"]),
        "canonical_entitlements": canonical_entitlements,
        "subscription_lifecycle": {
            "status": canonical_entitlements["status"],
            "period_end": canonical_entitlements["period_end"],
            "cancel_at_period_end": canonical_entitlements["cancel_at_period_end"],
            "grace_until": canonical_entitlements["grace_until"],
        },
        "agents": await agents.agent_list(db, user),
        "flags": flags,
        "webapp_url": settings.webapp_url,
    }


class ExperimentExposureIn(BaseModel):
    """Только техническая метка варианта: без текста вопроса и личных данных."""
    experiment: str = Field(min_length=3, max_length=48, pattern=r"^[a-z0-9_:-]+$")
    variant: str = Field(min_length=1, max_length=24, pattern=r"^[a-z0-9_-]+$")


@router.get("/experiment-assignment", dependencies=[Depends(rate_limit("read"))])
async def experiment_assignment(experiment: str = Query(min_length=3, max_length=48),
                                user=Depends(current_user), db=Depends(get_db)):
    variant = await monetization_repo.assign_variant(db, user["tg_id"], experiment)
    await analytics.track(db, "experiment_exposure", user["tg_id"],
                          props={"experiment": experiment, "variant": variant}, surface="miniapp")
    return {"experiment": experiment, "variant": variant, "source": "server"}


@router.post("/experiment-exposure", dependencies=[Depends(rate_limit("write"))])
async def experiment_exposure(item: ExperimentExposureIn, user=Depends(current_user),
                              db=Depends(get_db)):
    """Фиксирует показ feature-варианта для последующего сравнения конверсий."""
    await analytics.track(db, "experiment_exposure", user["tg_id"],
                          props={"experiment": item.experiment, "variant": item.variant},
                          surface="miniapp")
    return {"ok": True}


class AccountDeletionIn(BaseModel):
    """Explicit confirmation prevents accidental irreversible deletion."""
    confirm: bool = Field(default=False)


@router.get("/account/privacy", dependencies=[Depends(rate_limit("read"))])
async def account_privacy(user=Depends(current_user)):
    payload = {
        "status": user["status"],
        "anonymization": {
            "delete_mode": "anonymize",
            "kept": ["settlement-safe payment/order trace", "aggregated analytics"],
            "removed_or_replaced": ["name", "username", "birth data", "private content", "memory text"],
            "note": "Payment records may be retained when legally or financially required; they are not used to restore the account.",
        },
        "categories": [
            {"key": "profile", "label": "Профиль и настройки", "exportable": True},
            {"key": "payment_history", "label": "История заказов и статусы", "exportable": True},
            {"key": "private_content", "label": "Чаты, память, дневник и расклады", "exportable": False},
            {"key": "accounting_trace", "label": "Служебный платёжный trace", "exportable": False},
        ],
    }
    return JSONResponse(content=payload, headers={
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    })


@router.get("/account/export", dependencies=[Depends(rate_limit("read"))])
async def export_account(user=Depends(current_user), db=Depends(get_db)):
    """Export a bounded, user-safe account view; never include raw private content."""
    payment_history = await billing.payment_history(db, user["tg_id"], limit=100)
    payload = {
        "export_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": {"name": user["name"], "lang": user["lang"], "tz": user["tz"],
                    "created_at": user["created_at"], "status": user["status"]},
        "payment_history": payment_history,
        "privacy": "Raw chats, memory text, diary text and provider payloads are excluded from this export.",
    }
    return JSONResponse(content=payload, headers={
        "Content-Disposition": 'attachment; filename="oracle-account-export.json"',
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    })


@router.post("/account/delete", dependencies=[Depends(rate_limit("write"))])
async def delete_account(item: AccountDeletionIn, user=Depends(deletion_user), db=Depends(get_db)):
    """Anonymize the current account while retaining only settlement-safe records."""
    if not item.confirm:
        raise HTTPException(400, "для удаления требуется явное подтверждение")
    already_deleted = user["status"] == "deleted"
    if not already_deleted:
        await users.anonymize(db, user["tg_id"])
        await analytics.track(db, "account_deleted", user["tg_id"],
                              props={"mode": "anonymized"}, surface="miniapp")
    return {"ok": True, "already_deleted": already_deleted, "status": "deleted"}


class ProfileIn(BaseModel):
    oracle_name: str | None = Field(default=None, max_length=30)
    persona: str | None = None
    morning_push: bool | None = None
    memory_enabled: bool | None = None
    lang: str | None = Field(default=None, max_length=8)
    gender: Literal["f", "m"] | None = None
    tz: str | None = Field(default=None, max_length=64)
    goal: str | None = Field(default=None, max_length=40)


@router.post("/profile", dependencies=[Depends(rate_limit("write"))])
@router.patch("/profile", dependencies=[Depends(rate_limit("write"))])
async def update_profile(item: ProfileIn, user=Depends(current_user),
                         db=Depends(get_db)):
    """Меняет настройки профиля. Пустые поля не трогаем."""
    fields: dict = {}
    if item.oracle_name:
        fields["oracle_name"] = item.oracle_name.strip()[:30]
    if item.persona:
        codes = {p["code"] for p in await persona_list(db)}
        if item.persona not in codes:
            raise HTTPException(400, "неизвестный образ")
        fields["persona"] = item.persona
    if item.morning_push is not None:
        fields["morning_push"] = int(item.morning_push)
    if item.memory_enabled is not None:
        fields["memory_enabled"] = int(item.memory_enabled)
    if item.goal:
        fields["goal"] = item.goal.strip()[:40]
    if item.lang is not None:
        lang = item.lang.strip().lower()
        if lang not in {"ru", "en"}:
            raise HTTPException(400, "поддерживаются языки ru и en")
        fields["lang"] = lang
    if "gender" in item.model_fields_set:
        fields["gender"] = item.gender
    if item.tz:
        from zoneinfo import ZoneInfo
        try:
            ZoneInfo(item.tz)
        except Exception:
            raise HTTPException(400, "неизвестная таймзона")
        fields["tz"] = item.tz
    if fields:
        await users.update(db, user["tg_id"], **fields)
        await analytics.track(db, "profile_update", user["tg_id"],
                              props={"fields": list(fields)}, surface="miniapp")
    return {"ok": True, "updated": list(fields)}


@router.get("/personas")
async def personas(db=Depends(get_db)):
    return await persona_list(db)


@router.get("/referral")
async def referral(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Экран рефералки: ссылка, статистика, текст для шеринга."""
    bot_username = await content.get_setting(db, "brand.bot_username", "") or ""
    stats = await referrals.stats(db, user["tg_id"])
    link = (referrals.link_for(bot_username, user["tg_id"]) if bot_username
            else f"?start=ref_{user['tg_id']}")
    return {
        "link": link,
        "bot_username": bot_username,
        "share_text": referrals.share_text(stats["bonus_per_invite"], user["lang"]),
        **stats,
    }


@router.get("/memories")
async def memories(user=Depends(confirmed_age_user), db=Depends(get_db)):
    if not bool(user["memory_enabled"]):
        return []
    return await dialog.memories_full(db, user["tg_id"], limit=60)


class MemoryIn(BaseModel):
    fact: str = Field(min_length=3, max_length=300)
    kind: str = Field(default="fact", max_length=20)


@router.post("/memories", dependencies=[Depends(rate_limit("write"))])
async def add_memory(item: MemoryIn, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Ручное добавление факта из Mini App — та же дедупликация, что у агента."""
    if not bool(user["memory_enabled"]):
        raise HTTPException(409, "память отключена в настройках приватности")
    await dialog.save_memory(db, user["tg_id"], item.fact.strip(),
                             kind=item.kind or "fact")
    return {"ok": True}


@router.delete("/memories/{memory_id}", dependencies=[Depends(rate_limit("write"))])
async def forget(memory_id: int, user=Depends(confirmed_age_user), db=Depends(get_db)):
    """«Забудь это» — клиентка должна управлять тем, что о ней помнят."""
    await dialog.forget_memory(db, memory_id, user["tg_id"])
    return {"ok": True}


@router.get("/faq")
async def faq(lang: Literal["ru", "en"] = Query("ru"), db=Depends(get_db)):
    """Публичный FAQ; язык выбирается явно, поэтому endpoint остаётся без auth."""
    items = await content.list_content(db, "faq", active_only=True)
    localized = [content.localized_item(item, lang) for item in items]
    return [{"code": i["code"], "title": i["title"], "body": i["body"]}
            for i in localized]
