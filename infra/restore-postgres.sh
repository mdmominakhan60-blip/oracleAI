#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 /path/to/oracle-YYYYMMDD-HHMMSS.dump.enc" >&2
  exit 2
fi

encrypted="$1"
key_file="${BACKUP_ENCRYPTION_KEY_FILE:-/etc/oracle/backup.key}"
compose_file="${COMPOSE_FILE:-infra/docker-compose.yml}"
target_db="${RESTORE_TARGET_DB:-}"

if [[ -z "$target_db" ]]; then
  echo "RESTORE_TARGET_DB is required; restore into a fresh isolated database" >&2
  exit 1
fi
if [[ ! "$target_db" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
  echo "RESTORE_TARGET_DB must be a simple PostgreSQL database identifier" >&2
  exit 1
fi
if [[ "$target_db" == "${POSTGRES_DB:-oracle}" ]]; then
  [[ "${RESTORE_IN_PLACE:-0}" == "1" && "${RESTORE_CONFIRM:-}" == "I_UNDERSTAND_IN_PLACE_RESTORE" ]] || {
    echo "in-place restore requires RESTORE_IN_PLACE=1 and explicit confirmation" >&2
    exit 1
  }
fi

[[ -r "$encrypted" ]] || { echo "backup is not readable: $encrypted" >&2; exit 1; }
[[ -r "$encrypted.sha256" ]] || { echo "checksum is missing: $encrypted.sha256" >&2; exit 1; }
[[ -r "$key_file" ]] || { echo "backup key is not readable: $key_file" >&2; exit 1; }

sha256sum --check "$encrypted.sha256"
tmp="$(mktemp --suffix=.oracle.dump)"
cleanup() { rm -f "$tmp"; }
trap cleanup EXIT

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 \
  -pass "file:${key_file}" -in "$encrypted" -out "$tmp"

# An isolated target database is the default. Writers are stopped only for
# an explicitly confirmed in-place restore into the live database.
if [[ "$target_db" == "${POSTGRES_DB:-oracle}" ]]; then
  docker compose -f "$compose_file" stop api bot worker beat
else
  # createdb has no --if-not-exists until PostgreSQL 18; probe first so the
  # rehearsal stays idempotent and isolated on PG16. docker exec runs as root,
  # so connect over TCP with the application role instead of a peer socket.
  if ! docker compose -f "$compose_file" exec -T \
    -e PGUSER="${POSTGRES_USER:-oracle}" -e PGPASSWORD="${POSTGRES_PASSWORD}" -e PGHOST=localhost \
    postgres \
    psql --dbname=postgres --tuples-only --no-align \
    --command "SELECT 1 FROM pg_database WHERE datname = '$target_db'" \
    | grep -q '^1$'; then
    docker compose -f "$compose_file" exec -T \
      -e PGUSER="${POSTGRES_USER:-oracle}" -e PGPASSWORD="${POSTGRES_PASSWORD}" -e PGHOST=localhost \
      postgres \
      createdb --username="${POSTGRES_USER:-oracle}" -- "$target_db"
  fi
fi
cat "$tmp" | docker compose -f "$compose_file" exec -T \
  -e PGUSER="${POSTGRES_USER:-oracle}" \
  -e PGPASSWORD="${POSTGRES_PASSWORD}" \
  -e PGHOST=localhost \
  postgres \
  pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname="$target_db"

echo "PostgreSQL restore completed into isolated database '$target_db'. Review output and run integrity/owner-isolation checks before application use."
