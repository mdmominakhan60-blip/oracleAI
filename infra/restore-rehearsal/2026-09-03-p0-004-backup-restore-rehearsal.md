# P0-004: Encrypted off-site backup + restore rehearsal

Дата репетиции: 2026-09-03
Исполнитель: DevOps Engineer (Paperclip, run f9bd7383)

## Цель и критерии done

Задача: зашифрованный off-site backup PostgreSQL+pgvector и репетиция восстановления.

Критерии done:
- [x] backup зашифрован (AES-256-CBC + PBKDF2, ключ вне БД)
- [x] backup хранится off-site (S3-совместимый MinIO, bucket `oracleai-backups`, префикс `oracleai/`)
- [x] restore rehearsal выполнен и задокументирован (восстановление в изолированную БД `oracle_restore`)
- [x] статический контракт-гейт P0-004 проходит 40/40 (`scripts/check_p004_infrastructure.py`)

## Схема решения

```
PostgreSQL (pgvector/pgvector:pg16, БД oracle)
   │  pg_dump --format=custom --no-owner --no-privileges
   ▼
backup daemon (oracleai-backup:local, сервис backup в infra/docker-compose.yml)
   │  openssl enc -aes-256-cbc -pbkdf2 -iter 200000  (ключ /etc/oracle/backup.key)
   │  sha256sum → .sha256
   ▼
/backups/oracle-<ts>.dump.enc (+ .sha256)      ── локальная копия (BACKUP_STORAGE_PATH)
   │  upload_s3_backup.py (boto3)
   ▼
MinIO bucket oracleai-backups/oracleai/          ── OFF-SITE (BACKUP_S3_URL=http://oracle-minio:9000)
   │  mc cp  (download)
   ▼
restore-postgres.sh → openssl -d → pg_restore → изолированная БД oracle_restore
```

## Что настроено

### 1. Ключ шифрования
- Файл: `/etc/oracle/backup.key` (openssl rand -base64 48, mode 600, владелец softis).
- Монтируется в backup-контейнер через `BACKUP_ENCRYPTION_KEY_HOST_PATH=/etc/oracle/backup.key`.
- Хранится вне БД и вне репозитория. Ключ не коммитится и не выводится в логи.

### 2. Off-site хранилище (MinIO, S3-совместимое)
- Контейнер `oracle-minio` в сети `infra_oracle_internal`, volume `minio_data`.
- Console/API: `127.0.0.1:9000` / `9001`.
- Bucket: `oracleai-backups`. Объекты: `oracleai/oracle-<ts>.dump.enc` + `.enc.sha256`.

### 3. Параметры в `.env`
```ini
BACKUP_REQUIRE_ENCRYPTION=1
BACKUP_REQUIRE_OFFSITE=1
BACKUP_KEEP=14
BACKUP_S3_URL=http://oracle-minio:9000
BACKUP_S3_ACCESS_KEY=<set>
BACKUP_S3_SECRET_KEY=<set>
BACKUP_S3_BUCKET=oracleai-backups
BACKUP_S3_REGION=us-east-1
BACKUP_S3_PREFIX=oracleai
```

### 4. Сервис backup
- Образ: `oracleai-backup:local` (infra/backup.Dockerfile: postgres:16-bookworm + openssl + python3-boto3).
- Запущен: `docker compose --profile backup up -d backup` → контейнер `infra-backup-1`.
- Цикл: pg_dump → контроль `pg_restore --list` → openssl-шифрование → sha256 → S3-upload → retention 14 дней → sleep 86400.

## Выполненный backup (доказательство)

Файл: `oracle-20260903-032904.dump.enc` (233280 байт) + `.sha256`.

- Проверка зашифрованности: первые 16 байт = `Salted__` (openssl Salted_ header) → не plaintext.
- `backup-status.json`:
  ```json
  {"last_attempt_utc":"2026-09-03T03:29:04Z","local_backup_ok":true,"offsite_required":1,"offsite_ok":true}
  ```
- Off-site в MinIO:
  ```
  oracleai-backups/oracleai/oracle-20260903-032904.dump.enc       228KiB
  oracleai-backups/oracleai/oracle-20260903-032904.dump.enc.sha256 107B
  ```
