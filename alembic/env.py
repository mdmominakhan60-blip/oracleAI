from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    # BUS-755: compose migrate-сервис работает админ-ролью (oracle, DDL).
    # DATABASE_URL_ADMIN применяется, только если указывает на ту же базу,
    # что и DATABASE_URL: в тестах (make _test) DATABASE_URL переопределяется
    # на oracle_test через -e, а env_file-наследие несёт прод-DATABASE_URL_ADMIN.
    # Без этой проверки миграции тестов ушли бы в прод-БД.
    admin = os.getenv("DATABASE_URL_ADMIN", "").strip()
    base = os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url")

    def _db_name(url: str) -> str:
        return url.rsplit("/", 1)[-1].split("?")[0] if url else ""

    url = admin if admin and base and _db_name(admin) == _db_name(base) else base
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), literal_binds=True,
                      dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=None,
                      compare_type=True, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
