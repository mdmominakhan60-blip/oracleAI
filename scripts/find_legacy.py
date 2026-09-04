"""Classify occurrences of legacy / transitional markers in the repository.

Не просто grep: каждое совпадение классифицируется по контексту (путь,
окружающий текст). Задача — периодически прогонять и убеждаться, что
"transitional" не превращается в постоянный слой.

Классы:
    intentional        — компонент осознанно так назван (README, DECISIONS),
                          не является legacy-кодом
    external_adapter   — совместимость с внешним провайдером/подрядчиком
    historical         — только чтение (audit/EVIDENCE)
    transitional       — временно; должно быть удалено до релиза
    obsolete           — legacy-код, подлежит удалению
    unknown            — не смог классифицировать, требует ручного review

Запуск: `python -m scripts.find_legacy` (exit 0). Для CI можно передать
`--strict`, тогда `obsolete`/`unknown`/`transitional` дают exit 1.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MARKERS = re.compile(
    r"\b(legacy|deprecated|compat(?:ibility)?|shim|adapter|fallback|obsolete|temporary|migration)\b",
    re.IGNORECASE,
)

SEARCH_ROOTS = ("app", "scripts", "tests", "alembic", "docs")
FILE_GLOBS = ("*.py", "*.md", "*.yaml", "*.yml", "*.ini", "*.sql")


def _classify(rel_path: str, line: str, marker: str) -> str:
    p = rel_path.replace("\\", "/")
    low = line.lower()
    if p.startswith("docs/ARCHIVE/") or p.startswith("docs/EVIDENCE/") or p.startswith("docs/RELEASE/"):
        return "historical"
    if p.startswith("docs/") and marker.lower() in {"migration", "compat", "compatibility", "legacy"}:
        return "historical" if "audit" in p.lower() or "review" in p.lower() else "intentional"
    if p.startswith("alembic/versions/"):
        return "intentional"  # every alembic revision is a "migration"
    if "external" in low and ("api" in low or "provider" in low or "payment" in low):
        return "external_adapter"
    if "webhook" in low or "cryptobot" in low or "paddle" in low or "telegram" in low:
        return "external_adapter"
    if p.startswith("app/") and marker.lower() in {"legacy", "obsolete", "shim", "fallback"}:
        # inside runtime code these are usually transitional or obsolete
        if "test" in p or "spec" in p:
            return "intentional"
        return "transitional"
    if p.startswith("tests/"):
        return "intentional"
    if marker.lower() == "adapter":
        return "external_adapter"
    if marker.lower() in {"legacy", "obsolete"}:
        return "obsolete"
    if marker.lower() == "migration":
        return "intentional"
    return "unknown"


def scan(root: Path) -> list[tuple[str, int, str, str, str]]:
    hits = []
    for sub in SEARCH_ROOTS:
        base = root / sub
        if not base.exists():
            continue
        for pattern in FILE_GLOBS:
            for path in base.rglob(pattern):
                rel = str(path.relative_to(root))
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for lineno, line in enumerate(text.splitlines(), 1):
                    for m in MARKERS.finditer(line):
                        cls = _classify(rel, line, m.group(1))
                        hits.append((rel, lineno, m.group(1), cls, line.strip()))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 if any obsolete/unknown/transitional hits remain")
    parser.add_argument("--show", default="obsolete,unknown,transitional",
                        help="comma-separated classes to print in detail")
    args = parser.parse_args()

    hits = scan(ROOT)
    counts = Counter(h[3] for h in hits)
    print("Legacy marker report")
    print("=" * 40)
    for cls in ("obsolete", "transitional", "unknown", "external_adapter",
                "intentional", "historical"):
        print(f"  {cls:16s} {counts.get(cls, 0):5d}")
    print()

    to_show = {c.strip() for c in args.show.split(",") if c.strip()}
    filtered = [h for h in hits if h[3] in to_show]
    if filtered:
        print("Detailed matches:")
        for rel, lineno, marker, cls, line in filtered[:200]:
            print(f"  [{cls}] {rel}:{lineno} :: {marker}: {line[:120]}")
        if len(filtered) > 200:
            print(f"  ... {len(filtered) - 200} more")

    bad = counts.get("obsolete", 0) + counts.get("transitional", 0) + counts.get("unknown", 0)
    if args.strict and bad:
        print(f"\nfind_legacy: strict mode — {bad} non-intentional hits", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
