from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UTILS = (ROOT / "miniapp/js/01-utils.js").read_text(encoding="utf-8")
CHART = (ROOT / "miniapp/js/10-chart.js").read_text(encoding="utf-8")
MISC = (ROOT / "miniapp/js/12-misc.js").read_text(encoding="utf-8")
CSS = (ROOT / "miniapp/css/15-ritual-redesign.css").read_text(encoding="utf-8")

REQUIRED_KEYS = (
    "provenanceTitle",
    "provenanceSummary",
    "provenanceProduct",
    "provenanceBackend",
    "provenanceVersion",
    "provenanceEphemeris",
    "provenanceLicense",
    "provenanceLicenseCopy",
    "provenanceUnavailable",
    "provenanceFallback",
)


def assert_all(text: str, needles: tuple[str, ...], label: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        raise SystemExit(f"{label}: missing {', '.join(missing)}")


# The RU and EN dictionaries are kept in the same file. Each key must occur twice.
for key in REQUIRED_KEYS:
    occurrences = UTILS.count(f"{key}:")
    if occurrences != 2:
        raise SystemExit(f"localization parity: {key} occurs {occurrences} times, expected 2")

assert_all(
    CHART,
    (
        "app.chartProvenanceHtml = function(c)",
        "c.engine_provenance",
        "c.calculation && c.calculation.engine_provenance",
        "esc(label)",
        "esc(item)",
        "profileT('provenanceTitle')",
        "profileT('provenanceFallback')",
        "profileT('provenanceLicenseCopy')",
        "value('license_notice') ? profileT('provenanceLicenseCopy') : ''",
    ),
    "chat provenance helper",
)
if CHART.count("${this.chartProvenanceHtml(c)}") != 1:
    raise SystemExit("chat chart surface: expected one provenance render")

assert_all(MISC, ("${this.chartProvenanceHtml(c)}", "profileFormat('ascendant'"), "full chart provenance render")
if "${esc(profileT('ascendant'))}" in MISC or "{sign}" in MISC:
    raise SystemExit("full chart surface: unresolved localization placeholder")
assert_all(
    CSS,
    (
        ".chart-provenance",
        ".chart-provenance summary",
        ".chart-provenance[open] .chart-provenance__chevron",
        ".chart-provenance__row",
        ".chart-provenance__fallback",
        "prefers-reduced-motion",
    ),
    "provenance CSS",
)
print("Frontend provenance contract check passed")
