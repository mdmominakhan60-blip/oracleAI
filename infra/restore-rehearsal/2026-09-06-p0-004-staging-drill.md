# P0-004 backup/restore drill — production-like staging (BUS-108)

**Дата прогона:** 2026-09-06 (05:06–05:17 UTC)
**Исполнитель:** DevOps Engineer
**Цель:** закрыть гейт P0-004 (Operations) прогоном encrypted backup → restore →
migration/rollback rehearsal на disposable production-like инфраструктуре (staging-стек MVP-1),
а не только на живой проде, как в репетиции 2026-09-03.

## Окружение (production-like)

- Staging compose-проект `oracleai-staging`, сеть `oracle_staging_internal`, порты 3443/3080.
- Источник: `oracleai-staging-staging-postgres-1`, БД `oracle_staging`, PG16.15 + pgvector 0.8.6,
  alembic head `0008_funnel_session_id`, 54 таблицы, 4 пользователя.
- Все drill-объекты (БД `oracle_drill_restore`, `oracle_drill_migrate`, `oracle_drill_rollback`,
  временные api-контейнеры) созданы и удалены в изоляции; живой `oracle_staging` не изменялся.
- Реальные дампы с PII — только в `infra/backups/` (запретная зона, `.gitignore:69`), в git не попадают.

## 1. Backup (encrypted + integrity)

| Шаг | Результат |
|---|---|
| `pg_dump --format=custom --no-owner --no-privileges` | 1s, 143 843 bytes |
| `pg_restore --list` (целостность до шифрования) | OK |
| `openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass file:/etc/oracle/backup.key` | 143 872 bytes, header `Salted__` (зашифрован, не plaintext) |
| `sha256sum` | `cb92b22a…2722` записан в `.dump.enc.sha256` |
| Off-site upload (MinIO `oracleai-staging-backups/staging/`) | `oracle_staging-20260905-230710.dump.enc` + `.sha256` присутствуют |

Ключ шифрования `/etc/oracle/backup.key` (600, владелец `softis`) — вне репозитория и вне БД.

## 2. Restore (из off-site копии в чистую БД) + приложение зелёное

Restore выполнен из **off-site копии** (скачано с MinIO, не из локального каталога) — это
доказывает восстановимость именно из внешнего хранилища.

| Шаг | Результат |
|---|---|
| `sha256sum --check` скачанного объекта | MATCH (`cb92b22a…2722`) |
| `openssl enc -d` | OK, 143 843 bytes |
| `pg_restore --clean --if-exists` в `oracle_drill_restore` | 2s |
| Таблицы | 54 (совпадает с источником) |
| Точный `count(*)` по всем 54 таблицам | **ALL MATCH** (diff пуст) |
| Расширения | `plpgsql 1.0`, `vector 0.8.6` |
| Функциональный pgvector-запрос (`embedding <-> …`) | вернул 3 строки |
| Приложение: временный api `staging-r3` против `oracle_drill_restore` | `/health` 200, `database.ok=true`, `schema_tables=54`, `users=4` |
| Auth-гейт (`/api/reports`, `/api/history` без Telegram-подписи) | 401 (fail-closed сохранён) |
| Owner-scope (схема) | `tg_id NOT NULL` во всех owner-scoped таблицах: reports, memories, chat_requests, diary, tarot_readings |

Временный api-контейнер и `oracle_drill_restore` удалены после проверки. Расшифрованный plaintext-дамп удалён.

## 3. Migration rehearsal (полная цепочка alembic)

Через `staging-migrate` образ (`oracleai-staging:staging-r3`) на чистой БД `oracle_drill_migrate`:

| Шаг | Время | Результат |
|---|---|---|
| `alembic upgrade head` (0001→0008 с нуля) | единицы секунд | 8 миграций применены, head `0008_funnel_session_id` |
| `alembic downgrade 0007_add_tarot_deck` | 2s | OK (0008→0007) |
| `alembic downgrade 0006_drop_age_columns` | 2s | OK, колонка `deck` удалена из `tarot_readings` |
| `alembic downgrade 0003_widen_tg_id_to_bigint` | 1s | OK (цепочка 0006→0005→0004→0003) |
| `alembic downgrade 0002_task_jobs` (разрушающий) | 2s | **RuntimeError** «tg_id downgrade to INTEGER is destructive…», транзакционный откат, версия осталась `0003` — **fail-closed guard подтверждён** |
| `alembic upgrade head` (re-upgrade 0003→0008) | 3s | OK, head восстановлен |

Rollback-target = ревизия предыдущего релиза (`0007`), не `base` — guard 0003 делает откат ниже
int32-границы намеренно невозможным без восстановления из бэкапа (см. [[staging-compose-lessons]] п.3).

## 4. Rollback rehearsal (приложение + схема)

Откат версии приложения и схемы на копии staging-БД (живой staging не трогался — конкурентный ран BUS-134):

