"""Покупки: витрина, оформление заказа, выдача купленного, промокоды.

Здесь собран весь путь денег, чтобы «что клиентка получила за оплату» читалось
одним файлом. Инварианты:

- заказ создаётся ДО оплаты и получает уникальный payload → повторный вебхук
  Telegram не выдаёт товар дважды;
- выдача (`_apply_grant`) — единственная точка, где что-то начисляется, и она
  вызывается только из `apply_payment`, `pay_with_crystals` и `redeem_promo`;
- покупка за Кристаллы сначала списывает баланс и только потом выдаёт: обратный
  порядок при сбое оставил бы товар бесплатным.
"""
from __future__ import annotations

import asyncio
import logging

from ..config import settings
from ..data.session import transaction
from ..repo import analytics, billing as repo, content, growth, users
from ..repo import monetization as monetization_repo
from . import analytics as analytics_service
from .entitlements import entitlements

log = logging.getLogger("oracle.billing")

#: Реферальный бонус с первой оплаты приглашённой (G20). Без замка две оплаты
#: подряд успевали прочитать «первая» и начислить бонус дважды — начисление по
#: приглашённому сериализуем.
_bonus_locks: dict[int, asyncio.Lock] = {}
_BONUS_LOCKS_MAX = 4096


def _bonus_lock(tg_id: int) -> asyncio.Lock:
    lock = _bonus_locks.get(tg_id)
    if lock is None:
        lock = asyncio.Lock()
        if len(_bonus_locks) >= _BONUS_LOCKS_MAX:
            _bonus_locks.clear()
        _bonus_locks[tg_id] = lock
    return lock

# Что делает выдача для каждого вида товара.
GRANT_KINDS = ("plan", "crystals", "spread", "report", "question")


