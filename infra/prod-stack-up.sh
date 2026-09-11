#!/usr/bin/env bash
# Автозапуск прод-стека (compose-проект `infra`) после ребута хоста (BUS-440).
#
# Инцидент 2026-09-07 06:30 UTC (8-й краш за 2 недели): контейнеры infra-*
# автостартовали по restart: unless-stopped, но через ~90 с были массово
# остановлены (graceful SIGTERM, кластер в одну секунду) в ещё живом буте —
# явный docker stop снимает unless-stopped навсегда, и прод лежал до ручного
# подъёма. Похожий класс уже покрыт для staging юнитом BUS-419
# (oracleai-staging-stack.service): там lift-скрипт пинает IMAGE_TAG от
# boot-дрейфа на latest; прод билдится из локального контекста
# (infra-api:latest), поэтому пиновать нечего — up -d идемпотентен и
# локальный образ не пересоздаёт.
#
# Скрипт идемпотентен: для здорового стека `up -d` — no-op (compose
# пересоздаёт только контейнеры с рассинхроном конфига). --no-build-guard:
# без флага сборки; деплой — только по DEPLOYMENT.md (build строго вручную).
#
# Установка:
#   cp infra/systemd/oracleai-prod-stack.service ~/.config/systemd/user/
#   systemctl --user daemon-reload
#   systemctl --user enable --now oracleai-prod-stack.service
#   loginctl enable-linger "$(whoami)"   # уже включён (BUS-105/BUS-419)
#
# Логи: journalctl --user -u oracleai-prod-stack -f

set -euo pipefail

INFRA_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$INFRA_DIR/../.env"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
PROJECT="infra"

# BUS-1018: скрипт не принимает аргументов. Инцидент 2026-09-11 21:12Z:
# пробный вызов `prod-stack-up.sh --help` молча проигнорировал аргумент и
# поднял локальный стек → второй поллер с тем же BOT_TOKEN →
# TelegramConflictError 409 на обоих ботах ~28 минут.
if [[ $# -gt 0 ]]; then
  echo "prod-stack-up.sh: аргументы не поддерживаются (получено: $*)." >&2
  echo "Использование: $0 (без аргументов)" >&2
  exit 2
fi

# Гард BUS-1018 (fail-closed): канонический прод — VPS (BUS-704,
# app.primebond.bond, deploy@130.162.245.223). Локальный подъём
# production-конфигом создаёт второй поллер с тем же BOT_TOKEN.
# При APP_ENV=production требуем совпадения hostname с PROD_CANONICAL_HOST
# из .env; иначе отказ ДО docker compose up. Локальный .env НЕ должен
# задавать PROD_CANONICAL_HOST ( hostname ПК не канонический прод).
# Аварийный обход (VPS лежит, локальный стек как временный фейловер):
# ORACLEAI_ALLOW_LOCAL_PROD=1 в окружении вызывающего шелла — осознанный
# ручной шаг, в .env его задавать нельзя.
read_env_var() {
  # KEY=VALUE без source: в .env секреты, файл не исполняем.
  grep -E "^$1=" "$ENV_FILE" 2>/dev/null | tail -n1 | cut -d= -f2- \
    | tr -d "\"' \r"
}
APP_ENV_VALUE="$(read_env_var APP_ENV || true)"
if [[ "${APP_ENV_VALUE:-}" == "production" ]]; then
  CANONICAL_HOST="$(read_env_var PROD_CANONICAL_HOST || true)"
  CURRENT_HOST="$(hostname)"
  if [[ "${ORACLEAI_ALLOW_LOCAL_PROD:-0}" == "1" ]]; then
    echo "$(date -u +%FT%TZ) prod-stack: ПРЕДУПРЕЖДЕНИЕ ORACLEAI_ALLOW_LOCAL_PROD=1 — гард канонического прода обойдён осознанно" >&2
  elif [[ -z "$CANONICAL_HOST" ]]; then
    echo "$(date -u +%FT%TZ) prod-stack: ОТКАЗ — APP_ENV=production, но PROD_CANONICAL_HOST не задан в .env." >&2
    echo "Канонический прод — VPS (BUS-704). Локальный подъём создаст второй поллер (инцидент dual-poller 2026-09-11)." >&2
    echo "На каноническом хосте задай PROD_CANONICAL_HOST=$(hostname) в .env; аварийный обход: ORACLEAI_ALLOW_LOCAL_PROD=1." >&2
    exit 1
  elif [[ "$CURRENT_HOST" != "$CANONICAL_HOST" ]]; then
    echo "$(date -u +%FT%TZ) prod-stack: ОТКАЗ — канонический прод на VPS ($CANONICAL_HOST, BUS-704), этот хост: $CURRENT_HOST." >&2
    echo "Локальный подъём создаст второй поллер с тем же BOT_TOKEN (инцидент dual-poller 2026-09-11)." >&2
    echo "Аварийный обход: ORACLEAI_ALLOW_LOCAL_PROD=1." >&2
    exit 1
  fi
fi

echo "$(date -u +%FT%TZ) prod-stack: поднимаю compose-проект '$PROJECT'"

# --remove-orphans (хвост BUS-104): сносит контейнеры проекта infra, которых
# нет в этом манифесте (например tunnel-пару из docker-compose.tunnel.yml).
# После основного подъёма tunnel-оверлей поднимать заново осознанно:
#   docker compose -p infra -f docker-compose.yml -f docker-compose.tunnel.yml up -d
docker compose -p "$PROJECT" \
  -f "$COMPOSE_FILE" \
  --env-file "$ENV_FILE" \
  --profile backup \
  up -d --no-build --remove-orphans

# Ждём зелёного api (healthcheck compose уже гейтит up -d, но проверяем
# явно для чёткого сигнала в journal).
for i in $(seq 1 90); do
  health="$(docker inspect --format '{{.State.Health.Status}}' \
    infra-api-1 2>/dev/null || echo missing)"
  [[ "$health" == "healthy" ]] && {
    echo "$(date -u +%FT%TZ) prod-stack: infra-api healthy, прод поднят"
    exit 0
  }
  sleep 2
done

echo "$(date -u +%FT%TZ) prod-stack: ВНИМАНИЕ infra-api не healthy за 180с" >&2
exit 1
