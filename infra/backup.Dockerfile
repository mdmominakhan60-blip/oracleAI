FROM postgres:16-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates openssl python3 python3-boto3 \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/upload_s3_backup.py /usr/local/bin/upload_s3_backup.py
RUN chmod 0755 /usr/local/bin/upload_s3_backup.py
