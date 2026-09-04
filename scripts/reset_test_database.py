"""Recreate an isolated PostgreSQL database for tests.

The command is intentionally explicit and destructive: it only accepts a database
name from a PostgreSQL URL and refuses PostgreSQL template/system databases. Schema
creation remains Alembic's responsibility; this utility only resets the database
and installs the optional pgvector extension required by the test schema.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
from urllib.parse import unquote, urlsplit, urlunsplit

import asyncpg


_POSTGRES_SCHEME = re.compile(r"^postgresql(?:\+[^:]+)?$", re.IGNORECASE)
_PROTECTED_DATABASES = {"postgres", "template0", "template1"}


def _asyncpg_dsn(url: str) -> str:
    parts = urlsplit(url)
    if not _POSTGRES_SCHEME.fullmatch(parts.scheme):
        raise ValueError("database URL must use PostgreSQL")
    return urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment))


def _database_name(url: str) -> str:
    name = urlsplit(_asyncpg_dsn(url)).path.removeprefix("/")
    if not name or name in _PROTECTED_DATABASES or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("refusing to reset an invalid or protected database name")
    return name


def _quoted_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _database_user(url: str) -> str:
    user = unquote(urlsplit(_asyncpg_dsn(url)).username or "")
    if not user or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", user):
        raise ValueError("target PostgreSQL URL must include a safe application username")
    return user


def _admin_dsn(target_url: str, explicit: str | None) -> str:
    if explicit:
        return _asyncpg_dsn(explicit)
    target = urlsplit(_asyncpg_dsn(target_url))
    return urlunsplit((target.scheme, target.netloc, "/postgres", target.query, target.fragment))


def _database_dsn(admin_dsn: str, name: str) -> str:
    parts = urlsplit(admin_dsn)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


async def reset(database_url: str, admin_url: str | None = None) -> str:
    name = _database_name(database_url)
    owner = _database_user(database_url)
    admin = await asyncpg.connect(_admin_dsn(database_url, admin_url))
    try:
        await admin.execute(f"DROP DATABASE IF EXISTS {_quoted_identifier(name)} WITH (FORCE)")
        await admin.execute(
            f"CREATE DATABASE {_quoted_identifier(name)} OWNER {_quoted_identifier(owner)}")
    finally:
        await admin.close()

    if os.getenv("PGVECTOR_ENABLED", "1") == "1":
        extension_dsn = _database_dsn(_admin_dsn(database_url, admin_url), name)
        extension = await asyncpg.connect(extension_dsn)
        try:
            await extension.execute("CREATE EXTENSION IF NOT EXISTS vector")
        finally:
            await extension.close()
    return name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL", ""),
        help="target PostgreSQL URL; defaults to TEST_DATABASE_URL or DATABASE_URL",
    )
    parser.add_argument(
        "--admin-database-url",
        default=os.getenv("POSTGRES_ADMIN_DATABASE_URL"),
        help="optional PostgreSQL URL with CREATEDB privilege",
    )
    args = parser.parse_args()
    if not args.database_url:
        parser.error("--database-url, TEST_DATABASE_URL, or DATABASE_URL is required")
    name = asyncio.run(reset(args.database_url, args.admin_database_url))
    print(f"recreated PostgreSQL test database: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
