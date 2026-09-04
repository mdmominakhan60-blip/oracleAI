"""Деньги: идемпотентность оплаты, баланс ✦, права доступа, промокоды, рефералы.

Самая важная группа тестов в проекте: ошибка здесь — это либо выданный бесплатно
товар, либо списанные и потерянные деньги клиентки.
"""
from __future__ import annotations

import asyncio

import pytest

from app.repo import analytics
from app.repo import billing as repo
from app.repo import growth, users
from app.services import billing as svc
from app.services import referrals


# ─────────────────────────── Кристаллы ────────────────────────────────────────

async def test_add_and_spend_crystals_records_ledger(db, user):
    balance = await repo.add_crystals(db, user["tg_id"], 50, "test_grant")
    assert balance == (user["crystals"] or 0) + 50

    assert await repo.spend_crystals(db, user["tg_id"], 20, "test_spend")
    history = await repo.crystal_history(db, user["tg_id"])
    assert history[0]["delta"] == -20
    assert history[0]["balance"] == balance - 20


async def test_spend_more_than_balance_is_refused(db, user):
    fresh = await users.get(db, user["tg_id"])
    too_much = (fresh["crystals"] or 0) + 1
    assert not await repo.spend_crystals(db, user["tg_id"], too_much, "test")
    after = await users.get(db, user["tg_id"])
    assert after["crystals"] == fresh["crystals"], "баланс изменился при отказе"


async def test_parallel_spends_cannot_overdraw(db, user):
    """Две одновременные покупки не должны увести баланс в минус.

    Проверка «хватает ли» отдельным SELECT давала именно эту гонку: оба вызова
    видели достаточный баланс и оба списывали.
    """
    await users.update(db, user["tg_id"], crystals=30)
    results = await asyncio.gather(
        repo.spend_crystals(db, user["tg_id"], 20, "a"),
        repo.spend_crystals(db, user["tg_id"], 20, "b"),
    )
    assert sum(results) == 1, "списались оба раза"
    fresh = await users.get(db, user["tg_id"])
    assert fresh["crystals"] == 10


# ──────────────────────────── заказы и оплата ─────────────────────────────────

async def test_order_payload_is_unique(db, user):
    first = await repo.create_order(db, user["tg_id"], "plan", sku="vip",
                                    amount_stars=1300)
    second = await repo.create_order(db, user["tg_id"], "plan", sku="vip",
                                     amount_stars=1300)
    assert first["payload"] != second["payload"]


async def test_payment_is_applied_once(db, user):
    """Telegram может доставить successful_payment повторно."""
    order = await svc.checkout_plan(db, user["tg_id"], "vip")
    first = await svc.apply_payment(db, order["payload"], charge_id="ch_1",
                                    amount_stars=order["amount_stars"])
    assert first and first["granted"]["kind"] == "plan"

    second = await svc.apply_payment(db, order["payload"], charge_id="ch_1",
                                     amount_stars=order["amount_stars"])
    assert second is None, "повторный вебхук выдал подписку дважды"

    cur = await db.execute("SELECT COUNT(*) c FROM payments WHERE tg_id=?",
                           (user["tg_id"],))
    assert (await cur.fetchone())["c"] == 1


async def test_payment_extends_subscription_and_ltv(db, free_user):
    order = await svc.checkout_plan(db, free_user["tg_id"], "vip")
    await svc.apply_payment(db, order["payload"], amount_stars=order["amount_stars"])
    fresh = await users.get(db, free_user["tg_id"])
    assert users.sub_active(fresh), "подписка не активировалась"
    assert fresh["sub_level"] == "vip"
    assert fresh["ltv_stars"] == order["amount_stars"]


async def test_renewal_adds_to_remaining_days(db, user):
    """Продление считается от текущего конца — оплата не сгорает."""
    before = users.sub_days_left(await users.get(db, user["tg_id"]))
    order = await svc.checkout_plan(db, user["tg_id"], "vip")
    await svc.apply_payment(db, order["payload"], amount_stars=order["amount_stars"])
    after = users.sub_days_left(await users.get(db, user["tg_id"]))
    assert after >= before + 29


async def test_unknown_payload_is_ignored(db):
    assert await svc.apply_payment(db, "o999:plan:nope") is None


async def test_payment_below_order_amount_is_refused(db, user):
    """Аудит 2.1: смена цены между инвойсом и оплатой не выдаёт грант."""
    order = await svc.checkout_plan(db, user["tg_id"], "vip")
    assert await svc.apply_payment(db, order["payload"],
                                   amount_stars=order["amount_stars"] - 1) is None
    fresh = await repo.order_by_payload(db, order["payload"])
    assert fresh["status"] == "pending", "недооплата пометила заказ paid"


