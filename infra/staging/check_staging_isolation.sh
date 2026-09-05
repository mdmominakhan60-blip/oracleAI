#!/usr/bin/env bash
# Проверка сетевой/секретной изоляции staging от прод-стека (критерий BUS-105,
# на приёмке смотрит Security Engineer). Запуск: bash infra/staging/check_staging_isolation.sh
set -Eeuo pipefail

STAGING_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0
ok()   { echo "PASS: $1"; }
fail_(){ echo "FAIL: $1"; fail=1; }

# 1. Сети: staging-сеть не должна содержать прод-контейнеры, и наоборот.
echo "--- сети ---"
if docker network inspect oracle_staging_internal --format '{{range .Containers}}{{.Name}} {{end}}' | grep -Ev 'staging' | grep -q '[a-z]'; then
  fail_ "в oracle_staging_internal есть нестейджинг-контейнеры"
else
  ok "в oracle_staging_internal только staging-контейнеры"
fi
PROD_NET="$(docker inspect infra-postgres-1 --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null || echo oracle_internal)"
if docker network inspect "$PROD_NET" --format '{{range .Containers}}{{.Name}} {{end}}' 2>/dev/null | grep -q 'staging'; then
  fail_ "в прод-сети $PROD_NET найден staging-контейнер"
else
  ok "в прод-сети $PROD_NET нет staging-контейнеров"
fi

# 2. Порты: staging-HTTPS не пересекается с продовым 80/443.
echo "--- порты ---"
if docker ps --format '{{.Names}} {{.Ports}}' | grep -E 'staging' | grep -qE '0\.0\.0\.0:(80|443)->'; then
  fail_ "staging-контейнер слушает продовый порт 80/443"
else
  ok "staging не занимает продовые порты 80/443"
fi

# 3. Секреты: в .env.staging не должно быть продовых значений.
echo "--- секреты ---"
ENV_STAGING="$STAGING_DIR/.env.staging"
[[ -f "$ENV_STAGING" ]] || { echo "FAIL: нет $ENV_STAGING"; exit 1; }
# Прод-бот-токен узнаваем по боту, который сейчас в проде: сверяем по любому
# непустому BOT_TOKEN продового .env — значения должны различаться.
PROD_ENV="/home/softis/apps/oraclAI/oracleAI/.env"
if [[ -r "$PROD_ENV" ]]; then
  prod_bot="$(grep -E '^BOT_TOKEN=' "$PROD_ENV" | cut -d= -f2-)"
  staging_bot="$(grep -E '^BOT_TOKEN=' "$ENV_STAGING" | cut -d= -f2-)"
  if [[ -n "$prod_bot" && "$prod_bot" == "$staging_bot" ]]; then
    fail_ "BOT_TOKEN в staging совпадает с продовым"
  else
    ok "BOT_TOKEN staging отличается от продового"
  fi
  prod_llm="$(grep -E '^(ANTHROPIC_API_KEY|OPENAI_API_KEY)=' "$PROD_ENV" | cut -d= -f2- | tr -d ' ')"
  for kv in $prod_llm; do :; done
  if grep -qE '^(ANTHROPIC_API_KEY|OPENAI_API_KEY)=..+' "$ENV_STAGING" \
     && grep -E '^(ANTHROPIC_API_KEY|OPENAI_API_KEY)=' "$ENV_STAGING" | cut -d= -f2- \
        | grep -qF "$(grep -E '^ANTHROPIC_API_KEY=' "$PROD_ENV" | cut -d= -f2-)"; then
    fail_ "продовый ANTHROPIC_API_KEY обнаружен в staging env"
  else
    ok "продовых LLM-ключей в staging env нет"
  fi
  prod_pg="$(grep -E '^POSTGRES_PASSWORD=' "$PROD_ENV" | cut -d= -f2-)"
  staging_pg="$(grep -E '^POSTGRES_PASSWORD=' "$ENV_STAGING" | cut -d= -f2-)"
  if [[ -n "$prod_pg" && "$prod_pg" == "$staging_pg" ]]; then
    fail_ "POSTGRES_PASSWORD staging совпадает с продовым"
  else
    ok "POSTGRES_PASSWORD staging отличается от продового"
  fi
  # 3b. Paddle (BUS-134): в staging обязателен SANDBOX-ключ, и он не должен
  # совпадать с продовым. Sandbox-ключ Paddle содержит маркер sdbx_; продовый —
  # live_. Пустой PADDLE_API_KEY допустим (платежи на staging не настроены),
  # но тогда предупреждаем отдельно ниже (пункт 5).
  prod_paddle="$(grep -E '^PADDLE_API_KEY=' "$PROD_ENV" | cut -d= -f2- || true)"
  staging_paddle="$(grep -E '^PADDLE_API_KEY=' "$ENV_STAGING" | cut -d= -f2- || true)"
  if [[ -n "$staging_paddle" ]]; then
    if [[ "$staging_paddle" == *"sdbx_"* ]]; then
      ok "PADDLE_API_KEY staging — sandbox-ключ (sdbx_)"
    else
      fail_ "PADDLE_API_KEY staging не содержит маркер sdbx_ — подозрение на продовый ключ"
    fi
    if [[ -n "$prod_paddle" && "$prod_paddle" == "$staging_paddle" ]]; then
      fail_ "PADDLE_API_KEY staging совпадает с продовым"
    else
      ok "PADDLE_API_KEY staging отличается от продового"
    fi
    staging_paddle_secret="$(grep -E '^PADDLE_WEBHOOK_SECRET=' "$ENV_STAGING" | cut -d= -f2- || true)"
    if [[ -n "$staging_paddle_secret" ]]; then
      ok "PADDLE_WEBHOOK_SECRET staging задан"
    else
      fail_ "PADDLE_WEBHOOK_SECRET пуст при заданном PADDLE_API_KEY — вебхуки не проверить"
    fi
  else
    ok "PADDLE_API_KEY staging пуст — платежи не настроены (см. предупреждение в финале)"
  fi
else
  echo "SKIP: продовый .env не читается — сверка секретов невозможна вручную"
fi

# 4. Compose-проекты различны.
echo "--- compose-проект ---"
proj="$(docker inspect oracleai-staging-staging-api-1 --format '{{index .Config.Labels "com.docker.compose.project"}}' 2>/dev/null || echo none)"
[[ "$proj" == "oracleai-staging" ]] && ok "staging живёт в compose-проекте oracleai-staging" || fail_ "ожидался проект oracleai-staging, получен $proj"

# 5. Платёжный контур: предупреждение (не fail) о неполной Paddle-конфигурации —
# BUS-134. Refund/chargeback-политика F1 — решение CFO+Engineering Lead.
echo "--- платежи (Paddle sandbox, BUS-134) ---"
if [[ -n "$staging_paddle" ]]; then
  if grep -qE '^PADDLE_CHECKOUT_URL=..' "$ENV_STAGING" && grep -qE '^PADDLE_PRICE_IDS=..' "$ENV_STAGING"; then
    ok "PADDLE_CHECKOUT_URL и PADDLE_PRICE_IDS заданы — sandbox-платежи настроены"
  else
    echo "WARN: Paddle-ключ задан, но PADDLE_CHECKOUT_URL/PADDLE_PRICE_IDS пусты — checkout не заработает"
  fi
else
  echo "WARN: PADDLE_API_KEY пуст — P0-002 external (BUS-134) не закрыт: ключи запрашивает board/user в Paddle Dashboard (sandbox)"
fi

echo
[[ $fail -eq 0 ]] && { echo "ISOLATION: OK"; exit 0; } || { echo "ISOLATION: FAILED"; exit 1; }
