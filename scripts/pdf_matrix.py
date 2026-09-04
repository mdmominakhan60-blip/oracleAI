"""Generate and validate the PDF visual-regression matrix outside the source tree.

Usage::

    python -m scripts.pdf_matrix --out /tmp/oracleai-pdf-matrix

The output directory is intentionally external to the repository. The harness
writes one HTML/PDF artifact per case plus a machine-readable summary, so a
release candidate can attach rendered pages without polluting source control.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pdfgen import builder, render


@dataclass(frozen=True)
class MatrixCase:
    code: str
    name: str
    birth_date: str
    birth_time: str | None
    birth_city: str | None
    lang: str
    lat: float | None = None
    lon: float | None = None
    tz: str = "Europe/Moscow"


CASES = (
    MatrixCase("ru-exact", "Анна", "1990-06-21", "14:30", "Казань", "ru"),
    MatrixCase("en-exact", "Anna", "1990-06-21", "14:30", "Kazan", "en"),
    MatrixCase("ru-date-only", "Анна", "1990-06-21", None, "Казань", "ru"),
    MatrixCase("en-date-only", "Anna", "1990-06-21", None, "Kazan", "en"),
    MatrixCase(
        "ru-long-fields",
        "Анна-Мария с очень длинным именем для проверки переноса строк",
        "1988-01-15",
        "00:05",
        "Казань — очень длинное название района и города",
        "ru",
        55.79,
        49.12,
    ),
    MatrixCase(
        "en-edge-latitude",
        "Anna Longyearbyen",
        "2001-12-31",
        "23:59",
        "Longyearbyen",
        "en",
        78.2232,
        15.6469,
        "Arctic/Longyearbyen",
    ),
)

FORBIDDEN_COMMON = ("undefined", "None", "[object Object]")


async def _resolve_city(city: str, *_args, **_kwargs):
    """Use deterministic fixture coordinates; the matrix must not depend on DNS."""
    normalized = (city or "").casefold()
    if "longyearbyen" in normalized:
        return 78.2232, 15.6469, "Arctic/Longyearbyen"
    return 55.79, 49.12, "Europe/Moscow"


def _validate_html(case: MatrixCase, html: str) -> list[str]:
    errors: list[str] = []
    if f'<html lang="{case.lang}">' not in html:
        errors.append("wrong html language")
    for token in FORBIDDEN_COMMON:
        if token in html:
            errors.append(f"forbidden token: {token}")
    if case.name not in html:
        errors.append("name missing")
    if case.birth_time:
        if 'class="natal-print-image"' not in html:
            errors.append("exact-time chart image missing")
        if "Куспиды домов" not in html and "House cusps" not in html:
            errors.append("exact-time house section missing")
    else:
        forbidden = (
            "Асцендент в —", "Планеты по домам:", "Сферы жизни: планеты по домам",
            "Ascendant in —", "Planets by house:", "Life areas: planets by houses",
        )
        for token in forbidden:
            if token in html:
                errors.append(f"date-only claim leaked: {token}")
        if "Изображение колеса не строится" not in html and "wheel image is not generated" not in html:
            errors.append("date-only limitation missing")
    if not re.search(r"<h[1-6][^>]*>.*?</h[1-6]>", html, re.S):
        errors.append("no headings")
    return errors


async def run_case(case: MatrixCase, out_dir: Path) -> dict:
    order = builder.Order(
        name=case.name,
        birth_date=case.birth_date,
        birth_time=case.birth_time,
        birth_city=case.birth_city,
        lang=case.lang,
    )
    html = await builder.generate(None, order, concurrency=1)
    errors = _validate_html(case, html)
    html_path = out_dir / f"{case.code}.html"
    html_path.write_text(html, encoding="utf-8")
    output_path = render.render_pdf(html, out_dir / f"{case.code}.pdf")
    return {
        **asdict(case),
        "output": str(output_path),
        "output_type": output_path.suffix.lstrip("."),
        "html_bytes": len(html.encode("utf-8")),
        "errors": errors,
        "status": "pass" if not errors else "fail",
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="OracleAI PDF visual-regression matrix")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original_resolver = builder.geo.resolve_city_async
    builder.geo.resolve_city_async = _resolve_city
    try:
        results = [await run_case(case, args.out) for case in CASES]
    finally:
        builder.geo.resolve_city_async = original_resolver
    summary = {"cases": results, "passed": sum(r["status"] == "pass" for r in results), "total": len(results)}
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] == summary["total"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
