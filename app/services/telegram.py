"""Прямые вызовы Bot API из веб-процесса.

API-процессу нужны три вещи от Telegram: ссылка на оплату для Mini App, возврат
Stars и отправка сообщения клиентке из админки. Тянуть ради этого весь aiogram в
веб-процесс незачем — здесь тонкий HTTP-клиент на три метода.

Валюта XTR (Stars) не требует `provider_token`: цифровые товары в Telegram
продаются только так, это правило платформы.
"""
from __future__ import annotations

import asyncio
import logging

from ..config import settings
from ..core import flood

log = logging.getLogger("oracle.telegram")

API = "https://api.telegram.org/bot{token}/{method}"
TIMEOUT = 20

#: Сколько раз пробуем создать ссылку на оплату. Внешний API мгновенно
#: недоступен чаще, чем кажется, а клиентке на экране — красный экран ошибки.
INVOICE_RETRIES = 3


class TelegramError(Exception):
    """Telegram отклонил запрос."""


async def call(method: str, payload: dict) -> dict:
    """Вызов Bot API. Перед запросом ждём токен общего бакета исходящих (G18)."""
    import aiohttp

    if not settings.bot_token:
        raise TelegramError("BOT_TOKEN не задан")
    if not flood.is_control(method):
        await flood.acquire()
    url = API.format(token=settings.bot_token, method=method)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, json=payload) as resp:
            data = await resp.json()
    if not data.get("ok"):
        raise TelegramError(data.get("description") or "неизвестная ошибка Telegram")
    return data["result"]


async def create_invoice_link(title: str, description: str, payload: str,
                              amount_stars: int, *, label: str | None = None) -> str:
    """Ссылка на оплату. `payload` — тот же ключ идемпотентности, что и в заказе.

    Ретрай с нарастающей паузой: ссылка идемпотентна, и вторая попытка не ломает
    заказ. Три попытки даже с учётом 429 — один пользовательский экшен, а не
    цикл рассылки, так что флуд-контроль тут не накручивается.
    """
    if amount_stars <= 0:
        raise TelegramError("цена должна быть больше нуля")
    import aiohttp
    body = {
        "title": title[:32],                       # ограничения Telegram
        "description": (description or title)[:255],
        "payload": payload,
        "currency": "XTR",
        "prices": [{"label": (label or title)[:32], "amount": amount_stars}],
    }
    last: Exception = TelegramError("createInvoiceLink не вызван")
    for attempt in range(INVOICE_RETRIES):
        try:
            result = await call("createInvoiceLink", body)
        except (TelegramError, aiohttp.ClientError, asyncio.TimeoutError) as e:
            last = e
            await asyncio.sleep(0.3 * (2 ** attempt))
            continue
        if isinstance(result, str):
            return result
        last = TelegramError("Telegram вернул неожиданный ответ")
    raise last


async def send_message(tg_id: int, text: str, *, html: bool = True) -> bool:
    """Сообщение клиентке (ответ поддержки из панели)."""
    try:
        await call("sendMessage", {
            "chat_id": tg_id,
            "text": text[:4096],
            "parse_mode": "HTML" if html else None,
            "link_preview_options": {"is_disabled": True},
        })
        return True
    except TelegramError as e:
        log.warning("сообщение не доставлено: %s", type(e).__name__)
        return False


async def refund_star_payment(tg_id: int, charge_id: str) -> bool:
    """Возврат Stars. Без него любой спор пришлось бы решать «на честном слове»."""
    try:
        await call("refundStarPayment",
                   {"user_id": tg_id, "telegram_payment_charge_id": charge_id})
        return True
    except TelegramError as e:
        log.warning("возврат платежа не прошёл: %s", type(e).__name__)
        return False


async def bot_username() -> str:
    """Имя бота — нужно для реферальных ссылок в Mini App."""
    try:
        me = await call("getMe", {})
        return me.get("username", "")
    except TelegramError:
        return ""
