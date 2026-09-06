"""Unit tests for scripts.ensure_test_role (BUS-303).

Covers DDL generation, literal quoting, and CLI validation without a live
PostgreSQL connection. Any test that would require a running database is
skipped — `make ensure-test-role` covers the idempotent happy path.
"""
from __future__ import annotations

import os
import runpy

# conftest.py выставляет DEV_MODE=1; config.py требует APP_ENV=dev|test.
# Выставляем до любых импортов, которые триггерят загрузку config.
os.environ.setdefault("APP_ENV", "test")

import pytest

from scripts.ensure_test_role import _quote_literal, _validated_role, role_ddl


# ---------------------------------------------------------------------------
# role_ddl — SQL text generation
# ---------------------------------------------------------------------------

def test_role_ddl_create():
    ddl = role_ddl("oracle_test", "s3cret!", exists=False)
    assert ddl == (
        "CREATE ROLE oracle_test WITH LOGIN "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE "
        "PASSWORD 's3cret!'"
    )


def test_role_ddl_alter():
    ddl = role_ddl("oracle_test", "n3w-pw", exists=True)
    assert ddl.startswith("ALTER ROLE oracle_test WITH ")
    assert "NOSUPERUSER NOCREATEDB NOCREATEROLE" in ddl
    assert "PASSWORD 'n3w-pw'" in ddl


def test_role_ddl_rejects_unsafe_name():
    with pytest.raises(ValueError, match="unsafe role name"):
        role_ddl("ORACLE_TEST", "pw", exists=False)
    with pytest.raises(ValueError, match="unsafe role name"):
        role_ddl("oracle;DROP", "pw", exists=False)


# ---------------------------------------------------------------------------
# _quote_literal — SQL injection protection
# ---------------------------------------------------------------------------

def test_quote_literal_plain():
    assert _quote_literal("s3cret!") == "'s3cret!'"


def test_quote_literal_escapes_single_quotes():
    assert _quote_literal("it's") == "'it''s'"


def test_quote_literal_empty():
    assert _quote_literal("") == "''"


# ---------------------------------------------------------------------------
# _validated_role — input validation
# ---------------------------------------------------------------------------

def test_validated_role_accepts_snake_case():
    assert _validated_role("oracle_test") == "oracle_test"


def test_validated_role_rejects_bad_chars():
    with pytest.raises(ValueError):
        _validated_role("oracle-test")
    with pytest.raises(ValueError, match="unsafe"):
        _validated_role("oracle_test; DROP")


# ---------------------------------------------------------------------------
# main() — CLI validation
# ---------------------------------------------------------------------------


def test_main_requires_admin_dsn(monkeypatch):
    monkeypatch.delenv("POSTGRES_ADMIN_DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_ROLE_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path("scripts/ensure_test_role.py", run_name="__main__")
    assert exc.value.code != 0


def test_main_requires_password(monkeypatch):
    monkeypatch.setenv("POSTGRES_ADMIN_DATABASE_URL", "postgresql://u:p@h:5432/postgres")
    monkeypatch.delenv("TEST_ROLE_PASSWORD", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        runpy.run_path("scripts/ensure_test_role.py", run_name="__main__")
    assert exc.value.code != 0
