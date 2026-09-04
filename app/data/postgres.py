"""Async SQLAlchemy/asyncpg backend behind the existing repository DB protocol.

All SQL call sites speak native PostgreSQL dialect (ADR-0001): named :params,
explicit ON CONFLICT (<col>) DO NOTHING, explicit RETURNING id. The SQLite→PG
translation shim described in ADR-0003 has been removed (DB-001 close-out).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from contextvars import ContextVar
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


def _split_script(script: str) -> list[str]:
    """Split DDL without treating semicolons in comments/strings as separators."""
    statements: list[str] = []
    start = 0
    quote: str | None = None
    line_comment = False
    i = 0
    while i < len(script):
        char = script[i]
        nxt = script[i + 1] if i + 1 < len(script) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            i += 1
            continue
        if quote:
            if char == quote:
                if nxt == quote:
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if char == "-" and nxt == "-":
            line_comment = True
            i += 2
            continue
        if char in ("'", '"'):
            quote = char
        elif char == ";":
            statement = script[start:i].strip()
            if statement:
                statements.append(statement)
            start = i + 1
        i += 1
    tail = script[start:].strip()
    if tail:
        statements.append(tail)
    return statements


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(int(os.getenv(name, str(default))), minimum)
    except (TypeError, ValueError):
        return default


def _coerce_pg(value):
    """PostgreSQL NUMERIC arrives as Decimal; repositories expect int/float."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _qmark_to_named(sql: str) -> str:
    """Convert positional '?' placeholders to named :pN binds.

    Only bare placeholders are translated; '?' inside string literals stays
    untouched. App SQL is native named-param; this keeps positional call sites
    (the test layer and legacy repo helpers) working on the native driver."""
    out: list[str] = []
    index = 0
    counter = 0
    quote = None
    while index < len(sql):
        ch = sql[index]
        if quote:
            if ch == quote:
                quote = None
            out.append(ch)
            index += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            index += 1
        elif ch == "?":
            counter += 1
            out.append(f":p{counter}")
            index += 1
        else:
            out.append(ch)
            index += 1
    return "".join(out)


def _prepare_params(sql: str, params: Any) -> tuple[str, Any]:
    if isinstance(params, dict):
        return sql, params
    values = list(params) if isinstance(params, (tuple, list)) else []
    if "?" not in sql:
        return sql, {}
    sql = _qmark_to_named(sql)
    return sql, {f"p{i}": value for i, value in enumerate(values, 1)}


def _to_positional(sql: str, rows: list[Any]) -> tuple[str, list[dict]]:
    if not rows or isinstance(rows[0], dict):
        return sql, rows
    bind_rows = []
    for row in rows:
        bind_rows.append({f"p{i}": value for i, value in enumerate(row, 1)})
    return _qmark_to_named(sql), bind_rows


class PostgresRow:
    """A row-compatible view over a SQLAlchemy Row (supports row["col"])."""

    __slots__ = ("_values", "_mapping")

    def __init__(self, row):
        mapping = {key: _coerce_pg(value) for key, value in row._mapping.items()}
        self._values = tuple(mapping.values())
        self._mapping = mapping

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return self._mapping[key]

    def __iter__(self):
        # `dict(row)` is used throughout the existing repositories.
        return iter(self._mapping.items())

    def keys(self):
        return self._mapping.keys()

    def get(self, key, default=None):
        return self._mapping.get(key, default)

    def __repr__(self) -> str:
        return repr(self._mapping)


class PostgresCursor:
    def __init__(self, rows: Iterable[PostgresRow] = (), *, rowcount: int = -1,
                 lastrowid: int | None = None):
        self._rows = list(rows)
        self._position = 0
        self.rowcount = rowcount
        self.lastrowid = lastrowid

    async def fetchone(self):
        if self._position >= len(self._rows):
            return None
        row = self._rows[self._position]
        self._position += 1
        return row

    async def fetchall(self):
        rows = self._rows[self._position:]
        self._position = len(self._rows)
        return rows

    async def fetchmany(self, size: int | None = None):
        end = self._position + (size or 1)
        rows = self._rows[self._position:end]
        self._position += len(rows)
        return rows


class PostgresDatabase:
    """Connection-pool backed async DB object used by current repositories."""

    is_postgres = True

    def __init__(self, url: str):
        self.url = url
        self.engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            pool_size=_env_int("PG_POOL_SIZE", 10),
            max_overflow=_env_int("PG_MAX_OVERFLOW", 10, minimum=0),
            pool_timeout=_env_int("PG_POOL_TIMEOUT", 30),
            # Recycle idle connections to survive NAT/PgBouncer silent timeouts.
            pool_recycle=_env_int("PG_POOL_RECYCLE", 1800),
        )
        self._connection: ContextVar[Any] = ContextVar(
            "oracle_pg_connection", default=None)

    async def execute(self, sql: str, params: Any = ()) -> PostgresCursor:
        sql, bind = _prepare_params(sql, params)
        connection = self._connection.get()
        if connection is not None:
            result = await connection.execute(text(sql), bind)
            return self._cursor_from_result(result)
        if sql.upper().startswith(("SELECT", "WITH", "SHOW", "EXPLAIN")):
            async with self.engine.connect() as connection:
                result = await connection.execute(text(sql), bind)
                return self._cursor_from_result(result)
        async with self.engine.begin() as connection:
            result = await connection.execute(text(sql), bind)
            return self._cursor_from_result(result)

    @staticmethod
    def _cursor_from_result(result) -> PostgresCursor:
        rows = [PostgresRow(row) for row in result.fetchall()] if result.returns_rows else []
        return PostgresCursor(rows, rowcount=result.rowcount)

    async def executemany(self, sql: str, rows: Iterable[Any]) -> PostgresCursor:
        rows = list(rows)
        if not rows:
            return PostgresCursor([], rowcount=0)
        sql, bind_rows = _to_positional(sql, rows)
        connection = self._connection.get()
        if connection is not None:
            result = await connection.execute(text(sql), bind_rows)
        else:
            async with self.engine.begin() as connection:
                result = await connection.execute(text(sql), bind_rows)
        return PostgresCursor([], rowcount=result.rowcount)

    async def executescript(self, script: str) -> None:
        statements = _split_script(script)
        async with self.engine.begin() as connection:
            for statement in statements:
                await connection.execute(text(statement))

    async def commit(self) -> None:
        # Non-transactional statements use engine.begin() and are committed already.
        return None

    async def rollback(self) -> None:
        return None

    @asynccontextmanager
    async def transaction(self):
        current = self._connection.get()
        if current is not None:
            yield self
            return
        async with self.engine.begin() as connection:
            token = self._connection.set(connection)
            try:
                yield self
            finally:
                self._connection.reset(token)

    async def healthcheck(self) -> dict:
        cur = await self.execute("SELECT current_database(), current_setting('server_version')")
        row = await cur.fetchone()
        tables = await self.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public'")
        users = await self.execute("SELECT COUNT(*) FROM users")
        return {
            "ok": True,
            "integrity": "ok",
            "database": row[0] if row else None,
            "server_version": row[1] if row else None,
            "journal_mode": "postgresql",
            "page_count": None,
            "users": (await users.fetchone())[0],
            "schema_tables": (await tables.fetchone())[0],
        }

    async def close(self) -> None:
        await self.engine.dispose()
