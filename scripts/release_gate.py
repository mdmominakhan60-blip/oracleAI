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

# BUS-848: ключи, чьи значения не должны попадать в *.log рабочего дерева.
# DSN-ключи дают пароль из URL; прочие — значение целиком.
_LOG_SECRET_KEYS = (
    "POSTGRES_PASSWORD",
    "ORACLEAI_MCP_ROLE_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
    "BOT_TOKEN",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "CUSTOM_LLM_API_KEY",
    "PADDLE_WEBHOOK_SECRET",
    "PADDLE_API_KEY",
    "DEV_KEY",
)
_LOG_DSN_KEYS = ("TEST_DATABASE_URL", "DATABASE_URL", "POSTGRES_ADMIN_DATABASE_URL")
_LOG_MIN_SECRET_LEN = 8
_LOG_MAX_FILE_SIZE = 64 * 1024 * 1024
_LOG_SCAN_EXCLUDED_DIRS = {".git", ".venv", "node_modules", ".codegraph", "artifacts"}

REQUIRED_DOCS = (
    ROOT / "ORIENTATION.md",
    ROOT / "docs" / "product-v2" / "README.md",
    ROOT / "docs" / "product-v2" / "ARCHITECTURE.md",
    ROOT / "docs" / "product-v2" / "DESIGN_SYSTEM.md",
    ROOT / "docs" / "product-v2" / "ACCEPTANCE_CRITERIA.md",
    ROOT / "docs" / "product-v2" / "TEST_PLAN.md",
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


def _collect_log_needles(env: dict[str, str], env_file: Path) -> list[str]:
    """Значения секретов для скана логов: пароли из DSN + значения целиком.

    Значения из env и env_file СКЛАДЫВАЮТСЯ (fail-closed): тест-ран может
    перезаписать DATABASE_URL=TEST_DATABASE_URL, но прод-значение в .env
    остаётся утечкой, которую надо ловить — поэтому один ключ даёт needles
    из всех своих значений, а не только из приоритетного.
    """
    sources: list[dict[str, str]] = [dict(env), {}]
    for line in _read_env_file(env_file):
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and not value.startswith("$"):
            sources[1][key] = value

    def _secret_values(key: str) -> list[str]:
        out: list[str] = []
        for source in sources:
            value = source.get(key, "").strip()
            if not value or value.startswith("$"):
                continue
            out.append(value)
        return out

    needles: list[str] = []
    for key in _LOG_DSN_KEYS:
        for url in _secret_values(key):
            parts = urlsplit(url)
            password = parts.password or ""
            if len(password) >= _LOG_MIN_SECRET_LEN:
                needles.append(password)
    for key in _LOG_SECRET_KEYS:
        for value in _secret_values(key):
            if len(value) >= _LOG_MIN_SECRET_LEN:
                needles.append(value)
    return sorted(set(needles), key=len, reverse=True)


def _read_env_file(path: Path) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [ln for ln in lines if ln and not ln.startswith("#") and "=" in ln]


def check_log_secrets(root: Path | None = None) -> list[str]:
    """BUS-848: *.log рабочего дерева не должны содержать значений из .env.

    Вектор BUS-374: прод-пароль попал в make-test.log (170 вхождений) через
    repr asyncpg и xtrace. Гейт fail-closed: любая утечка блокирует релиз.
    Ошибки не содержат самих значений — вердикт тоже не должен утекать.
    """
    root = root or ROOT
    env: dict[str, str] = dict(os.environ)
    needles = _collect_log_needles(env, root / ".env")
    if not needles:
        return []
    errors: list[str] = []
    for path in sorted(root.rglob("*.log")):
        rel_parts = path.relative_to(root).parts
        if any(part in _LOG_SCAN_EXCLUDED_DIRS for part in rel_parts[:-1]):
            continue
        try:
            if path.stat().st_size > _LOG_MAX_FILE_SIZE:
                errors.append(
                    f"log secret scan: {path.relative_to(root)} skipped "
                    f"(exceeds size limit) — review manually")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"log secret scan: cannot read "
                          f"{path.relative_to(root)}: {type(exc).__name__}")
            continue
        count = sum(text.count(needle) for needle in needles)
        if count:
            errors.append(
                f"log secret scan: {path.relative_to(root)} contains "
                f"{count} occurrence(s) of a secret value from .env/env — "
                f"rotate the value and purge the log")
    return errors


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
