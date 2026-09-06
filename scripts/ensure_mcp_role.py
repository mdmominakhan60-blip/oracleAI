#!/usr/bin/env python3
"""Idempotently ensure the oracle_mcp_ro PostgreSQL role exists (BUS-277).

Second defense layer for the read-only MCP server on top of the
``default_transaction_read_only`` server setting: the role itself holds only
SELECT, so even a connection without server_settings cannot write.

Requires a superuser DSN (``POSTGRES_ADMIN_DATABASE_URL``) and the role
password (``ORACLEAI_MCP_ROLE_PASSWORD`` — independent secret, NOT the
POSTGRES_PASSWORD). Works on existing clusters (restores, migrated volumes);
fresh clusters can run the same script right after ``make up``.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re

import asyncpg

DEFAULT_ROLE = "oracle_mcp_ro"
DEFAULT_SCHEMA = "public"

_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
_SCHEMA_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    # asyncpg не допускает bind-параметры в utility-командах (CREATE/ALTER ROLE),
    # поэтому пароль встраивается литералом с удвоением одинарных кавычек.
    return "'" + value.replace("'", "''") + "'"


def _validated(value: str, pattern: re.Pattern, what: str) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"refusing unsafe {what}: {value!r}")
    return value


async def ensure(admin_dsn: str, role: str, password: str, schema: str) -> dict:
    conn = await asyncpg.connect(admin_dsn)
    try:
        exists = bool(await conn.fetchval(
            "SELECT 1 FROM pg_roles WHERE rolname = $1", role,
        ))
        ddl = (
            f"{'ALTER ROLE' if exists else 'CREATE ROLE'} "
            f"{_quote_ident(role)} WITH LOGIN "
            "NOSUPERUSER NOCREATEDB NOCREATEROLE "
            f"PASSWORD {_quote_literal(password)}"
        )
        await conn.execute(ddl)

        owner = await conn.fetchval(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()",
        )
        grants = [
            f"GRANT USAGE ON SCHEMA {_quote_ident(schema)} TO {_quote_ident(role)}",
            f"GRANT SELECT ON ALL TABLES IN SCHEMA {_quote_ident(schema)} TO {_quote_ident(role)}",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {_quote_ident(owner)} "
            f"IN SCHEMA {_quote_ident(schema)} GRANT SELECT ON TABLES TO {_quote_ident(role)}",
        ]
        for g in grants:
            await conn.execute(g)

        action = "normalized" if exists else "created"
        print(
            f"{action} role {role} (NOSUPERUSER NOCREATEDB NOCREATEROLE, SELECT-only "
            f"on schema {schema}, default privileges for owner {owner})"
        )
        return {"action": action, "role": role, "owner": owner, "schema": schema}
    finally:
        await conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure oracle_mcp_ro read-only role")
    parser.add_argument(
        "--admin-database-url",
        default=os.getenv("POSTGRES_ADMIN_DATABASE_URL"),
        help="superuser DSN (e.g. postgresql://oracle:pass@host:5432/postgres)",
    )
    parser.add_argument("--role", default=DEFAULT_ROLE)
    parser.add_argument("--schema", default=DEFAULT_SCHEMA)
    parser.add_argument(
        "--password",
        default=os.getenv("ORACLEAI_MCP_ROLE_PASSWORD", ""),
        help="role password; required (set ORACLEAI_MCP_ROLE_PASSWORD)",
    )
    args = parser.parse_args()
    _validated(args.role, _ROLE_NAME, "role name")
    _validated(args.schema, _SCHEMA_NAME, "schema name")
    if not args.admin_database_url:
        raise SystemExit("POSTGRES_ADMIN_DATABASE_URL is required")
    if not args.password:
        raise SystemExit(
            "role password is required: pass --password or set ORACLEAI_MCP_ROLE_PASSWORD "
            "(independent secret; generate with: openssl rand -hex 24)"
        )
    asyncio.run(ensure(args.admin_database_url, args.role, args.password, args.schema))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
