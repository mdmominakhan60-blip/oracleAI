"""Лавка: тарифы, товары, оплата Stars и Кристаллами, промокоды.

Оплата Stars из Mini App идёт через `createInvoiceLink`: ссылку открывает
`Telegram.WebApp.openInvoice`, а зачисление приходит боту апдейтом
`successful_payment` — там же и выдача. Поэтому здесь мы только создаём заказ
и ссылку, но ничего не выдаём.
"""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ...services.billing import CRYPTO_ASSETS

from ...services.repo_gateway import billing as billing_repo
from ...services.repo_gateway import monetization as monetization_repo
from ...services import analytics
from ...services import billing as billing_svc
from ...services import invoices
from ..deps import confirmed_age_user, get_db, rate_limit

log = logging.getLogger("oracle.api.shop")

router = APIRouter(prefix="/api/shop", tags=["shop"])


@router.get("")
async def storefront(user=Depends(confirmed_age_user), db=Depends(get_db)):
    await analytics.track(db, analytics.E_SHOP_VIEW, user["tg_id"], surface="miniapp")
    return await billing_svc.storefront(db, user)


class InvoiceIn(BaseModel):
    sku: str | None = None
    plan: str | None = None
    billing_period: Literal["monthly", "annual"] = "monthly"


@router.post("/invoice", dependencies=[Depends(rate_limit("write"))])
async def create_invoice(item: InvoiceIn, user=Depends(confirmed_age_user),
                         db=Depends(get_db)):
    """Ссылка на оплату Stars для `openInvoice`."""
    if not item.sku and not item.plan:
        raise HTTPException(400, "нужен sku товара или код тарифа")
    try:
        order = (await billing_svc.checkout_plan(db, user["tg_id"], item.plan,
                                                 surface="miniapp", billing_period=item.billing_period)
                 if item.plan else
                 await billing_svc.checkout_product(db, user["tg_id"], item.sku,
                                                    surface="miniapp"))
    except billing_svc.PurchaseError as e:
        raise HTTPException(400, str(e)) from e

    try:
        link = await invoices.create_link(
            order["title"], order["description"], order["payload"],
            order["amount_stars"])
    except invoices.InvoiceError as e:
        log.error("ссылка на оплату не создана: %s", e)
        raise HTTPException(503, "Оплата сейчас недоступна, попробуй чуть позже 🌙")
    return {"link": link, "payload": order["payload"],
            "amount_stars": order["amount_stars"], "title": order["title"]}


@router.post("/web-checkout", dependencies=[Depends(rate_limit("write"))])
async def web_checkout(item: InvoiceIn, user=Depends(confirmed_age_user),
                       db=Depends(get_db)):
    """Ссылка на оплату подписки вне Telegram.

    Комиссия web-платёжки — единицы процентов против ~30-40% у Stars, поэтому
    основной чек (месячная подписка) по бизнес-плану идёт именно так. Кто она и
    какой тариф выбрала, передаём в `custom_data`: вебхук вернёт это обратно.
    """
    from ...config import settings
    from ...services.repo_gateway import content

    if not await content.is_on(db, "web_payments", user["tg_id"], default=False):
        raise HTTPException(404, "web-оплата пока недоступна")
    if not settings.paddle_checkout_url:
        raise HTTPException(503, "web-оплата не настроена")

    plan_code = (item.plan or "vip").strip()
    try:
        order = await billing_svc.checkout_web_plan(
            db, user["tg_id"], plan_code, surface="web",
            billing_period=item.billing_period)
    except billing_svc.PurchaseError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    return {"link": order["link"], "plan": order["sku"],
            "billing_period": item.billing_period,
            "price_usd": order["plan"]["price_usd"]}


class SubscriptionCancelIn(BaseModel):
    cancel_at_period_end: bool = True


@router.post("/subscription/cancel", dependencies=[Depends(rate_limit("write"))])
async def cancel_subscription(item: SubscriptionCancelIn, user=Depends(confirmed_age_user), db=Depends(get_db)):
    state = await monetization_repo.set_cancel_at_period_end(
        db, user["tg_id"], item.cancel_at_period_end)
    if not state:
        raise HTTPException(404, "активная v2-подписка не найдена")
    await analytics.track(db, "subscription_lifecycle", user["tg_id"],
                          props={"action": "cancel_at_period_end" if item.cancel_at_period_end else "resume"},
                          surface="miniapp")
    return {"ok": True, "subscription": state}


class CryptoIn(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    asset: str = Field(default="USDT", min_length=2, max_length=8)


@router.post("/crypto-invoice", dependencies=[Depends(rate_limit("write"))])
async def crypto_invoice(item: CryptoIn, user=Depends(confirmed_age_user),
                         db=Depends(get_db)):
    """Ссылка на оплату пакета Кристаллов криптой (Crypto Pay)."""
    from ...config import settings
    if not settings.cryptobot_api_token:
        raise HTTPException(503, "крипто-оплата не настроена")
    asset = item.asset.strip().upper()
    if asset not in CRYPTO_ASSETS:
        raise HTTPException(400, "этот криптоактив пока недоступен")
    try:
        order = await billing_svc.checkout_crypto_crystals(
            db, user["tg_id"], item.sku, asset=asset, surface="miniapp")
    except billing_svc.PurchaseError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    return {"link": order["link"], "sku": order["sku"],
            "amount_usd": order["amount_usd"], "asset": order["asset"]}


class CrystalsIn(BaseModel):
    sku: str = Field(min_length=1, max_length=40)


@router.post("/crystals", dependencies=[Depends(rate_limit("write"))])
async def buy_with_crystals(item: CrystalsIn, user=Depends(confirmed_age_user),
                            db=Depends(get_db)):
    """Покупка за Кристаллы — мгновенно, без Telegram-инвойса."""
    try:
        result = await billing_svc.pay_with_crystals(db, user["tg_id"], item.sku,
                                                    surface="miniapp")
    except billing_svc.PurchaseError as e:
        raise HTTPException(402, str(e)) from e
    fresh = await billing_repo.list_entitlements(db, user["tg_id"])
    return {"ok": True, "granted": result["granted"], "entitlements": fresh}


class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=40)


@router.post("/promo", dependencies=[Depends(rate_limit("write"))])
async def redeem_promo(item: PromoIn, user=Depends(confirmed_age_user), db=Depends(get_db)):
    result = await billing_svc.redeem_promo(db, user["tg_id"], item.code)
    if not result:
        raise HTTPException(400, "Этот код не отзывается... проверь написание 🌙")
    return {"ok": True, **result}


@router.get("/orders")
async def orders(user=Depends(confirmed_age_user), db=Depends(get_db)):
    return await billing_repo.user_orders(db, user["tg_id"], limit=30)


@router.get("/payment-history")
async def payment_history(user=Depends(confirmed_age_user), db=Depends(get_db)):
    return await billing_repo.payment_history(db, user["tg_id"], limit=30)


@router.get("/crystals/history")
async def crystals_history(user=Depends(confirmed_age_user), db=Depends(get_db)):
    return await billing_repo.crystal_history(db, user["tg_id"], limit=40)
