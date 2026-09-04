#!/usr/bin/env bash
set -Eeuo pipefail

: "${BACKUP_ENCRYPTION_KEY_FILE:?BACKUP_ENCRYPTION_KEY_FILE is required}"
: "${BACKUP_KEEP:=14}"
: "${BACKUP_REQUIRE_ENCRYPTION:=1}"
: "${BACKUP_REQUIRE_OFFSITE:=0}"
: "${BACKUP_STATUS_FILE:=/backups/backup-status.json}"

if [[ ! -r "$BACKUP_ENCRYPTION_KEY_FILE" ]]; then
  echo "backup key is missing or unreadable: $BACKUP_ENCRYPTION_KEY_FILE" >&2
  exit 1
fi

s3_fields=(BACKUP_S3_ACCESS_KEY BACKUP_S3_SECRET_KEY BACKUP_S3_BUCKET)
s3_configured=0
for field in "${s3_fields[@]}"; do
  [[ -n "${!field:-}" ]] && s3_configured=1
done
if [[ "$s3_configured" == "1" ]]; then
  for field in "${s3_fields[@]}"; do
    [[ -n "${!field:-}" ]] || {
      echo "incomplete S3 backup configuration: $field is missing" >&2
      exit 1
    }
  done
fi
if [[ "$BACKUP_REQUIRE_OFFSITE" == "1" && "$s3_configured" != "1" ]]; then
  echo "BACKUP_REQUIRE_OFFSITE=1 but S3-compatible backup configuration is absent" >&2
  exit 1
fi

mkdir -p /backups
write_status() {
  local timestamp="$1" local_ok="$2" offsite_required="$3" offsite_ok="$4"
  printf '{"last_attempt_utc":"%s","local_backup_ok":%s,"offsite_required":%s,"offsite_ok":%s}\n' \
    "$timestamp" "$local_ok" "$offsite_required" "$offsite_ok" >"$BACKUP_STATUS_FILE"
}

# Never remove a completed backup on shutdown; only clean the in-progress dump.
tmp=""
trap 'rm -f "${tmp:-}"' EXIT

while true; do
  ts="$(date -u +%Y%m%d-%H%M%S)"
  iso_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  tmp="/backups/.oracle-${ts}.dump.tmp"
  encrypted="/backups/oracle-${ts}.dump.enc"

  if pg_dump --format=custom --no-owner --no-privileges --file="$tmp"; then
    # A custom-format dump can be listed without restoring it. This catches
    # truncated/corrupt output before encryption and retention are applied.
    pg_restore --list "$tmp" >/dev/null
    if [[ "$BACKUP_REQUIRE_ENCRYPTION" != "1" ]]; then
      echo "BACKUP_REQUIRE_ENCRYPTION must remain 1 for production backups" >&2
      write_status "$iso_ts" false "$BACKUP_REQUIRE_OFFSITE" false
      sleep 300
      continue
    fi
    openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt \
      -pass "file:${BACKUP_ENCRYPTION_KEY_FILE}" \
      -in "$tmp" -out "$encrypted"
    rm -f "$tmp"
    sha256sum "$encrypted" > "${encrypted}.sha256"
    offsite_ok=false
    if [[ "$s3_configured" == "1" ]]; then
      if /usr/local/bin/upload_s3_backup.py "$encrypted"; then
        offsite_ok=true
      else
        echo "off-site upload failed; retaining encrypted local backup and retrying later" >&2
      fi
    fi
    write_status "$iso_ts" true "$BACKUP_REQUIRE_OFFSITE" "$offsite_ok"
    if [[ "$BACKUP_REQUIRE_OFFSITE" == "1" && "$offsite_ok" != "true" ]]; then
      sleep 300
      continue
    fi
    echo "encrypted PostgreSQL backup created: $(basename "$encrypted")"
  else
    echo "pg_dump failed; retaining previous backups" >&2
    write_status "$iso_ts" false "$BACKUP_REQUIRE_OFFSITE" false
    rm -f "$tmp"
  fi

  find /backups -maxdepth 1 -type f -name 'oracle-*.dump.enc' \
    -mtime +"$BACKUP_KEEP" -delete
  find /backups -maxdepth 1 -type f -name 'oracle-*.dump.enc.sha256' \
    -mtime +"$BACKUP_KEEP" -delete
  sleep 86400
done
