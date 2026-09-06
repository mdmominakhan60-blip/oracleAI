#!/usr/bin/env bash
# BUS-208: per-bucket least-privilege MinIO users for backup keys.
# Создаёт по одному MinIO-пользователю на бакет; политика каждого —
# только свой бакет, без DeleteObject (anti-delete; overwrite смягчён versioning).
#
# Запуск: на хосте, где живёт MinIO-контейнер (oracle-minio):
#   sudo bash infra/minio-setup-backup-users.sh
# Скрипт idempotent: повторный запуск переносит существующих юзеров.
#
# Секреты (access/secret ключи) НЕ хранятся в репо: скрипт генерирует
# случайные секреты для НОВЫХ юзеров и печатает их один раз; для
# существующих юзеров ничего не меняет (ротация — через `mc admin user svcacct add`
# или пересоздание юзера вручную).
set -Eeuo pipefail

MINIO_CONTAINER="${MINIO_CONTAINER:-oracle-minio}"
MINIO_ALIAS="${MINIO_ALIAS:-local}"

declare -a BUCKETS=(oracleai-backups oracleai-staging-backups)
declare -A USERS=(
  [oracleai-backups]="prod-backup-writer"
  [oracleai-staging-backups]="staging-backup-writer"
)
declare -A POLICIES=(
  [oracleai-backups]="prod-backup-rw"
  [oracleai-staging-backups]="staging-backup-rw-v2"
)

m() { docker exec "$MINIO_CONTAINER" mc "$@"; }

# 1. Бакеты существуют (создаём, если нет).
for bucket in "${BUCKETS[@]}"; do
  if ! m ls "$MINIO_ALIAS/" 2>/dev/null | grep -q "$bucket/"; then
    m mb "$MINIO_ALIAS/$bucket"
    echo "created bucket: $bucket"
  fi
  # Versioning: старые версии переживают overwrite, удаляемое остаётся recoverable.
  if ! m version info "$MINIO_ALIAS/$bucket" 2>/dev/null | grep -q "enabled"; then
    m version enable "$MINIO_ALIAS/$bucket"
    echo "versioning enabled: $bucket"
  fi
done

# 2. Пользователь + политика на каждый бакет.
for bucket in "${BUCKETS[@]}"; do
  user="${USERS[$bucket]}"
  policy="${POLICIES[$bucket]}"

  # 2a. Политика: PutObject/GetObject/ListBucket (разрешаем MultipartUpload —
  # нужен boto3.upload_file), БЕЗ DeleteObject.
  if ! m admin policy info "$MINIO_ALIAS" "$policy" >/dev/null 2>&1; then
    policy_file="/tmp/${policy}.json"
    docker exec -i "$MINIO_CONTAINER" sh -c "cat > $policy_file" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:ListBucketMultipartUploads", "s3:AbortMultipartUpload"],
      "Resource": ["arn:aws:s3:::${bucket}", "arn:aws:s3:::${bucket}/*"]
    }
  ]
}
EOF
    m admin policy create "$MINIO_ALIAS" "$policy" "$policy_file"
    docker exec "$MINIO_CONTAINER" rm -f "$policy_file"
    echo "created policy: $policy (bucket=$bucket, no s3:DeleteObject)"
  fi

  # 2b. Пользователь. Если уже есть — не трогаем (idempotent).
  if m admin user info "$MINIO_ALIAS" "$user" >/dev/null 2>&1; then
    echo "user exists, keeping: $user (policy attach refreshed)"
    m admin policy attach "$MINIO_ALIAS" "$policy" --user "$user" 2>/dev/null || true
    continue
  fi

  secret="$(head -c 32 /dev/urandom | base64 | tr -d '/+=' | head -c 40)"
  m admin user add "$MINIO_ALIAS" "$user" "$secret"
  m admin policy attach "$MINIO_ALIAS" "$policy" --user "$user"
  # Печатаем секрет один раз — сохраняем в env-файл соответствующей среды вручную.
  echo "USER CREATED: $user accesskey=$user secret=$secret"
done

# 3. Root-креды (minioadmin) больше не должны использоваться backup-сервисами.
echo
echo "Done. Verify .env BACKUP_S3_ACCESS_KEY points to a per-bucket user, NOT minioadmin."