async def test_payment_overpay_is_accepted(db, user):
    """Больше ожидаемого — не проблема (цены растут), грант выдаётся."""
    order = await svc.checkout_plan(db, user["tg_id"], "vip")
    result = await svc.apply_payment(db, order["payload"],
                                     amount_stars=order["amount_stars"] + 100)
    assert result and result["granted"]["kind"] == "plan"


# ─────────────── атомарность: оплата и выдача одним коммитом ─────────────────

async def test_payment_crash_midway_leaves_order_pending(db, free_user, monkeypatch):
    """Сбой между «оплачено» и «выдано» не оставляет заказ paid без товара.

    Раньше пометка оплаты и выдача были отдельными транзакциями: падение между
    ними = клиентка заплатила, а подписки нет, и повторный вебхук уже ничего
    не выдаст. Теперь всё в одной транзакции — сбой откатывает и оплату.
    """
    order = await svc.checkout_plan(db, free_user["tg_id"], "vip")

    async def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(users, "extend_subscription", boom)
    with pytest.raises(RuntimeError):
        await svc.apply_payment(db, order["payload"],
                                amount_stars=order["amount_stars"])

    row = await repo.get_order(db, order["id"])
    assert row["status"] == "pending", "заказ оплачен, хотя выдача не прошла"
    cur = await db.execute("SELECT COUNT(*) c FROM payments WHERE order_id=?",
                           (order["id"],))
    assert (await cur.fetchone())["c"] == 0
    fresh = await users.get(db, free_user["tg_id"])
    assert not users.sub_active(fresh), "подписка выдана при откате оплаты"


async def test_crystals_purchase_crash_does_not_spend(db, user, monkeypatch):
    """Сбой на выдаче не списывает ✦: списание и выдача в одной транзакции."""
    await users.update(db, user["tg_id"], crystals=200)

    async def boom(*_a, **_k):
        raise RuntimeError("db down")

    monkeypatch.setattr(repo, "grant_entitlement", boom)
    with pytest.raises(RuntimeError):
        await svc.pay_with_crystals(db, user["tg_id"], "spread_celtic")

    fresh = await users.get(db, user["tg_id"])
    assert fresh["crystals"] == 200, "✦ списаны, хотя выдача не прошла"
    assert await repo.available_entitlements(db, user["tg_id"], "spread", "celtic") == 0


async def test_promo_crash_keeps_code_usable(db, user, monkeypatch):
    """Сбой на выдаче не сжигает промокод: зачёт кода и выдача в одной транзакции."""
    codes = await growth.create_codes(db, 1, days=30, plan_code="vip",
                                      batch="etsy-test")

    async def boom(*_a, **_k):
        raise RuntimeError("db down")

    with monkeypatch.context() as m:
        m.setattr(users, "extend_subscription", boom)
        with pytest.raises(RuntimeError):
            await svc.redeem_promo(db, user["tg_id"], codes[0])

    # код не засчитан — активируется со второй попытки (патч уже снят)
    result = await svc.redeem_promo(db, user["tg_id"], codes[0])
    assert result and result["granted"]["kind"] == "plan"


# ──────────────────── покупка товара за Stars и ✦ ─────────────────────────────

async def test_buying_spread_grants_entitlement(db, user):
    order = await svc.checkout_product(db, user["tg_id"], "spread_celtic")
    result = await svc.apply_payment(db, order["payload"],
                                     amount_stars=order["amount_stars"])
    assert result["granted"]["kind"] == "spread"
    assert await repo.available_entitlements(db, user["tg_id"], "spread", "celtic") == 1
    # право на другой расклад при этом не появилось
    assert await repo.available_entitlements(db, user["tg_id"], "spread", "year") == 0


async def test_buying_with_crystals_charges_once(db, user):
    await users.update(db, user["tg_id"], crystals=200)
    result = await svc.pay_with_crystals(db, user["tg_id"], "spread_celtic")
    assert result["granted"]["kind"] == "spread"
    fresh = await users.get(db, user["tg_id"])
    product = await repo.get_product(db, "spread_celtic")
    assert fresh["crystals"] == 200 - product["price_crystals"]
    cur = await db.execute(
        "SELECT COUNT(*) n FROM events WHERE tg_id=? AND name=?",
        (user["tg_id"], analytics.E_CREDIT_SPENT),
    )
    assert (await cur.fetchone())["n"] == 1


