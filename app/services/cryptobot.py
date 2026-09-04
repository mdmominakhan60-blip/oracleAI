"""Клиент Crypto Pay (@CryptoBot) — приём крипты без юрлица и KYC.

Поток тот же, что у Stars: заказ с уникальным payload создаётся до оплаты,
payload уезжает в инвойс, подтверждение приходит вебхуком — и выдача идёт через
тот же `services.billing.apply_payment`. Отличие одно: вебхук надо один раз
прописать руками в @CryptoBot → Crypto Pay → Create App → Webhook URL.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from urllib.parse import quote

import aiohttp

from ..config import settings

log = logging.getLogger("oracle.cryptobot")

API = "https://pay.crypt.bot/api/"


class CryptoPayError(RuntimeError):
    """Crypto Pay недоступен или вернул некорректный ответ."""


def verify_webhook(raw: bytes, header: str | None) -> bool:
    """Verify HMAC-SHA256(raw_body) with SHA256(app_token) as the key."""
    token = settings.cryptobot_api_token
    if not token or not header:
        return False
    # Crypto Pay derives the HMAC key as SHA256(app_token), then signs the
    # unparsed request body. Using the raw token silently rejects real webhooks.
    secret = hashlib.sha256(token.encode()).digest()
    calc = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, header.strip())


async def _call(method: str, payload: dict) -> dict:
    if not settings.cryptobot_api_token:
        raise CryptoPayError("CRYPTOBOT_API_TOKEN не задан")
    headers = {
        "Crypto-Pay-API-Token": settings.cryptobot_api_token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{API}{method}", headers=headers,
                                    json=payload) as response:
                if response.status >= 400:
                    raise CryptoPayError(
                        f"Crypto Pay вернул HTTP {response.status}")
                body = await response.text()
    except CryptoPayError:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise CryptoPayError("Crypto Pay временно недоступен") from exc
    try:
        data = json.loads(body)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise CryptoPayError("Crypto Pay вернул некорректный ответ") from exc
    if not data.get("ok"):
        raise CryptoPayError(str(data.get("error") or "неизвестная ошибка"))
    return data.get("result") or {}


SUPPORTED_ASSETS = frozenset({"USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX", "USDC"})


async def create_invoice(*, amount_usd: float, payload: str,
                         description: str, asset: str | None = None) -> dict:
    """Создаёт одноразовый Crypto Pay invoice.

    Без ``asset`` используется прежний USD invoice, который Crypto Pay может
    принять в любой доступной монете. При заданном asset цена фиксируется
    сервером в USD и Crypto Pay конвертирует её в выбранный актив.
    """
    normalized_asset = (asset or "").strip().upper() or None
    if normalized_asset and normalized_asset not in SUPPORTED_ASSETS:
        raise CryptoPayError("неподдерживаемый crypto asset")
    invoice = {
        "currency_type": "crypto" if normalized_asset else "fiat",
        "amount": f"{amount_usd:.2f}",
        "description": description[:1024],
        "payload": payload[:4096],
        "allow_anonymous": False,
        "allow_comments": False,
        "expires_in": 1800,
    }
    if normalized_asset:
        invoice["asset"] = normalized_asset
    else:
        invoice["fiat"] = "USD"
    result = await _call("createInvoice", invoice)
    pay_url = str(result.get("bot_invoice_url") or result.get("pay_url") or "")
    invoice_id = result.get("invoice_id")
    if not pay_url or not invoice_id:
        raise CryptoPayError("Crypto Pay не вернул invoice_id/pay_url")
    return {"invoice_id": int(invoice_id), "link": pay_url,
            "bot": settings.cryptobot_app_name and
                   quote(settings.cryptobot_app_name, safe="")}


async def get_invoice(invoice_id: int) -> dict | None:
    """Статус инвойса — для ручного перепровера и тестов."""
    result = await _call("getInvoices", {
        "invoice_ids": str(invoice_id), "status": "all"})
    items = result.get("items") or []
    return items[0] if items else None


async def get_balance() -> list[dict]:
    """Read-only баланс приложения для операционного health check."""
    result = await _call("getBalance", {})
    items = result.get("items") if isinstance(result, dict) else result
    return items if isinstance(items, list) else []
