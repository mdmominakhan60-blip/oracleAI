"""Create the OracleAI PostgreSQL native baseline schema.

Revision ID: 0001_pg_baseline
Revises:

Загружает native PostgreSQL DDL из `alembic/schema/baseline.sql`. Это
единственная точка создания схемы: `app/data/schema.py` (SQLite-flavour) и
`app/data/pg_schema.py` (SQLite→PostgreSQL transform) удалены.
"""
from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001_pg_baseline"
down_revision = None
branch_labels = None
depends_on = None


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "baseline.sql"


def _statements(script: str) -> list[str]:
    """Split a SQL script on unquoted, non-commented semicolons.

    Historically we used app.data.postgres._split_script here. That module is a
    runtime helper; keeping the splitter inline lets Alembic run without
    importing runtime code (better isolation for migrations).
    """
    parts: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(script):
        ch = script[i]
        nxt = script[i + 1] if i + 1 < len(script) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            buf.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                buf.append("*/")
                i += 2
                continue
            buf.append(ch)
            i += 1
            continue
        if in_single:
            buf.append(ch)
            if ch == "'":
                if nxt == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            in_line_comment = True
            buf.append("--")
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            buf.append("/*")
            i += 2
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            statement = "".join(buf).strip()
            if statement:
                parts.append(statement)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _is_effective(statement: str) -> bool:
    """Skip pure-comment statements (a leading /* ... */ or -- block)."""
    for line in statement.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        return True
    return False


def upgrade() -> None:
    script = SCHEMA_PATH.read_text(encoding="utf-8")
    for statement in _statements(script):
        if _is_effective(statement):
            op.execute(statement)


def downgrade() -> None:
    # Downgrade is intentionally conservative: dropping a production database
    # from a migration is unsafe. Restore a backup instead of deleting data.
    raise RuntimeError("PostgreSQL baseline downgrade is destructive; restore a backup")
