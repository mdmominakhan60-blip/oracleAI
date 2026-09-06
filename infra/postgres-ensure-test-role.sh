#!/bin/bash
# BUS-303: непривилегированная роль для тестовых ранов.
# Выполняется docker-entrypoint'ом postgres ТОЛЬКО на чистом томе
# (docker-entrypoint-initdb.d). Для существующих кластеров роль нормализует
# `make ensure-test-role` (scripts/ensure_test_role.py).
# Пароль роли = POSTGRES_PASSWORD: тот же домен доверия (роль не имеет прав
# SUPERUSER/CREATEDB/CREATEROLE, доступ — только к сети oracle_internal).
set -euo pipefail
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER:-oracle}" --dbname "${POSTGRES_DB:-oracle}" <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'oracle_test') THEN
    CREATE ROLE oracle_test WITH LOGIN
      NOSUPERUSER NOCREATEDB NOCREATEROLE
      PASSWORD '${POSTGRES_PASSWORD}';
  ELSE
    ALTER ROLE oracle_test WITH
      NOSUPERUSER NOCREATEDB NOCREATEROLE
      PASSWORD '${POSTGRES_PASSWORD}';
  END IF;
END
\$\$;
SQL
