#!/usr/bin/env bash
# Автозапуск staging-стека после ребута хоста (BUS-419).
#
# Проблема (факт 2026-09-07 06:30 UTC): systemd-юниты туннеля и watchdog
# поднялись, но docker-стек остался лежать: api/bot Exited(143/137),
# migrate Exited(255) на stale-образе, beat/worker Created. restart:
# unless-stopped не спасает (см. разбор ниже), туннель-юнит пересоздаёт
# только api/bot и без IMAGE_TAG (boot-дрейф на latest).
#
# Почему restart: unless-stopped не поднимает стек после ребута:
#   - unless-stopped рестартует контейнер ТОЛЬКО если он был running при
#     остановке демона. Зависимости через depends_on/healthcheck
#     (migrate=service_completed_successfully, api→healthy) останавливают
#     цепочку: beat/worker зависят от migrate-completed, а одноразовый
#     migrate-контейнер (restart: "no") в Created/Exited не «комплитится»
#     заново — compose-граф стоит, подняв только postgres/redis.
#   - Замена unless-stopped на always не чинит одноразовый migrate:
#     контейнер с restart: "no" не рестартуется политикой демона вовсе.
#
# Решение: oneshot-юнит, который после boot выполняет канонический
# `up -d` с пиннутым IMAGE_TAG из CURRENT_RELEASE (защита от boot-дрейфа
# на latest — класс BUS-270/тик 04:20Z 07.09) и профилем telegram для
# staging-бота. Идемпотентен: повторный запуск = no-op для здорового стека.
#
# Установка:
#   cp infra/staging/systemd/oracleai-staging-stack.service \
#      ~/.config/systemd/user/
#   systemctl --user daemon-reload
#   systemctl --user enable --now oracleai-staging-stack.service
#   loginctl enable-linger "$(whoami)"   # уже включён для watchdog (BUS-105)
#
# Логи: journalctl --user -u oracleai-staging-stack -f

set -euo pipefail

STAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$STAGING_DIR/.env.staging"
COMPOSE_FILE="$STAGING_DIR/docker-compose.staging.yml"
RELEASE_FILE="$STAGING_DIR/CURRENT_RELEASE"
PROJECT="oracleai-staging"

# Пин релиза: без IMAGE_TAG compose резолвит stale latest (root cause
# boot-дрейфа — tunnel-unit и этот скрипт обязаны всегда пиннуть).
IMAGE_TAG="$(cat "$RELEASE_FILE")"
export IMAGE_TAG RELEASE_ID="$IMAGE_TAG"

echo "$(date -u +%FT%TZ) stack: поднимаю oracleai-staging на IMAGE_TAG=$IMAGE_TAG"

# --profile telegram: бот обязателен для бета-трафика Wave-1. Guard'ы от
# BUS-138 не нужны здесь: скрипт не трогает токен, .env.staging уже валиден
# (иначе стек не поднялся бы руками раньше). Туннель-юнит сам recreate'ит
# api/bot при смене URL, но только если он стартует ПОСЛЕ стека — поэтому
# у этого юнита Before=туннель (см. unit-файл).
docker compose -p "$PROJECT" \
  -f "$COMPOSE_FILE" \
  --env-file "$ENV_FILE" \
  --profile telegram \
  up -d --build=false

# Ждём зелёного api (healthcheck compose уже гейтит up -d, но проверяем
# явно для чёткого сигнала в journal).
for i in $(seq 1 60); do
  health="$(docker inspect --format '{{.State.Health.Status}}' \
    oracleai-staging-staging-api-1 2>/dev/null || echo missing)"
  [[ "$health" == "healthy" ]] && {
    echo "$(date -u +%FT%TZ) stack: staging-api healthy, стек поднят"
    exit 0
  }
  sleep 2
done

echo "$(date -u +%FT%TZ) stack: ВНИМАНИЕ staging-api не healthy за 120с" >&2
exit 1
