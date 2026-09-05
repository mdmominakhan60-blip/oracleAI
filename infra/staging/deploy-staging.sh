#!/usr/bin/env bash
# Deploy oracleAI на staging: чистый checkout → зелёный health-check по HTTPS.
# Идемпотентен: повторный запуск обновляет релиз (build → migrate → recreate).
#
# Использование (из корня репо продукта):
#   bash infra/staging/deploy-staging.sh [RELEASE_ID]
# RELEASE_ID — обычно git SHA короткий; по умолчанию текущий HEAD.
#
# Предусловия: infra/staging/.env.staging заполнен (см. .env.staging.example).
# Прод-стек не трогаем: другой compose-проект, другие порты/сети/тома.
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="$REPO_ROOT/infra/staging"
COMPOSE="docker compose -p oracleai-staging -f $STAGING_DIR/docker-compose.staging.yml --env-file $STAGING_DIR/.env.staging"

RELEASE_ID="${1:-$(git -C "$REPO_ROOT" rev-parse --short HEAD)}"
export IMAGE_TAG="$RELEASE_ID"

[[ -f "$STAGING_DIR/.env.staging" ]] || { echo "Нет $STAGING_DIR/.env.staging — скопируй .env.staging.example и заполни" >&2; exit 1; }
[[ -f "$REPO_ROOT/miniapp/dist/manifest.json" ]] || {
  echo "miniapp/dist/manifest.json отсутствует — APP_ENV=staging требует собранный Mini App (node scripts/build_frontend.mjs)" >&2
  exit 1
}

echo "=== [1/5] Build образа oracleai-staging:$IMAGE_TAG (без прерывания работающего стека)"
$COMPOSE build --pull

echo "=== [2/5] Up (создание/обновление; migrate-ran до api)"
$COMPOSE up -d

echo "=== [3/5] Ожидание зелёного health-check staging-api"
for i in $(seq 1 60); do
  health="$(docker inspect --format '{{.State.Health.Status}}' oracleai-staging-staging-api-1 2>/dev/null || echo missing)"
  [[ "$health" == "healthy" ]] && { echo "staging-api healthy"; break; }
  [[ "$i" == 60 ]] && { echo "staging-api не стал healthy за 120с" >&2; docker ps --filter name=staging; docker logs oracleai-staging-staging-api-1 --tail 50; exit 1; }
  sleep 2
done

echo "=== [4/5] HTTPS health-check через staging-Caddy (self-signed)"
# -k: self-signed сертификат (tls internal) — для staging это ожидаемо.
# Retry: при первом старте Caddy выпускает сертификат — первые соединения
# могут обрываться (curl 35), поэтому ждём до 30 попыток.
https_ok=""
for i in $(seq 1 30); do
  if curl -fsSk "https://localhost:3443/health" >/dev/null 2>&1; then https_ok=1; break; fi
  sleep 2
done
[[ -n "$https_ok" ]] || { echo "HTTPS /health так и не ответил за 60с" >&2; docker logs oracleai-staging-staging-caddy-1 --tail 30; exit 1; }
echo "HTTPS /health OK: $(curl -sk "https://localhost:3443/health")"

echo "=== [5/5] Фиксация релиза"
echo "$IMAGE_TAG" > "$STAGING_DIR/CURRENT_RELEASE"
# История релизов для rollback-скрипта: дата_UTC, событие, тег, ревизия схемы alembic.
# Ревизию берём из БД — это цель отката схемы при rollback на этот релиз.
SCHEMA_REV="$(docker compose -p oracleai-staging exec -T staging-postgres \
  psql -U "${POSTGRES_USER:-oracle_staging}" -d "${POSTGRES_DB:-oracle_staging}" -tAc \
  "SELECT version_num FROM alembic_version" 2>/dev/null || echo unknown)"
printf '%s\tdeploy\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$IMAGE_TAG" "$SCHEMA_REV" >> "$STAGING_DIR/RELEASE_HISTORY.tsv"
echo "Deploy завершён: RELEASE_ID=$IMAGE_TAG, схема=$SCHEMA_REV"
