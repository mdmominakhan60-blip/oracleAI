from __future__ import annotations


import pytest

from scripts.reset_test_database import _asyncpg_dsn, _database_name, main


def test_reset_helper_normalizes_sqlalchemy_postgres_url():
    assert _asyncpg_dsn(
        "postgresql+asyncpg://user:pass@db:5432/oracle_test?sslmode=require"
    ) == "postgresql://user:pass@db:5432/oracle_test?sslmode=require"


def test_reset_helper_accepts_only_safe_postgres_database_name():
    assert _database_name("postgresql://user:pass@db:5432/oracle_test") == "oracle_test"

    with pytest.raises(ValueError, match="database URL must use PostgreSQL"):
        _database_name("sqlite:///oracle_test.db")

    with pytest.raises(ValueError, match="protected database"):
        _database_name("postgresql://user:pass@db:5432/postgres")

    with pytest.raises(ValueError, match="protected database"):
        _database_name("postgresql://user:pass@db:5432/template1")

    with pytest.raises(ValueError, match="ending in '_test'"):
        _database_name("postgresql://user:pass@db:5432/oracle")

    with pytest.raises(ValueError, match="invalid database name"):
        _database_name("postgresql://user:pass@db:5432/oracle-prod")


def test_reset_helper_rejects_prod_database_url():
    with pytest.raises(ValueError, match="ending in '_test'"):
        _database_name("postgresql://user:pass@db:5432/oracle")


def test_main_requires_allow_db_reset(monkeypatch):
    monkeypatch.delenv("ALLOW_DB_RESET", raising=False)
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://user:pass@db:5432/oracle_test")
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0


def test_main_does_not_fallback_to_database_url(monkeypatch):
    monkeypatch.delenv("ALLOW_DB_RESET", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db:5432/oracle")
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code != 0
