"""Подключение к PostgreSQL, сиды и транзакции.

Единственный бэкенд — PostgreSQL через `postgres.PostgresDatabase`. Alembic
создаёт и изменяет схему до старта приложения; этот модуль только проверяет
миграционную ревизию, открывает pool и применяет идемпотентные product seeds.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from ..config import settings

log = logging.getLogger("oracle.db")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


async def connect(*, seed: bool = True):
    """Открывает PostgreSQL из DATABASE_URL после Alembic migration."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL не задан")
    from .postgres import PostgresDatabase

    db = PostgresDatabase(settings.database_url)
    try:
        revision = await db.execute(
            "SELECT version_num FROM alembic_version ORDER BY version_num LIMIT 1")
        if not await revision.fetchone():
            raise RuntimeError(
                "Alembic schema revision is missing; run `alembic upgrade head`")
        if seed:
            from .seed import seed_defaults
            async with db.transaction():
                await seed_defaults(db)
        return db
    except SQLAlchemyError as exc:
        await db.close()
        raise RuntimeError(
            "PostgreSQL schema is unavailable; run `alembic upgrade head`") from exc
    except Exception:
        await db.close()
        raise


@asynccontextmanager
async def transaction(db):
    """Атомарный пишущий блок. Внутри НЕ вызывать db.commit().

    Вложенные вызовы из той же задачи выполняются внутри внешней транзакции —
    это нужно сервисам (деньги: оплата→выдача одним коммитом), которые
    оборачивают несколько repo-операций в свои `transaction()`.
    """
    async with db.transaction():
        yield db


async def healthcheck(db) -> dict:
    """Состояние БД для /health и админки."""
    return await db.healthcheck()
