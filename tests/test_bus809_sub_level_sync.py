"""BUS-809 / G-10: транзакционная синхронизация users.sub_level ↔ subscription_state.tier_code.

- upsert_subscription_state пишет sub_level тем же коммитом;
- upsert без state-строки (вне транзакции sync) users не трогает — legacy-канон цел;
- refund-revoke (billing.py:198) гасит ОБЕ стороны: sub_level и tier_code 'free'.
"""
from __future__ import annotations

import pytest

from app.repo import billing as billing_repo
from app.repo import monetization as monetization_repo
from app.repo import subscription_sync
from app.repo import users as users_repo

TG = 9001


@pytest.fixture
async def sync_on(db):
    """Флаг subscription_sync включён (Phase4 cut-over, план BUS-735 r2)."""
    from app.repo import content
    await content.set_flag(db, "subscription_sync", is_on=True)


async def _paid_state(db, tg_id: int, tier: str = "vip_plus") -> None:
    await monetization_repo.upsert_subscription_state(
        db, tg_id, tier_code=tier, catalog_version="v2",
        price_book_version="v2", status="active",
        period_start="2026-09-01T00:00:00+00:00",
        period_end="2099-09-30T00:00:00+00:00",
        ai_message_limit=300, compute_budget_usd=1.0,
        monthly_crystals_granted=150)


async def test_upsert_syncs_sub_level(db, sync_on):
    """Путь записи state: users.sub_level совпадает с tier_code после upsert."""
    await users_repo.ensure(db, TG, "Синк")
    await _paid_state(db, TG)
    user = await users_repo.get(db, TG)
    state = await monetization_repo.get_subscription_state(db, TG)
    assert user["sub_level"] == "vip_plus"
    assert state is not None and state["tier_code"] == "vip_plus"
    assert user["sub_level"] == state["tier_code"]


async def test_upsert_updates_sub_level_on_tier_change(db, sync_on):
    """Повторный upsert с другим tier перезаписывает sub_level тем же коммитом."""
    await users_repo.ensure(db, TG, "Синк")
    await _paid_state(db, TG, tier="vip_plus")
    await _paid_state(db, TG, tier="vip_core")
    user = await users_repo.get(db, TG)
    state = await monetization_repo.get_subscription_state(db, TG)
    assert user["sub_level"] == "vip_core"
    assert state is not None and state["tier_code"] == "vip_core"


async def test_revoke_keeps_both_sides_free(db):
    """refund-revoke (billing.py:198): sub_level и tier_code совпадают после операции."""
    await users_repo.ensure(db, TG, "Рефанд")
    await users_repo.extend_subscription(db, TG, "vip_plus", 30)
    await _paid_state(db, TG, tier="vip_plus")
    order = await billing_repo.create_order(
        db, TG, "plan", sku="vip_plus", title="VIP+", surface="web",
        meta={"grant_kind": "plan", "grant_code": "vip_plus", "grant_qty": 1,
              "valid_days": 30, "provider": "paddle",
              "paddle_transaction_id": "txn_bus809"})
    await billing_repo.mark_order_paid(db, order["payload"], charge_id="txn_bus809",
                                       amount_stars=0, provider="paddle",
                                       currency="USD")
    assert await billing_repo.queue_refund_revoke(
        db, order["id"], source="paddle") is True
    revoked = await billing_repo.complete_refund_revoke(
        db, order["id"], tg_id=TG)
    assert revoked is True
    user = await users_repo.get(db, TG)
    state = await monetization_repo.get_subscription_state(db, TG)
    assert user["sub_level"] == "free"
    assert state is not None and state["tier_code"] == "free"
    assert user["sub_level"] == state["tier_code"]
    assert state["status"] == "expired"


async def test_sync_no_state_row_leaves_users_alone(db):
    """Без строки state sync_sub_level — no-op: легальную legacy-подписку не трогаем."""
    await users_repo.ensure(db, TG, "Легаси")
    await users_repo.extend_subscription(db, TG, "vip", 30)
    tier = await subscription_sync.sync_sub_level(db, TG)
    assert tier is None
    user = await users_repo.get(db, TG)
    assert user["sub_level"] == "vip"


async def test_reconcile_dry_run_then_fix(db):
    """Сверка: dry-run только отчёт, fix выравнивает, повтор — 0 расхождений."""
    await users_repo.ensure(db, TG, "Сверка")
    await _paid_state(db, TG, tier="vip_core")
    # Ручное расхождение (как в проде до выката sync): users отстал от канона.
    await db.execute("UPDATE users SET sub_level='trial' WHERE tg_id=:tg_id",
                     {"tg_id": TG})

    dry = await subscription_sync.reconcile(db, dry_run=True)
    assert dry["divergent"] == 1
    assert dry["fixed"] == 0
    user = await users_repo.get(db, TG)
    assert user["sub_level"] == "trial"  # dry-run ничего не писал

    fix = await subscription_sync.reconcile(db, dry_run=False)
    assert fix["divergent"] == 1
    assert fix["fixed"] == 1
    user = await users_repo.get(db, TG)
    assert user["sub_level"] == "vip_core"

    again = await subscription_sync.reconcile(db, dry_run=False)
    assert again["divergent"] == 0
    assert again["fixed"] == 0


async def test_upsert_sync_gated_by_flag(db):
    """Флаг subscription_sync выключен (Phase0): upsert НЕ пишет users.sub_level."""
    await users_repo.ensure(db, TG, "Гейт")
    await _paid_state(db, TG, tier="vip_plus")
    user = await users_repo.get(db, TG)
    state = await monetization_repo.get_subscription_state(db, TG)
    assert state is not None and state["tier_code"] == "vip_plus"
    assert user["sub_level"] != "vip_plus"  # гейт Phase0: users не тронут
