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

echo "$(date -u +%FT%TZ) prod-stack: поднимаю compose-проект '$PROJECT'"

docker compose -p "$PROJECT" \
  -f "$COMPOSE_FILE" \
  --env-file "$ENV_FILE" \
  --profile backup \
  up -d --no-build

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
