# Staging-инфраструктура oracleAI (BUS-105)

**Назначение:** disposable staging для controlled beta и репетиций P0-гейтов (P0-001..P0-004). Отдельно от прод-стека, с изолированными сетями, данными и секретами.
**Топология:** идентична продовой (postgres+pgvector, redis, api, bot, worker, beat, caddy) — но отдельный compose-проект `oracleai-staging`.

## Расположение артефактов

| Артефакт | Путь |
|---|---|
| Compose-файл staging | `infra/staging/docker-compose.staging.yml` |
| Caddy edge (self-signed TLS) | `infra/staging/staging.Caddyfile` |
| Env-шаблон (без секретов) | `infra/staging/.env.staging.example` |
| Реальный staging-env (в .gitignore) | `infra/staging/.env.staging` |
| Deploy-скрипт | `infra/staging/deploy-staging.sh` |
| Rollback-скрипт | `infra/staging/rollback-staging.sh` |
| Watchdog алертов | `infra/staging/staging-alert-watch.sh` |
| Проверка изоляции | `infra/staging/check_staging_isolation.sh` |
| Текущий релиз / история | `infra/staging/CURRENT_RELEASE`, `infra/staging/RELEASE_HISTORY.tsv` |
| Алерт-лог | `infra/staging/alerts.log` (в .gitignore через `*.log`) |

## Изоляция от прода (критерий BUS-105, ревью Security Engineer)

| Измерение | Прод | Staging |
|---|---|---|
| Compose-проект | `infra` (контейнеры `infra-*`) | `oracleai-staging` (контейнеры `oracleai-staging-*`) |
| Docker-сеть | `oracle_internal` | `oracle_staging_internal` |
| Порты HTTPS/HTTP | 80 / 443 | 3443 / 3080 |
| PostgreSQL | том `postgres_data`, БД `oracle` | том `oracleai-staging_pg_data`, БД `oracle_staging`, отдельный пароль |
| Redis | том `redis_data` | том `oracleai-staging_redis_data` |
| Env/секреты | `/home/softis/apps/oraclAI/oracleAI/.env` | `infra/staging/.env.staging` (свой BOT_TOKEN, свой POSTGRES_PASSWORD, без продовых LLM-ключей) |
| LLM | реальный провайдер | `LLM_PROVIDER=off` (детерминированные фолбэки) |
| Telegram-бот | прод-бот | отдельный staging-бот (свой токен от @BotFather) |

Проверка: `bash infra/staging/check_staging_isolation.sh` — сети, порты, секреты, compose-проект.

**APP_ENV:** staging работает с `APP_ENV=production` (production-like). Fail-closed валидация API (`app/api/main.py:_validate_production_config`) принимает только `dev|test|production`; значение `staging` она бы отвергла. Изоляция — инфраструктурная (проект/сеть/порты/секреты), а не через APP_ENV. `DEV_MODE=0` обязателен.

## Предусловия

