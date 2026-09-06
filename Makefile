# .env участвует в интерполяции ${VAR:?} до чтения env_file сервисов — без --env-file
# любой вызов compose из чистого шелла падает ("required variable ... missing").
COMPOSE := docker compose --env-file .env -f infra/docker-compose.yml

.PHONY: init up down restart ps logs observability build migrate selfcheck docs-check shell worker-scale up-local-llm backup restore backup-drill test p004-audit config ensure-mcp-role

init:
	@test -f .env || cp .env.example .env
	@echo "Edit .env, then run: make up"

build:
	$(COMPOSE) build --pull

up:
	$(COMPOSE) up -d --build
	$(COMPOSE) ps

up-local-llm:
	$(COMPOSE) --profile local-llm up -d --build ollama
	$(COMPOSE) --profile local-llm run --rm ollama-init
	$(COMPOSE) up -d --build api bot worker beat
	@echo "Local LLM is ready. Ensure CUSTOM_LLM_BASE_URL=http://ollama:11434/v1 and model names are set in .env."

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) up -d --build --force-recreate

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100 api bot worker beat redis postgres caddy loki alloy prometheus grafana cadvisor node-exporter

observability:
	$(COMPOSE) ps loki alloy prometheus grafana cadvisor node-exporter

migrate:
	$(COMPOSE) run --rm migrate

selfcheck:
	$(COMPOSE) exec api python -m scripts.selfcheck

docs-check:
	python3 scripts/check_documentation_links.py

shell:
	$(COMPOSE) exec api /bin/bash

worker-scale:
	$(COMPOSE) up -d --scale worker=$(N)

backup:
	$(COMPOSE) --profile backup up -d --build backup

restore:
	@test -n "$(BACKUP)" || (echo "usage: make restore BACKUP=/path/to/oracle-<timestamp>.dump.enc RESTORE_TARGET_DB=oracle_restore" && exit 2)
	@test -n "$(RESTORE_TARGET_DB)" || (echo "RESTORE_TARGET_DB must name an isolated database" && exit 2)
	RESTORE_TARGET_DB="$(RESTORE_TARGET_DB)" ./infra/restore-postgres.sh "$(BACKUP)"

# P0-004 drill, рефактор после удаления SQLite: исполнительский drill-скрипт ушёл
# вместе с SQLite; статический контракт P0-004 проверяет всю backup/restore-инфру.
backup-drill:
	python3 scripts/check_p004_infrastructure.py
	bash -n infra/backup-postgres.sh infra/restore-postgres.sh

ensure-test-role:
	$(COMPOSE) run --rm --entrypoint "" \
		-e POSTGRES_ADMIN_DATABASE_URL=postgresql://oracle:$(POSTGRES_PASSWORD)@postgres:5432/postgres \
		api python scripts/ensure_test_role.py

# BUS-277: read-only роль для MCP-сервера (второй слой защиты поверх
# default_transaction_read_only). Пароль роли — независимый секрет
# ORACLEAI_MCP_ROLE_PASSWORD в .env (не POSTGRES_PASSWORD).
ensure-mcp-role:
	@test -f .env && grep -q '^ORACLEAI_MCP_ROLE_PASSWORD=' .env || \
		{ echo "ORACLEAI_MCP_ROLE_PASSWORD не задан в .env (сгенерируй: openssl rand -hex 24)"; exit 1; }
	$(COMPOSE) run --rm --entrypoint "" \
		-e POSTGRES_ADMIN_DATABASE_URL=postgresql://$${POSTGRES_USER:-oracle}:$$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)@postgres:5432/postgres \
		-e ORACLEAI_MCP_ROLE_PASSWORD=$$(grep '^ORACLEAI_MCP_ROLE_PASSWORD=' .env | cut -d= -f2-) \
		api python scripts/ensure_mcp_role.py

test:
	$(CURDIR)/.venv/bin/python scripts/check_test_env.py || python3 scripts/check_test_env.py
	$(COMPOSE) run --rm --entrypoint "" -e DEV_MODE=1 -e DEV_KEY=test-dev-key \
		-e ALLOW_DB_RESET=1 \
		-e TEST_DATABASE_URL=postgresql+asyncpg://oracle_test:$(POSTGRES_PASSWORD)@postgres:5432/oracle_test \
		-e DATABASE_URL=postgresql+asyncpg://oracle_test:$(POSTGRES_PASSWORD)@postgres:5432/oracle_test \
		-e POSTGRES_ADMIN_DATABASE_URL=postgresql://oracle:$(POSTGRES_PASSWORD)@postgres:5432/postgres \
		-v $(CURDIR)/tests:/opt/oracle/tests \
		-v $(CURDIR)/infra:/opt/oracle/infra \
		-v $(CURDIR)/data:/opt/oracle/data:ro \
		-v $(CURDIR)/.env.production.example:/opt/oracle/.env.production.example:ro \
		-v $(CURDIR)/.env.example:/opt/oracle/.env.example:ro \
		-v $(CURDIR)/.github:/opt/oracle/.github:ro \
		-v $(CURDIR)/.git:/opt/oracle/.git:ro \
		-v $(CURDIR)/Makefile:/opt/oracle/Makefile:ro \
		-v $(CURDIR)/scripts:/opt/oracle/scripts \
		-v $(CURDIR)/load:/opt/oracle/load \
		-v $(CURDIR)/requirements-dev.txt:/opt/oracle/requirements-dev.txt \
		-v $(CURDIR)/pytest.ini:/opt/oracle/pytest.ini \
		api bash -c "python scripts/reset_test_database.py && alembic upgrade head && pip install --quiet -r requirements-dev.txt && python -m pytest tests -q"

p004-audit:
	python3 scripts/check_p004_infrastructure.py
	bash -n infra/backup-postgres.sh infra/restore-postgres.sh

config:
	$(COMPOSE) config
