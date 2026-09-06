#!/usr/bin/env python3
"""Fail-closed guard for the test database URL (BUS-304).

Прод-инцидент 2026-09-06: агентский ран прогнал тесты против прод-базы,
потому что окружение насле­довало .env, а проверки жили только в
reset-хелпере. Этот модуль закрывает последний fail-open вектор: pytest
отказывается стартовать, если эффективный URL указывает не на *_test базу.

Правило одно: TEST_DATABASE_URL приоритетен, DATABASE_URL никогда не
используется как молчаливый fallback на прод. Самодостаточен (без asyncpg),
чтобы запускаться голым python3 в любом окружении.
"""
from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlsplit

_POSTGRES_SCHEME = re.compile(r"postgresql(?:\+[^:]+)?", re.IGNORECASE)
_DATABASE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ALLOWED_SUFFIX = "_test"


def database_name(url: str) -> str:
    """Имя базы из PostgreSQL URL; ValueError для не-PostgreSQL и пустых имён."""
    parts = urlsplit(url.strip())
    if not _POSTGRES_SCHEME.fullmatch(parts.scheme):
        raise ValueError(
            "database URL must be PostgreSQL (postgresql:// or postgresql+asyncpg://)"
        )
    name = parts.path.removeprefix("/")
    if not _DATABASE_NAME.fullmatch(name):
        raise ValueError("database URL must contain a valid database name")
    return name


def validate_test_database_url(url: str) -> str:
    """Имя тестовой базы; ValueError, если база не оканчивается на _test."""
    name = database_name(url)
    if not name.endswith(_ALLOWED_SUFFIX):
        raise ValueError(
            f"refusing to run tests against database '{name}': "
            f"only databases ending in '{_ALLOWED_SUFFIX}' are safe "
            f"(production databases must never receive test traffic)"
        )
    return name


def ensure_test_environment() -> str | None:
    """Вернуть None, если окружение безопасно для тестов, иначе текст ошибки.

    TEST_DATABASE_URL приоритетен (согласовано с tests/conftest.py):
    заданный и валидный test-URL проходит, даже если DATABASE_URL — прод.
    """
    test_url = os.getenv("TEST_DATABASE_URL", "")
    if test_url.strip():
        try:
            validate_test_database_url(test_url)
        except ValueError as exc:
            return f"TEST_DATABASE_URL is unsafe: {exc}"
        return None
    prod_url = os.getenv("DATABASE_URL", "")
    if not prod_url.strip():
        return (
            "no database URL: set TEST_DATABASE_URL to a *_test database; "
            "DATABASE_URL is never used as a fallback"
        )
    try:
        validate_test_database_url(prod_url)
    except ValueError as exc:
        return (
            f"DATABASE_URL points at a non-test database and TEST_DATABASE_URL "
            f"is not set: {exc}. Set TEST_DATABASE_URL (e.g. "
            f"postgresql+asyncpg://user:pass@host:5432/oracle_test) or run make test"
        )
    return None


def main() -> int:
    problem = ensure_test_environment()
    if problem:
        print(f"test env guard: {problem}", file=sys.stderr)
        return 1
    url = os.getenv("TEST_DATABASE_URL", "") or os.getenv("DATABASE_URL", "")
    print(f"test env guard: OK ({database_name(url)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
