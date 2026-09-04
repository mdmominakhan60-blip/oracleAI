from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.observability import JsonRedactingFormatter, redact_text
from scripts import check_cache_busting, ops_alerts

ROOT = Path(__file__).resolve().parent.parent


def test_redact_text_removes_secrets_email_and_numeric_ids():
    value = "tg_id=123456789 api_key=sk-secret email=test@example.com Bearer abc.def"
    redacted = redact_text(value)
    assert "123456789" not in redacted
    assert "sk-secret" not in redacted
    assert "test@example.com" not in redacted
    assert "Bearer abc.def" not in redacted


def test_json_formatter_emits_operational_fields_without_pii():
    record = logging.LogRecord(
        "oracle.test", logging.WARNING, __file__, 1,
        "failed for tg_id=123456789", (), None,
    )
    record.event = "webhook_failure"
    record.status_code = 401
    record.path = "/api/webhooks/paddle"
    payload = json.loads(JsonRedactingFormatter().format(record))
    assert payload["event"] == "webhook_failure"
    assert payload["status_code"] == 401
    assert payload["path"] == "/api/webhooks/paddle"
    assert "123456789" not in payload["message"]
    assert "request_id" in payload
    assert "release_id" in payload


def test_sensitive_logger_calls_do_not_interpolate_pii():
    sources = (
        ROOT / "app" / "api" / "deps.py",
        ROOT / "app" / "bot" / "shop.py",
        ROOT / "app" / "services" / "billing.py",
        ROOT / "app" / "services" / "broadcast.py",
        ROOT / "app" / "services" / "chat.py",
        ROOT / "app" / "services" / "scheduler.py",
        ROOT / "app" / "services" / "telegram.py",
    )
    forbidden = ("tg_id", "invoice_payload", "charge_id")
    for path in sources:
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"\blog\.(debug|info|warning|error|exception)\(", line):
                assert not any(token in line for token in forbidden), (
                    f"PII/payment identifier in logger call: {path}:{line}"
                )


def test_ops_alert_log_counts_are_windowed(tmp_path):
    now = datetime.now(timezone.utc).isoformat()
    log_file = tmp_path / "oracle.jsonl"
    log_file.write_text(
        "\n".join([
            json.dumps({"ts": now, "event": "http_5xx"}),
            json.dumps({"ts": now, "event": "webhook_failure"}),
            json.dumps({"ts": now, "event": "llm_fallback"}),
            json.dumps({"ts": now, "event": "llm_request"}),
        ]) + "\n",
        encoding="utf-8",
    )
    counts = ops_alerts._log_counts(
        log_file, ops_alerts._now() - timedelta(minutes=1)
    )
    assert counts == {
        "http_5xx": 1,
        "webhook_failure": 1,
        "llm_fallback": 1,
        "llm_request": 1,
    }


def test_cache_busting_policy_and_public_legal_pages():
    assert check_cache_busting.main() == 0
    for name in ("privacy.html", "terms.html", "privacy-en.html", "terms-en.html"):
        assert (ROOT / "web" / name).is_file()


async def test_ops_alerts_recognize_postgres_backup_and_offsite_failure(db, tmp_path, monkeypatch, capsys):
    """Backup alerts fire from backup-status.json while scheduler is healthy."""
    from app.data.session import utcnow

    await db.execute(
        "INSERT INTO scheduler_leases(name, last_status, last_finished_at, "
        "failure_count, last_error) VALUES(?,?,?,?,?)",
        ("main", "ok", utcnow(), 0, None),
    )
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "oracle-20260827-150000.dump.enc").write_bytes(b"encrypted")
    (backup_dir / "backup-status.json").write_text(
        json.dumps({
            "last_attempt_utc": datetime.now(timezone.utc).isoformat(),
            "local_backup_ok": True,
            "offsite_required": True,
            "offsite_ok": False,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", [
        "ops_alerts", "--backup-dir", str(backup_dir)
    ])

    # ops_alerts reads PostgreSQL through its own asyncpg connection inside
    # main(), so main() must run in a fresh thread, not the test's event loop.
    assert await asyncio.to_thread(ops_alerts.main) == 1
    result = json.loads(capsys.readouterr().out)
    assert "backup_stale_or_missing" not in result["alerts"]
    assert "backup_offsite_unavailable" in result["alerts"]

    status = json.loads((backup_dir / "backup-status.json").read_text(encoding="utf-8"))
    status["offsite_ok"] = True
    (backup_dir / "backup-status.json").write_text(json.dumps(status), encoding="utf-8")
    assert await asyncio.to_thread(ops_alerts.main) == 0
    healthy = json.loads(capsys.readouterr().out)
    assert healthy["ok"] is True


async def test_ops_alert_db_counts_include_scheduler_status(db, tmp_path, monkeypatch, capsys):
    """The script reads llm_usage/scheduler_leases from PostgreSQL (via DATABASE_URL)."""
    from app.data.session import utcnow

    stamp = utcnow()
    await db.execute(
        "INSERT INTO scheduler_leases(name, last_status, last_finished_at, "
        "failure_count, last_error) VALUES(?,?,?,?,?)",
        ("main", "ok", stamp, 0, None),
    )
    await db.executemany(
        "INSERT INTO llm_usage(tg_id, purpose, ok, created_at) VALUES(?,?,?,?)",
        [(1001, "answer:oracle", 1, stamp), (1001, "answer:oracle", 0, stamp)],
    )
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    (backup_dir / "oracle-20260827-150000.dump.enc").write_bytes(b"encrypted")
    (backup_dir / "backup-status.json").write_text(
        json.dumps({
            "last_attempt_utc": stamp,
            "local_backup_ok": True,
            "offsite_required": False,
            "offsite_ok": True,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["ops_alerts", "--backup-dir", str(backup_dir)])

    await asyncio.to_thread(ops_alerts.main)
    result = json.loads(capsys.readouterr().out)
    assert result["scheduler_status"] == "ok"
    assert result["scheduler_age_minutes"] is not None
    assert result["scheduler_failures"] == 0
    assert result["llm_calls"] == 2
    assert result["llm_failed"] == 1
