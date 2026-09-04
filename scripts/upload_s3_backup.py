#!/usr/bin/env python3
"""Upload an already-encrypted backup and its checksum to S3-compatible storage."""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required for off-site backup")
    return value


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} /backups/oracle-<timestamp>.dump.enc", file=sys.stderr)
        return 2

    encrypted = Path(argv[1])
    checksum = Path(f"{encrypted}.sha256")
    if not encrypted.is_file() or not checksum.is_file():
        print("encrypted backup or checksum is missing", file=sys.stderr)
        return 1

    try:
        endpoint = os.environ.get("BACKUP_S3_URL", "").strip() or None
        access_key = _required("BACKUP_S3_ACCESS_KEY")
        secret_key = _required("BACKUP_S3_SECRET_KEY")
        bucket = _required("BACKUP_S3_BUCKET")
        region = os.environ.get("BACKUP_S3_REGION", "us-east-1").strip() or "us-east-1"
        prefix = os.environ.get("BACKUP_S3_PREFIX", "oracleai").strip("/")

        import boto3  # type: ignore[import-not-found]

        client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        key_prefix = f"{prefix}/" if prefix else ""
        client.upload_file(str(encrypted), bucket, f"{key_prefix}{encrypted.name}")
        client.upload_file(str(checksum), bucket, f"{key_prefix}{checksum.name}")
    except Exception as exc:  # noqa: BLE001
        # Never include endpoint, bucket credentials or provider response details.
        print(f"off-site backup upload failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(f"off-site PostgreSQL backup uploaded: {encrypted.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