1. Заполненный `infra/staging/.env.staging` (из шаблона): `POSTGRES_PASSWORD` (уникальный), `BOT_TOKEN` (staging-бот, не прод), `ADMIN_ID`, `WEBAPP_URL` (https://<staging-домен>), `RELEASE_ID`.
2. Собранный Mini App: `node scripts/build_frontend.mjs` (проверка — `miniapp/dist/manifest.json`). APP_ENV=production требует манифест.
3. Свободные порты 3443/3080 (прод-Caddy занимает 80/443 — конфликт исключён).

## Deploy-процедура (от чистого checkout до зелёного health-check)

```bash
cd /home/softis/apps/oraclAI/oracleAI
node scripts/build_frontend.mjs                  # один раз; в чистом checkout обязательно
cp infra/staging/.env.staging.example infra/staging/.env.staging
# заполнить .env.staging (см. Предусловия)
bash infra/staging/deploy-staging.sh <RELEASE_ID>   # RELEASE_ID = короткий git SHA
```

Скрипт делает (идемпотентно, повторный запуск = обновление релиза):
1. `docker compose build --pull` — образ `oracleai-staging:<RELEASE_ID>` (без прерывания работающего стека).
2. `up -d` — новый контейнер `staging-migrate` применяет `alembic upgrade head` к чистой БД и завершается; api/bot/worker/beat стартуют только после `service_completed_successfully`.
3. Ожидание `healthy` у `staging-api` (healthcheck: `curl localhost:8080/health` — проверяет и БД).
4. HTTPS health-check через staging-Caddy: `curl -fsSk https://localhost:3443/health` (self-signed → `-k`).
5. `CURRENT_RELEASE` ← RELEASE_ID; строка в `RELEASE_HISTORY.tsv`.

### Замечания по репетиции в локальной сети
- `STAGING_DOMAIN=localhost` → Caddy `tls internal` (self-signed). Клиенты используют `-k`/отключённую верификацию. Для staging-бота с публичным доменом — свой домен/сертификат, пусть и отдельный от продового.
- `curl -k` допустим только для staging health-check'ов; на проде `curl` без `-k`.

## Rollback-процедура (код + БД)

Ключевой принцип: **схему БД откатывает тот образ, который её поднял** (предыдущий образ не знает миграций, появившихся после него). Порядок: остановка app-сервисов → `alembic downgrade` из текущего образа → свап образа на предыдущий тег → health-check.

```bash
# Перед rollback убедиться, что предыдущий образ существует: docker images oracleai-staging
bash infra/staging/rollback-staging.sh [<PREVIOUS_RELEASE_ID>]
# Если нужно переопределить целевую ревизию схемы:
STAGING_ALEMBIC_TARGET=<revision> bash infra/staging/rollback-staging.sh [<PREVIOUS_RELEASE_ID>]
```

- Без аргумента берёт предыдущий релиз из `RELEASE_HISTORY.tsv`; целевую ревизию схемы — из записи deploy этого релиза.
- Сравнивает текущую `alembic_version` с целевой: если совпадают — downgrade пропускается (код-only rollback, ~8с).
- Если downgrade-цепочка упирается в защитный guard миграции (RuntimeError), транзакция откатывается целиком, схема остаётся на текущей ревизии — это fail-closed; восстановление такой схемы возможно только из бэкапа (см. P0-004).
- Скрипт меряет и печатает общее время rollback.
- PostgreSQL/Redis не останавливаются — откатываются только app-контейнеры и схема.

Для P0-004 (восстановление из бэкапа в staging-БД) — `make restore BACKUP=<dump.enc> RESTORE_TARGET_DB=<isolated_db>` против прод-стека, или прямая загрузка дампа в staging-postgres. Полный drill — отдельная задача P0-004.

## Наблюдаемость staging

- **Health-check'и** на всех сервисах (api — `/health` с проверкой БД, bot — хартбит в БД, worker — celery ping, caddy — HTTPS probe). `docker compose -p oracleai-staging ps` показывает статус.
- **Логи**: `docker compose -p oracleai-staging logs -f --tail=100`; json-file с ротацией 10MB×5.
- **Watchdog**: `staging-alert-watch.sh` слушает docker events (die) по лейблу проекта; при смерти контейнера с ненулевым (или неизвестным) exit code пишет `[ts] ALERT container_died container=<name> exit_code=<n>` в `alerts.log` и (опционально) шлёт webhook (`STAGING_ALERT_WEBHOOK_URL` в .env.staging, формат `{"text": ...}`). exit_code=0 (успешный one-shot job вроде staging-migrate) алертом не считается.
- **Запуск watchdog — через systemd user unit** (`infra/staging/systemd/oracleai-staging-watchdog.service`), не через nohup из сессии: nohup-процесс из heartbeat-рана умирает вместе с процессной группой рана (факт 2026-09-05: алерты оборвались, crash-loop бота остался незамеченным). Установка: скопировать unit в `~/.config/systemd/user/`, `daemon-reload`, `enable --now`, `loginctl enable-linger`.
- Прод-стек продолжает использовать Prometheus-алерты `infra/observability/alerts.yml` (routing по `name=~"infra-.*"`); staging не входит в продовый Prometheus — его события идут через watchdog.

## Статус репетиций (evidence, прогоны BUS-105 от 2026-09-05)

| Репетиция | Результат | Замеры |
|---|---|---|
| Deploy от чистой БД | **PASS** | миграции 0001→0007 на чистой БД, 54 таблицы, `alembic_version=0007_add_tarot_deck` |
| HTTPS health-check | **PASS** | `GET https://localhost:3443/health` → `{"ok":true,"database":"oracle_staging","schema_tables":54}` через staging-Caddy (self-signed) |
| Идемпотентный redeploy | **PASS** | повторный `deploy-staging.sh` поверх работающего стека — healthy без ручных правок |
| Rollback код-only (схема совпадает) | **PASS, 8s** | staging-r2 → staging-r1, health-check зелёный после свапа |
| Rollback схемы (drill) | **PASS, ~15s roundtrip** | downgrade 0007→0006 (deck-колонка удалена) + upgrade 0006→0007 (восстановлена); обе операции транзакционны |
| Watchdog-алерт | **PASS** | `docker kill staging-beat` → `[ts] ALERT container_died container=... exit_code=137` в alerts.log |
| Watchdog как systemd unit (после приёмки) | **PASS** | unit `oracleai-staging-watchdog` enabled+running (linger=yes); drill: exit0-контейнер молчит, exit1 → алерт; nohup-вариант заменён (умирал вместе с процессной группой heartbeat-рана) |
| Изоляция | **PASS (7/7)** | `check_staging_isolation.sh`: сети, порты, BOT_TOKEN, LLM-ключи, POSTGRES_PASSWORD, compose-проект |
| Публичный HTTPS для device-доступа (BUS-138) | **PASS** | cloudflared quick-tunnel (`*.trycloudflare.com`, валидный TLS Cloudflare) → staging-Caddy 3443 (host-header `localhost`, `--no-tls-verify` на origin). systemd unit `oracleai-staging-public-tunnel`; скрипт `staging-public-tunnel.sh` при смене URL атомарно обновляет WEBAPP_URL/PUBLIC_URL в `.env.staging` и recreate'ит staging-api (бота — только с реальным токеном). URL в `infra/staging/PUBLIC_URL.txt`. Ограничение quick-tunnel: URL меняется при каждом рестарте туннеля — норма для staging |
| Staging-бот с реальным токеном | **внешняя зависимость** | нужен человек: @BotFather → отдельный бот (не прод-бот!). Бот выведен из дефолтного `up -d` через compose-профиль `telegram` (`docker compose -p oracleai-staging -f infra/staging/docker-compose.staging.yml --env-file infra/staging/.env.staging --profile telegram up -d`); с placeholder-токеном бот честно падает (TelegramUnauthorizedError). После выдачи токена: вписать его в `.env.staging` (BOT_TOKEN, целиком заменить placeholder) — туннель-скрипт или ручной `--profile telegram up -d` поднимут бота. **Fail-closed guard в туннель-скрипте (факт 2026-09-06):** если вписан токен, совпадающий с продовым (`oracleAI/.env`), бот НЕ поднимается, отказ пишется в journal — продовый токен в staging вызвал конфликт getUpdates двух poller'ов (@oraclAi_bot) и красную изоляцию |
| Restore drill P0-004 на staging | отдельная задача | P0-004 gate |

### Уроки прогонов (важно для будущего прод-deploy)

1. **Один `build:` в compose.** Несколько сервисов с одинаковым `image:`/`build:` из YAML-якоря запускают параллельные сборки одного тега → гонка (`AlreadyExists` при тегировании). `build: !reset null` в Compose 5.5 не работает — выносите `build:` из якоря на единственный сервис.
2. **Схему откатывает текущий (новый) образ.** Откат через предыдущий образ невозможен — он не знает новых миграций. Downgrade-транзакция атомарна: guard миграции 0003 (`RuntimeError: tg_id downgrade to INTEGER is destructive`) откатил ВСЮ цепочку до guard'а, схема осталась на head — это корректное fail-closed поведение.
3. **Target downgrade = ревизия предыдущего релиза, не `base`.** Деплой-скрипт пишет фактическую `alembic_version` в `RELEASE_HISTORY.tsv`; rollback берёт её оттуда.
4. **`compose run` без `IMAGE_TAG`** пересобирает/тянет `:latest` — всегда экспортируйте тег.
5. **Caddy healthcheck**: `wget --no-check-certificate https://...` в `["CMD", ...]` парсится как единый URL (400 → вечный unhealthy); нужен `["CMD-SHELL", ...]`.
6. **Первый старт Caddy**: выпуск self-signed сертификата занимает секунды — health-check с retry (30×2с) в deploy-скрипте обязателен.
7. **Watchdog вне systemd — не watchdog.** Процесс, запущенный nohup из heartbeat-рана, умирает вместе с процессной группой рана; crash-loop остаётся незамеченным. Только systemd user unit с linger.
8. **One-shot job'и (migrate) не должны алертить.** Успешный `staging-migrate` (exit 0) в die-событиях выглядит как смерть контейнера — фильтруйте exit_code=0 в watchdog, иначе каждый deploy создаёт ложный алерт.
9. **Сервис с невалидным внешним токеном (staging-bot) — через compose `profiles`.** Пока токен от @BotFather не выдан, бот вне дефолтного `up -d` (`--profile telegram` включает) — иначе TelegramUnauthorizedError crash-loop и alert-шум.

## Ограничения и правила

- Staging — disposable: тома можно сносить и поднимать заново; персистентные данные только в изолированных томах staging_*.
- Никаких реальных пользовательских данных и продовых секретов.
- Любое изменение этой топологии — через коммит в репо (инфраструктура как код).
- Внешние LLM-вызовы на staging отключены (`LLM_PROVIDER=off`); включение реального провайдера — отдельное решение владельца гейта P0-003.
