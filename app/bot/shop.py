"""Лавка: подписки, одиночные расклады, разборы, вопросы, Кристаллы, оплата.

Приём платежа — единственное место, где выдаётся купленное, и оно идемпотентно:
Telegram может доставить `successful_payment` повторно, и товар не должен уйти
дважды (см. `services.billing.apply_payment`).
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, LabeledPrice, Message,
                           PreCheckoutQuery)

from ..repo import users
from ..services import access, billing as billing_svc, analytics
from ..services.entitlements import entitlements
from .chat import _send_long
from .keyboards import (back_menu, main_menu, plans_kb, products_kb, shop_kb)

log = logging.getLogger("oracle.bot.shop")
router = Router()

KIND_TITLES = {
    "spread": ("🎴 <b>Одиночные расклады</b>",
               "Большие расклады без подписки. Открытый расклад ждёт тебя 30 дней."),
    "report": ("📜 <b>Большие разборы</b>",
               "Длинный текст, который остаётся у тебя навсегда — "
               "его можно перечитывать."),
    "question": ("💬 <b>Дополнительные вопросы</b>",
                 "Сверх дневного лимита, когда нужно именно сейчас."),
    "crystals": ("✦ <b>Кристаллы</b>",
                 "Внутренняя валюта: экстренные вопросы и расклады со скидкой."),
}


async def _menu(db, tg_id: int):
    user = await users.get(db, tg_id)
    return main_menu(is_admin=await access.is_admin(db, tg_id),
                     lang="en" if user and user["lang"] == "en" else "ru")


# ─────────────────────────────── витрина ──────────────────────────────────────

@router.callback_query(F.data == "shop")
async def shop(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    await analytics.track(db, analytics.E_SHOP_VIEW, cb.from_user.id)
    lang = "en" if user and user["lang"] == "en" else "ru"
    await cb.message.answer(
        (f"💎 <b>Oracle Premium</b>\n\nYou have ✦{user['crystals']} Crystals.\n\n<i>Choose a plan or unlock a single reading when you need it.</i>"
         if lang == "en" else
         f"💎 <b>Лавка Оракула</b>\n\nУ тебя ✦{user['crystals']} Кристаллов.\n\n<i>Выбери тариф или открой отдельный разбор, когда он нужен.</i>"),
        reply_markup=shop_kb(lang))
    await cb.answer()


@router.callback_query(F.data.in_({"plans", "plans:monthly", "plans:annual"}))
async def plans(cb: CallbackQuery, db):
    user = await users.get(db, cb.from_user.id)
    canonical = await billing_svc.catalog_plans(db, user)
    available = [
        {**plan, "tagline": plan.get("tagline") or plan.get("description"),
         "features": plan.get("features") or []}
        for plan in canonical["plans"]
    ]
    current = (await entitlements.snapshot(db, user))["tier"]
    period = "annual" if cb.data == "plans:annual" else "monthly"
    lang = "en" if user and user["lang"] == "en" else "ru"

    lines = ["👑 <b>Premium access</b>" if lang == "en" else "👑 <b>Уровни доступа</b>",
             "Choose monthly or annual. The server resolves the final price." if lang == "en" else "Выбери месяц или год. Финальную цену всегда определяет сервер.", ""]
    for plan in available:
        price = plan.get("annual_price_stars") if period == "annual" else plan.get("price_stars")
        if not price:
            continue
        mark = " ← yours" if plan["code"] == current and lang == "en" else " ← твой" if plan["code"] == current else ""
        badge = f" · <i>{plan['badge']}</i>" if plan.get("badge") else ""
        days = plan.get("annual_period_days") if period == "annual" else plan.get("period_days")
        lines.append(f"<b>{plan['title']}</b> — ⭐{price} / {days} days{badge}{mark}" if lang == "en" else f"<b>{plan['title']}</b> — ⭐{price} / {days} дн.{badge}{mark}")
        if plan.get("tagline"):
            lines.append(f"<i>{plan['tagline']}</i>")
        for feature in (plan.get("features") or [])[:6]:
            lines.append(f"  • {feature}")
        lines.append("")
    await _send_long(cb.message, "\n".join(lines),
                     reply_markup=plans_kb(available, current, period=period, lang=lang))
    await cb.answer()


async def _show_products(cb: CallbackQuery, db, kind: str) -> None:
    if kind == "crystals":
        canonical = await billing_svc.catalog_plans(db, None)
        products = [{**item, "price_crystals": 0, "grant_kind": "crystals",
                     "grant_code": item["sku"], "grant_qty": item["crystals"] + item.get("bonus", 0),
                     "valid_days": None, "price_stars": item["price_stars"]}
                    for item in canonical["crystal_packs"]]
    else:
        products = await billing_svc.list_products(db, kind)
    if not products:
        await cb.answer("Здесь пока пусто")
        return
    from ...config import settings
    crypto_on = bool(settings.cryptobot_api_token)
    title, hint = KIND_TITLES.get(kind, ("💎 <b>Товары</b>", ""))
    lines = [title, f"<i>{hint}</i>", ""]
    for product in products:
        price = []
        if product["price_stars"]:
            price.append(f"⭐{product['price_stars']}")
        if product["price_crystals"]:
            price.append(f"✦{product['price_crystals']}")
        lines.append(f"<b>{product['title']}</b> — {' или '.join(price)}")
        if product["description"]:
            lines.append(f"<i>{product['description']}</i>")
        lines.append("")
    await cb.message.answer("\n".join(lines), reply_markup=products_kb(
        products,
        crypto_skus=billing_svc.CRYSTAL_PACKS_USD if crypto_on else ()))
    await cb.answer()


@router.callback_query(F.data == "shop_spreads")
async def shop_spreads(cb: CallbackQuery, db):
    await _show_products(cb, db, "spread")


@router.callback_query(F.data == "shop_reports")
async def shop_reports(cb: CallbackQuery, db):
    await _show_products(cb, db, "report")


@router.callback_query(F.data == "shop_questions")
async def shop_questions(cb: CallbackQuery, db):
    await _show_products(cb, db, "question")


@router.callback_query(F.data == "shop_crystals")
async def shop_crystals(cb: CallbackQuery, db):
    await _show_products(cb, db, "crystals")


@router.callback_query(F.data.startswith("product:"))
async def product_card(cb: CallbackQuery, db):
    """Карточка товара — на случай, если название не влезло в кнопку."""
    sku = cb.data.split(":", 1)[1]
    product = await billing_svc.product(db, sku)
    if not product:
        await cb.answer("Товара больше нет")
        return
    await cb.answer(f"{product['title']}: {product['description'] or ''}"[:190],
                    show_alert=True)


# ────────────────────────────── оплата Stars ──────────────────────────────────

@router.callback_query(F.data.startswith("buy_plan:"))
async def buy_plan(cb: CallbackQuery, db):
    parts = cb.data.split(":")
    code = parts[1]
    billing_period = parts[2] if len(parts) > 2 and parts[2] in {"monthly", "annual"} else "monthly"
    try:
        order = await billing_svc.checkout_plan(db, cb.from_user.id, code, billing_period=billing_period)
    except billing_svc.PurchaseError as e:
        await cb.answer(str(e), show_alert=True)
        return
    plan = order["plan"]
    await cb.message.answer_invoice(
        title=plan["title"][:32],
        description=(plan.get("tagline") or plan["title"])[:255],
        payload=order["payload"],
        currency="XTR",
        prices=[LabeledPrice(label=plan["title"][:32],
                             amount=order["amount_stars"])])
    await cb.answer()


@router.callback_query(F.data.startswith("buy_sku:"))
async def buy_sku(cb: CallbackQuery, db):
    sku = cb.data.split(":", 1)[1]
    try:
        order = await billing_svc.checkout_product(db, cb.from_user.id, sku)
    except billing_svc.PurchaseError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.message.answer_invoice(
        title=order["title"][:32],
        description=order["description"][:255],
        payload=order["payload"],
        currency="XTR",
        prices=[LabeledPrice(label=order["title"][:32],
                             amount=order["amount_stars"])])
    await cb.answer()


@router.callback_query(F.data.startswith("buy_crypto:"))
async def buy_crypto(cb: CallbackQuery, db):
    """Крипто-оплата пакета Кристаллов через Crypto Pay (без юрлица)."""
    from ...config import settings
    if not settings.cryptobot_api_token:
        await cb.answer("Крипто-оплата скоро откроется 🌙")
        return
    sku = cb.data.split(":", 1)[1]
    try:
        order = await billing_svc.checkout_crypto_crystals(db, cb.from_user.id, sku)
    except billing_svc.PurchaseError as e:
        await cb.answer(str(e), show_alert=True)
        return
    await cb.answer()
    await cb.message.answer(
        f"₿ <b>{order['title']}</b> — ${order['amount_usd']:.2f}\n\n"
        f"Оплатить можно картой или криптой (USDT, TON, BTC…) через @CryptoBot. "
        f"Кристаллы придут автоматически сразу после оплаты.\n"
        f"<i>Если оплата не прошла — напиши /start и попробуй ещё раз.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="₿ Оплатить", url=order["link"])],
            [InlineKeyboardButton(text="← Лавка", callback_data="shop")]]))


@router.callback_query(F.data.startswith("buy_crystals:"))
async def buy_with_crystals(cb: CallbackQuery, db):
    """Покупка за Кристаллы — сразу, без инвойса."""
    sku = cb.data.split(":", 1)[1]
    try:
        result = await billing_svc.pay_with_crystals(db, cb.from_user.id, sku)
    except billing_svc.PurchaseError as e:
        await cb.answer(str(e), show_alert=True)
        user = await users.get(db, cb.from_user.id)
        await cb.message.answer("💎 Buy Crystals:" if user and user["lang"] == "en" else "💎 Пополнить Кристаллы:",
                                reply_markup=shop_kb("en" if user and user["lang"] == "en" else "ru"))
        return
    user = await users.get(db, cb.from_user.id)
    await cb.answer("Открыто ✨")
    await cb.message.answer(
        f"✨ <b>{result['product']['title']}</b> — открыто!\n"
        f"Осталось ✦{user['crystals']}.\n\n"
        f"{_granted_hint(result['granted'])}",
        reply_markup=await _menu(db, cb.from_user.id))


def _granted_hint(granted: dict) -> str:
    """Что делать дальше — иначе покупка выглядит как «деньги ушли, и всё»."""
    kind = granted.get("kind")
    if kind == "spread":
        return "Открой 🎴 Расклад Таро — он уже ждёт тебя в списке."
    if kind == "report":
        return "Разбор соберётся в Mini App: раздел «Карта» → «Мои разборы»."
    if kind == "question":
        return f"Тебе доступно вопросов сверх лимита: {granted.get('qty', 1)}."
    if kind == "crystals":
        return f"Баланс: ✦{granted.get('balance', 0)}."
    if kind == "plan":
        return f"Доступ продлён на {granted.get('days', 30)} дней."
    return ""


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, db):
    """Подтверждаем оплату, если заказ существует.

    Уже оплаченный payload не отклоняем: Telegram может повторно доставить
    pre_checkout для ретрая, и отказ в кассе за оплаченный заказ выглядит
    для клиентки как ложный сбой. Идемпотентность выдачи держит
    `apply_payment` — повторная доставка не выдаст товар дважды.
    """
    order = await billing_svc.order_by_payload(db, query.invoice_payload)
    if not order:
        await query.answer(ok=False, error_message="Заказ не найден, создай его заново")
        return
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def paid(message: Message, db):
    payment = message.successful_payment
    result = await billing_svc.apply_payment(
        db, payment.invoice_payload,
        charge_id=payment.telegram_payment_charge_id,
        amount_stars=payment.total_amount)
    if not result:
        # повторная доставка апдейта: товар уже выдан
        log.info("повторная оплата пропущена",
                 extra={"event": "payment_duplicate"})
        await message.answer("Эта оплата уже зачтена ✨",
                             reply_markup=await _menu(db, message.from_user.id))
        return

    granted = result["granted"]
    if granted.get("kind") == "plan":
        text = (f"👑 <b>{granted['title']}</b> — доступ открыт на "
                f"{granted['days']} дней.\n"
                f"Я помню всё — продолжим с того места, где остановились ✨")
        if granted.get("crystals"):
            text += f"\n\nИ подарок: +✦{granted['crystals']} Кристаллов."
    elif granted.get("kind") == "crystals":
        text = (f"✨ +✦{granted['amount']}! Вселенная приняла твой дар.\n"
                f"Баланс: ✦{granted['balance']}.")
    else:
        text = (f"✨ <b>{result['order']['title']}</b> — открыто!\n\n"
                f"{_granted_hint(granted)}")
    await message.answer(text, reply_markup=await _menu(db, message.from_user.id))


# ──────────────────────────── мои покупки ─────────────────────────────────────

@router.callback_query(F.data == "my_entitlements")
async def my_entitlements(cb: CallbackQuery, db):
    items = await billing_svc.user_entitlements(db, cb.from_user.id)
    if not items:
        await cb.answer("Открытых покупок нет", show_alert=True)
        return
    names = {"spread": "расклад", "report": "разбор", "question": "вопрос"}
    lines = ["🎁 <b>Твои открытые покупки</b>", ""]
    for item in items:
        left = item["qty_total"] - item["qty_used"]
        until = f" · до {item['expires_at'][:10]}" if item["expires_at"] else ""
        lines.append(f"• {names.get(item['kind'], item['kind'])} "
                     f"{item['code'] or ''} ×{left}{until}")
    await cb.message.answer("\n".join(lines), reply_markup=back_menu())
    await cb.answer()
