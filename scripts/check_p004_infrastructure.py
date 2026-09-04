"""Static contract gate for P0-004 backup, restore and recovery infrastructure."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(text: str, needle: str, label: str, failures: list[str]) -> None:
    if needle not in text:
        failures.append(f"{label}: missing {needle!r}")


def check() -> list[str]:
    failures: list[str] = []
    compose = (ROOT / "infra/docker-compose.yml").read_text(encoding="utf-8")
    backup = (ROOT / "infra/backup-postgres.sh").read_text(encoding="utf-8")
    backup_dockerfile = (ROOT / "infra/backup.Dockerfile").read_text(encoding="utf-8")
    restore = (ROOT / "infra/restore-postgres.sh").read_text(encoding="utf-8")
    upload = (ROOT / "scripts/upload_s3_backup.py").read_text(encoding="utf-8")
    alerts = (ROOT / "scripts/ops_alerts.py").read_text(encoding="utf-8")
    prod_env = (ROOT / ".env.production.example").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for path in (
        ROOT / "infra/backup-postgres.sh",
        ROOT / "infra/restore-postgres.sh",
        ROOT / "scripts/upload_s3_backup.py",
    ):
        if not path.is_file() or not path.stat().st_mode & 0o111:
            failures.append(f"{path.relative_to(ROOT)}: must be executable")

    for needle in (
        'dockerfile: infra/backup.Dockerfile',
        'APP_ENV: ${APP_ENV:?APP_ENV must be set explicitly}',
        'DATABASE_URL: ${DATABASE_URL:?DATABASE_URL must be set to a PostgreSQL URL}',
        'POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}',
        'GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?GRAFANA_ADMIN_PASSWORD must be set}',
        'BACKUP_REQUIRE_OFFSITE: ${BACKUP_REQUIRE_OFFSITE:-0}',
        'BACKUP_STATUS_FILE: /backups/backup-status.json',
        '${BACKUP_STORAGE_PATH:-./backups}:/backups',
        './backup-postgres.sh:/usr/local/bin/backup-postgres.sh:ro',
        'env_file:\n      - ../.env',
    ):
        require(compose, needle, "compose backup service", failures)

    for needle in (
        "FROM postgres:16-bookworm",
        "python3-boto3",
        "COPY scripts/upload_s3_backup.py",
    ):
        require(backup_dockerfile, needle, "backup image", failures)

    for needle in (
        "pg_dump --format=custom",
        "pg_restore --list",
        "openssl enc -aes-256-cbc -pbkdf2",
        "sha256sum",
        "BACKUP_REQUIRE_OFFSITE",
        "/usr/local/bin/upload_s3_backup.py",
        "backup-status.json",
    ):
        require(backup, needle, "backup helper", failures)

    for needle in (
        'RESTORE_TARGET_DB is required',
        'RESTORE_CONFIRM',
        'I_UNDERSTAND_IN_PLACE_RESTORE',
        'SELECT 1 FROM pg_database WHERE datname',
        '--dbname="$target_db"',
        'sha256sum --check',
    ):
        require(restore, needle, "restore helper", failures)

    for needle in (
        'boto3.client',
        'BACKUP_S3_ACCESS_KEY',
        'BACKUP_S3_SECRET_KEY',
        'BACKUP_S3_BUCKET',
        'client.upload_file',
    ):
        require(upload, needle, "off-site uploader", failures)

    for needle in ('oracle-*.dump.enc', 'backup-status.json', 'backup_offsite_unavailable'):
        require(alerts, needle, "backup monitoring", failures)

    for needle in (
        'BACKUP_REQUIRE_ENCRYPTION=1',
        'BACKUP_REQUIRE_OFFSITE=1',
        'BACKUP_S3_URL=',
        'BACKUP_S3_BUCKET=',
        'BACKUP_STORAGE_PATH=',
    ):
        require(prod_env, needle, "production backup env contract", failures)

    for needle in (
        'python scripts/check_p004_infrastructure.py',
        'bash -n infra/backup-postgres.sh infra/restore-postgres.sh',
    ):
        require(ci, needle, "CI P0-004 gate", failures)

    for needle in ('p004-audit:', 'backup:', 'restore:', 'backup-drill:'):
        require(makefile, needle, "Makefile P0-004 target", failures)

    # Refuse accidental plaintext/sensitive backup naming in the tracked infra.
    if re.search(r"oracle-\*\.dump(?!\.enc)", compose + backup):
        failures.append("backup artifact contract: plaintext dump glob found")

    return failures


def main() -> int:
    failures = check()
    result = {"ok": not failures, "checks": 40 - len(failures), "failures": failures}
    print(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
