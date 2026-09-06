"""BUS-304: guard против тестовых прогонов против прод-базы."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.test_env_guard import database_name, ensure_test_environment

ROOT = Path(__file__).resolve().parent.parent
TEST_URL = "postgresql+asyncpg://oracle:oracle@postgres:5432/oracle_test"
PROD_URL = "postgresql+asyncpg://oracle:oracle@postgres:5432/oracle"


def test_database_name_parses_sqlalchemy_and_plain_urls():
    assert database_name("postgresql://u:p@db:5432/oracle_test") == "oracle_test"
    assert database_name(TEST_URL) == "oracle_test"
    assert database_name(f"{TEST_URL}?sslmode=require") == "oracle_test"


def test_database_name_rejects_non_postgres_and_empty():
    with pytest.raises(ValueError, match="must be PostgreSQL"):
        database_name("sqlite:///test.db")
    with pytest.raises(ValueError, match="valid database name"):
        database_name("postgresql://u:p@db:5432/")


def test_validate_rejects_non_test_suffix():
    from scripts.test_env_guard import validate_test_database_url

    with pytest.raises(ValueError, match="ending in '_test'"):
        validate_test_database_url(PROD_URL)
    assert validate_test_database_url(TEST_URL) == "oracle_test"


def test_good_test_url_passes(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)
    assert ensure_test_environment() is None


def test_test_url_overrides_prod_database_url(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", TEST_URL)
    monkeypatch.setenv("DATABASE_URL", PROD_URL)
    assert ensure_test_environment() is None


def test_no_urls_fails_closed(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert "no database URL" in ensure_test_environment()


def test_prod_database_url_without_test_url_fails(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", PROD_URL)
    assert "non-test database" in ensure_test_environment()


def test_non_postgres_test_url_fails(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "sqlite:///oracle_test.db")
    assert "must be PostgreSQL" in ensure_test_environment()


def test_non_test_suffix_in_test_url_fails(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", PROD_URL)
    assert "unsafe" in ensure_test_environment()


@pytest.mark.parametrize(
    "env, expected",
    [
        ({"TEST_DATABASE_URL": TEST_URL}, 0),
        ({"DATABASE_URL": TEST_URL}, 0),
        ({"TEST_DATABASE_URL": PROD_URL}, 1),
        ({"DATABASE_URL": PROD_URL}, 1),
        ({}, 1),
    ],
)
def test_cli_exit_codes(monkeypatch, env, expected):
    for name in ("TEST_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "test_env_guard.py")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected
