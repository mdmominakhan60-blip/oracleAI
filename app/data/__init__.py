"""Слой данных: подключение и seed.

Разделение ответственности:
- `postgres.py` — PostgreSQL-адаптер репозиторного DB-протокола;
- `session.py`  — подключение к БД, проверка миграционной ревизии, транзакции;
- `seed.py`     — идемпотентные product seeds.

DDL живёт исключительно в Alembic (`alembic/schema/baseline.sql` + версии в
`alembic/versions/`). Историческая пара `schema.py` (SQLite-flavour) +
`pg_schema.py` (SQLite→PostgreSQL transform) удалена.

Репозитории (`app/repo/`) — единственные, кто пишет SQL поверх этого слоя.
"""
from .session import connect, healthcheck, utcnow  # noqa: F401

__all__ = ["connect", "healthcheck", "utcnow"]
