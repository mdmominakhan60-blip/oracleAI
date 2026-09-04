"""Liveness-чек бота для docker-compose.

Бот не поднимает HTTP — постучать в него нельзя напрямую. Доверяем хартбиту:
планировщик бота пишет `settings.system.heartbeat` каждый тик. Метка протухла —
процесс жив, а цикл мёртв, пусть Docker перезапустит контейнер.

Хартбит читается из того же бэкенда, что и приложение: PostgreSQL (DATABASE_URL).
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone

STALE_S = float(os.getenv("HEARTBEAT_STALE_S", "1800"))   # 3 × тик по 10 минут


def _dsn() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL не задан")
    # SQLAlchemy-style "postgresql+asyncpg://..." -> asyncpg "postgresql://..."
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


async def _check() -> int:
    import asyncpg

    conn = await asyncpg.connect(_dsn())
    try:
        row = await conn.fetchval(
            "SELECT value_json FROM settings WHERE key='system.heartbeat'")
    finally:
        await conn.close()
    if not row:
        return 1                                  # хартбита ещё нет — бот не дошёл до тика
    try:
        stamp = json.loads(row)
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()
    except (ValueError, TypeError, json.JSONDecodeError):
        return 1
    return 0 if age <= STALE_S else 1


def main() -> int:
    try:
        return asyncio.run(_check())
    except Exception:  # noqa: BLE001
        return 1


if __name__ == "__main__":
    sys.exit(main())
