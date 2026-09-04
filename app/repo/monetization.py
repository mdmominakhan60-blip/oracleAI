"""Persistence for the versioned monetization v2 model.

This module is additive. Legacy ``plans``, ``products``, ``orders``,
``entitlements`` and ``crystal_ledger`` remain the historical source for old
purchases; v2 writes are kept in the versioned tables and always retain the
legacy order/payment trail.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ..data.monetization_catalog import CATALOG_VERSION, PRICE_BOOK_VERSION
from ..data.session import transaction, utcnow


def _json(value) -> str:
    return json.dumps(value or [], ensure_ascii=False)


async def active_catalog_version(db) -> dict:
    cur = await db.execute(
        "SELECT * FROM catalog_versions WHERE status='active' "
        "ORDER BY effective_from DESC LIMIT 1")
    row = await cur.fetchone()
    return dict(row) if row else {
        "version": CATALOG_VERSION,
        "price_book_version": PRICE_BOOK_VERSION,
        "status": "active",
    }


async def price_item(db, code: str, *, item_type: str | None = None,
                     channel: str | None = None, include_inactive: bool = False):
    clauses = ["code=:code"]
    params: dict[str, object] = {"code": code}
    if item_type:
        clauses.append("item_type=:item_type")
        params["item_type"] = item_type
    if channel:
        clauses.append("channel=:channel")
        params["channel"] = channel
    if not include_inactive:
        clauses.append("is_active=1")
        clauses.append("is_public=1")
    # INVARIANT: clause fragments come from this function only (no user input).
    sql = ("SELECT * FROM price_book_items WHERE " + " AND ".join(clauses)
           + " ORDER BY effective_from DESC, id DESC LIMIT 1")
    cur = await db.execute(sql, params)
    row = await cur.fetchone()
    return dict(row) if row else None


async def list_price_items(db, *, item_type: str | None = None,
                           channel: str | None = None,
                           public_only: bool = True) -> list[dict]:
    clauses = [
        "price_book_version=(SELECT price_book_version FROM catalog_versions "
        "WHERE status='active' ORDER BY effective_from DESC LIMIT 1)"
    ]
    params: dict[str, object] = {}
    if item_type:
        clauses.append("item_type=:item_type")
        params["item_type"] = item_type
    if channel:
        clauses.append("channel=:channel")
        params["channel"] = channel
    if public_only:
        clauses.extend(["is_active=1", "is_public=1"])
    cur = await db.execute(
        "SELECT * FROM price_book_items WHERE " + " AND ".join(clauses) +
        " ORDER BY sort, id", params)
    return [dict(row) for row in await cur.fetchall()]


async def catalog_payload(db, *, current_state: dict | None = None) -> dict:
    plans = await list_price_items(db, item_type="plan", channel="web")
    annual = await list_price_items(db, item_type="annual_plan", channel="web")
    stars_plans = {row["code"]: row for row in await list_price_items(db, item_type="plan", channel="stars")}
    annual_by_code = {row["code"]: row for row in annual}
    stars_annual = {row["code"]: row for row in await list_price_items(db, item_type="annual_plan", channel="stars")}
    plan_payload = []
    for row in plans:
        stars = stars_plans.get(row["code"], {})
        plan_payload.append({
            "code": row["code"], "title": row["title"],
            "tagline": row["description"], "price_usd": (row["amount_minor"] or 0) / 100,
            "price_stars": stars.get("amount_stars", 0),
            "annual_price_usd": (annual_by_code.get(row["code"], {}).get("amount_minor") or 0) / 100,
            "annual_price_stars": stars_annual.get(row["code"], {}).get("amount_stars", 0),
            "period_days": row["period_days"], "features": json.loads(row["features_json"] or "[]"),
            "compute_budget_usd": row["expected_cost_usd"], "catalog_version": row["catalog_version"],
            "price_book_version": row["price_book_version"], "badge": "recommended" if row["code"] == "vip_plus" else None,
            "is_active": bool(row["is_active"]), "is_public": bool(row["is_public"]), "sort": row["sort"],
        })
    annual_payload = []
    for row in annual:
        stars = stars_annual.get(row["code"], {})
        annual_payload.append({
            "code": row["code"], "title": row["title"], "tagline": row["description"],
            "price_usd": (row["amount_minor"] or 0) / 100,
            "price_stars": stars.get("amount_stars", 0),
            "period_days": row["period_days"],
            "tier_code": row["tier_code"], "catalog_version": row["catalog_version"],
            "price_book_version": row["price_book_version"],
        })
    packs = await list_price_items(db, item_type="crystal_pack", channel="crypto")
    star_packs = {row["code"]: row for row in await list_price_items(db, item_type="crystal_pack", channel="stars")}
    pack_payload = []
    for row in packs:
        star = star_packs.get(row["code"], {})
        pack_payload.append({
            "sku": row["code"], "kind": "crystals", "title": row["title"],
            "description": row["description"], "crystals": row["crystal_qty"],
            "bonus": row["bonus_qty"], "price_usd": (row["amount_minor"] or 0) / 100,
            "price_stars": star.get("amount_stars", 0), "catalog_version": row["catalog_version"],
            "price_book_version": row["price_book_version"], "sort": row["sort"],
        })
    deep = await list_price_items(db, item_type="deep_operation", channel="internal")
    product_payload = [{
        "sku": row["code"], "kind": "deep_operation", "title": row["title"],
        "description": row["description"], "price_crystals": row["crystal_qty"],
        "expected_cost_usd": row["expected_cost_usd"], "grant_kind": row["grant_kind"],
        "grant_code": row["grant_code"], "grant_qty": row["grant_qty"],
        "valid_days": row["valid_days"], "catalog_version": row["catalog_version"],
        "price_book_version": row["price_book_version"], "sort": row["sort"],
    } for row in deep]
    version = await active_catalog_version(db)
    return {
        "catalog_version": version["version"], "price_book_version": version["price_book_version"],
        "plans": plan_payload, "annual_plans": annual_payload,
        "crystal_packs": pack_payload, "products": product_payload,
        "current_entitlements": current_state or {},
    }


async def get_subscription_state(db, tg_id: int) -> dict | None:
    cur = await db.execute(
        "SELECT * FROM subscription_state WHERE tg_id=:tg_id",
        {"tg_id": tg_id})
    row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_subscription_state(db, tg_id: int, *, tier_code: str,
                                    catalog_version: str, price_book_version: str,
                                    status: str, period_start: str | None,
                                    period_end: str | None, ai_message_limit: int,
                                    compute_budget_usd: float,
                                    monthly_crystals_granted: int,
                                    cancel_at_period_end: bool = False,
                                    grace_until: str | None = None) -> dict:
    now = utcnow()
    async with transaction(db):
        await db.execute(
            "INSERT INTO subscription_state("
            "tg_id,tier_code,catalog_version,price_book_version,status,"
            "period_start,period_end,cancel_at_period_end,grace_until,"
            "ai_message_limit,ai_messages_used,compute_budget_usd,"
            "compute_used_usd,monthly_crystals_granted,updated_at) "
            "VALUES(:tg_id,:tier_code,:catalog_version,:price_book_version,"
            ":status,:period_start,:period_end,:cancel_at_period_end,"
            ":grace_until,:ai_message_limit,0,:compute_budget_usd,0.0,"
            ":monthly_crystals_granted,:updated_at) "
            "ON CONFLICT (tg_id) DO UPDATE SET tier_code=excluded.tier_code, "
            "catalog_version=excluded.catalog_version, "
            "price_book_version=excluded.price_book_version, "
            "status=excluded.status, period_start=excluded.period_start, "
            "period_end=excluded.period_end, "
            "cancel_at_period_end=excluded.cancel_at_period_end, "
            "grace_until=excluded.grace_until, "
            "ai_message_limit=excluded.ai_message_limit, "
            "compute_budget_usd=excluded.compute_budget_usd, "
            "monthly_crystals_granted=excluded.monthly_crystals_granted, "
            "updated_at=excluded.updated_at",
            {
                "tg_id": tg_id, "tier_code": tier_code,
                "catalog_version": catalog_version,
                "price_book_version": price_book_version,
                "status": status, "period_start": period_start,
                "period_end": period_end,
                "cancel_at_period_end": int(cancel_at_period_end),
                "grace_until": grace_until,
                "ai_message_limit": max(0, int(ai_message_limit)),
                "compute_budget_usd": max(0.0, float(compute_budget_usd or 0)),
                "monthly_crystals_granted":
                    max(0, int(monthly_crystals_granted or 0)),
                "updated_at": now,
            })
    return (await get_subscription_state(db, tg_id)) or {}


async def reserve_usage(db, tg_id: int, operation_key: str, *, capability: str,
                        sku: str | None, catalog_version: str, tier_code: str,
                        period_start: str | None, compute_cost_usd: float = 0,
                        crystal_cost: int = 0, charged_source: str = "included") -> dict | None:
    now = utcnow()
    async with transaction(db):
        cur = await db.execute(
            "SELECT * FROM monetization_usage "
            "WHERE tg_id=:tg_id AND operation_key=:operation_key",
            {"tg_id": tg_id, "operation_key": operation_key})
        existing = await cur.fetchone()
        if existing:
            return dict(existing)
        cur = await db.execute(
            "INSERT INTO monetization_usage("
            "tg_id,operation_key,capability,sku,catalog_version,tier_code,"
            "period_start,units,compute_cost_usd,crystal_cost,charged_source,"
            "status,created_at,updated_at) "
            "VALUES(:tg_id,:operation_key,:capability,:sku,:catalog_version,"
            ":tier_code,:period_start,1,:compute_cost_usd,:crystal_cost,"
            ":charged_source,'reserved',:created_at,:updated_at) RETURNING id",
            {
                "tg_id": tg_id, "operation_key": operation_key,
                "capability": capability, "sku": sku,
                "catalog_version": catalog_version, "tier_code": tier_code,
                "period_start": period_start,
                "compute_cost_usd": max(0.0, float(compute_cost_usd or 0)),
                "crystal_cost": max(0, int(crystal_cost or 0)),
                "charged_source": charged_source,
                "created_at": now, "updated_at": now,
            })
        row = await cur.fetchone()
        usage_id = int(row["id"]) if row else 0
    cur = await db.execute(
        "SELECT * FROM monetization_usage WHERE id=:usage_id",
        {"usage_id": usage_id})
    row = await cur.fetchone()
    return dict(row) if row else None


async def finish_usage(db, tg_id: int, operation_key: str, *, status: str) -> bool:
    if status not in {"succeeded", "failed", "restored"}:
        raise ValueError("invalid monetization usage status")
    async with transaction(db):
        cur = await db.execute(
            "UPDATE monetization_usage SET status=:status, updated_at=:updated_at "
            "WHERE tg_id=:tg_id AND operation_key=:operation_key "
            "AND status='reserved'",
            {"status": status, "updated_at": utcnow(),
             "tg_id": tg_id, "operation_key": operation_key})
        return bool(cur.rowcount)


async def crystal_lot(db, tg_id: int, *, source: str, qty: int,
                     order_id: int | None = None, valid_days: int | None = None) -> int:
    if qty <= 0:
        return 0
    expires = None
    if valid_days:
        expires = (datetime.now(timezone.utc) + timedelta(days=valid_days)).isoformat()
    async with transaction(db):
        cur = await db.execute(
            "INSERT INTO crystal_lots(tg_id,source,order_id,original_qty,"
            "remaining_qty,expires_at,created_at) "
            "VALUES(:tg_id,:source,:order_id,:qty,:qty,:expires_at,:created_at) "
            "RETURNING id",
            {"tg_id": tg_id, "source": source, "order_id": order_id,
             "qty": qty, "expires_at": expires, "created_at": utcnow()})
        row = await cur.fetchone()
        return int(row["id"]) if row else 0


async def ensure_legacy_lot(db, tg_id: int, current_balance: int) -> None:
    if current_balance <= 0:
        return
    cur = await db.execute(
        "SELECT 1 FROM crystal_lots WHERE tg_id=:tg_id AND remaining_qty>0 LIMIT 1",
        {"tg_id": tg_id})
    if await cur.fetchone():
        return
    await crystal_lot(db, tg_id, source="legacy", qty=current_balance)


async def allocate_lots(db, tg_id: int, amount: int) -> list[tuple[int, int]]:
    """Atomically decrement non-expired lots, expiring bonus lots first."""
    if amount <= 0:
        return []
    now = utcnow()
    allocations: list[tuple[int, int]] = []
    remaining = amount
    async with transaction(db):
        cur = await db.execute(
            "SELECT id, remaining_qty FROM crystal_lots "
            "WHERE tg_id=:tg_id AND remaining_qty>0 "
            "AND (expires_at IS NULL OR expires_at>:now) "
            "ORDER BY (source='purchased'), expires_at, id",
            {"tg_id": tg_id, "now": now})
        lots = await cur.fetchall()
        for lot in lots:
            if remaining <= 0:
                break
            take = min(remaining, int(lot["remaining_qty"]))
            cur = await db.execute(
                "UPDATE crystal_lots SET remaining_qty=remaining_qty-:take "
                "WHERE id=:lot_id AND remaining_qty>=:take",
                {"take": take, "lot_id": lot["id"]})
            if cur.rowcount:
                allocations.append((int(lot["id"]), take))
                remaining -= take
        if remaining:
            raise ValueError("insufficient crystal lots")
    return allocations


async def increment_ai_usage(db, tg_id: int, limit: int) -> bool:
    """Increment a monthly AI counter only while the server-side limit remains."""
    async with transaction(db):
        cur = await db.execute(
            "UPDATE subscription_state SET ai_messages_used=ai_messages_used+1, "
            "updated_at=:updated_at "
            "WHERE tg_id=:tg_id AND status IN ('active','cancelled','grace') "
            "AND (ai_message_limit=0 OR ai_messages_used < :limit)",
            {"updated_at": utcnow(), "tg_id": tg_id,
             "limit": max(0, int(limit))})
        return bool(cur.rowcount)


async def set_cancel_at_period_end(db, tg_id: int, cancel: bool = True) -> dict | None:
    async with transaction(db):
        cur = await db.execute(
            "UPDATE subscription_state SET cancel_at_period_end=:cancel_flag, "
            "status=CASE WHEN :cancel_flag=1 AND status='active' THEN 'cancelled' "
            "WHEN :cancel_flag=0 AND status='cancelled' THEN 'active' "
            "ELSE status END, updated_at=:updated_at "
            "WHERE tg_id=:tg_id",
            {"cancel_flag": int(cancel), "updated_at": utcnow(),
             "tg_id": tg_id})
        if not cur.rowcount:
            return None
    return await get_subscription_state(db, tg_id)


async def transition_expired(db, tg_id: int) -> dict | None:
    now = utcnow()
    async with transaction(db):
        cur = await db.execute(
            "UPDATE subscription_state SET status='expired', tier_code='free', "
            "ai_message_limit=0, compute_budget_usd=0, updated_at=:updated_at "
            "WHERE tg_id=:tg_id AND period_end IS NOT NULL "
            "AND period_end<=:now AND status IN ('active','cancelled','grace')",
            {"updated_at": now, "tg_id": tg_id, "now": now})
        if not cur.rowcount:
            return await get_subscription_state(db, tg_id)
    return await get_subscription_state(db, tg_id)


async def dashboard(db, days: int = 30) -> dict:
    """Aggregate v2 monetization evidence without inventing net revenue."""
    since = (datetime.now(timezone.utc) - timedelta(days=max(1, int(days)))).isoformat()

    async def scalar(sql: str, params: dict | None = None):
        cur = await db.execute(sql, params or {})
        row = await cur.fetchone()
        return row[0] if row else 0

    cur = await db.execute(
        "SELECT tier_code, COUNT(*) users FROM subscription_state "
        "WHERE status IN ('active','cancelled','grace') "
        "GROUP BY tier_code ORDER BY users DESC")
    active_by_tier = {row["tier_code"]: int(row["users"] or 0)
                      for row in await cur.fetchall()}
    cur = await db.execute(
        "SELECT COALESCE(sku,'unknown') sku, COUNT(*) orders, "
        "COALESCE(SUM(amount_stars),0) stars "
        "FROM orders WHERE status='paid' AND paid_at>=:since "
        "GROUP BY sku ORDER BY stars DESC",
        {"since": since})
    revenue_by_sku = [{"sku": row["sku"], "orders": int(row["orders"] or 0),
                       "stars": int(row["stars"] or 0)}
                      for row in await cur.fetchall()]
    cur = await db.execute(
        "SELECT COALESCE(reason,'unknown') source, "
        "COALESCE(SUM(CASE WHEN delta>0 THEN delta ELSE 0 END),0) granted, "
        "COALESCE(SUM(CASE WHEN delta<0 THEN -delta ELSE 0 END),0) spent "
        "FROM crystal_ledger WHERE created_at>=:since GROUP BY reason",
        {"since": since})
    crystal_by_source = [{"source": row["source"],
                          "granted": int(row["granted"] or 0),
                          "spent": int(row["spent"] or 0)}
                         for row in await cur.fetchall()]
    cur = await db.execute(
        "SELECT event_kind, COUNT(*) events, COALESCE(SUM(cost_usd),0) cost_usd "
        "FROM product_cost_events WHERE created_at>=:since GROUP BY event_kind",
        {"since": since})
    cogs_by_kind = [{"event_kind": row["event_kind"],
                     "events": int(row["events"] or 0),
                     "cost_usd": round(float(row["cost_usd"] or 0), 6)}
                    for row in await cur.fetchall()]

    names = (
        "paywall_view", "paywall_choice", "invoice_created", "paid",
        "first_paid_action", "credit_pack_checkout_started", "credit_pack_paid",
        "credit_spent", "subscription_lifecycle", "report_delivered",
        "refund_completed",
    )
    funnel = {}
    for name in names:
        funnel[name] = int(await scalar(
            "SELECT COUNT(*) FROM events WHERE name=:name AND created_at>=:since",
            {"name": name, "since": since}))

    paid_orders = int(await scalar(
        "SELECT COUNT(*) FROM orders WHERE status='paid' AND paid_at>=:since",
        {"since": since}))
    refunds = int(await scalar(
        "SELECT COUNT(*) FROM orders WHERE status='refunded' AND created_at>=:since",
        {"since": since}))
    repeat = int(await scalar(
        "SELECT COUNT(*) FROM (SELECT tg_id FROM orders WHERE status='paid' "
        "AND paid_at>=:since GROUP BY tg_id HAVING COUNT(*)>1) AS repeat_users",
        {"since": since}))
    outstanding = int(await scalar(
        "SELECT COALESCE(SUM(remaining_qty),0) FROM crystal_lots "
        "WHERE remaining_qty>0"))
    purchased = int(await scalar(
        "SELECT COALESCE(SUM(remaining_qty),0) FROM crystal_lots "
        "WHERE source='purchased' AND remaining_qty>0"))
    bonus = int(await scalar(
        "SELECT COALESCE(SUM(remaining_qty),0) FROM crystal_lots "
        "WHERE source='subscription_bonus' AND remaining_qty>0"))
    return {
        "window_days": int(days), "since": since,
        "revenue": {"paid_orders": paid_orders, "refunded_orders": refunds,
                    "refund_rate_pct": round(refunds * 100 / paid_orders, 2)
                    if paid_orders else 0.0,
                    "gross_stars": int(await scalar(
                        "SELECT COALESCE(SUM(amount_stars),0) FROM payments "
                        "WHERE status='succeeded' AND created_at>=:since",
                        {"since": since})),
                    "by_sku": revenue_by_sku, "net_revenue_estimate": None},
        "subscription": {"active_by_tier": active_by_tier,
                         "new_paid_users": int(await scalar(
                             "SELECT COUNT(DISTINCT tg_id) FROM orders "
                             "WHERE status='paid' AND paid_at>=:since",
                             {"since": since})),
                         "repeat_payers": repeat,
                         "renewal_and_churn":
                             "not_available_without provider lifecycle exports"},
        "crystals": {"by_source": crystal_by_source, "outstanding": outstanding,
                     "purchased_outstanding": purchased, "bonus_outstanding": bonus,
                     "repeat_purchase_users": int(await scalar(
                         "SELECT COUNT(*) FROM (SELECT tg_id FROM orders "
                         "WHERE kind='crystals' AND status='paid' "
                         "AND paid_at>=:since GROUP BY tg_id HAVING COUNT(*)>1) "
                         "AS repeat_crystal_users",
                         {"since": since}))},
        "funnel": funnel,
        "cogs": {"by_kind": cogs_by_kind,
                 "total_variable_cost_usd": round(
                     sum(item["cost_usd"] for item in cogs_by_kind), 6)},
        "contribution_margin_estimate": None,
        "required_inputs": ["provider_settlement_realization",
                            "tax_and_withholding_rate", "refund_rate_by_channel",
                            "fixed_opex", "paid_marketing",
                            "provider_lifecycle_export"],
    }


async def assign_variant(db, tg_id: int, experiment: str,
                         variants: tuple[str, ...] = ("control", "price_b", "price_c")) -> str:
    """Return a deterministic sticky assignment for a user and experiment."""
    import hashlib
    safe_experiment = (experiment or "").strip().lower()[:48]
    choices = tuple(v for v in variants if v and len(v) <= 24)
    if not safe_experiment or not choices:
        raise ValueError("invalid experiment")
    cur = await db.execute(
        "SELECT variant FROM monetization_assignments "
        "WHERE tg_id=:tg_id AND experiment=:experiment",
        {"tg_id": tg_id, "experiment": safe_experiment})
    row = await cur.fetchone()
    if row:
        return row["variant"]
    digest = hashlib.sha256(f"{tg_id}:{safe_experiment}".encode()).digest()
    variant = choices[int.from_bytes(digest[:4], "big") % len(choices)]
    async with transaction(db):
        await db.execute(
            "INSERT INTO monetization_assignments("
            "tg_id,experiment,variant,assigned_at) "
            "VALUES(:tg_id,:experiment,:variant,:assigned_at) "
            "ON CONFLICT (tg_id, experiment) DO NOTHING",
            {"tg_id": tg_id, "experiment": safe_experiment,
             "variant": variant, "assigned_at": utcnow()})
    cur = await db.execute(
        "SELECT variant FROM monetization_assignments "
        "WHERE tg_id=:tg_id AND experiment=:experiment",
        {"tg_id": tg_id, "experiment": safe_experiment})
    row = await cur.fetchone()
    return row["variant"] if row else variant
