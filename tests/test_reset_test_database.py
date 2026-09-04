from __future__ import annotations

import pytest

from scripts.reset_test_database import _asyncpg_dsn, _database_name


def test_reset_helper_normalizes_sqlalchemy_postgres_url():
    assert _asyncpg_dsn(
        "postgresql+asyncpg://user:pass@db:5432/oracle_test?sslmode=require"
    ) == "postgresql://user:pass@db:5432/oracle_test?sslmode=require"


def test_reset_helper_accepts_only_safe_postgres_database_name():
    assert _database_name("postgresql://user:pass@db:5432/oracle_test") == "oracle_test"

    with pytest.raises(ValueError, match="PostgreSQL"):
        _database_name("sqlite:///oracle_test.db")

    with pytest.raises(ValueError, match="protected"):
        _database_name("postgresql://user:pass@db:5432/postgres")

    with pytest.raises(ValueError, match="protected"):
        _database_name("postgresql://user:pass@db:5432/template1")

    with pytest.raises(ValueError, match="protected"):
        _database_name("postgresql://user:pass@db:5432/oracle-test")
