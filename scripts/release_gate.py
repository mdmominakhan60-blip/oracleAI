"""Deterministic pre-deployment gate for OracleAI production releases."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REQUIRED_DOCS = (
    ROOT / "docs" / "PRODUCT.md",
    ROOT / "docs" / "SECURITY.md",
    ROOT / "docs" / "DEPLOYMENT.md",
    ROOT / "docs" / "LLM_EVALUATION.md",
    ROOT / "docs" / "RELEASE/LAUNCH_GOVERNANCE.md",
    ROOT / "docs" / "RELEASE/PRODUCTION_READINESS.md",
    ROOT / "docs" / "RELEASE/CURRENT_STATUS.md",
    ROOT / "docs" / "PRODUCTION_GAUNTLET.md",
    ROOT / "docs" / "PRODUCTION_FINAL_REVIEW.md",
    ROOT / "docs" / "UI_PIXEL_AUDIT.md",
)


def check_docs() -> list[str]:
    return [str(path.relative_to(ROOT)) for path in REQUIRED_DOCS if not path.is_file()]


def check_static_contract() -> list[str]:
    errors: list[str] = []
    try:
        from scripts.check_agent_quality import build_report

        quality = build_report()
        if not quality["ok"]:
            errors.extend(f"agent quality: {item}" for item in quality["errors"])
    except Exception as exc:  # noqa: BLE001
        errors.append(f"agent quality check failed: {type(exc).__name__}: {exc}")
    try:
        from app.core import palm

        schema = palm.PALM_RESPONSE_FORMAT["json_schema"]
        root = schema["schema"]
        if schema.get("strict") is not True:
            errors.append("Palm response schema is not strict")
        if root.get("additionalProperties") is not False:
            errors.append("Palm root schema must close additionalProperties")
        if set(root.get("required", ())) != set(root.get("properties", ())):
            errors.append("Palm root required/properties mismatch")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"Palm schema import/check failed: {type(exc).__name__}: {exc}")
    try:
        from scripts.check_p004_infrastructure import check

        errors.extend(f"P0-004: {item}" for item in check())
    except Exception as exc:  # noqa: BLE001
        errors.append(f"P0-004 infrastructure check failed: {type(exc).__name__}: {exc}")
    return errors


def check_production_env() -> list[str]:
    errors: list[str] = []
    if os.getenv("APP_ENV") != "production":
        errors.append("APP_ENV must equal production")
    if os.getenv("DEV_MODE", "0").lower() not in {"0", "false", "no"}:
        errors.append("DEV_MODE must be disabled")
    if not os.getenv("WEBAPP_URL", "").startswith("https://"):
        errors.append("WEBAPP_URL must be an HTTPS URL")
    for name in (
        "BOT_TOKEN", "ADMIN_ID", "POSTGRES_PASSWORD", "GRAFANA_ADMIN_PASSWORD",
        "DATABASE_URL", "RELEASE_ID",
    ):
        if not os.getenv(name):
            errors.append(f"{name} is missing")
    for name in ("POSTGRES_PASSWORD", "GRAFANA_ADMIN_PASSWORD"):
        password = os.getenv(name, "").strip().lower()
        if password in {"oracle", "change_me", "change-me", "password", "postgres"}:
            errors.append(f"{name} uses an unsafe template value")
    database_url = os.getenv("DATABASE_URL", "").lower()
    if database_url and "postgresql" not in database_url:
        errors.append("DATABASE_URL must point to PostgreSQL")
    if os.getenv("CELERY_ENABLED", "0") == "1" and not os.getenv("REDIS_URL", "").strip():
        errors.append("REDIS_URL is required when CELERY_ENABLED=1")
    if os.getenv("RELEASE_ID", "").strip().lower() == "local":
        errors.append("RELEASE_ID must identify the deployed commit/tag")
    return errors


def check_log_secrets() -> list[str]:
    """BUS-847: *.log в репо не должны содержать значений секретов из .env.

    Утечка BUS-776 (170 вхождений прод-POSTGRES_PASSWORD в make-test.log)
    была поймана человеком; этот гейт делает проверку fail-closed перед
    релизом. Fail-open на недоступном .env: без .env проверять нечего.
    """
    env_file = ROOT / ".env"
    if not env_file.is_file():
        return []
    needles: list[str] = []
    for line in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip("'\"")
        if not value or value.startswith("$"):
            continue
        # URL-переменные (DATABASE_URL и т.п.) — берём только пароль из netloc;
        # сам URL как needle был бы ложным срабатыванием на не-секретную часть.
        if key.endswith("_URL") or key.endswith("_DSN"):
            password = urlsplit(value).password or ""
            if len(password) >= 8:
                needles.append(password)
        elif key in _LOG_SECRET_KEYS and len(value) >= 8:
            needles.append(value)
    if not needles:
        return []
    errors: list[str] = []
    skip_parts = {".git", "node_modules", ".venv"}
    for log_path in sorted(ROOT.rglob("*.log")):
        if skip_parts & set(log_path.parts):
            continue
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            errors.append(f"{log_path.relative_to(ROOT)}: unreadable")
            continue
        for needle in needles:
            if needle in content:
                # Печатаем только имя файла и имя переменной, не значение.
                errors.append(
                    f"{log_path.relative_to(ROOT)}: contains a secret value "
                    f"(length {len(needle)}); scrub or delete the log")
                break
    return errors


_LOG_SECRET_KEYS = frozenset({
    "POSTGRES_PASSWORD",
    "ORACLEAI_MCP_ROLE_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
    "BOT_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "CUSTOM_LLM_API_KEY",
    "PADDLE_WEBHOOK_SECRET",
    "PADDLE_API_KEY",
})


def run(*, production: bool = False) -> list[str]:
    errors = check_docs() + check_static_contract() + check_log_secrets()
    if production:
        errors.extend(check_production_env())
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true",
                        help="also enforce production environment variables")
    args = parser.parse_args()
    errors = run(production=args.production)
    if errors:
        print("RELEASE GATE: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("RELEASE GATE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
