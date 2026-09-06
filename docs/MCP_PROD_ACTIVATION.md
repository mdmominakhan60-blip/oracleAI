# MCP oracleAI — prod activation runbook (BUS-277)

Read-only MCP-сервер (`scripts/mcp_server.py`, BUS-254) подключается к БД
продукта. Этот runbook — как включить его на проде и как проверить защиту.

Модель защиты — два независимых слоя:

1. **server_settings** в пуле MCP (`default_transaction_read_only=on`) —
   купирует даже баг в repo-запросе.
2. **Роль `oracle_mcp_ro`** — SELECT-only (NOSUPERUSER NOCREATEDB
   NOCREATEROLE). Даже соединение без server_settings не может писать.

## 1. Роль (один раз на кластер)

```bash
# Пароль роли — НЕ тот же секрет, что POSTGRES_PASSWORD.
# Сгенерировать и положить в .env прод-каталога:
openssl rand -hex 24   # → ORACLEAI_MCP_ROLE_PASSWORD в .env

make ensure-mcp-role
```

Скрипт идемпотентен: повторный запуск нормализует (ALTER ROLE) и повторно
выдаёт GRANT'ы. После Alembic-миграций новые таблицы получают SELECT через
`ALTER DEFAULT PRIVILEGES` от владельца БД (oracle).

Проверка из контейнера (без --rm, чтобы видеть логи):

```bash
docker compose --env-file .env -f infra/docker-compose.yml run --rm --entrypoint "" \
  -e POSTGRES_ADMIN_DATABASE_URL=postgresql://oracle:<PW>@postgres:5432/postgres \
  -e ORACLEAI_MCP_ROLE_PASSWORD=<MCP_PW> \
  api python scripts/ensure_mcp_role.py
```

## 2. Сетевой доступ (стабильный адрес)

`infra/docker-compose.yml` публикует порт postgres строго на loopback:

```yaml
ports:
  - "${POSTGRES_HOST_BIND:-127.0.0.1}:${POSTGRES_HOST_PORT:-5433}:5432"
```

Docker-IP контейнера (172.x) нестабилен — используем `127.0.0.1:5433`.
Порт не доступен снаружи хоста (bind на loopback).

Staging-стек (`infra/staging/docker-compose.staging.yml`) — отдельный файл,
свой `staging-postgres` без публикации порта; конфликтов с 5433 нет.

## 3. Конфиг MCP-клиента (вне git)

Лончер `~/.local/bin/oracleai-mcp` читает `~/.oracleai-mcp.env` (chmod 600):

```bash
ORACLEAI_MCP_DATABASE_URL=postgresql+asyncpg://oracle_mcp_ro:<MCP_PW>@127.0.0.1:5433/oracle
```

## 4. Smoke + негативный тест (обязателен)

```bash
# Живость: initialize + tools/list + db_health возвращает реальные данные.
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1.0"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"db_health","arguments":{}}}' \
 | ~/.local/bin/oracleai-mcp

# Негативный тест на целевой БД — права роли, не server_settings:
#   INSERT / DELETE / DDL под oracle_mcp_ro → InsufficientPrivilegeError.
# (см. evidence BUS-277: все три отвергнуты на проде 2026-09-06)
```

## 5. Ротация пароля роли

Порядок (синхронно — роль и конфиг клиента, без окна неработоспособности):

```bash
# 1. Новый секрет в .env прод-каталога (openssl rand -hex 24 → ORACLEAI_MCP_ROLE_PASSWORD).
# 2. ALTER ROLE по каноническому пути:
make ensure-mcp-role
# 3. Синхронно перезаписать ~/.oracleai-mcp.env (600) тем же значением:
#    ORACLEAI_MCP_DATABASE_URL=postgresql+asyncpg://oracle_mcp_ro:<NEW_PW>@127.0.0.1:5433/oracle
#    (runbook-формат: user:password@host — без задвоенных сегментов; парсер
#    mcp_server.py regex'ом возьмёт всё до @ как пароль).
# 4. Smoke: stdio db_health + негативные пробы INSERT/DELETE/DDL → denied.
```

История: 2026-09-06 — ротация после нормализации DSN (watchdog-ревью BUS-278:
задвоенный сегмент `oracle_mcp_ro://` в старом конфиге; негативные пробы
подтверждены после ротации).

## 6. Границы

- Роль не имеет прав на sequence/функции — только SELECT по таблицам.
- Self-GRANT (`GRANT ... TO oracle_mcp_ro`) технически проходит, но не даёт
  привилегий сверх собственных (только SELECT) — verified на staging.
- `SECURITY DEFINER`-функций в public-схеме нет (count=0 на 2026-09-06);
  при добавлении таковых — пересмотреть.
- Пункт 3 задачи (Paperclip gateway remote_http для внешних клиентов) —
  зона CTO; локальный stdio — только trusted host.
