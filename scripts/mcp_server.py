#!/usr/bin/env python3
"""Read-only MCP-сервер oracleAI (BUS-254): аналитика и CRM для Paperclip-агентов.

Транспорт: MCP JSON-RPC 2.0 over stdio (initialize / tools/list / tools/call).
Реализация на stdlib + asyncpg — без новой зависимости в продуктовом локе:
поверх read-only репозиториев MCP-протокол тут тривиален.

Данные читаются ТОЛЬКО через app/repo (единственный владелец SQL по ADR).
Пул открывается с default_transaction_read_only=on и statement_timeout:
даже бага в repo-запросе не даст записать данные staging/prod БД.

Запуск: ORACLEAI_MCP_DATABASE_URL=postgresql+asyncpg://... python3 scripts/mcp_server.py
Лончер для агентов: ~/.local/bin/oracleai-mcp (секрет в ~/.oracleai-mcp.env, 600).
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import asyncpg  # noqa: E402

# ────────────────────────────── пул (read-only) ──────────────────────────────

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        import os

        url = os.getenv("ORACLEAI_MCP_DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError(
                "ORACLEAI_MCP_DATABASE_URL не задан (postgresql+asyncpg://...)")
        m = re.match(
            r"postgresql\+asyncpg://([^:]+):([^@]+)@([^:/]+):(\d+)/(\w+)", url)
        if not m:
            raise RuntimeError("ORACLEAI_MCP_DATABASE_URL: ожидался формат "
                               "postgresql+asyncpg://user:pass@host:port/db")
        user, password, host, port, database = m.groups()
        _pool = await asyncpg.create_pool(
            user=user, password=password, host=host, port=int(port),
            database=database, min_size=1, max_size=4,
            command_timeout=30,
            server_settings={
                "default_transaction_read_only": "on",
                "statement_timeout": "30000",
                "idle_in_transaction_session_timeout": "15000",
            },
        )
    return _pool


def _jsonable(value):
    """asyncpg отдаёт datetime/Decimal — приводим к JSON-совместимым типам."""
    import datetime as dt
    import decimal

    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return value.decode("utf-8", errors="replace")
    return value


# ────────────────────────────── инструменты ──────────────────────────────────
# app/repo импортируем лениво в вызовах: модуль тянет app.config (dotenv .env
# продукта), и на хосте без .env импорт на старте уронил бы весь сервер.

async def _repo(module: str):
    from app import repo
    return getattr(repo, module)


TOOLS = [
    {
        "name": "analytics_overview",
        "description": (
            "Верхние KPI oracleAI: пользователи (total/today/7d/30d, onboarded, "
            "подписки), DAU/WAU/MAU, вопросы, расклады, выручка в Stars, платившие."),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "analytics_activation_funnel",
        "description": "Privacy-safe Mini App activation/return funnel по first-open когорте за N дней.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 120,
                                    "description": "Окно наблюдения, дней (по умолчанию 30)"}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "analytics_funnel",
        "description": "Воронка конверсии по когорте регистрации: пришла → онбординг → вопрос → возврат → оплата.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 120}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "analytics_retention",
        "description": "Retention-когорты по дню регистрации (day1/day3/day7) за N дней.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 120}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "analytics_llm_costs",
        "description": "Затраты на LLM: токены и стоимость по дням/провайдерам за N дней.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 120}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "analytics_monetization",
        "description": "Монетизационные KPI: конверсия в оплату, выручка по источникам, подписки.",
        "inputSchema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "minimum": 1, "maximum": 120}},
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "crm_search_users",
        "description": "Поиск клиенток CRM: по имени/username/telegram id + сегмент (all/active/free/paying/...).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Имя, username или tg_id"},
                "segment": {"type": "string", "description": "Сегмент users.segment_ids (по умолчанию all)"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                "offset": {"type": "integer", "minimum": 0},
                "order": {"type": "string", "enum": ["created_at", "last_seen", "ltv", "name"]},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "crm_user_card",
        "description": (
            "Карточка клиентки 360°: профиль, план подписки, теги, заметки, память, "
            "диалоги, расклады, PDF-отчёты, заказы, кристаллы, рефералы, события. "
            "Требует tg_id (целое число)."),
        "inputSchema": {
            "type": "object",
            "properties": {"tg_id": {"type": "integer", "description": "Telegram user id"}},
            "required": ["tg_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "crm_tags",
        "description": "Все теги CRM с количеством пользовательниц.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "db_health",
        "description": "Здоровье БД oracleAI: имя базы, версия сервера, число таблиц, пользователи.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": {"readOnlyHint": True},
    },
]


async def call_tool(name: str, arguments: dict):
    days = int(arguments.get("days") or 30)
    if name == "db_health":
        pool = await _get_pool()
        async with pool.acquire() as conn:
            database = await conn.fetchval("SELECT current_database()")
            version = await conn.fetchval("SHOW server_version")
            tables = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='public'")
            users = await conn.fetchval("SELECT COUNT(*) FROM users")
        return {"database": database, "server_version": version,
                "schema_tables": tables, "users": users}

    if name == "analytics_overview":
        db = _DbFacade(await _get_pool())
        return _jsonable(await (await _repo("analytics")).overview(db))

    if name == "analytics_activation_funnel":
        db = _DbFacade(await _get_pool())
        return _jsonable(await (await _repo("analytics")).activation_funnel(db, days=days))

    if name == "analytics_funnel":
        db = _DbFacade(await _get_pool())
        return _jsonable(await (await _repo("analytics")).funnel(db, days=days))

    if name == "analytics_retention":
        db = _DbFacade(await _get_pool())
        return _jsonable(await (await _repo("analytics")).retention(db, cohort_days=7))

    if name == "analytics_llm_costs":
        db = _DbFacade(await _get_pool())
        return _jsonable(await (await _repo("analytics")).llm_costs(db, days=days))

    if name == "analytics_monetization":
        db = _DbFacade(await _get_pool())
        return _jsonable(await (await _repo("analytics")).monetization_kpis(db, days=days))

    if name == "crm_search_users":
        db = _DbFacade(await _get_pool())
        users_repo = await _repo("users")
        rows = await users_repo.search(
            db,
            query=str(arguments.get("query") or ""),
            segment=str(arguments.get("segment") or "all"),
            limit=min(int(arguments.get("limit") or 20), 100),
            offset=int(arguments.get("offset") or 0),
            order=str(arguments.get("order") or "created_at"),
        )
        total = await users_repo.count(
            db, query=str(arguments.get("query") or ""),
            segment=str(arguments.get("segment") or "all"))
        # PII-минимизация для списков: без профиля/чартов, только идентификация.
        fields = ("tg_id", "name", "username", "lang", "sub_level", "sub_until",
                  "crystals", "ltv_stars", "onboarded", "status", "created_at",
                  "last_seen")
        return {"total": total,
                "users": [{k: _jsonable(r.get(k)) for k in fields} for r in rows]}

    if name == "crm_user_card":
        tg_id = int(arguments["tg_id"])
        db = _DbFacade(await _get_pool())
        card = await (await _repo("crm")).user_card(db, tg_id)
        return _jsonable(card) if card else {"error": f"пользователь {tg_id} не найден"}

    if name == "crm_tags":
        db = _DbFacade(await _get_pool())
        return _jsonable(await (await _repo("crm")).all_tags(db))

    raise KeyError(f"неизвестный инструмент: {name}")


class _Row(dict):
    """dict с доступом и по строковому ключу, и по позиции (row[0])."""

    def __init__(self, record):
        super().__init__(record)
        self._values = tuple(record.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class _DbFacade:
    """Адаптер asyncpg-пула под протокол repo-функций (fetch→execute)."""

    is_postgres = True  # repo-функции выбирают диалект SQL по этому флагу

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    class _Cursor:
        def __init__(self, rows):
            self._rows = [_Row(r) for r in rows]
            self._pos = 0

        async def fetchone(self):
            if self._pos >= len(self._rows):
                return None
            row = self._rows[self._pos]
            self._pos += 1
            return row

        async def fetchall(self):
            self._pos = len(self._rows)
            return self._rows

        async def fetchmany(self, size=None):
            end = self._pos + (size or 1)
            rows = self._rows[self._pos:end]
            self._pos = len(rows) + self._pos
            return rows

    async def execute(self, sql: str, params=None):
        params = params or {}
        # repo-слой использует именованные :param — переводим в $N для asyncpg.
        names = []

        def _sub(match):
            names.append(match.group(1))
            return f"${len(names)}"

        pg_sql = re.sub(r"(?<![:\w]):(\w+)", _sub, sql)
        args = [params[n] for n in names]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(pg_sql, *args)
        return self._Cursor(rows)


# ────────────────────────────── JSON-RPC stdio ───────────────────────────────

PROTOCOL_VERSION = "2024-11-05"


async def _dispatch(request: dict) -> dict | None:
    method = request.get("method")
    request_id = request.get("id")
    is_notification = request_id is None

    def reply(result):
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def error(code: int, message: str):
        return {"jsonrpc": "2.0", "id": request_id,
                "error": {"code": code, "message": message}}

    try:
        if method == "initialize":
            return reply({
                "protocolVersion": request.get("params", {}).get(
                    "protocolVersion", PROTOCOL_VERSION),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "oracleai", "version": "0.1.0"},
            })
        if method == "notifications/initialized":
            return None
        if method == "ping":
            return reply({})
        if method == "tools/list":
            return reply({"tools": TOOLS})
        if method == "tools/call":
            params = request.get("params") or {}
            try:
                result = await call_tool(
                    str(params.get("name")), dict(params.get("arguments") or {}))
                return reply({
                    "content": [{"type": "text",
                                 "text": json.dumps(result, ensure_ascii=False)}],
                    "isError": False,
                })
            except KeyError as exc:
                return reply({"content": [{"type": "text",
                                           "text": str(exc)}], "isError": True})
            except Exception as exc:  # tool-level failure → isError, не crash
                return reply({"content": [{"type": "text",
                                           "text": f"{type(exc).__name__}: {exc}"}],
                              "isError": True})
        if is_notification:
            return None
        return error(-32601, f"метод не найден: {method}")
    except Exception as exc:
        if is_notification:
            return None
        return error(-32603, f"{type(exc).__name__}: {exc}")


async def serve() -> None:
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    await loop.connect_read_pipe(
        lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)
    out_lock = asyncio.Lock()
    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response = {"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32700, "message": "ошибка разбора JSON"}}
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            continue
        response = await _dispatch(request)
        if response is not None:
            async with out_lock:
                sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
                sys.stdout.flush()


if __name__ == "__main__":
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass
