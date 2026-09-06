"""Общие примитивы аутентификации, не зависящие от FastAPI-роутеров.

Импорт отсюда безопасен из `deps.py` (не вызывает круговой зависимости через
`routers/__init__.py`). Session-token: stateless HMAC(tg_id:expiry).
"""
from __future__ import annotations

import hashlib
import hmac
import time


def sign_session_token(tg_id: int, expiry: int) -> str:
    secret = _bot_token()
    payload = f"{tg_id}:{expiry}".encode()
    sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()[:16]
    return f"{tg_id}:{expiry}:{sig}"


def verify_session_token(token: str) -> int | None:
    if not token or not _bot_token():
        return None
    try:
        tg_id_s, expiry_s, sig = token.split(":", 2)
        tg_id = int(tg_id_s)
        expiry = int(expiry_s)
    except (ValueError, TypeError):
        return None
    if time.time() > expiry:
        return None
    payload = f"{tg_id}:{expiry}".encode()
    expected = hmac.new(_bot_token(), payload, hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        return None
    return tg_id


def _bot_token() -> bytes:
    from ..config import settings
    return settings.bot_token.encode()
