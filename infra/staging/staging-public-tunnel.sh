#!/usr/bin/env bash
# Публичный HTTPS-туннель для staging (BUS-138).
# Почему не named-tunnel/домен: у хоста нет выделенного домена (прод тоже
# работает через trycloudflare quick-tunnel), cloudflared без origincert.
# Quick-tunnel даёт валидный TLS от Cloudflare (Telegram Mini App требует
# публичный HTTPS с валидным сертом; self-signed Caddy клиенты Telegram не
# доверяют). URL случайный и меняется при каждом рестарте туннеля, поэтому
# скрипт парсит URL, атомарно обновляет .env.staging и recreate'ит контейнеры,
# читающие WEBAPP_URL при старте (staging-api, staging-bot).
#
# Host: staging-Caddy смотрит на {$STAGING_DOMAIN}=localhost (site-block),
# поэтому на HTTPS-порт (3443) идём с --http-host-header localhost и
# --no-tls-verify (self-signed origin). Caddy-защиты сохраняются: /metrics
# 404, лимиты тела, security-заголовки (проверено BUS-138).
#
# Установка:
#   mkdir -p ~/.config/systemd/user
#   cp infra/staging/systemd/oracleai-staging-public-tunnel.service \
#      ~/.config/systemd/user/
#   systemctl --user daemon-reload
#   systemctl --user enable --now oracleai-staging-public-tunnel.service
#   loginctl enable-linger "$(whoami)"   # уже включён для watchdog (BUS-105)
#
# Логи: journalctl --user -u oracleai-staging-public-tunnel -f
# Публичный URL: cat infra/staging/PUBLIC_URL.txt

set -euo pipefail

STAGING_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$STAGING_DIR/.env.staging"
URL_FILE="$STAGING_DIR/PUBLIC_URL.txt"
LOG="$STAGING_DIR/tunnel.log"

# При старте система читает .env.staging сам; здесь только наш поддиапазон.
# Порядок редиректов важен: 2>/dev/null ДО < — иначе ошибка отсутствующего
# файла уйдёт в stderr скрипта (journal) при первом запуске.
PREV_URL=""
if [[ -r "$URL_FILE" ]]; then read -r PREV_URL < "$URL_FILE" || true; fi

# cloudflared живёт в ~/.local/bin — вне PATH systemd user unit'а.
CF_BIN="${CF_BIN:-$HOME/.local/bin/cloudflared}"

exec "$CF_BIN" tunnel \
  --no-autoupdate \
  --url "https://localhost:${STAGING_HTTPS_PORT:-3443}" \
  --http-host-header "${STAGING_DOMAIN:-localhost}" \
  --no-tls-verify \
  --loglevel info \
  >"$LOG" 2>&1 &
CF_PID=$!

# Ждём URL от Cloudflare (первый запуск ~3-10с).
NEW_URL=""
for _ in $(seq 1 60); do
  NEW_URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$LOG" | head -1 || true)"
  [[ -n "$NEW_URL" ]] && break
  sleep 1
done
if [[ -z "$NEW_URL" ]]; then
  echo "$(date -u +%FT%TZ) tunnel: URL не получен за 60с — cloudflared жив (pid $CF_PID), но output пуст" >&2
  wait "$CF_PID"
fi

echo "$(date -u +%FT%TZ) tunnel: $NEW_URL (prev: ${PREV_URL:-none})"
printf '%s\n' "$NEW_URL" > "$URL_FILE.tmp"
mv "$URL_FILE.tmp" "$URL_FILE"

# Обновляем WEBAPP_URL/PUBLIC_URL атомарно (env-файл игнорится git).
if [[ "$NEW_URL" != "$PREV_URL" ]]; then
  umask 177
  sed -i \
    -e "s|^WEBAPP_URL=.*|WEBAPP_URL=$NEW_URL|" \
    -e "s|^PUBLIC_URL=.*|PUBLIC_URL=$NEW_URL|" \
    "$ENV_FILE"
  # Контейнеры читают WEBAPP_URL при старте (валидация api, кнопка Mini App
  # бота) — recreate нужен при каждой смене URL. Бот recreate'ится ТОЛЬКО с
  # реальным токеном: placeholder → TelegramUnauthorizedError crash-loop и
  # алерт-шум (факт BUS-138).
  BOT_VAL="$(grep '^BOT_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
  COMPOSE_EXTRA=()
  SVC="staging-api"
  case "$BOT_VAL" in
    *placeholder*|*PLACEHOLDER*|*changeme*|"000000:AAA"*) : ;;
    ?*) COMPOSE_EXTRA=(--profile telegram); SVC="staging-api staging-bot" ;;
  esac
  docker compose -p oracleai-staging \
    -f "$STAGING_DIR/docker-compose.staging.yml" \
    --env-file "$ENV_FILE" \
    "${COMPOSE_EXTRA[@]}" \
    up -d --no-deps $SVC >/dev/null 2>&1 || true
  # Перепроверка health после recreate: retry-цикл (api recreate ~15-20с).
  # При провале НЕ выходим: exit убил бы cgroup вместе с cloudflared
  # (факт BUS-138: 530 после exit 0). Сбой виден в journal.
  HEALTH_OK=0
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 5 "$NEW_URL/health" >/dev/null 2>&1; then
      HEALTH_OK=1; break
    fi
    sleep 2
  done
  if [[ "$HEALTH_OK" == 1 ]]; then
    echo "$(date -u +%FT%TZ) tunnel: /health OK через $NEW_URL"
  else
    echo "$(date -u +%FT%TZ) tunnel: ВНИМАНИЕ /health не зелёный за 60с через $NEW_URL (см. staging-стек)" >&2
  fi
fi

# Держим сервис активным, пока жив cloudflared (systemd перезапустит скрипт
# при падении — URL сменится, env обновится заново этим же скриптом).
wait "$CF_PID"