| Шаг | Результат |
|---|---|
| Restore копии из дампа → `oracle_drill_rollback` (head 0008) | 54 таблицы |
| `alembic downgrade 0007_add_tarot_deck` (схема r1) | OK |
| Запуск api **старого образа `staging-r1`** против схемы 0007 | `/health` 200, `database.ok=true`, `schema_tables=54`, `users=4`, auth 401 |

Откат пары (версия приложения `staging-r1` + схема `0007`) зелёный. Совпадает с живой репетицией
BUS-105 (`RELEASE_HISTORY.tsv`: `rollback staging-r1 0007_add_tarot_deck`).

## 5. Storage permissions (минимальные привилегии)

| Хранилище | Права | Оценка |
|---|---|---|
| Host `infra/backups/` | каталог `755`, дампы `root:root 644` (контейнер пишет от root) | каталог world-readable; содержимое зашифровано AES-256, plaintext-дампов на диске нет. **Рекомендация:** `chmod 750`, писать от непривилегированного uid |
| Ключ `/etc/oracle/backup.key` | `600 softis:softis`, вне репо и вне БД | OK |
| Прод backup-контейнер | `no-new-privileges:true`, key смонтирован `:ro`, `/backups:rw` | OK |
| MinIO buckets | `oracleai-backups` (prod), `oracleai-staging-backups` (staging) | **НАРУШЕНИЕ (устранено 2026-09-06, BUS-208):** prod-ключ имел write-доступ к staging-бакету (кросс-бакет запись подтверждена тестом). Устранено: per-bucket пользователи `prod-backup-writer` / `staging-backup-writer`, см. ниже |

### 5.1. Устранение нарушения (BUS-208, 2026-09-06)

MinIO-ключи переведены на per-bucket least-privilege. Настройка — idempotent IaC-скрипт
`infra/minio-setup-backup-users.sh` (запуск на хосте MinIO; секреты в репо не хранятся).

| Принципал | Политика | Бакет | Действия |
|---|---|---|---|
| `prod-backup-writer` | `prod-backup-rw` | `oracleai-backups` | GetObject, PutObject, ListBucket, ListBucketMultipartUploads, AbortMultipartUpload — **без DeleteObject** |
| `staging-backup-writer` | `staging-backup-rw-v2` | `oracleai-staging-backups` | те же, **без DeleteObject** |

Дополнительные слои защиты:
- **Versioning включён** на обоих бакетах: overwrite оставляет предыдущую версию восстановимой.
- Ключи `minioadmin` (root) выведены из backup-контуров: `BACKUP_S3_ACCESS_KEY` обоих сред —
  per-bucket пользователь; root-креды остаются только на MinIO-контейнере.

Верификация (2026-09-06, probe-объекты `bus208-verify/*`, удалены после теста):

| Тест | prod-ключ | staging-ключ |
|---|---|---|
| put+get в свой бакет | PASS | PASS |
| put в чужой бакет | AccessDenied | AccessDenied |
| list чужого бакета | AccessDenied | AccessDenied |
| delete в свой бакет | AccessDenied (no-delete) | AccessDenied (no-delete) |

Позитивная проверка контура: prod daily-loop после ротации ключей выгрузил
`oracle-20260906-013036.dump.enc` (+sha256) в `oracleai-backups/oracleai/` без ошибок.

## Находки (вне acceptance-минимума, но релевантные гейту)

1. **Staging compose не имеет backup-сервиса.** Прод-стек (`infra/docker-compose.yml`) поднимает
   `backup` (daily encrypted loop), а `docker-compose.staging.yml` — нет. Регулярный шифрованный
   бэкап staging-БД не настроен; данный drill сделал разовый бэкап вручную. Для production-like
   parity стоит завести `staging-backup` сервис (или cron) с отдельным staging-ключом.
2. **MinIO-ключи не per-bucket scoped.** Прод-бэкап-креды пишут в staging-бакет. Для least privilege
   нужны отдельные IAM-пользователи MinIO с политикой `s3:PutObject` только на свой бакет/префикс.
   **Устранено 2026-09-06 (BUS-208)** — см. раздел 5.1; negative-тесты AccessDenied в обе стороны зелёные.

Обе находки — конфигурационные, не блокируют доказательство механики backup→restore→migration→rollback,
которая в этом drill пройдена end-to-end на production-like инфраструктуре.

## Итог по acceptance criteria

- ✅ Backup→restore цикл прошёл: данные восстановлены из off-site копии, точные row counts совпали,
  приложение зелёное на восстановленной БД (`/health` 200, owner-scope 401).
- ✅ Шифрование подтверждено (header `Salted__`, ключ вне репо), ключи не в git.
- ✅ Migration rehearsal (полная цепочка + fail-closed guard) и rollback rehearsal (r1+0007) пройдены,
  шаги и время зафиксированы выше.
- ✅ Storage permissions документированы; выявлены 2 нарушения least-privilege (зафиксированы как follow-up).

**RTO-оценка (staging-объём):** backup 1s + restore 2s + re-upgrade 3s ⇒ восстановление схемы и данных
< 10s для текущего объёма. Прод-объём масштабируется линейно по данным; механика идентична.
