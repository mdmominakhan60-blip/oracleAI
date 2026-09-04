"""Проверка operational сигналов для cron/monitoring.

Источник HTTP/webhook сигналов — JSONL logs, источник LLM/freshness — PostgreSQL.
Скрипт не выводит строки сообщений, diary, memory или webhook payload.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dsn() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL не задан")
    # SQLAlchemy-style "postgresql+asyncpg://..." -> asyncpg "postgresql://..."
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _log_counts(path: Path, cutoff: datetime) -> dict[str, int]:
    counts = {"http_5xx": 0, "webhook_failure": 0, "llm_fallback": 0, "llm_request": 0}
    if not path.is_file():
        return counts
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        stamp = _parse_time(item.get("ts"))
        if not stamp or stamp < cutoff:
            continue
        event = item.get("event")
        if event in counts:
            counts[event] += 1
    return counts


def _empty_counts() -> dict[str, float | int | str | None]:
    return {
        "llm_calls": 0, "llm_failed": 0, "last_backup_age_s": -1,
        "scheduler_status": "missing", "scheduler_age_s": -1,
        "scheduler_failures": 0, "scheduler_error": None,
    }


async def _db_counts(cutoff: datetime) -> dict[str, float | int | str | None]:
    empty = _empty_counts()
    try:
        import asyncpg

        conn = await asyncpg.connect(_dsn())
    except Exception:  # noqa: BLE001 — недоступная БД приравнивается к "missing"
        return empty
    try:
        stamp = cutoff.isoformat()
        calls = await conn.fetchval(
            "SELECT COUNT(*) FROM llm_usage WHERE created_at >= $1", stamp) or 0
        failed = await conn.fetchval(
            "SELECT COUNT(*) FROM llm_usage WHERE created_at >= $1 AND ok = 0",
            stamp) or 0
        scheduler = None
        try:
            scheduler = await conn.fetchrow(
                "SELECT last_status, last_finished_at, failure_count, last_error "
                "FROM scheduler_leases WHERE name = 'main'")
        except asyncpg.UndefinedTableError:
            scheduler = None
    finally:
        await conn.close()
    result = dict(empty)
    result.update({"llm_calls": calls, "llm_failed": failed})
    if scheduler:
        finished = _parse_time(scheduler["last_finished_at"])
        result.update({
            "scheduler_status": scheduler["last_status"] or "unknown",
            "scheduler_age_s": max(0, (_now() - finished).total_seconds())
            if finished else -1,
            "scheduler_failures": int(scheduler["failure_count"] or 0),
            "scheduler_error": scheduler["last_error"],
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-file", default="")
    parser.add_argument("--backup-dir", default="backups")
    parser.add_argument("--window-minutes", type=int, default=15)
    parser.add_argument("--max-5xx", type=int, default=0)
    parser.add_argument("--max-webhook-failures", type=int, default=0)
    parser.add_argument("--max-fallback-rate", type=float, default=0.25)
    parser.add_argument("--max-backup-age-hours", type=float, default=30)
    parser.add_argument("--max-scheduler-age-minutes", type=float, default=30)
    args = parser.parse_args()
    if args.window_minutes < 1:
        parser.error("--window-minutes must be positive")

    cutoff = _now() - timedelta(minutes=args.window_minutes)
    log_counts = _log_counts(Path(args.log_file), cutoff) if args.log_file else {
        "http_5xx": 0, "webhook_failure": 0, "llm_fallback": 0, "llm_request": 0,
    }
    db_counts = asyncio.run(_db_counts(cutoff))
    completed_llm = log_counts["llm_fallback"] + log_counts["llm_request"]
    total_llm = max(completed_llm, int(db_counts["llm_calls"]))
    failed_llm = int(db_counts["llm_failed"])
    fallback_rate = log_counts["llm_fallback"] / completed_llm if completed_llm else 0.0

    backup_dir = Path(args.backup_dir)
    backups = sorted(
        [
            *backup_dir.glob("oracle-*.dump.enc"),
            *backup_dir.glob("oracle-*.dump.enc.sha256"),
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    backup_age_h = ((_now().timestamp() - backups[0].stat().st_mtime) / 3600) if backups else float("inf")
    alerts: list[str] = []
    backup_status: dict[str, object] = {}
    status_path = backup_dir / "backup-status.json"
    if status_path.is_file():
        try:
            loaded_status = json.loads(status_path.read_text(encoding="utf-8"))
            if not isinstance(loaded_status, dict):
                raise ValueError("backup status must be an object")
            backup_status = loaded_status
        except (OSError, ValueError, json.JSONDecodeError):
            backup_status = {}
            alerts.append("backup_status_invalid")
        if backup_status.get("local_backup_ok") is False:
            alerts.append("backup_job_failed")
        if backup_status.get("offsite_required") and backup_status.get("offsite_ok") is not True:
            alerts.append("backup_offsite_unavailable")
    if log_counts["http_5xx"] > args.max_5xx:
        alerts.append("http_5xx_threshold")
    if log_counts["webhook_failure"] > args.max_webhook_failures:
        alerts.append("webhook_failure_threshold")
    if fallback_rate > args.max_fallback_rate:
        alerts.append("llm_fallback_rate_threshold")
    if backup_age_h > args.max_backup_age_hours:
        alerts.append("backup_stale_or_missing")
    scheduler_status = str(db_counts.get("scheduler_status") or "missing")
    scheduler_age_s = float(db_counts.get("scheduler_age_s", -1))
    if scheduler_status == "error":
        alerts.append("scheduler_last_run_failed")
    if scheduler_status in {"missing", "never"} or scheduler_age_s < 0:
        alerts.append("scheduler_status_missing")
    elif scheduler_age_s > args.max_scheduler_age_minutes * 60:
        alerts.append("scheduler_stale")

    result = {
        "ok": not alerts,
        "window_minutes": args.window_minutes,
        "http_5xx": log_counts["http_5xx"],
        "webhook_failures": log_counts["webhook_failure"],
        "llm_calls": total_llm,
        "llm_failed": failed_llm,
        "llm_fallbacks": log_counts["llm_fallback"],
        "llm_fallback_rate": round(fallback_rate, 4),
        "backup_age_hours": round(backup_age_h, 2) if backup_age_h != float("inf") else None,
        "backup_local_ok": backup_status.get("local_backup_ok"),
        "backup_offsite_required": backup_status.get("offsite_required"),
        "backup_offsite_ok": backup_status.get("offsite_ok"),
        "scheduler_status": scheduler_status,
        "scheduler_age_minutes": round(scheduler_age_s / 60, 2) if scheduler_age_s >= 0 else None,
        "scheduler_failures": int(db_counts.get("scheduler_failures", 0)),
        "alerts": alerts,
    }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 1 if alerts else 0


if __name__ == "__main__":
    raise SystemExit(main())
