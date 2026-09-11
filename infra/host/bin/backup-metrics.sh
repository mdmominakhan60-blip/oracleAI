#!/usr/bin/env bash
# BUS-833: экспорт метрик бэкап-цикла прода на VPS в node-exporter textfile.
# Источник — /srv/oracle/backups/backup-status.json (пишет infra-backup-1, формат
# infra/backup-postgres.sh:write_status) + возраст свежайшего oracle-*.dump.enc.
# node-exporter на VPS скрейпит textfile-каталог (BUS-603-паттерн) → Prometheus →
# алерты OracleAIBackupStale / OracleAIBackupOffsiteStale (infra/observability/alerts.yml).
#
# Размещение на VPS: /opt/oracleAI/infra/host/bin/backup-metrics.sh
# systemd --user таймер (ubuntu@VPS): oracleai-backup-metrics.{service,timer} —
# OnCalendar=*:0/10 (каждые 10 мин, RPO D4 требует обнаружения за часы, не секунды).
set -Eeuo pipefail

BACKUP_DIR="${BACKUP_DIR:-/srv/oracle/backups}"
STATUS_FILE="$BACKUP_DIR/backup-status.json"
OUT_DIR="${OUT_DIR:-/var/lib/oracleai/textfile}"
OUT_FILE="$OUT_DIR/backup-status.prom"
# Алерт стейлится на 26ч (суточный цикл + запас на ретраи, см. alerts.yml).
STALE_SECONDS="${STALE_SECONDS:-93600}"

install -d -m 755 "$OUT_DIR"

now=$(date -u +%s)
last_attempt=0
local_ok=0
offsite_required=0
offsite_ok=0

if [[ -r "$STATUS_FILE" ]]; then
  ts=$(python3 - "$STATUS_FILE" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
    from calendar import timegm
    t = d.get("last_attempt_utc", "")
    print(timegm(__import__("time").strptime(t, "%Y-%m-%dT%H:%M:%SZ")))
except Exception:
    print(0)
PY
  )
  [[ "$ts" =~ ^[0-9]+$ ]] && last_attempt=$ts
  grep -q '"local_backup_ok":true' "$STATUS_FILE" && local_ok=1
  grep -q '"offsite_required":true' "$STATUS_FILE" && offsite_required=1
  grep -q '"offsite_ok":true' "$STATUS_FILE" && offsite_ok=1
fi

# Возраст свежайшего дампа по mtime (источник истины — файл, не только статус).
newest=0
if compgen -G "$BACKUP_DIR/oracle-*.dump.enc" >/dev/null; then
  f=$(ls -t "$BACKUP_DIR"/oracle-*.dump.enc | head -1)
  newest=$(stat -c %Y "$f")
fi

age_now=$(( now - last_attempt ))
age_newest=$(( now - newest ))
stale=$(( age_newest > STALE_SECONDS ? 1 : 0 ))
# Offsite считается протухшим, если требуется и последний успешный offsite
# был при уже протухшем дампе либо статус не подтверждает offsite_ok.
offsite_stale=0
if (( offsite_required == 1 && offsite_ok != 1 )); then offsite_stale=1; fi

tmp=$(mktemp "$OUT_DIR/.backup-status.XXXXXX")
{
  echo "# HELP oracleai_backup_last_attempt_unixtime Last backup attempt (UTC epoch)"
  echo "# TYPE oracleai_backup_last_attempt_unixtime gauge"
  echo "oracleai_backup_last_attempt_unixtime $last_attempt"
  echo "# HELP oracleai_backup_newest_dump_unixtime Newest encrypted dump mtime (UTC epoch)"
  echo "# TYPE oracleai_backup_newest_dump_unixtime gauge"
  echo "oracleai_backup_newest_dump_unixtime $newest"
  echo "# HELP oracleai_backup_newest_age_seconds Age of newest encrypted dump"
  echo "# TYPE oracleai_backup_newest_age_seconds gauge"
  echo "oracleai_backup_newest_age_seconds $age_newest"
  echo "# HELP oracleai_backup_stale Newest dump older than RPO window"
  echo "# TYPE oracleai_backup_stale gauge"
  echo "oracleai_backup_stale $stale"
  echo "# HELP oracleai_backup_last_status_ok Last attempt reported local_backup_ok"
  echo "# TYPE oracleai_backup_last_status_ok gauge"
  echo "oracleai_backup_last_status_ok $local_ok"
  echo "# HELP oracleai_backup_offsite_required Offsite upload required by config"
  echo "# TYPE oracleai_backup_offsite_required gauge"
  echo "oracleai_backup_offsite_required $offsite_required"
  echo "# HELP oracleai_backup_offsite_ok Last attempt uploaded offsite"
  echo "# TYPE oracleai_backup_offsite_ok gauge"
  echo "oracleai_backup_offsite_ok $offsite_ok"
  echo "# HELP oracleai_backup_offsite_stale Offsite required but not confirmed"
  echo "# TYPE oracleai_backup_offsite_stale gauge"
  echo "oracleai_backup_offsite_stale $offsite_stale"
} > "$tmp"
chmod 644 "$tmp"
mv "$tmp" "$OUT_FILE"
