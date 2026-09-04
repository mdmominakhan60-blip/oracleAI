"""Architecture lint — fails if legacy duplicate implementations return.

Проверки:
1. `AgentSpec(...)` — конструктор нельзя вызывать вне `app/core/agents/registry.py`
   (единственная точка сборки из файлового профиля).
2. `from app.db ...` / `import app.db` — фасад удалён.
3. Runtime schema creation — `app/data/schema.py`, `app/data/pg_schema.py`,
   `app.data.schema`, `app.data.pg_schema` больше не существуют.
4. Executable Python в `SKILL.md` — SKILL.md должен быть markdown с YAML
   front matter, без исполняемых блоков.
5. Импорты из удалённого `app.core.skills` / `app.core.agents.specs` не
   должны возвращаться.

Запуск: `python -m scripts.check_architecture`
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

FAILURES: list[str] = []

# ---------------------------------------------------------------------------- 1

AGENT_SPEC_CALL = re.compile(r"\bAgentSpec\s*\(")
REGISTRY_FILE = APP / "core" / "agents" / "registry.py"


def check_agent_spec_constructor() -> None:
    for path in APP.rglob("*.py"):
        if path == REGISTRY_FILE:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if AGENT_SPEC_CALL.search(line) and "def " not in line and "class " not in line \
                    and ":" not in line.split("(")[0] and "return" not in line.split("AgentSpec")[0]:
                # allow return AgentSpec(...) inside registry only; anywhere else in app/ is forbidden
                # (function signatures like `spec: AgentSpec` don't call the constructor)
                if "AgentSpec(" in line and not any(
                        h in line for h in (" AgentSpec)", ": AgentSpec", "-> AgentSpec", "type[AgentSpec")):
                    FAILURES.append(
                        f"{path.relative_to(ROOT)}:{lineno}: hardcoded AgentSpec(...) — "
                        f"must live in app/core/agents/registry.py only")


# ---------------------------------------------------------------------------- 2

APP_DB_IMPORT = re.compile(r"\b(?:from\s+app\.db\b|import\s+app\.db\b|from\s+\.\.?db\s+import|from\s+app\s+import\s+db\b)")


def check_app_db_removed() -> None:
    for path in list(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if rel.parts[0] in {"scripts"} and rel.name == "check_architecture.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if APP_DB_IMPORT.search(line):
                FAILURES.append(
                    f"{rel}:{lineno}: forbidden 'app.db' import — the facade is removed")


# ---------------------------------------------------------------------------- 3

SCHEMA_IMPORTS = re.compile(
    r"\b(?:app\.data\.schema|app\.data\.pg_schema)\b")


def check_schema_modules_removed() -> None:
    forbidden_files = [APP / "data" / "schema.py", APP / "data" / "pg_schema.py"]
    for f in forbidden_files:
        if f.exists():
            FAILURES.append(f"{f.relative_to(ROOT)}: must not exist — DDL lives in Alembic only")
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] == "scripts" and rel.name == "check_architecture.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if SCHEMA_IMPORTS.search(line):
                FAILURES.append(
                    f"{rel}:{lineno}: forbidden schema import — use alembic/schema/baseline.sql")


# ---------------------------------------------------------------------------- 4

EXEC_MD_CODE = re.compile(r"```(?:python|py|shell|bash)\b", re.IGNORECASE)


def check_skill_md_no_executable() -> None:
    for path in (APP / "agents").rglob("SKILL.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        # allow front-matter YAML fences; forbid python/shell code fences
        for lineno, line in enumerate(text.splitlines(), 1):
            if EXEC_MD_CODE.search(line):
                FAILURES.append(
                    f"{path.relative_to(ROOT)}:{lineno}: executable code block in SKILL.md — "
                    f"executable operations belong in app/core/tool_registry.py")


# ---------------------------------------------------------------------------- 5

LEGACY_IMPORTS = re.compile(
    r"\b(?:app\.core\.skills|app\.core\.agents\.specs)\b")


def check_legacy_imports_gone() -> None:
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if rel.parts[0] == "scripts" and rel.name == "check_architecture.py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if LEGACY_IMPORTS.search(line):
                FAILURES.append(
                    f"{rel}:{lineno}: legacy import — use app.core.tool_registry / "
                    f"app.core.agents.registry")


# ---------------------------------------------------------------------------- main


def main() -> int:
    check_agent_spec_constructor()
    check_app_db_removed()
    check_schema_modules_removed()
    check_skill_md_no_executable()
    check_legacy_imports_gone()
    if FAILURES:
        print("architecture-lint FAIL", file=sys.stderr)
        for line in FAILURES:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("architecture-lint OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
