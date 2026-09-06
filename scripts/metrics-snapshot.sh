#!/usr/bin/env bash
set -Eeuo pipefail
# BUS-270: один файл с базовыми метриками стака (требование "дашборд/выборка").
# Источник: Prometheus instant API (проще, чем разворачивать Grafana).
# Зависимости: curl, jq.
PROM="${PROM_URL:-http://127.0.0.1:9090}"
SNAP="$1"; SNAP="${SNAP:-$(date -u +%Y%m%d-%H%M%SZ)}"
OUT="infra/staging/monitoring/snapshots/${SNAP}"
mkdir -p "$OUT"
queries=(
  'oracleai_http_requests_total{job="oracleai-api"}[5m]:rate'
  'oracleai_http_requests_total{status=~"5..",job="oracleai-api"}[5m]:rate'
  'oracleai_http_requests_total{status="429",job="oracleai-api"}[5m]:rate'
  'oracleai_llm_usage_total[5m]:rate'
  'up{job="oracleai-api"}:scalar'
)
for q in "${queries[@]}"; do
  fname="$(echo "$q" | tr -cs 'A-Za-z0-9_' '_' | sed 's/_$//').json"
  curl -fsS --max-time 8 "${PROM}/api/v1/query?query=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$q")" \
    -o "${OUT}/${fname}" 2>/dev/null || echo '[]' > "${OUT}/${fname}"
done
echo "$OUT"
