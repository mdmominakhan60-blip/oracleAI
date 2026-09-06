#!/usr/bin/env python3
"""Idempotently ensure the oracle_test PostgreSQL role exists with least privilege.

Called from ``make ensure-test-role`` and before tests (make test / CI). Requires a
superuser DSN (``POSTGRES_ADMIN_DATABASE_URL``) — typically the ``postgres`` maintenance
database on the primary cluster.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re

import asyncpg

DEFAULT_ROLE = "oracle_test"

_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def _quote_literal(value: str) -> str:
    # asyncpg не допускает bind-параметры в utility-командах (CREATE/ALTER ROLE),
    # поэтому пароль встраивается литералом с удвоением одинарных кавычек.
    return "'" + value.replace("'", "''") + "'"


def _validated_role(role: str) -> str:
    if not _ROLE_NAME.fullmatch(role):
        raise ValueError(f"refusing unsafe role name: {role!r}")
    return role


def role_ddl(role: str, password: str, exists: bool) -> str:
    verb = "ALTER ROLE" if exists else "CREATE ROLE"
    return (
        f"{verb} {_validated_role(role)} WITH LOGIN "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE "
        f"PASSWORD {_quote_literal(password)}"
    )


async def ensure(admin_dsn: str, role: str, password: str) -> str:
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = $1)", role,
        )
        await conn.execute(role_ddl(role, password, bool(exists)))
        action = "normalized" if exists else "created"
        print(f"{action} role {role} (NOSUPERUSER NOCREATEDB NOCREATEROLE)")
        return action
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure oracle_test PostgreSQL role")
    parser.add_argument(
        "--admin-database-url",
        default=os.getenv("POSTGRES_ADMIN_DATABASE_URL"),
        help="superuser DSN (e.g. postgresql://oracle:pass@host:5432/postgres)",
    )
    parser.add_argument("--role", default=DEFAULT_ROLE)
    parser.add_argument(
        "--password",
        default=os.getenv("TEST_ROLE_PASSWORD") or os.getenv("POSTGRES_PASSWORD") or "",
        help="role password; defaults to TEST_ROLE_PASSWORD, then POSTGRES_PASSWORD",
    )
    args = parser.parse_args()
    if not args.admin_database_url:
        raise SystemExit("POSTGRES_ADMIN_DATABASE_URL is required")
    if not args.password:
        raise SystemExit(
            "role password is required: pass --password "
            "or set TEST_ROLE_PASSWORD / POSTGRES_PASSWORD"
        )
    asyncio.run(ensure(args.admin_database_url, args.role, args.password))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
