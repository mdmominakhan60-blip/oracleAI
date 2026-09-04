# ADR-0003 — DB-001 Shim Removal Plan (SHIM_ENFORCED gate)

**Status:** accepted
**Date:** 2026-08-30
**Task:** DB-001 finalize, part of the multi-etap PostgreSQL/Frontend/Arch plan

## Context

ADR-0001 fixed the target SQL dialect for DB-001 (SQLAlchemy `text()` + named params +
explicit `ON CONFLICT (<col>) DO NOTHING` + explicit `RETURNING id`). ADR-0002 finished
the architecture migration. As of this ADR the SQL shim inventory
(`docs/SQL_SHIM_INVENTORY.md`) reports the following outstanding files still using
positional `?` and/or `INSERT OR IGNORE`:

| File | `?` | `INSERT OR IGNORE` | lastrowid | Notes |
|------|-----|--------------------|-----------|-------|
| `app/repo/analytics.py` | 61 | 0 | 0 | week 3 (heavy aggregations) |
| `app/repo/monetization.py` | 72 | 1 | 2 | week 3 (v2 catalog paths) |
| `app/repo/notifications.py` | 14 | 0 | 0 | week 3 (short helpers) |
| `app/repo/palm.py` | 18 | 0 | 1 | week 3 (upload trails) |
| `app/repo/readings.py` | 96 | 0 | 5 | week 3 (largest — tarot + natal ledgers) |
| `app/services/chat.py` | 2 | 0 | 0 | leftover MIN(day) sub-select |
| `app/services/scheduler.py` | 26 | 0 | 0 | job planning queries |
| `app/data/seed.py` | 18 | 5 | 0 | product seed (last, after everything else migrated) |

Weeks 1-2 (users, content, admin, dialog, billing, growth, comms, crm, jobs, horoscopes,
payment_monitor) are DONE and marked in the inventory report.

## Decision

Introduce a `SHIM_ENFORCED` feature flag on `PostgresDatabase` that controls what happens
when `_translate_sql` decides the SQL still needs translation:

- **`SHIM_ENFORCED=0` (default, current prod)** — the shim silently translates the SQL
  and warns via the `oracle.db.shim` logger with the caller frame. Nothing breaks; the
  warning surfaces via the existing log pipeline so we can see how much traffic still uses
  the shim in production.
- **`SHIM_ENFORCED=1` (CI + staging)** — the shim raises `LegacyShimUsageError` with the
  offending SQL. Any un-ported query fails the test, the CI job, or the staging boot. The
  flag is turned on in `.github/workflows/ci.yml` for the `quality` job after week 3 so
  every new query lands native.
- **After one green production release with `SHIM_ENFORCED=1` and zero warnings for two
  weeks** — the shim, `_ID_TABLES`, `_INSERT_TABLE_RE`, and the whole `_translate_sql`
  function are deleted in a single clean-up commit; `PostgresDatabase.execute` stops
  mutating SQL entirely.

## Why a flag, not a hard cut

- Zero-downtime: the migration is being done incrementally per repo; a hard cut would
  freeze the branch for weeks.
- Observability first: prod logs the exact call sites still using the shim so week-3 work
  gets a precise checklist rather than a grep.
- Reversible: flipping `SHIM_ENFORCED=0` restores the prior behaviour in one env change.

## Detection heuristic

The shim classifies SQL as "still needs translation" iff EITHER of these is true:

1. The SQL contains a `?` placeholder outside a string literal.
2. The SQL starts with `INSERT OR IGNORE`.

Both are structural, deterministic, and match what ADR-0001 sets as the migration target.

## Consequences

- CI gains one env var (`SHIM_ENFORCED=1`) and a targeted test that a native-dialect query
  is unchanged by the shim, while a legacy-dialect query is now rejected.
- Production `oracle.db.shim` logs become the authoritative "still to port" list.
- Once the counter in `docs/SQL_SHIM_INVENTORY.md` reaches zero across all repos, we do a
  clean-up PR that deletes the shim; this is the DB-001 close-out.

## Rollback

The flag defaults to off. A regression that would depend on the shim continues to work
in production while it is deployed and only fails in CI, giving the team a full release
cycle to react before the shim is deleted.

## Close-out (DB-001, 2026-08-30)

The inventory reached 0 placeholders and 0 `INSERT OR IGNORE` across all repos
(see `docs/SQL_SHIM_INVENTORY.md`, commit ae42aac). With no remaining call sites,
the two-week warning soak is moot: the shim is dead code. In the close-out commit
the shim, `LegacyShimUsageError`, `_ID_TABLES`, `_INSERT_TABLE_RE` and
`_translate_sql` were deleted; `PostgresDatabase.execute` no longer mutates SQL.
Remaining call sites that still used legacy dialect (geocache, safety events,
shared context, diary/history/profile routers) were ported to native PG named
params in the same change. `SHIM_ENFORCED` removed from CI.
