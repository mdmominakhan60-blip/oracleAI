"""Активные права пользователя: единый агрегат ledger + подписка (BUS-813)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..contracts.entitlements import EntitlementItem, EntitlementsResponse
from ..deps import current_user, get_db, rate_limit
from ...services import billing as billing_svc
from ...services.entitlements import entitlements

router = APIRouter(prefix="/api", tags=["entitlements"])

# Состояния подписки, при которых числящееся право нельзя применить:
# счётчики не сгорают (ledger), но UI должен показывать право как заблокированное.
_LOCKED_SUBSCRIPTION_STATUSES = {"grace", "cancelled", "expired"}


@router.get("/entitlements", response_model=EntitlementsResponse,
            dependencies=[Depends(rate_limit("read"))])
async def entitlements_view(user=Depends(current_user), db=Depends(get_db)):
    """Текущие активные права текущего пользователя (owner-scope, read-only).

    Owner-scope: tg_id берётся только из аутентифицированной зависимости,
    параметра tg_id в контракте нет — чужие данные недостижимы.
    Fail-closed: нет прав — пустой список items.
    """
    tg_id = user["tg_id"]
    ledger = await billing_svc.user_entitlements(db, tg_id)
    state = await entitlements.snapshot(db, user)
    sub_status = state["status"]
    usable = sub_status not in _LOCKED_SUBSCRIPTION_STATUSES
    items = [EntitlementItem(
        id=int(row["id"]),
        kind=str(row["kind"]),
        code=row.get("code"),
        qty_total=int(row.get("qty_total") or 0),
        qty_used=int(row.get("qty_used") or 0),
        qty_left=max(0, int(row.get("qty_total") or 0) - int(row.get("qty_used") or 0)),
        expires_at=row.get("expires_at"),
        source=str(row.get("source") or "purchase"),
        order_id=row.get("order_id"),
        created_at=row.get("created_at"),
        subscription_status=sub_status,
        usable=usable,
    ) for row in ledger]
    return EntitlementsResponse(
        tier=state["tier"],
        subscription_status=sub_status,
        period_end=state.get("period_end"),
        grace_until=state.get("grace_until"),
        items=items,
    )
