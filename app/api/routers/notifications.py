"""User-visible, owner-scoped notification inbox."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...services.repo_gateway import notifications, users
from ..deps import confirmed_age_user, get_db, rate_limit

router = APIRouter(prefix="/api", tags=["notifications"])


class NotificationPreferencesIn(BaseModel):
    morning_forecast: bool | None = None


_TAGS = re.compile(r"</?(?:b|i|strong|em)>", re.IGNORECASE)
_BREAKS = re.compile(r"<br ?/?>", re.IGNORECASE)


def _plain(value: str | None) -> str:
    text = str(value or "")
    return _TAGS.sub("", _BREAKS.sub(chr(10), text))[:4000]


@router.get("/notifications", dependencies=[Depends(rate_limit("read"))])
async def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    user=Depends(confirmed_age_user),
    db=Depends(get_db),
):
    """Return only the authenticated user's bounded notification inbox."""
    lang = user["lang"] if user["lang"] in {"ru", "en"} else "ru"
    await notifications.sync_daily_forecast(db, int(user["tg_id"]), lang=lang)
    payload = await notifications.list_for_user(db, int(user["tg_id"]), limit=limit)
    for item in payload["items"]:
        item["body"] = _plain(item.get("body"))
    payload["privacy"] = "Only server-owned summaries are shown; private chat text and provider payloads are excluded."
    return payload


@router.get("/notifications/preferences", dependencies=[Depends(rate_limit("read"))])
async def get_notification_preferences(user=Depends(confirmed_age_user)):
    """Return only supported user delivery preferences; provider settings stay admin-only."""
    return {
        "morning_forecast": bool(user["morning_push"]),
        "delivery_channel": "telegram_bot",
        "timezone": user["tz"],
        "supported": ["morning_forecast"],
    }


@router.patch("/notifications/preferences", dependencies=[Depends(rate_limit("write"))])
async def update_notification_preferences(item: NotificationPreferencesIn,
                                          user=Depends(confirmed_age_user), db=Depends(get_db)):
    if item.morning_forecast is None:
        return await get_notification_preferences(user)
    await users.update(db, int(user["tg_id"]), morning_push=int(item.morning_forecast))
    refreshed = await users.get(db, int(user["tg_id"]))
    return await get_notification_preferences(refreshed)


@router.post("/notifications/read-all", dependencies=[Depends(rate_limit("write"))])
async def mark_notifications_read(user=Depends(confirmed_age_user), db=Depends(get_db)):
    """Mark the current user's notifications read; repeating the call is safe."""
    changed = await notifications.mark_all_read(db, int(user["tg_id"]))
    payload = await notifications.list_for_user(db, int(user["tg_id"]), limit=100)
    return {"ok": True, "marked_count": changed, "unread_count": payload["unread_count"]}
