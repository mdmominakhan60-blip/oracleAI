#!/usr/bin/env bash
# Watchdog staging: детектирует смерть контейнера staging-стека и пишет алерт-событие.
#
# Механизм: docker events (event=die) по фильтру label com.docker.compose.project=oracleai-staging.
# При событии: запись в infra/staging/alerts.log + опциональный webhook
# (STAGING_ALERT_WEBHOOK_URL в .env.staging — например, Telegram Bot API чат дежурного).
#
# Запуск (host, вне compose — события докера недоступны изнутри контейнера без сокета):
#   nohup bash infra/staging/staging-alert-watch.sh >> infra/staging/watchdog.log 2>&1 &
#
# Для прод-стека аналогичный алерт уже есть: infra/observability/alerts.yml
# (OracleAIContainerRestarting / OracleAIObservabilityTargetDown).
set -Eeuo pipefail

STAGING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALERT_LOG="$STAGING_DIR/alerts.log"
WEBHOOK_URL="${STAGING_ALERT_WEBHOOK_URL:-}"

log_alert() {
  local ts line
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  line="[$ts] ALERT container_died container=$1 exit_code=$2"
  echo "$line" | tee -a "$ALERT_LOG"
  if [[ -n "$WEBHOOK_URL" ]]; then
    curl -fsS -X POST "$WEBHOOK_URL" -H 'Content-Type: application/json' \
      -d "{\"text\": \"$line\"}" >/dev/null 2>&1 \
      || echo "[$ts] WARN webhook delivery failed" >> "$ALERT_LOG"
  fi
}

echo "[watchdog] старт: слежу за die-событиями compose-проекта oracleai-staging"
docker events --filter 'event=die' \
  --filter 'label=com.docker.compose.project=oracleai-staging' \
  --format '{{json .}}' |
while read -r ev; do
  container="$(echo "$ev" | grep -o '"Actor":{"ID":"[^"]*","Attributes":{[^}]*}' | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4)"
  # exitCode в событии — строка: "exitCode":"137" (фактическая находка BUS-105).
  exit_code="$(echo "$ev" | grep -o '"exitCode":"[0-9]*"' | head -1 | cut -d'"' -f4)"
  log_alert "${container:-unknown}" "${exit_code:-unknown}"
done
