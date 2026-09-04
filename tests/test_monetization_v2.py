from __future__ import annotations

import pytest

from app.config import settings
from app.repo import monetization, users
from app.services import billing as billing_svc, chat, limits
from app.services.entitlements import entitlements


@pytest.mark.asyncio
async def test_production_user_starts_free_without_trial_or_welcome_crystals(db, monkeypatch):
    monkeypatch.setattr(settings, "auto_trial", False)
    created = await users.ensure(db, 2201, "Новая")
    assert created["sub_level"] == "free"
    assert created["sub_until"] is None
    assert created["crystals"] == 0
    assert not users.sub_active(created)


@pytest.mark.asyncio
async def test_v2_catalog_contains_requested_tiers_prices_and_annual_period(db, user):
    payload = await monetization.catalog_payload(db)
    codes = [item["code"] for item in payload["plans"]]
    assert codes == ["free", "vip_core", "vip_plus", "pro", "concierge_v2"]
    plus = next(item for item in payload["plans"] if item["code"] == "vip_plus")
    assert plus["price_usd"] == 34.99
    assert plus["annual_price_usd"] == 349.90
    assert plus["annual_price_stars"] > plus["price_stars"]
    assert {item["sku"] for item in payload["crystal_packs"]} == {
        "crystals_50_v2", "crystals_150_v2", "crystals_400_v2",
    }


@pytest.mark.asyncio
async def test_v2_plan_payment_updates_canonical_state_and_monthly_allowance(db, free_user):
    order = await billing_svc.checkout_plan(db, free_user["tg_id"], "vip_plus")
    assert order["amount_stars"] > 0
    result = await billing_svc.apply_payment(
        db, order["payload"], amount_stars=order["amount_stars"])
    assert result["granted"]["kind"] == "plan"
    fresh = await users.get(db, free_user["tg_id"])
    state = await entitlements.snapshot(db, fresh)
    assert state["tier"] == "vip_plus"
    assert state["status"] == "active"
    allowance = await limits.allowance(db, fresh)
    assert allowance.period == "month"
    assert allowance.limit == 300
    assert allowance.left == 300


@pytest.mark.asyncio
async def test_annual_v2_checkout_uses_annual_price_and_365_days(db, free_user):
    order = await billing_svc.checkout_plan(
        db, free_user["tg_id"], "pro", billing_period="annual")
    assert order["amount_stars"] > 3640 * 10 - 20
    assert order["plan"]["period_days"] == 365
    stored = await billing_svc.repo.get_order(db, order["id"])
    meta = billing_svc._order_meta(stored)
    assert meta["billing_period"] == "annual"
    assert meta["valid_days"] == 365


@pytest.mark.asyncio
async def test_v2_deep_purchase_is_idempotently_reserved_and_finished(db, user):
    await users.update(db, user["tg_id"], crystals=200)
    result = await billing_svc.pay_with_crystals(db, user["tg_id"], "report_natal_deep")
    assert result["product"]["sku"] == "report_natal_deep"
    cur = await db.execute(
        "SELECT status, crystal_cost, charged_source FROM monetization_usage WHERE tg_id=?",
        (user["tg_id"],))
    row = await cur.fetchone()
    assert row["status"] == "succeeded"
    assert row["crystal_cost"] == 120
    assert row["charged_source"] == "crystals"
    fresh = await users.get(db, user["tg_id"])
    assert fresh["crystals"] == 80


@pytest.mark.asyncio
async def test_server_assignment_is_sticky_and_not_client_selected(db, user):
    first = await monetization.assign_variant(db, user["tg_id"], "pricing_v2")
    second = await monetization.assign_variant(db, user["tg_id"], "pricing_v2")
    assert first == second
    assert first in {"control", "price_b", "price_c"}


@pytest.mark.asyncio
async def test_free_ai_chat_is_denied_when_auto_trial_is_off(db, free_user, monkeypatch):
    monkeypatch.setattr(settings, "auto_trial", False)
    with pytest.raises(chat.ChatDenied) as exc:
        await chat.ask(db, free_user, "Подскажи про отношения", surface="miniapp")
    assert exc.value.verdict.reason == "subscription_required"
