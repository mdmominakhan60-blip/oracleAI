#!/usr/bin/env bash
set -Eeuo pipefail
# BUS-270: один файл с базовыми метриками стака (требование "дашборд/выборка").
# Источник: Prometheus instant API (проще, чем разворачивать Grafana).
# Зависимости: curl, jq.
# Использование: bash scripts/metrics-snapshot.sh [имя-снимка]
#   PROM_URL=http://127.0.0.1:9090 bash scripts/metrics-snapshot.sh
PROM="${PROM_URL:?set PROM_URL, e.g. http://infra-prometheus-1:9090}"
# Важно: на хосте порт 9090 — НЕ Prometheus API (другой UI).
# Примеры:
#   PROM_URL=http://infra-prometheus-1:9090 docker exec -i infra-prometheus-1 sh /scripts/metrics-snapshot.sh
#   PROM_URL=http://<exposed-prometheus>:9090 bash scripts/metrics-snapshot.sh
SNAP="${1:-$(date -u +%Y%m%d-%H%M%SZ)}"
OUT="infra/staging/monitoring/snapshots/${SNAP}"
mkdir -p "$OUT"
queries=(
  # req/s за последние 5 минут по прод-стаку
  'sum(rate(oracleai_http_requests_total{job="oracleai-api"}[5m]))'
  # error rate: 5xx/с
  'sum(rate(oracleai_http_requests_total{status=~"5..",job="oracleai-api"}[5m]))'
  # 429/с (в т.ч. fail-closed)
  'sum(rate(oracleai_http_requests_total{status="429",job="oracleai-api"}[5m]))'
  # LLM-вызовы: ok и не-ok по провайдерам (staging+prod)
  'sum by (ok, provider) (increase(oracleai_llm_usage_total[10m]))'
  # живость API-таргетов
  'up{job=~"oracleai.*"}'
)
for q in "${queries[@]}"; do
  fname="$(echo "$q" | tr -cs 'A-Za-z0-9_' '_' | sed 's/_$//').json"
  curl -fsS --max-time 8 "${PROM}/api/v1/query?query=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$q")" \
    -o "${OUT}/${fname}" 2>/dev/null || echo '[]' > "${OUT}/${fname}"
done
echo "$OUT"