- Лог сервиса: `off-site PostgreSQL backup uploaded: oracle-20260903-032904.dump.enc`

## Restore rehearsal (доказательство)

Ключевой момент: восстановление выполнялось из **off-site копии** (скачана из MinIO через `mc cp`), а не из локального каталога — это доказывает, что off-site копия восстановима.

Шаги:
1. `mc cp local/oracleai-backups/oracleai/oracle-20260903-032904.dump.enc(.sha256)` → host `/backups/`.
2. `RESTORE_TARGET_DB=oracle_restore ./infra/restore-postgres.sh /backups/oracle-20260903-032904.dump.enc`
   - Проверка контрольной суммы: `sha256sum --check` → `ЦЕЛ` (OK).
   - Расшифровка: `openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000`.
   - `pg_restore --clean --if-exists --no-owner --no-privileges` в БД `oracle_restore`.
   - Вывод: `PostgreSQL restore completed into isolated database 'oracle_restore'`.
3. Сравнение схем и строк с живой БД `oracle`:
   - Расширения: `vector 0.8.6` и `plpgsql` восстановлены.
   - Набор таблиц `public.*` идентичен живой БД.
   - Построчные счётчики по всем `public.*` таблицам совпали с живой БД (расхождений нет).
4. Функциональная проверка pgvector в восстановленной БД:
   ```sql
   SELECT ARRAY[1.0,2.0,3.0]::vector <-> ARRAY[4.0,5.0,6.0]::vector;  -- 5.196... (работает)
   ```
5. После проверки изолированная БД `oracle_restore` удалена (репетиция не меняет прод-данные).

## Исправления в P0-004 инфраструктуре (commit d48ea7c)

В ходе репетиции найдены и исправлены два бага `infra/restore-postgres.sh`:
1. `createdb --if-not-exists` не поддерживается до PostgreSQL 18. Заменено на проверку существования через `psql` (`SELECT 1 FROM pg_database WHERE datname=...`) + `createdb` без флага. Осталось идемпотентным на PG16.
2. `docker compose exec` внутри контейнера работает от root, у которого нет PG-роли. Все exec-команды теперь передают `PGUSER`, `PGPASSWORD`, `PGHOST=localhost` (TCP-подключение ролью `oracle`).
3. Обновлён needle в `scripts/check_p004_infrastructure.py` под исправленную логику.

Верификация после фикса: `make backup-drill` → `{'ok': True, 'checks': 40, 'failures': []}` + `bash -n`.

## Как пользоваться

```bash
# Запустить backup-демон (раз в сутки, retention 14 дней)
make backup                       # docker compose --profile backup up -d backup

# Восстановление в изолированную БД (рекомендуемый безопасный путь)
make restore BACKUP=/backups/oracle-<ts>.dump.enc RESTORE_TARGET_DB=oracle_restore

# In-place восстановление в живую БД — только с явным подтверждением
# RESTORE_IN_PLACE=1 RESTORE_CONFIRM=I_UNDERSTAND_IN_PLACE_RESTORE ...

# Статический контракт-гейт + синтаксис скриптов
make backup-drill

# Мониторинг (alerts: backup_job_failed, backup_offsite_unavailable, backup_stale_or_missing)
python3 scripts/ops_alerts.py --backup-dir backups
```

## Мониторинг и алерты
- `backup-status.json` пишется сервисом на каждой попытке; `ops_alerts.py` поднимает `backup_offsite_unavailable`, если off-site требуется и не удался, и `backup_stale_or_missing` при возрасте > 30 ч.

## Ограничения / заметки
- Off-site цель здесь — локальный MinIO (S3-совместимый). Для боевого off-site заменить `BACKUP_S3_URL` на реальный S3/R2/Backblaze endpoint и передать реальные ключи (через секреты, не в `.env` в репо). Сам механизм (boto3, S3 API, шифрование) не меняется.
- Ключ `/etc/oracle/backup.key` обязан существовать на host до запуска backup-профиля; создаётся командой из `.env.production.example`.
- Восстановление всегда идёт в изолированную БД по умолчанию; in-place требует двух явных флагов.
