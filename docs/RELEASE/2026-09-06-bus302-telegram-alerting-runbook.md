# Runbook: доставка алертов в Telegram (BUS-302)

Дата: 2026-09-06 · Владелец: DevOps · Статус: работает (prod + staging таргеты)

## Что настроено

Конвейер: `prometheus (rules) → alertmanager:9093 → Telegram (чат оператора)`.

- **alertmanager** — сервис в `infra/docker-compose.yml` (образ `prom/alertmanager:v0.28.1`,
  healthcheck `/-/ready`, том `alertmanager_data` для silences/nflog).
- **Конфиг генерируется из env при старте** — `infra/observability/alertmanager-entrypoint.sh`:
  `bot_token = ALERT_BOT_TOKEN || BOT_TOKEN`, `chat_id = ALERT_CHAT_ID || ADMIN_ID` (обязателен,
  проверяется на целое число — Alertmanager парсит `chat_id` строго в int64).
  Секреты в git не попадают; `infra/observability/alertmanager.yml` — только справочник шаблона.
- **Прометей** шлёт алерты на `alertmanager:9093` (секция `alerting` в `infra/observability/prometheus.yml`).
- **Скрейп ботов**: job `oracleai-bot` → `bot:9101`, job `oracleai-staging-bot` → `staging-bot:9101`
  (в `app/bot/main.py` — `prometheus_client.start_http_server(9101)`; порт не публикуется наружу).
- **Routing**: единый receiver `telegram-operator`; `group_wait=30s`, `group_interval=5m`,
  `repeat_interval=4h`; inhibit: critical глушит warning того же job.
- Шаблон сообщения: alertname + severity + summary/description + StartsAt, parse_mode HTML.

## Как проверить доставку (2 минуты)

1. Открыть API alertmanager (только из сети `oracle_internal`):
   ```bash
   docker exec -i infra-alertmanager-1 sh -c 'wget -qO- --post-data="[{\"labels\":{\"alertname\":\"ManualTest\",\"severity\":\"warning\",\"job\":\"oracleai-bot\"},\"annotations\":{\"summary\":\"тест доставки\"},\"startsAt\":\"'"$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"'\"}]" --header "Content-Type: application/json" http://localhost:9093/api/v2/alerts'
   ```
2. Через ~30–60 с в логах должно появиться:
   `msg="Telegram message successfully published" ... chat_id=<id>` (уровень debug).
   ```bash
   docker logs infra-alertmanager-1 --since 5m 2>&1 | grep 'Telegram message'
   ```
3. Сообщение приходит в чат оператора (Telegram). После снятия алерта приходит resolve.

Если сообщения нет — смотри `docker logs infra-alertmanager-1 | grep -iE "notify|error"`;
частые причины: конфиг не загрузился (int64 chat_id), прометей не видит AM
(`GET /api/v1/alertmanagers` на :9090 должен вернуть url).

## Критерий «алерт не слеп»: oracleai_llm_usage_total

`OracleAILLMFailureRateHigh` считает rate по `oracleai_llm_usage_total`. Серия создаётся
только первым `.inc()` (app/core/llm.py:217) в процессе, который кто-то скрейпит.
Проверка живости:

```promql
oracleai_llm_usage_total          # ≥1 серия; пусто = вызовов не было после старта процесса
up{job=~"oracleai-bot|oracleai-staging-bot"}   # оба = 1
```

Статус на 2026-09-06: серия есть (`job=oracleai-staging-api, ok="1", purpose="forecast"=1`),
оба bot-таргета up, правило `OracleAILLMFailureRateHigh` health=ok. Снапшот:
`infra/staging/monitoring/snapshots/bus302-alerting/`.

## Плейбук изменений

- Поменял(а) routing/шаблон → правь `alertmanager-entrypoint.sh` (генератор) и
  справочник `alertmanager.yml` вместе; `docker compose --env-file ../.env up -d alertmanager`.
- Поменял(а) скрейп-таргеты → `prometheus.yml`, затем `up -d prometheus`
  (bind-mount inode trap: `/-/reload` не увидит перезаписанный файл — только recreate контейнера).
- Дежурный чат меняется через `ALERT_CHAT_ID` в `.env` (без коммита секрета) + `up -d alertmanager`.

## Ограничения / next

- Секреты при аутентификации теста: токен бота один для алертов и бота — отдельный
  @BotFather-бот для алертов делаем при разделении окружений (опционально).
- Metrics из worker (celery) в реестр бота/API не попадают — worker-пул не скрейпится;
  отдельная задача при появлении LLM-задач в очереди (см. комментарий в BUS-302).
