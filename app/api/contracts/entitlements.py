"""Response models for the entitlements aggregate (BUS-813, R07/G-13)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

EntitlementStatus = Literal["active", "grace", "cancelled", "expired", "free", "unknown"]


class EntitlementItem(BaseModel):
    """Одно купленное право (лидер-лимит с ledger entitlements)."""
    id: int
    kind: str
    code: str | None
    qty_total: int
    qty_used: int
    qty_left: int
    expires_at: str | None
    source: str
    order_id: int | None
    created_at: str | None
    # Статус подписки в момент выдачи агрегата — при grace/cancel/expired
    # право числится, но помечено неактивным состоянием подписки.
    subscription_status: EntitlementStatus
    usable: bool


class EntitlementsResponse(BaseModel):
    """Нормированный агрегат активных прав текущего пользователя."""
    tier: str
    subscription_status: EntitlementStatus
    period_end: str | None
    grace_until: str | None
    items: list[EntitlementItem]
