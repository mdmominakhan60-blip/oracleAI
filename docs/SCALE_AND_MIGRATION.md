# PostgreSQL scale and migration runbook

## Current decision

**OracleAI uses PostgreSQL as its sole database backend** in development, test, staging and production. `DATABASE_URL` is mandatory; an absent or non-PostgreSQL URL is a configuration error. The application uses SQLAlchemy 2.0 with `asyncpg`, while Alembic is the authoritative schema creation and change mechanism.

The database is not created or upgraded implicitly by application startup. Deployments must run `alembic upgrade head` before starting API, bot, workers or Beat. The `vector` extension is an infrastructure/DBA prerequisite when `PGVECTOR_ENABLED=1`; it is not a substitute for a migration.

## Operational measurements

Run measurements against the target PostgreSQL instance with a role that has only the required read permissions. Do not export raw user content or payment data.

```bash
DATABASE_URL=postgresql+asyncpg://oracle:password@db:5432/oracle \
  alembic current
```

For a lightweight SQL check, use PostgreSQL metadata and aggregate counts:

```sql
SELECT current_database(), current_setting('server_version');
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';
SELECT extname FROM pg_extension ORDER BY extname;
```

## Scale trigger matrix

| Signal | Observe now | Trigger | Response |
|---|---|---|---|
| Connections | Pool usage, wait time, active sessions and `pg_stat_activity`. | Pool exhaustion, rising wait time or connection budget breach. | Recalculate worker/pool budget, cap overflow, and inspect long-running transactions. |
| Table/index growth | `pg_total_relation_size`, row counts and index/table ratio. | Growth outside the retention or capacity budget. | Review retention, query plans and indexes before increasing resources. |
| Query latency | p50/p95/p99 for history, chat, memory, billing and analytics. | Error-budget breach or an unexplained regression. | Capture `EXPLAIN (ANALYZE, BUFFERS)` on a safe replica and fix the query/index contract. |
| PostgreSQL health | `SELECT 1`, readiness, locks, checkpoints and replication state where applicable. | Failed readiness, lock pressure or replication lag. | Stop unsafe rollout, resolve the DB incident and verify recovery before resuming. |
| Backup | Dump duration, checksum, encryption, retention and restore result. | Missed RPO/RTO, checksum failure or restore failure. | Stop release, repair the backup path and repeat an isolated restore drill. |
| API load | p50/p95, 5xx, pool wait, queue depth and provider latency. | Error budget or capacity threshold is exceeded. | Separate deterministic/API work from LLM and background workloads; then retest. |

A threshold is not an automatic schema change. Record the observation window, workload, release, user impact and rollback option in the incident or release note.

## Clean database rebuild

For a disposable test database, use the reset helper only with a dedicated PostgreSQL database name. It refuses protected database names and never accepts SQLite paths.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://oracle:oracle@127.0.0.1:5432/oracle_test \
POSTGRES_ADMIN_DATABASE_URL=postgresql+asyncpg://oracle:oracle@127.0.0.1:5432/postgres \
PGVECTOR_ENABLED=1 \
python scripts/reset_test_database.py

DATABASE_URL=postgresql+asyncpg://oracle:oracle@127.0.0.1:5432/oracle_test \
PGVECTOR_ENABLED=1 \
alembic upgrade head

DATABASE_URL=postgresql+asyncpg://oracle:oracle@127.0.0.1:5432/oracle_test \
PGVECTOR_ENABLED=1 \
python -m pytest tests/ -q
```

The expected order is **reset → extension → Alembic → seed/fixtures → tests**. Application processes must not be used to repair a missing table or column. The CI workflow provisions PostgreSQL, waits for readiness, applies migrations through the test harness, and then runs pytest.

## Production migration procedure

1. Provision PostgreSQL 16 or newer, create a least-privilege application role, and enable `vector` through the infrastructure/DBA path when embeddings are enabled.
2. Take an encrypted PostgreSQL backup and verify its checksum and restore listing before the release.
3. Run `DATABASE_URL=... alembic upgrade head` with the migration role.
4. Verify `alembic_version`, required tables, foreign keys, indexes, extensions and `/api/health`.
5. Run offline or mocked smoke flows on staging: profile, history, chat, reports, billing and webhook idempotency.
6. Start API, bot, workers and Beat only after migration completion and dependency readiness.
7. Record the revision, release ID, health evidence, smoke output and rollback owner in the release evidence.

Do not run a migration against production from an application startup hook, and do not perform an ad-hoc `ALTER TABLE` without a reviewed Alembic revision and backup.

## Rollback and recovery

Rollback is a **forward deployment or PostgreSQL restore procedure**, not a return to SQLite and not an Alembic downgrade of the baseline. Stop writes if necessary, preserve the incident evidence, restore an isolated PostgreSQL database first, validate schema and application smoke flows, and promote the verified recovery according to the deployment runbook. Keep the application and migration revisions compatible with the restored database.

PostgreSQL backup and restore helpers are [`infra/backup-postgres.sh`](../infra/backup-postgres.sh) and [`infra/restore-postgres.sh`](../infra/restore-postgres.sh). Backup artifacts must remain encrypted and checksummed; plaintext dumps must not be retained by the monitoring or release contract.

## Load test entry points

The workload in `load/` uses synthetic users and must target a disposable PostgreSQL database. Do not run it against production or with real Telegram sessions.

```bash
DATABASE_URL=postgresql+asyncpg://oracle:oracle@127.0.0.1:5432/oracle_load \
PGVECTOR_ENABLED=1 \
python scripts/seed_load.py --count 5000

APP_ENV=dev DEV_MODE=1 \
DATABASE_URL=postgresql+asyncpg://oracle:oracle@127.0.0.1:5432/oracle_load \
python -m uvicorn app.api.main:app --port 8000

locust -f load/locustfile.py --host http://127.0.0.1:8000 -u 1000 -r 25 --run-time 2m
```

The report must include release ID, PostgreSQL version, migration revision, p50/p95/p99 per endpoint, 5xx, pool wait, lock errors, backup duration and LLM calls. LLM generation is a separate workload; do not infer AI capacity from read-only API traffic.

## References

[1]: ../alembic/versions/0001_pg_baseline.py "PostgreSQL baseline schema"
[2]: ../alembic/versions/0003_widen_tg_id_to_bigint.py "PostgreSQL identifier widening"
[3]: ../scripts/reset_test_database.py "Disposable PostgreSQL test database reset"
[4]: ../infra/backup-postgres.sh "Encrypted PostgreSQL backup helper"
[5]: ../infra/restore-postgres.sh "Isolated PostgreSQL restore helper"
