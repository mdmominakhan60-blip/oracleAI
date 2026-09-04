"""SQL shim inventory — collects and classifies all SQL strings used by the
repository layer. DB-001 is CLOSED (shim removed 2026-08-30); this script
remains as a historical checklist generator / regression scanner.

Usage:
    python scripts/sql_shim_inventory.py              # prints + writes docs/SQL_SHIM_INVENTORY.md
    python scripts/sql_shim_inventory.py --stdout     # print only, no file write

The script scans:
    app/repo/*.py
    app/services/*.py
    app/data/seed.py
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files to scan
SCAN_GLOBS = [
    "app/repo/*.py",
    "app/services/*.py",
    "app/data/seed.py",
]

# ─── Classifiers ──────────────────────────────────────────────────────────────

# Pattern: count ? placeholders in a SQL string (not inside a string literal)
_Q_PLACEHOLDER = re.compile(r"\?")

_INSERT_OR_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.I)
_AUTOINCREMENT   = re.compile(r"\bAUTOINCREMENT\b", re.I)
_COLLATE_NOCASE  = re.compile(r"\bCOLLATE\s+NOCASE\b", re.I)
_LASTROWID_USE   = re.compile(r"\.lastrowid\b")
_ROWCOUNT_USE    = re.compile(r"\.rowcount\b")
_CTE             = re.compile(r"\bWITH\b.+?\bSELECT\b", re.I | re.S)
_WINDOW_FUNC     = re.compile(r"\bOVER\s*\(", re.I)
_EXECUTEMANY     = re.compile(r"\bexecutemany\s*\(", re.I)
# Dangerous: a string literal that CONTAINS a ? (could be used as SQL param in
# a context where it shouldn't be, or confuse the shim counter)
_LITERAL_WITH_Q  = re.compile(r"'[^']*\?[^']*'|\"[^\"]*\?[^\"]*\"")


@dataclass
class FileStats:
    path: str
    q_placeholders: int = 0          # total ? across all SQL calls
    insert_or_ignore: int = 0
    autoincrement: int = 0
    collate_nocase: int = 0
    lastrowid_uses: int = 0          # .lastrowid references in Python code
    rowcount_uses: int = 0           # .rowcount references in Python code
    cte_count: int = 0
    window_func_count: int = 0
    executemany_count: int = 0
    dangerous_literals: int = 0      # string literals containing ?
    sql_calls: int = 0               # db.execute / db.executemany call sites
    sql_strings: list[str] = field(default_factory=list)  # raw SQL texts found


def _extract_sql_strings(source: str) -> list[str]:
    """Heuristically extract SQL string arguments from execute() / executemany()
    calls.  We walk the AST and collect the first string argument of any call
    whose function attribute is named 'execute' or 'executemany'.
    """
    strings: list[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return strings

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name not in ("execute", "executemany"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        # Handle simple string literals
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            strings.append(first.value)
        # Handle implicit string concatenation (f"..." + "..." or "a" "b")
        elif isinstance(first, ast.JoinedStr):
            # f-string: reconstruct best-effort by joining Constant parts
            parts = [
                p.value for p in first.values
                if isinstance(p, ast.Constant) and isinstance(p.value, str)
            ]
            strings.append(" ".join(parts))
        elif isinstance(first, (ast.Add,)):
            pass  # skip complex concat; counted via raw-text fallback

    return strings


def _scan_file(path: Path) -> FileStats:
    source = path.read_text(encoding="utf-8")
    stats = FileStats(path=str(path.relative_to(ROOT)))

    # Python-level .lastrowid / .rowcount counts (in any context)
    stats.lastrowid_uses = len(_LASTROWID_USE.findall(source))
    stats.rowcount_uses  = len(_ROWCOUNT_USE.findall(source))
    stats.executemany_count = len(_EXECUTEMANY.findall(source))

    # Extract SQL strings via AST
    sql_strings = _extract_sql_strings(source)
    stats.sql_calls    = len(sql_strings)
    stats.sql_strings  = sql_strings

    for sql in sql_strings:
        stats.q_placeholders   += len(_Q_PLACEHOLDER.findall(sql))
        stats.insert_or_ignore += len(_INSERT_OR_IGNORE.findall(sql))
        stats.autoincrement    += len(_AUTOINCREMENT.findall(sql))
        stats.collate_nocase   += len(_COLLATE_NOCASE.findall(sql))
        stats.cte_count        += 1 if _CTE.search(sql) else 0
        stats.window_func_count += 1 if _WINDOW_FUNC.search(sql) else 0
        stats.dangerous_literals += len(_LITERAL_WITH_Q.findall(sql))

    return stats


def _collect_files() -> list[Path]:
    import glob as g
    files: list[Path] = []
    for pattern in SCAN_GLOBS:
        for p in sorted(g.glob(str(ROOT / pattern))):
            files.append(Path(p))
    return files


def _build_report(stats_list: list[FileStats]) -> str:
    lines: list[str] = []
    lines.append("# SQL Shim Inventory — DB-001 Migration Checklist")
    lines.append("")
    lines.append("Generated by `scripts/sql_shim_inventory.py`.")
    lines.append("This is the **working checklist** for Etap 1 (DB-001): replacing the")
    lines.append("`_translate_sql` shim with native PostgreSQL idioms.")
    lines.append("")
    lines.append("## Scope")
    lines.append("")
    lines.append("Scanned files:")
    for pattern in SCAN_GLOBS:
        lines.append(f"- `{pattern}`")
    lines.append("")

    # ── Summary table ──
    lines.append("## Per-File Summary")
    lines.append("")
    col_w = 45
    header = (
        f"| {'File':<{col_w}} | SQL calls | `?` total | "
        "INSERT OR IGNORE | AUTOINCREMENT | COLLATE NOCASE | "
        "lastrowid | rowcount | CTE | OVER | executemany | dangerous `?` |"
    )
    sep = (
        f"| {'-'*col_w} | --------- | --------- | "
        "---------------- | ------------- | -------------- | "
        "--------- | -------- | --- | ---- | ----------- | ------------- |"
    )
    lines.append(header)
    lines.append(sep)

    totals = FileStats(path="**TOTAL**")

    def _status_marker(stat: FileStats) -> str:
        """Return a marker column entry: DONE when nothing legacy left, ELSE empty."""
        legacy = (stat.q_placeholders + stat.insert_or_ignore + stat.autoincrement
                  + stat.collate_nocase + stat.lastrowid_uses)
        if stat.sql_calls == 0:
            return ""  # module has no SQL at all
        return "✅ DB-001" if legacy == 0 else ""

    for s in stats_list:
        rel = s.path
        marker = _status_marker(s)
        label = f"`{rel:<{col_w-2}}`"
        if marker:
            # keep column width readable while injecting the marker in-line
            trimmed_path = f"`{rel.rstrip()}` **{marker}**"
            label = trimmed_path.ljust(col_w + 2)
        lines.append(
            f"| {label} | {s.sql_calls:>9} | {s.q_placeholders:>9} | "
            f"{s.insert_or_ignore:>16} | {s.autoincrement:>13} | {s.collate_nocase:>14} | "
            f"{s.lastrowid_uses:>9} | {s.rowcount_uses:>8} | {s.cte_count:>3} | "
            f"{s.window_func_count:>4} | {s.executemany_count:>11} | {s.dangerous_literals:>13} |"
        )
        totals.sql_calls        += s.sql_calls
        totals.q_placeholders   += s.q_placeholders
        totals.insert_or_ignore += s.insert_or_ignore
        totals.autoincrement    += s.autoincrement
        totals.collate_nocase   += s.collate_nocase
        totals.lastrowid_uses   += s.lastrowid_uses
        totals.rowcount_uses    += s.rowcount_uses
        totals.cte_count        += s.cte_count
        totals.window_func_count += s.window_func_count
        totals.executemany_count += s.executemany_count
        totals.dangerous_literals += s.dangerous_literals

    s = totals
    lines.append(
        f"| **{s.path:<{col_w-4}}** | **{s.sql_calls}** | **{s.q_placeholders}** | "
        f"**{s.insert_or_ignore}** | **{s.autoincrement}** | **{s.collate_nocase}** | "
        f"**{s.lastrowid_uses}** | **{s.rowcount_uses}** | **{s.cte_count}** | "
        f"**{s.window_func_count}** | **{s.executemany_count}** | **{s.dangerous_literals}** |"
    )
    lines.append("")

    # ── Column legend ──
    lines.append("### Column Legend")
    lines.append("")
    lines.append("| Column | Meaning | DB-001 Action |")
    lines.append("| ------ | ------- | ------------- |")
    lines.append("| `?` total | Count of positional `?` placeholders | Replace with `:p0`, `:p1`, … native PostgreSQL named params via SQLAlchemy `text()` |")
    lines.append("| INSERT OR IGNORE | SQLite idiom | Replace with `INSERT … ON CONFLICT DO NOTHING` (already in shim; target: inline in SQL text) |")
    lines.append("| AUTOINCREMENT | SQLite DDL keyword | Remove from DDL; PostgreSQL uses `BIGSERIAL` (already done in `alembic/schema/baseline.sql`) |")
    lines.append("| COLLATE NOCASE | SQLite collation | Replace with `LOWER(col) = LOWER(?)` or `ILIKE` |")
    lines.append("| lastrowid | Python attribute on cursor | Ensure `RETURNING id` is present on all INSERT into `_ID_TABLES`; shim injects it today |")
    lines.append("| rowcount | Python attribute on cursor | Verify semantics: PG rowcount after `INSERT OR IGNORE` → ON CONFLICT DO NOTHING is 0 on conflict |")
    lines.append("| CTE | `WITH … SELECT` pattern | No change needed; PostgreSQL supports CTEs natively |")
    lines.append("| OVER | Window function | No change needed; PostgreSQL supports window functions natively |")
    lines.append("| executemany | Batch insert/update | Keep as-is; verify `RETURNING` not needed (executemany ignores lastrowid today) |")
    lines.append("| dangerous `?` | `?` inside a quoted string in SQL | Inspect manually — shim regex replaces ALL `?`, including those inside string literals |")
    lines.append("")

    # ── Migration checklist ──
    lines.append("## DB-001 Migration Checklist")
    lines.append("")
    lines.append("Use this checklist when inlining the shim transformations into the SQL callsites.")
    lines.append("")
    lines.append("### Phase 1 — `?` → named parameters")
    lines.append("")
    lines.append("- [ ] For every file in the table above with `?` > 0, replace `?` with "
                 "`:p0`, `:p1`, … (or meaningful names) and pass a `dict` instead of a `tuple`.")
    lines.append("- [x] Remove the `_translate_sql` placeholder-replacement loop (done, 2026-08-30).")
    lines.append("- [ ] Run full pytest suite after each file to catch regressions.")
    lines.append("")
    lines.append("### Phase 2 — INSERT OR IGNORE → ON CONFLICT DO NOTHING")
    lines.append("")
    lines.append("- [ ] Replace every `INSERT OR IGNORE INTO <table>` with "
                 "`INSERT INTO <table> … ON CONFLICT DO NOTHING`.")
    lines.append("- [ ] For tables with a non-PK unique constraint, specify the conflict target: "
                 "`ON CONFLICT (<col>) DO NOTHING`.")
    lines.append("- [x] Remove the `INSERT OR IGNORE` branch (done: shim deleted).")
    lines.append("")
    lines.append("### Phase 3 — RETURNING id / lastrowid")
    lines.append("")
    lines.append("- [ ] For every INSERT into an `_ID_TABLES` member, add `RETURNING id` explicitly.")
    lines.append("- [ ] Remove `_ID_TABLES` and the RETURNING-injection logic from `postgres.py`.")
    lines.append("- [ ] Verify `cursor.lastrowid` is populated correctly via `_cursor_from_result`.")
    lines.append("")
    lines.append("### Phase 4 — COLLATE NOCASE")
    lines.append("")
    if totals.collate_nocase:
        lines.append(f"- [ ] {totals.collate_nocase} occurrence(s) found — replace with `ILIKE` or `LOWER()` comparison.")
    else:
        lines.append("- [x] No `COLLATE NOCASE` found in scanned files — nothing to do.")
    lines.append("")
    lines.append("### Phase 5 — Dangerous `?` inside string literals")
    lines.append("")
    if totals.dangerous_literals:
        lines.append(f"- [ ] {totals.dangerous_literals} SQL string literal(s) contain `?` — inspect each manually "
                     "to ensure the shim did not corrupt intent (e.g., JSON pattern matching).")
    else:
        lines.append("- [x] No dangerous `?`-in-literal found.")
    lines.append("")
    lines.append("### Phase 6 — executemany + rowcount semantics")
    lines.append("")
    lines.append("- [ ] Confirm all `executemany` callers do NOT rely on `lastrowid` "
                 "(shim already returns `None` for `executemany`).")
    lines.append("- [ ] After ON CONFLICT DO NOTHING migration, verify that `rowcount == 0` on "
                 "a conflicting INSERT is handled gracefully (seed.py uses `cur.rowcount or 0`).")
    lines.append("")

    # ── Files with findings ──
    lines.append("## Detailed Findings")
    lines.append("")
    for s in stats_list:
        interesting = (
            s.insert_or_ignore or s.collate_nocase or s.autoincrement
            or s.lastrowid_uses or s.dangerous_literals or s.cte_count
            or s.window_func_count
        )
        if not interesting:
            continue
        lines.append(f"### `{s.path}`")
        lines.append("")
        if s.insert_or_ignore:
            lines.append(f"- **INSERT OR IGNORE**: {s.insert_or_ignore} occurrence(s)")
        if s.lastrowid_uses:
            lines.append(f"- **lastrowid**: {s.lastrowid_uses} usage(s) — ensure RETURNING id is explicit post-migration")
        if s.collate_nocase:
            lines.append(f"- **COLLATE NOCASE**: {s.collate_nocase} — replace with ILIKE")
        if s.autoincrement:
            lines.append(f"- **AUTOINCREMENT**: {s.autoincrement} — not used in PG (BIGSERIAL already)")
        if s.dangerous_literals:
            lines.append(f"- **Dangerous `?` in literals**: {s.dangerous_literals} — manual review needed")
        if s.cte_count:
            lines.append(f"- **CTE (WITH)**: {s.cte_count} — compatible with PostgreSQL, no change needed")
        if s.window_func_count:
            lines.append(f"- **Window functions (OVER)**: {s.window_func_count} — compatible with PostgreSQL, no change needed")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stdout", action="store_true",
                        help="Print report to stdout only, skip writing file")
    args = parser.parse_args()

    files = _collect_files()
    if not files:
        print("ERROR: no files found to scan", file=sys.stderr)
        sys.exit(1)

    stats_list: list[FileStats] = []
    for f in files:
        stats_list.append(_scan_file(f))

    report = _build_report(stats_list)

    if args.stdout:
        print(report)
    else:
        out_path = ROOT / "docs" / "SQL_SHIM_INVENTORY.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"Report written to {out_path.relative_to(ROOT)}")
        # Also print a brief summary
        totals_q = sum(s.q_placeholders for s in stats_list)
        totals_ioi = sum(s.insert_or_ignore for s in stats_list)
        totals_lr = sum(s.lastrowid_uses for s in stats_list)
        print(f"Scanned {len(stats_list)} files: "
              f"{totals_q} ?-placeholders, "
              f"{totals_ioi} INSERT OR IGNORE, "
              f"{totals_lr} lastrowid uses")


if __name__ == "__main__":
    main()
