# ADR-0001 — Target SQL dialect for DB-001 migration (SQLAlchemy named params)

**Status:** accepted; superseded in outcome by [ADR-0003](ADR-0003-shim-removal.md) (2026-08-30) — the shim, `_ID_TABLES` and `_INSERT_TABLE_RE` have been removed; all call-sites use the native PostgreSQL dialect described below. Kept as historical record of the dialect decision.
**Date:** 2026-08-29
**Task:** DB-001, Etap 1

## Context

`app/data/postgres.py::_translate_sql` translates SQLite idioms to PostgreSQL on the fly:

- Positional `?` placeholders → `$N` / named `:pN` via `text()`
- `INSERT OR IGNORE` → `INSERT … ON CONFLICT DO NOTHING` (empty conflict target)
- Auto-injection of `RETURNING id` for 31 tables in `_ID_TABLES`

The shim exists because ~400 `?` placeholders and 33 `INSERT OR IGNORE` calls were copied
from the original SQLite schema. The goal of DB-001 is to move all SQL call-sites to a
native PostgreSQL dialect so the shim can be deleted (week 3).

## Decision

**Target dialect:** SQLAlchemy `text()` with named parameters, `ON CONFLICT (<col>) DO NOTHING`,
and explicit `RETURNING id` in INSERT statements that need the inserted PK.

**Why not raw asyncpg?**
There are 70+ call sites that rely on the cursor/row protocol (`cursor.fetchone()`,
`row["col"]`, `cursor.rowcount`, `cursor.lastrowid`). Migrating all of them to asyncpg's
`Record` protocol in a single step would be a massive blast radius with no way to do it
incrementally. SQLAlchemy's `text()` with asyncpg dialect works transparently behind the
existing `PostgresDatabase` interface, keeping the blast radius per-file.

**Why named params (`:name` + dict) rather than positional (`$N` + list)?**
- Positional `?` are already translated by the shim; the shim also tracks the generated
  names to build the `dict` for SQLAlchemy. Moving to explicit named params removes the
  need for that translation entirely.
- Named params are self-documenting in complex queries (e.g. multi-param INSERTs).
- SQLAlchemy `text()` natively accepts `dict` params — no adapter needed.
- Positional `$1/$2` require manual numbering and break on query refactoring.

**Why `ON CONFLICT (<col>) DO NOTHING` and not empty `DO NOTHING`?**
The empty form (`ON CONFLICT DO NOTHING`) suppresses **any** constraint violation, including
unexpected FK violations and check violations. Specifying the conflict column (the UNIQUE or
PK column) ensures only the intended uniqueness constraint is silenced.

**Backward compatibility during migration:**
The shim (`_translate_sql`) continues to process all SQL that still uses `?`. Files ported
to native PG dialect bypass the shim automatically: named `:param` SQL contains no `?`, so
the shim's placeholder-replacement loop is a no-op and `INSERT OR IGNORE` detection does not
fire. `execute()` also supports `dict` params directly (already handled by `_bind_params`).
No code change to `postgres.py` is required to handle already-ported files correctly.

## Consequences

- Each repo file can be ported independently; the shim handles unported files.
- After all files are ported (week 3), the shim, `_ID_TABLES`, and `_INSERT_TABLE_RE` can
  be deleted in a single clean-up commit.
- `rowcount` semantics for `ON CONFLICT DO NOTHING` are `0` on conflict (PostgreSQL
  returns affected row count = 0 when nothing was inserted). Callers that check
  `if cur.rowcount:` correctly treat a conflict as "nothing was inserted."
- `lastrowid` is populated from `RETURNING id` results by `_cursor_from_result`; explicit
  `RETURNING id` in ported INSERT statements replaces the `_ID_TABLES` auto-injection.
