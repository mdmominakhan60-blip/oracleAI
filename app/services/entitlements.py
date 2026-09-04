"""Single server-authoritative entitlement engine for Bot and Mini App."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..data.monetization_catalog import CAPABILITY_MATRIX, LEGACY_TIER_ALIASES
from ..repo import monetization as repo
from ..repo import users


@dataclass(frozen=True)
class CapabilityDecision:
    allowed: bool
    capability: str
    tier_code: str
    status: str
    reason: str
    limit: int = 0
    used: int = 0
    remaining: int = 0
    crystals: int = 0
    period_end: str | None = None
    variant: str | None = None

    def as_dict(self) -> dict:
        return {
            "allowed": self.allowed, "capability": self.capability,
            "tier": self.tier_code, "status": self.status, "reason": self.reason,
            "limit": self.limit, "used": self.used, "remaining": self.remaining,
            "crystals": self.crystals, "period_end": self.period_end,
            "variant": self.variant,
        }


class EntitlementService:
    """Resolve access from trusted subscription and ledger state only."""

    async def state(self, db, user) -> dict:
        tg_id = int(user["tg_id"])
        stored = await repo.get_subscription_state(db, tg_id)
        now = datetime.now(timezone.utc)
        period_end = None
        if stored and stored.get("period_end"):
            try:
                period_end = datetime.fromisoformat(stored["period_end"])
            except (TypeError, ValueError):
                period_end = None
        if stored and period_end and period_end > now and stored.get("status") in {"active", "cancelled", "grace"}:
            return stored

        if users.sub_active(user):
            legacy = str(user["sub_level"] or "free")
            tier = LEGACY_TIER_ALIASES.get(legacy, legacy)
            return {
                "tg_id": tg_id, "tier_code": tier, "catalog_version": "legacy",
                "price_book_version": "legacy", "status": "active",
                "period_start": None, "period_end": user["sub_until"],
                "cancel_at_period_end": 0, "grace_until": None,
                "ai_message_limit": 120 if tier != "free" else 0,
                "ai_messages_used": 0, "compute_budget_usd": 0.12 if tier != "free" else 0,
                "compute_used_usd": 0, "monthly_crystals_granted": 0,
                "updated_at": None,
            }
        return {
            "tg_id": tg_id, "tier_code": "free", "catalog_version": "legacy",
            "price_book_version": "legacy", "status": "free", "period_start": None,
            "period_end": None, "cancel_at_period_end": 0, "grace_until": None,
            "ai_message_limit": 0, "ai_messages_used": 0, "compute_budget_usd": 0,
            "compute_used_usd": 0, "monthly_crystals_granted": 0, "updated_at": None,
        }

    async def can_use(self, db, user, capability: str) -> CapabilityDecision:
        if not capability or len(capability) > 80:
            return CapabilityDecision(False, capability or "unknown", "free", "free", "invalid_capability")
        current = await self.state(db, user)
        tier = current["tier_code"]
        matrix = CAPABILITY_MATRIX.get(tier, CAPABILITY_MATRIX["free"])
        rule = matrix.get(capability, False)
        if rule is False:
            reason = "subscription_required" if capability.startswith(("ai.", "report.", "voice", "priority")) else "feature_not_in_tier"
            return CapabilityDecision(
                False, capability, tier, current["status"], reason,
                int(current.get("ai_message_limit") or 0), int(current.get("ai_messages_used") or 0),
                max(0, int(current.get("ai_message_limit") or 0) - int(current.get("ai_messages_used") or 0)),
                int(user["crystals"] or 0), current.get("period_end"),
            )
        limit = int(current.get("ai_message_limit") or 0)
        used = int(current.get("ai_messages_used") or 0)
        if capability == "ai.chat" and limit > 0 and used >= limit:
            return CapabilityDecision(
                False, capability, tier, current["status"], "ai_quota_exhausted", limit, used, 0,
                int(user["crystals"] or 0), current.get("period_end"),
            )
        return CapabilityDecision(
            True, capability, tier, current["status"], "allowed", limit, used,
            max(0, limit - used) if limit else 0, int(user["crystals"] or 0),
            current.get("period_end"),
        )

    async def snapshot(self, db, user) -> dict:
        current = await self.state(db, user)
        decisions = {}
        for capability in (
            "today.basic", "astro.basic", "astro.advanced", "tarot.basic", "tarot.advanced",
            "ai.chat", "ai.memory", "ai.deep_context", "report.natal.basic", "report.natal.deep",
            "report.synastry.deep", "voice", "priority_queue", "monthly_report",
        ):
            decisions[capability] = (await self.can_use(db, user, capability)).as_dict()
        return {
            "tier": current["tier_code"], "status": current["status"],
            "catalog_version": current["catalog_version"],
            "price_book_version": current["price_book_version"],
            "period_end": current.get("period_end"),
            "cancel_at_period_end": bool(current.get("cancel_at_period_end")),
            "grace_until": current.get("grace_until"),
            "ai_message_limit": int(current.get("ai_message_limit") or 0),
            "ai_messages_used": int(current.get("ai_messages_used") or 0),
            "ai_messages_remaining": max(0, int(current.get("ai_message_limit") or 0) - int(current.get("ai_messages_used") or 0)),
            "compute_budget_usd": float(current.get("compute_budget_usd") or 0),
            "compute_used_usd": float(current.get("compute_used_usd") or 0),
            "crystals": int(user["crystals"] or 0),
            "capabilities": decisions,
        }


entitlements = EntitlementService()

can_use = entitlements.can_use
snapshot = entitlements.snapshot
