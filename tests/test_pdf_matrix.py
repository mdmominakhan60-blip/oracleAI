"""Contract tests for the external PDF visual-regression matrix."""
from __future__ import annotations

from scripts.pdf_matrix import CASES, _validate_html


def test_pdf_matrix_covers_localized_precision_and_long_field_cases():
    codes = {case.code for case in CASES}

    assert {"ru-exact", "en-exact", "ru-date-only", "en-date-only"} <= codes
    assert "ru-long-fields" in codes
    assert "en-edge-latitude" in codes
    assert {case.lang for case in CASES} == {"ru", "en"}
    assert {bool(case.birth_time) for case in CASES} == {True, False}


def test_pdf_matrix_rejects_precision_claims_in_date_only_html():
    case = next(case for case in CASES if case.code == "ru-date-only")
    html = (
        '<html lang="ru"><h1>Разбор</h1>'
        "<p>Асцендент в —</p>"
        "<p>Изображение колеса не строится</p></html>"
    )

    errors = _validate_html(case, html)

    assert any("date-only claim leaked" in error for error in errors)
