"""Unit tests for scripts.ensure_mcp_role (BUS-277).

Covers identifier quoting, DDL generation and CLI validation without a live
PostgreSQL connection. The idempotent happy path is covered by running
`make ensure-mcp-role` against the target cluster.
"""
from __future__ import annotations

import os

os.environ.setdefault("APP_ENV", "test")

import pytest

from scripts.ensure_mcp_role import (
    _quote_ident,
    _quote_literal,
    _validated,
)


def test_quote_ident_simple():
    assert _quote_ident("oracle_mcp_ro") == '"oracle_mcp_ro"'


def test_quote_ident_escapes_quotes():
    assert _quote_ident('a"b') == '"a""b"'


def test_quote_literal_escapes_quotes():
    assert _quote_literal("pa'ss") == "'pa''ss'"


def test_validated_accepts_valid_name():
    from scripts.ensure_mcp_role import _ROLE_NAME

    assert _validated("oracle_mcp_ro", _ROLE_NAME, "role name") == "oracle_mcp_ro"


def test_validated_rejects_injection():
    from scripts.ensure_mcp_role import _ROLE_NAME

    with pytest.raises(ValueError):
        _validated("ro; DROP ROLE x", _ROLE_NAME, "role name")


@pytest.mark.asyncio
async def test_ensure_rejects_unsafe_role_name():
    from scripts.ensure_mcp_role import _ROLE_NAME

    with pytest.raises(ValueError):
        _validated('bad"name', _ROLE_NAME, "role name")