async def test_crystals_purchase_without_balance_grants_nothing(db, user):
    await users.update(db, user["tg_id"], crystals=1)
    with pytest.raises(svc.PurchaseError):
        await svc.pay_with_crystals(db, user["tg_id"], "spread_celtic")
    assert await repo.available_entitlements(db, user["tg_id"], "spread", "celtic") == 0
    fresh = await users.get(db, user["tg_id"])
    assert fresh["crystals"] == 1, "списали при неудачной покупке"


async def test_crystal_pack_increases_balance(db, user):
    before = (await users.get(db, user["tg_id"]))["crystals"]
    order = await svc.checkout_product(db, user["tg_id"], "crystals_250")
    result = await svc.apply_payment(db, order["payload"],
                                     amount_stars=order["amount_stars"])
    assert result["granted"]["amount"] == 250
    after = (await users.get(db, user["tg_id"]))["crystals"]
    assert after == before + 250
    cur = await db.execute(
        "SELECT name, COUNT(*) n FROM events WHERE tg_id=? "
        "AND name IN (?, ?) GROUP BY name",
        (user["tg_id"], analytics.E_CREDIT_PACK_CHECKOUT_STARTED,
         analytics.E_CREDIT_PACK_PAID),
    )
    events = {row["name"]: row["n"] for row in await cur.fetchall()}
    assert events[analytics.E_CREDIT_PACK_CHECKOUT_STARTED] == 1
    assert events[analytics.E_CREDIT_PACK_PAID] == 1


# ─────────────────────────── права доступа ────────────────────────────────────

async def test_entitlement_is_consumed_once(db, user):
    await repo.grant_entitlement(db, user["tg_id"], "question", "*", qty=2)
    assert await repo.available_entitlements(db, user["tg_id"], "question") == 2
    assert await repo.consume_entitlement(db, user["tg_id"], "question")
    assert await repo.consume_entitlement(db, user["tg_id"], "question")
    assert not await repo.consume_entitlement(db, user["tg_id"], "question")
    assert await repo.available_entitlements(db, user["tg_id"], "question") == 0


async def test_expired_entitlement_is_not_available(db, user):
    await repo.grant_entitlement(db, user["tg_id"], "spread", "celtic", qty=1,
                                 valid_days=1)
    await db.execute("UPDATE entitlements SET expires_at='2000-01-01T00:00:00+00:00' "
                     "WHERE tg_id=?", (user["tg_id"],))
    await db.commit()
    assert await repo.available_entitlements(db, user["tg_id"], "spread", "celtic") == 0
    assert not await repo.consume_entitlement(db, user["tg_id"], "spread", "celtic")


async def test_wildcard_entitlement_covers_any_code(db, user):
    await repo.grant_entitlement(db, user["tg_id"], "question", "*", qty=1)
    assert await repo.available_entitlements(db, user["tg_id"], "question", "любой") == 1


# ──────────────────────────── промокоды ───────────────────────────────────────

async def test_promo_grants_plan_days(db, free_user):
    codes = await growth.create_codes(db, 1, days=30, plan_code="vip",
                                      batch="etsy-test")
    result = await svc.redeem_promo(db, free_user["tg_id"], codes[0])
    assert result["granted"]["kind"] == "plan"
    fresh = await users.get(db, free_user["tg_id"])
    assert users.sub_active(fresh)
    assert fresh["source"] == "promo:etsy-test", "канал привлечения не записан"


async def test_promo_cannot_be_used_twice(db, user, free_user):
    codes = await growth.create_codes(db, 1, days=30, max_uses=1)
    assert await svc.redeem_promo(db, user["tg_id"], codes[0])
    assert await svc.redeem_promo(db, free_user["tg_id"], codes[0]) is None


async def test_promo_with_multiple_uses(db, user, free_user):
    codes = await growth.create_codes(db, 1, days=7, max_uses=2, batch="multi")
    assert await svc.redeem_promo(db, user["tg_id"], codes[0])
    assert await svc.redeem_promo(db, free_user["tg_id"], codes[0])
    # тот же человек второй раз — нельзя
    assert await svc.redeem_promo(db, user["tg_id"], codes[0]) is None


async def test_expired_promo_is_refused(db, user):
    codes = await growth.create_codes(db, 1, days=30, valid_days=1)
    await db.execute("UPDATE promo_codes SET expires_at='2000-01-01T00:00:00+00:00'")
    await db.commit()
    assert await svc.redeem_promo(db, user["tg_id"], codes[0]) is None


async def test_promo_can_grant_crystals(db, user):
    before = (await users.get(db, user["tg_id"]))["crystals"]
    codes = await growth.create_codes(db, 1, kind="crystals", crystals=100)
    result = await svc.redeem_promo(db, user["tg_id"], codes[0])
    assert result["granted"]["amount"] == 100
    after = (await users.get(db, user["tg_id"]))["crystals"]
    assert after == before + 100