class PurchaseError(Exception):
    """Покупка невозможна — текст предназначен клиентке."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ─────────────────────────────── витрина ──────────────────────────────────────

async def storefront(db, user) -> dict:
    """Данные для магазина: legacy-compatible view plus one canonical v2 catalog."""
    plans = await repo.list_plans(db)
    products = await repo.list_products(db)
    current = user["sub_level"] if users.sub_active(user) else "free"
    groups: dict[str, list] = {}
    for p in products:
        groups.setdefault(p["kind"], []).append(p)
    canonical_state = await entitlements.snapshot(db, user)
    canonical = await monetization_repo.catalog_payload(db, current_state=canonical_state)
    return {
        "current_plan": current,
        "sub_active": users.sub_active(user),
        "sub_days_left": users.sub_days_left(user),
        "crystals": user["crystals"] or 0,
        "plans": plans,
        "products": groups,
        "entitlements": await repo.list_entitlements(db, user["tg_id"]),
        "catalog": canonical,
        "current_entitlements": canonical_state,
    }


async def _v2_item(db, code: str, *, item_type: str, channel: str):
    if not code:
        return None
    return await monetization_repo.price_item(db, code, item_type=item_type, channel=channel)


async def _v2_plan_definition(code: str) -> dict | None:
    from ..data.monetization_catalog import PLAN_DEFINITIONS
    return next((dict(item) for item in PLAN_DEFINITIONS if item["code"] == code), None)


async def _v2_crystal_item(db, sku: str, channel: str):
    return await _v2_item(db, sku, item_type="crystal_pack", channel=channel)


async def _v2_deep_item(db, sku: str):
    return await _v2_item(db, sku, item_type="deep_operation", channel="internal")


# ──────────────────────────── оформление заказа ───────────────────────────────

async def checkout_product(db, tg_id: int, sku: str, *,
                           surface: str = "bot") -> dict:
    """Создаёт order from the canonical v2 price book or the legacy catalog."""
    v2 = await _v2_crystal_item(db, sku, "stars")
    if v2:
        meta = {
            "grant_kind": "crystals", "grant_code": sku,
            "grant_qty": int(v2["crystal_qty"] or 0) + int(v2["bonus_qty"] or 0),
            "valid_days": None, "catalog_version": v2["catalog_version"],
            "price_book_version": v2["price_book_version"], "price_variant": "v2",
            "expected_cost_usd": v2["expected_cost_usd"],
        }
        order = await repo.create_order(
            db, tg_id, "crystals", sku=sku, title=v2["title"],
            amount_stars=int(v2["amount_stars"] or 0), surface=surface, meta=meta)
        await analytics_service.track_monetization(
            db, analytics_service.E_CREDIT_PACK_CHECKOUT_STARTED, tg_id,
            surface=surface if surface in {"bot", "miniapp"} else "system",
            sku=sku, channel=surface, credit_band_name=analytics_service.credit_band(meta["grant_qty"]),
            price_variant="v2")
        return {**order, "description": v2["description"] or v2["title"], "product": v2}

    product = await repo.get_product(db, sku)
    if not product:
        raise PurchaseError("Такого товара уже нет в лавке 🌙")
    if not product["price_stars"]:
        raise PurchaseError("Этот товар продаётся только за Кристаллы ✦")
    order = await repo.create_order(
        db, tg_id, product["kind"], sku=sku, title=product["title"],
        amount_stars=product["price_stars"], surface=surface,
        meta={"grant_kind": product["grant_kind"], "grant_code": product["grant_code"],
              "grant_qty": product["grant_qty"], "valid_days": product["valid_days"]})
    await analytics.track(db, analytics.E_INVOICE, tg_id,
                          props={"sku": sku, "stars": product["price_stars"]},
                          surface=surface)
    if product["kind"] == "crystals":
        await analytics_service.track_monetization(
            db, analytics_service.E_CREDIT_PACK_CHECKOUT_STARTED, tg_id,
            surface=surface if surface in {"bot", "miniapp"} else "system",
            sku=sku, channel=surface,
            credit_band_name=analytics_service.credit_band(product["grant_qty"]),
        )
    return {**order, "description": product["description"] or product["title"],
            "product": dict(product)}


async def checkout_plan(db, tg_id: int, plan_code: str, *,
                        surface: str = "bot", billing_period: str = "monthly") -> dict:
    """Создаёт order из v2 price book или legacy plans."""
    item_type = "annual_plan" if billing_period == "annual" else "plan"
    v2 = await _v2_item(db, plan_code, item_type=item_type, channel="stars")
    if v2 and int(v2["amount_stars"] or 0) > 0:
        definition = await _v2_plan_definition(plan_code) or {}
        order = await repo.create_order(
            db, tg_id, "plan", sku=plan_code, title=v2["title"],
            amount_stars=int(v2["amount_stars"]), surface=surface,
            meta={"grant_kind": "plan", "grant_code": plan_code, "grant_qty": 1,
                  "valid_days": v2["period_days"], "billing_period": billing_period,
                  "catalog_version": v2["catalog_version"],
                  "price_book_version": v2["price_book_version"], "price_variant": "v2",
                  "ai_message_limit": definition.get("ai_messages", 0),
                  "compute_budget_usd": definition.get("compute_budget_usd", 0),
                  "monthly_crystals_granted": definition.get("crystals_grant", 0)})
        await analytics.track(db, analytics.E_INVOICE, tg_id,
                              props={"plan": plan_code, "stars": v2["amount_stars"], "price_variant": "v2", "billing_period": billing_period},
                              surface=surface)
        return {**order, "description": v2["description"] or v2["title"], "plan": {**definition, **v2}}

    plan = await repo.get_plan(db, plan_code)
    if not plan or not plan.get("price_stars"):
        raise PurchaseError("Этот тариф нельзя оплатить здесь 🌙")
    order = await repo.create_order(
        db, tg_id, "plan", sku=plan_code, title=plan["title"],
        amount_stars=plan["price_stars"], surface=surface,
        meta={"grant_kind": "plan", "grant_code": plan_code,
              "grant_qty": 1, "valid_days": plan["period_days"]})
    await analytics.track(db, analytics.E_INVOICE, tg_id,
                          props={"plan": plan_code, "stars": plan["price_stars"]},
                          surface=surface)
    return {**order, "description": plan.get("tagline") or plan["title"], "plan": plan}


async def checkout_web_plan(db, tg_id: int, plan_code: str, *,
                            surface: str = "web", billing_period: str = "monthly") -> dict:
    """Создаёт pending-заказ, связанный с Paddle checkout.

    Browser-controlled parameters are never used as the source of a grant. The
    signed webhook resolves this payload back to the immutable server order.
    """
    item_type = "annual_plan" if billing_period == "annual" else "plan"
    v2 = await _v2_item(db, plan_code, item_type=item_type, channel="web")
    definition = await _v2_plan_definition(plan_code) or {}
    plan = v2 or await repo.get_plan(db, plan_code)
    if not plan or not plan.get("is_active", 1) or not plan.get("is_public", 1):
        raise PurchaseError("Этот тариф сейчас недоступен 🌙")
    price_usd = (float(plan.get("amount_minor") or 0) / 100) if v2 else float(plan.get("price_usd") or 0)
    if price_usd <= 0:
        raise PurchaseError("у этого тарифа нет web-цены")
    order = await repo.create_order(
        db, tg_id, "plan", sku=plan_code, title=plan["title"],
        amount_stars=0, surface=surface,
        meta={"grant_kind": "plan", "grant_code": plan_code,
              "grant_qty": 1, "valid_days": plan["period_days"],
              "billing_period": billing_period, "provider": "paddle", "price_usd": price_usd,
              "catalog_version": plan.get("catalog_version", "legacy"),
              "price_book_version": plan.get("price_book_version", "legacy"),
              "price_variant": "v2" if v2 else "legacy",
              "ai_message_limit": definition.get("ai_messages", plan.get("daily_questions", 0)),
              "compute_budget_usd": definition.get("compute_budget_usd", 0),
              "monthly_crystals_granted": definition.get("crystals_grant", plan.get("crystals_grant", 0))})
    from . import paddle
    try:
        created = await paddle.create_transaction(
            price_id=settings.paddle_price_id(plan_code),
            custom_data={"order_payload": order["payload"]},
        )
        if not await repo.set_order_meta(
                db, order["payload"], paddle_transaction_id=created["id"]):
            raise paddle.PaddleError("локальный заказ исчез")
    except (paddle.PaddleError, KeyError, TypeError) as exc:
        await repo.mark_order_failed(db, order["payload"])
        raise PurchaseError(
            "web-оплата сейчас недоступна, попробуй позже 🌙",
            status_code=503) from exc
    await analytics.track(db, "web_checkout", tg_id,
                          props={"plan": plan_code}, surface=surface)
    return {**order, "link": created["link"],
            "description": plan.get("description") or plan.get("tagline") or plan["title"],
            "plan": {**plan, "price_usd": price_usd, "billing_period": billing_period}}


#: USD-цены пакетов Кристаллов для Crypto Pay. Источник цены — только
#: сервер: клиент передаёт sku, всё остальное смотрим здесь.
CRYSTAL_PACKS_USD = {"crystals_100": 5.49, "crystals_250": 11.49,
                     "crystals_600": 21.49}
CRYPTO_ASSETS = frozenset({"USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"})


async def checkout_crypto_crystals(db, tg_id: int, sku: str,
                                   asset: str = "USDT", *,
                                   surface: str = "bot") -> dict:
    """Pending-заказ + инвойс Crypto Pay на пакет Кристаллов.

    Выдача произойдёт только после подписанного вебхука — как у Stars/Paddle.
    """
    v2 = await _v2_crystal_item(db, sku, "crypto")
    product = await repo.get_product(db, sku)
    if not v2 and (not product or product["kind"] != "crystals"):
        raise PurchaseError("Криптой можно пополнить только пакеты Кристаллов 💎")
    asset = (asset or "USDT").strip().upper()
    if asset not in CRYPTO_ASSETS:
        raise PurchaseError("Этот криптоактив пока недоступен")
    amount_usd = ((v2["amount_minor"] or 0) / 100 if v2 else CRYSTAL_PACKS_USD.get(sku))
    if not amount_usd:
        raise PurchaseError("Для этого пакета не задана крипто-цена 🌙")
    title = (v2 or product)["title"]
    grant_qty = int((v2 or product).get("crystal_qty", 0) or 0) + int((v2 or product).get("bonus_qty", 0) or 0) if v2 else product["grant_qty"]
    order = await repo.create_order(
        db, tg_id, "crystals", sku=sku, title=title,
        amount_stars=0, surface=surface,
        meta={"grant_kind": "crystals", "grant_code": sku,
              "grant_qty": grant_qty, "valid_days": None,
              "provider": "cryptobot", "amount_usd": amount_usd,
              "asset": asset, "catalog_version": (v2 or {}).get("catalog_version", "legacy"),
              "price_book_version": (v2 or {}).get("price_book_version", "legacy"),
              "price_variant": "v2" if v2 else "legacy"})
    from . import cryptobot
    try:
        created = await cryptobot.create_invoice(
            amount_usd=amount_usd, payload=order["payload"],
            description=f"Oracle: {(v2 or product)['title']}", asset=asset)
    except cryptobot.CryptoPayError as exc:
        await repo.mark_order_failed(db, order["payload"])
        raise PurchaseError(
            "крипто-оплата сейчас недоступна, попробуй позже 🌙",
            status_code=503) from exc
    await repo.set_order_meta(db, order["payload"],
                              cryptobot_invoice_id=created["invoice_id"])
    await analytics.track(db, "crypto_checkout", tg_id, props={"sku": sku, "asset": asset},
                          surface=surface)
    return {**order, "link": created["link"],
            "amount_usd": amount_usd,
            "asset": asset,
            "description": (v2 or product)["description"] or (v2 or product)["title"]}


async def pay_with_crystals(db, tg_id: int, sku: str, *,
                            surface: str = "bot") -> dict:
    """Покупка товара за Кристаллы — без Telegram-инвойса, сразу."""
    v2 = await _v2_deep_item(db, sku)
    product = await repo.get_product(db, sku)
    if not v2 and not product:
        raise PurchaseError("Такого товара уже нет в лавке 🌙")
    price = int(v2["crystal_qty"] or 0) if v2 else (product["price_crystals"] or 0)
    if price <= 0:
        raise PurchaseError("Этот товар продаётся только за ⭐ Stars")

    # Списание ✦, выдача и пометка заказа оплаченным — одной транзакцией:
    # сбой между шагами не оставляет списанный баланс без товара.
    async with transaction(db):
        sale = dict(v2) if v2 else {key: product[key] for key in product.keys()}
        order = await repo.create_order(
            db, tg_id, "deep_operation" if v2 else product["kind"], sku=sku, title=sale["title"],
            amount_crystals=price, surface=surface,
            meta={"grant_kind": sale["grant_kind"],
                  "grant_code": sale["grant_code"],
                  "grant_qty": sale["grant_qty"],
                  "valid_days": sale["valid_days"],
                  "catalog_version": sale.get("catalog_version", "legacy"),
                  "price_book_version": sale.get("price_book_version", "legacy"),
                  "price_variant": "v2" if v2 else "legacy",
                  "expected_cost_usd": sale.get("expected_cost_usd")})
        if v2:
            await monetization_repo.reserve_usage(
                db, tg_id, order["payload"], capability="deep_operation", sku=sku,
                catalog_version=sale.get("catalog_version", "legacy"), tier_code="free",
                period_start=None, compute_cost_usd=float(sale.get("expected_cost_usd") or 0),
                crystal_cost=price, charged_source="crystals")

        if not await repo.spend_crystals(db, tg_id, price, f"buy:{sku}",
                                         ref=order["payload"]):
            raise PurchaseError(f"Нужно ✦{price}, а у тебя меньше. Пополни запас 💎")

        granted = await _apply_grant(
            db, tg_id, sale["grant_kind"], sale["grant_code"],
            qty=sale["grant_qty"] or 1, valid_days=sale["valid_days"],
            source="purchase", order_id=order["id"])
        await repo.mark_order_paid(db, order["payload"], provider="crystals",
                                   amount_stars=0)
        await analytics.track(db, analytics.E_PAID, tg_id,
                              props={"sku": sku, "crystals": price}, surface=surface)
        if v2:
            await monetization_repo.finish_usage(db, tg_id, order["payload"], status="succeeded")
    await analytics_service.track_monetization(
        db, analytics_service.E_CREDIT_SPENT, tg_id,
        surface=surface if surface in {"bot", "miniapp"} else "system",
        sku=sku, channel=surface, credit_band_name=analytics_service.credit_band(price),
        result_category=sale["grant_kind"],
    )
    fresh_user = await users.get(db, tg_id)
    if fresh_user and int(fresh_user["crystals"] or 0) <= 20:
        await analytics_service.track_monetization(
            db, analytics_service.E_CREDIT_BALANCE_LOW, tg_id,
            surface=surface if surface in {"bot", "miniapp"} else "system",
            channel=surface, reason="threshold_20",
        )
    product_payload = {**sale, "sku": sale.get("sku") or sale.get("code")}
    return {"order": order, "granted": granted, "product": product_payload}


# ──────────────────────────── приём оплаты ────────────────────────────────────

async def apply_payment(db, payload: str, *, charge_id: str | None = None,
                        amount_stars: int | None = None,
                        provider: str = "telegram_stars",
                        currency: str = "XTR") -> dict | None:
    """Обрабатывает успешную оплату Stars. None — заказ уже обработан.

    Идемпотентность целиком на стороне БД (`mark_order_paid` меняет статус только
    из `pending`), поэтому повторная доставка апдейта безопасна.

    Вся выдача — в той же транзакции, что и пометка заказа оплаченным: сбой между
    «деньги приняты» и «товар выдан» невозможен как состояние. Либо всё зафиксирова
    лось, либо ничего.
    """
    async with transaction(db):
        order = await repo.mark_order_paid(db, payload, charge_id=charge_id,
                                           amount_stars=amount_stars,
                                           provider=provider, currency=currency)
        if not order:
            log.info("оплата уже обработана или заказ не найден",
                     extra={"event": "payment_duplicate_or_missing"})
            return None

        meta = _order_meta(order)
        granted = await _apply_grant(
            db, order["tg_id"], meta.get("grant_kind"), meta.get("grant_code"),
            qty=meta.get("grant_qty") or 1, valid_days=meta.get("valid_days"),
            source="purchase", order_id=order["id"])
        await analytics.track(db, analytics.E_PAID, order["tg_id"],
                              props={"sku": order["sku"], "kind": order["kind"],
                                     "stars": order["amount_stars"]},
                              surface=order["surface"] or "bot")
        await _referral_revenue_bonus(db, order["tg_id"], order["amount_stars"] or 0)
    if order["kind"] == "crystals":
        await analytics_service.track_monetization(
            db, analytics_service.E_CREDIT_PACK_PAID, order["tg_id"],
            surface=order["surface"] if order["surface"] in {"bot", "miniapp"} else "system",
            sku=order["sku"], channel=order["surface"],
            credit_band_name=analytics_service.credit_band(_order_meta(order).get("grant_qty")),
        )
    return {"order": dict(order), "granted": granted}


def _order_meta(order) -> dict:
    import json
    try:
        return json.loads(order["meta_json"] or "{}")
    except (TypeError, ValueError):
        return {}


# ──────────────────────────────── выдача ──────────────────────────────────────

async def _apply_grant(db, tg_id: int, kind: str | None, code: str | None, *,
                       qty: int = 1, valid_days: int | None = None,
                       source: str = "purchase",
                       order_id: int | None = None) -> dict:
    """Начисляет купленное. Возвращает описание для сообщения клиентке."""
    if kind == "plan":
        v2_definition = await _v2_plan_definition(code or "")
        plan = await repo.get_plan(db, code or "vip") if not v2_definition else v2_definition
        days = valid_days or plan.get("period_days") or 30
        until = await users.extend_subscription(db, tg_id, code or "vip", days)
        bonus = plan.get("crystals_grant") or 0
        if bonus:
            await repo.add_crystals(db, tg_id, bonus, f"plan_bonus:{code}")
            await monetization_repo.crystal_lot(
                db, tg_id, source="subscription_bonus", qty=int(bonus),
                order_id=order_id, valid_days=90)
        if v2_definition:
            catalog = await monetization_repo.active_catalog_version(db)
            await monetization_repo.upsert_subscription_state(
                db, tg_id, tier_code=code or "free", catalog_version=catalog["version"],
                price_book_version=catalog["price_book_version"], status="active",
                period_start=None, period_end=until,
                ai_message_limit=int(v2_definition.get("ai_messages") or 0),
                compute_budget_usd=float(v2_definition.get("compute_budget_usd") or 0),
                monthly_crystals_granted=int(bonus or 0))
        return {"kind": "plan", "plan": plan, "days": days, "until": until,
                "crystals": bonus, "catalog_version": (await monetization_repo.active_catalog_version(db))["version"] if v2_definition else "legacy",
                "title": plan.get("title", "Подписка")}

    if kind == "crystals":
        amount = qty or 0
        balance = await repo.add_crystals(db, tg_id, amount, f"purchase:{code or 'pack'}")
        if amount and code:
            v2_pack = await _v2_crystal_item(db, code, "stars") or await _v2_crystal_item(db, code, "crypto")
            if v2_pack:
                await monetization_repo.crystal_lot(
                    db, tg_id, source="purchased", qty=int(amount), order_id=order_id)
        return {"kind": "crystals", "amount": amount, "balance": balance,
                "title": f"✦ {amount} Кристаллов"}

    if kind in ("spread", "report", "question"):
        await repo.grant_entitlement(db, tg_id, kind, code, qty=qty,
                                     valid_days=valid_days, source=source,
                                     order_id=order_id)
        return {"kind": kind, "code": code, "qty": qty, "valid_days": valid_days,
                "title": {"spread": "Расклад", "report": "Разбор",
                          "question": "Вопросы"}[kind]}

    log.warning("неизвестный вид выдачи: %s/%s", kind, code)
    return {"kind": "unknown", "title": "Покупка"}


async def grant_manually(db, tg_id: int, kind: str, code: str | None = None, *,
                         qty: int = 1, days: int | None = None,
                         admin_id: int | None = None) -> dict:
    """Выдача из админки (подарок, компенсация, тест)."""
    granted = await _apply_grant(db, tg_id, kind, code, qty=qty, valid_days=days,
                                 source="admin")
    await analytics.track(db, "admin_grant", tg_id,
                          props={"kind": kind, "code": code, "qty": qty,
                                 "by": admin_id}, surface="admin")
    return granted


# ─────────────────────────────── промокоды ────────────────────────────────────

async def redeem_promo(db, tg_id: int, code: str) -> dict | None:
    """Активирует промокод и выдаёт то, что в нём записано.

    Счётчик использований кода и сама выдача — одной транзакцией: сбой между
    «код засчитан» и «товар выдан» не сжигает промокод впустую.
    """
    async with transaction(db):
        promo = await growth.redeem(db, code, tg_id)
        if not promo:
            return None
        kind = promo["kind"]
        if kind == "crystals":
            granted = await _apply_grant(db, tg_id, "crystals", promo["code"],
                                         qty=promo["crystals"], source="promo")
        elif kind == "product" and promo["sku"]:
            product = await repo.get_product(db, promo["sku"])
            if not product:
                return None          # rollback: код не засчитан
            granted = await _apply_grant(
                db, tg_id, product["grant_kind"], product["grant_code"],
                qty=product["grant_qty"] or 1, valid_days=product["valid_days"],
                source="promo")
        else:
            granted = await _apply_grant(db, tg_id, "plan", promo["plan_code"],
                                         valid_days=promo["days"], source="promo")
        await analytics.track(db, analytics.E_PROMO, tg_id,
                              props={"code": promo["code"], "batch": promo["batch"],
                                     "kind": kind})
        # партия промокода = канал привлечения: без него нельзя посчитать,
        # какой листинг приводит платящих
        user = await users.get(db, tg_id)
        if user and not user["source"] and promo["batch"]:
            await users.update(db, tg_id, source=f"promo:{promo['batch']}")
    return {**promo, "granted": granted}


# ─────────────────────── реферальный бонус с оплаты ───────────────────────────

async def _referral_revenue_bonus(db, tg_id: int, stars: int) -> None:
    """Кристаллы пригласившей, когда приглашённая впервые платит.

    Это главный аргумент делиться ссылкой: бонус приходит не за регистрацию (её
    легко накрутить), а за реальную оплату.
    """
    if stars <= 0:
        return
    referrer = await growth.referrer_of(db, tg_id)
    if not referrer:
        return
    share = await content.get_setting(db, "referral.revenue_share_crystals", 30)
    try:
        share = int(share or 0)
    except (TypeError, ValueError):
        share = 30
    if share <= 0:
        return
    # «первая оплата» — гонка: две оплаты приглашённой подряд смотрели на
    # счётчик до начисления и бонусовали пригласившую дважды. Замок на
    # приглашённую + транзакция: чтение счётчика и начисление — одно целое.
    async with _bonus_lock(tg_id):
        async with transaction(db):
            orders = await repo.user_orders(db, tg_id, limit=5)
            if sum(1 for o in orders if o["status"] == "paid") > 1:
                return
            await repo.add_crystals(db, referrer, share, "referral_revenue",
                                    ref=str(tg_id))
            await analytics.track(db, "referral_revenue_bonus", referrer,
                                  props={"invitee": tg_id, "crystals": share})

# ── presentation-facing reads (bot / api) ────────────────────────────────
async def catalog_plans(db, user) -> dict:
    """Канонический каталог планов; user=None — без персонального состояния."""
    from ..repo import monetization as monetization_repo
    from .entitlements import entitlements

    current_state = await entitlements.snapshot(db, user) if user else None
    return await monetization_repo.catalog_payload(db, current_state=current_state)


async def product(db, sku: str):
    return await repo.get_product(db, sku)


async def order_by_payload(db, payload: str):
    """Заказ по invoice-payload (pre_checkout / вебхуки провайдеров)."""
    return await repo.order_by_payload(db, payload)


async def user_entitlements(db, tg_id: int):
    return await repo.list_entitlements(db, tg_id)


async def list_products(db, kind: str | None = None):
    return await repo.list_products(db, kind)


async def spend_crystals(db, tg_id: int, amount: int, reason: str) -> bool:
    return await repo.spend_crystals(db, tg_id, amount, reason)


async def consume_entitlement(db, tg_id: int, kind: str, code: str = "*"):
    return await repo.consume_entitlement(db, tg_id, kind, code)


async def grant_entitlement(db, tg_id: int, kind: str, code: str = "*",
                            *, qty: int = 1, valid_days: int | None = None,
                            source: str = "manual", order_id: str | None = None):
    await repo.grant_entitlement(db, tg_id, kind, code, qty=qty,
                                 valid_days=valid_days, source=source,
                                 order_id=order_id)
