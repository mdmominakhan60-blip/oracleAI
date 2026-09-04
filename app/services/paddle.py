"""Small Paddle Billing client used only for server-created web transactions."""
from __future__ import annotations

import json
import logging
from urllib.parse import quote

import aiohttp

from ..config import settings

log = logging.getLogger("oracle.paddle")


class PaddleError(RuntimeError):
    """Paddle is unavailable or returned an invalid transaction response."""


async def create_transaction(*, price_id: str, custom_data: dict) -> dict:
    """Create a Paddle transaction and return a hosted checkout URL.

    The price and custom data are supplied by trusted server code. The returned
    URL contains only Paddle's transaction id, so changing browser query params
    cannot change the grant selected by the webhook.
    """
    if not settings.paddle_api_key:
        raise PaddleError("PADDLE_API_KEY не задан")
    if not price_id or not price_id.startswith("pri_"):
        raise PaddleError("для тарифа не настроен Paddle price_id")
    if not settings.paddle_checkout_url:
        raise PaddleError("PADDLE_CHECKOUT_URL не задан")

    payload = {
        "items": [{"price_id": price_id, "quantity": 1}],
        "custom_data": custom_data,
        "collection_mode": "automatic",
    }
    headers = {
        "Authorization": f"Bearer {settings.paddle_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{settings.paddle_api_url}/transactions",
                headers=headers,
                json=payload,
            ) as response:
                if response.status >= 400:
                    # Do not log the response body: provider errors may contain
                    # customer or transaction data.
                    raise PaddleError(f"Paddle API вернул HTTP {response.status}")
                body = await response.text()
    except PaddleError:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise PaddleError("Paddle временно недоступен") from exc

    try:
        data = json.loads(body).get("data") or {}
        transaction_id = str(data.get("id") or "")
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise PaddleError("Paddle вернул некорректный ответ") from exc
    if not transaction_id.startswith("txn_"):
        raise PaddleError("Paddle не вернул transaction_id")

    separator = "&" if "?" in settings.paddle_checkout_url else "?"
    link = (f"{settings.paddle_checkout_url}{separator}transaction_id="
            f"{quote(transaction_id, safe='')}")
    return {"id": transaction_id, "link": link}
