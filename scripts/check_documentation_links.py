"""Validate repository-relative Markdown links in the documentation tree."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")


def markdown_files() -> list[Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]


def main() -> int:
    failures: list[str] = []
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for target in LINK_RE.findall(text):
            if "://" in target or target.startswith(("mailto:", "#")):
                continue
            resolved = (path.parent / target).resolve()
            if not resolved.exists():
                failures.append(f"{path.relative_to(ROOT)} -> {target}")
    if failures:
        print("DOCUMENTATION_LINKS_FAIL")
        print("\n".join(failures))
        return 1
    print(f"DOCUMENTATION_LINKS_PASS files={len(markdown_files())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