async def test_unknown_promo_returns_none(db, user):
    assert await svc.redeem_promo(db, user["tg_id"], "НЕТТАКОГО") is None


# ──────────────────────────── рефералка ───────────────────────────────────────

async def test_referral_pays_both_sides(db, user, free_user):
    inviter_before = (await users.get(db, user["tg_id"]))["crystals"]
    invitee_before = (await users.get(db, free_user["tg_id"]))["crystals"]

    result = await referrals.apply(db, free_user["tg_id"], user["tg_id"])
    assert result and result["bonus"] > 0

    inviter_after = (await users.get(db, user["tg_id"]))["crystals"]
    invitee_after = (await users.get(db, free_user["tg_id"]))["crystals"]
    assert inviter_after == inviter_before + result["bonus"]
    assert invitee_after == invitee_before + result["bonus"]


async def test_referral_cannot_be_applied_twice(db, user, free_user):
    assert await referrals.apply(db, free_user["tg_id"], user["tg_id"])
    assert await referrals.apply(db, free_user["tg_id"], user["tg_id"]) is None


async def test_self_referral_is_refused(db, user):
    assert await referrals.apply(db, user["tg_id"], user["tg_id"]) is None


async def test_referral_cycle_is_refused(db, user, free_user):
    """Аудит 2.2: A→B и B→A — цикл, B сам себе реферер во 2-м уровне."""
    assert await referrals.apply(db, free_user["tg_id"], user["tg_id"])
    assert await referrals.apply(db, user["tg_id"], free_user["tg_id"]) is None


async def test_second_level_referral(db, user, free_user):
    """Подруга подруги приносит бонус и первому уровню тоже."""
    await users.ensure(db, 1003, "Третья")
    assert await referrals.apply(db, free_user["tg_id"], user["tg_id"])
    before = (await users.get(db, user["tg_id"]))["crystals"]
    result = await referrals.apply(db, 1003, free_user["tg_id"])
    assert result["level2"] and result["level2"]["tg_id"] == user["tg_id"]
    after = (await users.get(db, user["tg_id"]))["crystals"]
    assert after == before + result["level2"]["bonus"]


async def test_referrer_gets_share_of_first_payment(db, user, free_user):
    await referrals.apply(db, free_user["tg_id"], user["tg_id"])
    before = (await users.get(db, user["tg_id"]))["crystals"]
    order = await svc.checkout_plan(db, free_user["tg_id"], "vip")
    await svc.apply_payment(db, order["payload"], amount_stars=order["amount_stars"])
    after = (await users.get(db, user["tg_id"]))["crystals"]
    assert after > before, "бонус с первой оплаты приглашённой не начислен"


async def test_concurrent_first_payments_pay_referral_once(db, user, free_user):
    """Две параллельные первые оплаты приглашённой — бонус пригласившей ровно один.

    Раньше проверка «это первая оплата» и начисление были в разных транзакциях:
    обе оплаты успевали увидеть по одной записи и бонус удваивался (или терялся).
    Теперь вся оплата с бонусом — одна транзакция, и гонка невозможна.
    """
    await referrals.apply(db, free_user["tg_id"], user["tg_id"])
    before = (await users.get(db, user["tg_id"]))["crystals"]

    first = await svc.checkout_plan(db, free_user["tg_id"], "vip")
    second = await svc.checkout_plan(db, free_user["tg_id"], "vip")

    await asyncio.gather(
        svc.apply_payment(db, first["payload"], amount_stars=first["amount_stars"]),
        svc.apply_payment(db, second["payload"], amount_stars=second["amount_stars"]),
    )

    after = (await users.get(db, user["tg_id"]))["crystals"]
    assert after == before + 30, "реферальный бонус начислен не один раз"


# ──────────────────────────── возврат ─────────────────────────────────────────

async def test_refund_marks_order_and_reduces_ltv(db, user):
    order = await svc.checkout_plan(db, user["tg_id"], "vip")
    await svc.apply_payment(db, order["payload"], amount_stars=order["amount_stars"])
    assert await repo.refund_order(db, order["id"])
    fresh = await users.get(db, user["tg_id"])
    assert fresh["ltv_stars"] == 0
    row = await repo.get_order(db, order["id"])
    assert row["status"] == "refunded"
    assert not await repo.refund_order(db, order["id"]), "двойной возврат"


async def test_storefront_shows_plans_and_products(db, user):
    store = await svc.storefront(db, user)
    assert store["plans"] and "spread" in store["products"]
    assert store["current_plan"] == "vip"
