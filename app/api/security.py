"""Проверка подписи Telegram WebApp initData.

Схема из документации Telegram: секрет — HMAC(bot_token) с ключом «WebAppData»,
подпись — HMAC от отсортированной строки полей. Совпала подпись — данные пришли
от Telegram и их нельзя подделать на клиенте.

Дополнительно проверяем срок (`auth_date`): подпись у initData бессрочная, и без
проверки времени перехваченная строка работала бы вечно. Сутки — компромисс между
безопасностью и тем, что Mini App может висеть открытым.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from ..config import settings

log = logging.getLogger("oracle.api.security")

MAX_AGE_SECONDS = 24 * 3600
MAX_INIT_DATA_BYTES = 16 * 1024
MAX_INIT_DATA_FIELDS = 32
# Подпись из будущего — признак перехвата или сломанных часов клиента. Отклоняем
# лишь заметный уход вперёд: десяток минут — обычный рассинхрон часовых поясов.
MAX_FUTURE_SECONDS = 10 * 60


def parse_init_data(init_data: str) -> dict | None:
    """Проверяет подпись и возвращает разобранные поля или None."""
    if not init_data or not settings.bot_token:
        return None
    if len(init_data.encode("utf-8", "ignore")) > MAX_INIT_DATA_BYTES:
        return None
    try:
        raw_pairs = parse_qsl(init_data, keep_blank_values=True,
                              max_num_fields=MAX_INIT_DATA_FIELDS)
        pairs = dict(raw_pairs)
        # Duplicate keys make the signed representation ambiguous after parsing;
        # Telegram does not emit them, so reject rather than choosing one silently.
        if len(raw_pairs) != len(pairs):
            return None
        received_hash = pairs.pop("hash", "")
        if len(received_hash) != 64:
            return None
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret = hmac.new(b"WebAppData", settings.bot_token.encode(),
                          hashlib.sha256).digest()
        calc = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None

        auth_date_raw = pairs.get("auth_date")
        if not auth_date_raw:
            return None
        auth_date = int(auth_date_raw)
        if auth_date <= 0:
            return None
        now = time.time()
        if now - auth_date > MAX_AGE_SECONDS:
            log.info("initData просрочена (%.0f ч)", (now - auth_date) / 3600)
            return None
        if auth_date - now > MAX_FUTURE_SECONDS:
            log.info("initData из будущего (%.0f мин) — отклоняю",
                     (auth_date - now) / 60)
            return None

        user = json.loads(pairs.get("user", "{}") or "{}")
        if not user.get("id"):
            return None
        return {
            "tg_id": int(user["id"]),
            "first_name": user.get("first_name") or "",
            "username": user.get("username") or "",
            "language_code": user.get("language_code") or "ru",
            "start_param": pairs.get("start_param") or "",
            "auth_date": auth_date,
        }
    except (ValueError, TypeError, KeyError) as e:
        log.debug("initData не разобрана: %s", e)
        return None


def validate_init_data(init_data: str) -> int | None:
    """Только tg_id — совместимая обёртка для старых вызовов."""
    data = parse_init_data(init_data)
    return data["tg_id"] if data else None
