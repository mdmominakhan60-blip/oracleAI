# PostgreSQL backup and restore drill

**Дата:** 28 августа 2026

## Local verification

The repository’s local verification is a static infrastructure contract plus a disposable PostgreSQL rebuild. Run:

```bash
python3 scripts/check_p004_infrastructure.py
bash -n infra/backup-postgres.sh infra/restore-postgres.sh

TEST_DATABASE_URL=postgresql+asyncpg://oracle_test:oracle_test@127.0.0.1:5432/oracle_test \
POSTGRES_ADMIN_DATABASE_URL=postgresql://postgres:admin-password@127.0.0.1:5432/postgres \
python3 scripts/reset_test_database.py

DATABASE_URL=postgresql+asyncpg://oracle_test:oracle_test@127.0.0.1:5432/oracle_test \
alembic upgrade head
```

The reset helper accepts only a dedicated PostgreSQL database name, refuses protected databases, creates the database with the application role as owner and leaves schema creation to Alembic. It is a destructive test utility; never point it at a shared or production database.

The P0-004 gate verifies the Compose backup profile, encrypted PostgreSQL custom-format dump and checksum contract, S3-compatible uploader, explicit storage path, isolated restore guard, PostgreSQL freshness/off-site alerting and CI wiring. It does not pretend that local static checks prove production key custody, bucket access, RPO/RTO or restore timing.

## Production-like drill

Before public launch, run the encrypted backup and restore scripts with production storage permissions, key custody, a real off-site bucket, retention, checksum verification and an isolated target database. Record the source revision, backup artifact metadata, restore duration, row/schema checks, `/api/health`, representative owner-isolation checks, and rollback decision. Remove temporary plaintext dump files after verification.

The supported helpers are [`infra/backup-postgres.sh`](../infra/backup-postgres.sh) and [`infra/restore-postgres.sh`](../infra/restore-postgres.sh). A PostgreSQL restore is performed into an isolated target first; production in-place restore requires both explicit safety flags and an approved incident owner. This drill remains an external P0 launch gate until executed in a production-like environment.

## Executed rehearsal (2026-09-03)

A production-like rehearsal ran on 2026-09-03 against the running PostgreSQL/pgvector database:

- **Backup:** pg_dump (custom format) → `openssl enc -aes-256-cbc -pbkdf2` (key `/etc/oracle/backup.key`, outside the DB/repo) → `sha256sum`; uploaded to the off-site S3-compatible bucket `oracleai-backups/oracleai/` (MinIO). Object `oracle-20260903-032904.dump.enc` + `.sha256` verified present; local copy header starts with openssl `Salted__` (encrypted, not plaintext); checksum `ЦЕЛ`/OK.
- **Restore:** performed from the **off-site copy** (`mc cp` from MinIO, not the local directory) into an isolated database `oracle_restore`. Schema (extensions `vector 0.8.6`, `plpgsql`; all `public.*` tables) and per-table row counts matched the live database; a functional `vector <->` distance query returned the expected value. The isolated database was dropped afterwards; the live database was not modified.
- **Fixes found:** PG16 `createdb --if-not-exists` unsupported → psql existence probe; `docker compose exec` runs as root → explicit `PGUSER`/`PGPASSWORD`/`PGHOST=localhost` (commit d48ea7c).
- **Evidence:** [`infra/restore-rehearsal/2026-09-03-p0-004-backup-restore-rehearsal.md`](../infra/restore-rehearsal/2026-09-03-p0-004-backup-restore-rehearsal.md) (full runbook, dumps, checksums). Static gate `scripts/check_p004_infrastructure.py` passes 40/40.

Scope note: the off-site destination here is local S3-compatible MinIO. Swapping `BACKUP_S3_URL` for a real S3/R2/Backblaze endpoint with real key custody is what remains external before public launch; the encryption/checksum/restore mechanics are unchanged by that swap.

## References

[1]: ../scripts/check_p004_infrastructure.py "P0-004 static infrastructure gate"
[2]: ../scripts/reset_test_database.py "Disposable PostgreSQL database reset"
[3]: ../infra/backup-postgres.sh "Encrypted PostgreSQL backup helper"
[4]: ../infra/restore-postgres.sh "PostgreSQL restore helper"
