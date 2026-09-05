#!/usr/bin/env bash
# Rollback staging на предыдущую версию: код (предыдущий тег образа) + схема БД
# (alembic downgrade до ревизии предыдущего образа).
#
# Порядок — важен: downgrade выполняется ИЗ НОВОГО образа (он знает, как откатить
# свою схему), затем свап образа на предыдущий. Обратный порядок оставил бы БД
# на head-схеме с кодом предыдущей версии.
#
# Использование (из корня репо продукта):
#   bash infra/staging/rollback-staging.sh [PREVIOUS_RELEASE_ID]
# Без аргумента берёт предыдущий тег из infra/staging/RELEASE_HISTORY.tsv.
#
# План отката прод-деплоя аналогичен (BUS-105, раздел Rollback в STAGING_INFRASTRUCTURE.md).
set -Eeuo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGING_DIR="$REPO_ROOT/infra/staging"
COMPOSE="docker compose -p oracleai-staging -f $STAGING_DIR/docker-compose.staging.yml --env-file $STAGING_DIR/.env.staging"
HISTORY="$STAGING_DIR/RELEASE_HISTORY.tsv"

[[ -f "$STAGING_DIR/.env.staging" ]] || { echo "Нет $STAGING_DIR/.env.staging" >&2; exit 1; }
[[ -f "$STAGING_DIR/CURRENT_RELEASE" ]] || { echo "Нет CURRENT_RELEASE — сначала deploy" >&2; exit 1; }

CURRENT="$(cat "$STAGING_DIR/CURRENT_RELEASE")"
if [[ $# -ge 1 ]]; then
  TARGET="$1"
else
  # Последняя строка истории ≠ текущий тег = предыдущий релиз.
  TARGET="$(awk -F'\t' -v cur="$CURRENT" '$3 != cur {print $3}' "$HISTORY" 2>/dev/null | tail -1 || true)"
fi
[[ -n "${TARGET:-}" ]] || { echo "Не определён PREVIOUS_RELEASE_ID: передай аргументом или заполни RELEASE_HISTORY.tsv" >&2; exit 1; }

docker image inspect "oracleai-staging:$TARGET" >/dev/null 2>&1 \
  || { echo "Образ oracleai-staging:$TARGET не найден — rollback невозможен. Доступные теги:"; docker images oracleai-staging --format '{{.Tag}}'; exit 1; }

# Целевая ревизия схемы = ревизия, записанная при deploy TARGET-релиза.
# Это правильная цель отката: НЕ base (миграции с необратимыми преобразованиями
# — например 0003 tg_id int32→bigint — сознательно отказывают downgrade с
# RuntimeError: откат таких схем разрушителен и требует restore из бэкапа).
TARGET_REV="$(awk -F'\t' -v tag="$TARGET" '$3 == tag && $2 == "deploy" {rev=$4} END {print rev}' "$HISTORY" 2>/dev/null || true)"
ALEMBIC_TARGET="${STAGING_ALEMBIC_TARGET:-$TARGET_REV}"
[[ -n "$ALEMBIC_TARGET" && "$ALEMBIC_TARGET" != "unknown" ]] || {
  echo "Ревизия схемы для $TARGET не найдена в RELEASE_HISTORY.tsv; задай явно:" >&2
  echo "  STAGING_ALEMBIC_TARGET=<revision> bash $0 $TARGET" >&2; exit 1; }

echo "=== Rollback: $CURRENT → $TARGET (схема → $ALEMBIC_TARGET)"
SECONDS=0

echo "=== [1/5] Остановка app-сервисов (postgres/redis остаются)"
$COMPOSE stop staging-bot staging-worker staging-beat staging-api

echo "=== [2/5] alembic downgrade ИЗ ТЕКУЩЕГО (нового) образа — только если схема новее целевой"
# downgrade гоняем из образа ТЕКУЩЕГО релиза: он знает миграции, которые создал.
# IMAGE_TAG экспортируем явно, иначе compose run соберёт/потянет :latest.
export IMAGE_TAG="$CURRENT"
DB_REV="$(docker compose -p oracleai-staging exec -T staging-postgres \
  psql -U "${POSTGRES_USER:-oracle_staging}" -d "${POSTGRES_DB:-oracle_staging}" -tAc \
  "SELECT version_num FROM alembic_version" 2>/dev/null || echo unknown)"
if [[ "$DB_REV" == "$ALEMBIC_TARGET" ]]; then
  echo "    схема уже на $DB_REV — downgrade не нужен (код-only rollback)"
elif [[ "$DB_REV" == "unknown" ]]; then
  echo "    не удалось прочитать alembic_version" >&2; exit 1
else
  $COMPOSE run --rm --no-deps staging-migrate alembic downgrade "$ALEMBIC_TARGET"
fi

echo "=== [3/5] Свап образа на предыдущий тег"
$COMPOSE up -d --no-deps --no-build staging-api staging-bot staging-worker staging-beat
# beat не имеет healthcheck — ждём его стабильного старта вместе с остальными ниже.

echo "=== [4/5] Ожидание зелёного health-check"
for i in $(seq 1 60); do
  health="$(docker inspect --format '{{.State.Health.Status}}' oracleai-staging-staging-api-1 2>/dev/null || echo missing)"
  [[ "$health" == "healthy" ]] && { echo "staging-api healthy"; break; }
  [[ "$i" == 60 ]] && { echo "staging-api не стал healthy после rollback" >&2; exit 1; }
  sleep 2
done
curl -fsSk "https://localhost:3443/health" >/dev/null && echo "HTTPS /health OK"

echo "=== [5/5] Фиксация"
echo "$TARGET" > "$STAGING_DIR/CURRENT_RELEASE"
printf '%s\trollback\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TARGET" "$(docker compose -p oracleai-staging exec -T staging-postgres psql -U "${POSTGRES_USER:-oracle_staging}" -d "${POSTGRES_DB:-oracle_staging}" -tAc "SELECT version_num FROM alembic_version" 2>/dev/null || echo unknown)" >> "$HISTORY"
echo "Rollback завершён за ${SECONDS}s: $CURRENT → $TARGET (схема: $ALEMBIC_TARGET)"
