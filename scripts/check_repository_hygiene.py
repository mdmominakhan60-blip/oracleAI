"""Fail when forbidden artifacts or broken local documentation links return."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PATHS = (
    ".10x",
    "docs/research",
    "ORACLEAI_AUDIT_AND_ROADMAP.md",
    "astrology_library_research.md",
    "audit_checks.sh",
    "audit_findings.md",
    "audit_test_results.txt",
    "evidence_snapshot.txt",
    "gate_search.txt",
    "github_snapshot.txt",
    "ops_security_snapshot.txt",
    "pip_audit_results.txt",
    "pytest_results.txt",
    "ruff_results.txt",
    "docs/FILE_AUDIT.csv",
    "docs/PROJECT_MAP.md",
)
CURATED_AUDIT_FILES = {
    "docs/EVIDENCE/AUDIT/sqlite_scaling_10x_2026-08-26.md",
    "docs/EVIDENCE/AUDIT/staging_chat_indexes_2026-08-26.md",
}
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")


def markdown_files() -> list[Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def main() -> int:
    failures: list[str] = []
    for relative in FORBIDDEN_PATHS:
        if (ROOT / relative).exists():
            failures.append(f"forbidden path exists: {relative}")

    audit_dir = ROOT / "docs/EVIDENCE/AUDIT"
    if audit_dir.exists():
        for path in audit_dir.rglob("*"):
            relative = path.relative_to(ROOT).as_posix()
            if not path.is_file() or relative not in CURATED_AUDIT_FILES:
                failures.append(f"unexpected audit artifact: {relative}")

    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            if "://" in target or target.startswith("mailto:"):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                failures.append(f"broken local link: {path.relative_to(ROOT)} -> {target}")

    if failures:
        print("REPOSITORY_HYGIENE_FAIL")
        print("\n".join(failures))
        return 1
    print("REPOSITORY_HYGIENE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
