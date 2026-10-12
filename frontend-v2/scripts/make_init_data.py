#!/usr/bin/env python3
"""Генератор валидного Telegram initData для интеграционных проверок.

Алгоритм — тот же, что в app/api/security.py:parse_init_data:
    secret = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
    hash   = HMAC_SHA256(key=secret, msg=sorted "k=v" строки)

Использование: dev- или CI-окружение с известным BOT_TOKEN.
Секрет не печатается и не коммитится.
"""
import hashlib
import hmac
import json
import os
import sys
import time
from urllib.parse import urlencode


def _secret(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def build_init_data(tg_id: int, bot_token: str, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAH-integration",
        "user": json.dumps({"id": tg_id, "first_name": "Integration", "username": f"int-{tg_id}"}),
    }
    check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    h = hmac.new(_secret(bot_token), check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": h})


def main() -> None:
    tg_id = int(sys.argv[1]) if len(sys.argv) > 1 else 10001
    token = os.environ.get("BOT_TOKEN", "")
    if not token:
        # Fall back to the token of the running api container (read-only, never printed).
        import subprocess
        token = subprocess.run(
            ["docker", "exec", "infra-api-1", "printenv", "BOT_TOKEN"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    print(build_init_data(tg_id, token))


if __name__ == "__main__":
    main()
