"""Regression contracts for the automatable remainder of the P2 backlog."""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_deleted_palm_reading_scrubs_sensitive_metadata() -> None:
    source = (ROOT / "app/repo/palm.py").read_text(encoding="utf-8")
    for marker in (
        "status='deleted'",
        "image_sha256=NULL",
        "image_size=NULL",
        "analysis_json=NULL",
    ):
        assert marker in source


def test_payment_locale_dictionaries_have_matching_keys() -> None:
    source = (ROOT / "miniapp/js/17-payments.js").read_text(encoding="utf-8")
    match = re.search(
        r"const PAYMENT_I18N = \{\s*ru: \{(.*?)\n\s*\},\s*en: \{(.*?)\n\s*\},",
        source,
        re.S,
    )
    assert match
    key_pattern = r"(?:^|,)\s*([A-Za-z][A-Za-z0-9_]*)\s*:"
    # re.M: ключи в начале строки внутри блока; без него межключевая
    # строка-комментарий ломала разбор (BUS-981: комментарий BUS-635
    # перед includes давал ложный en-only).
    ru_keys = set(re.findall(key_pattern, match.group(1), re.M))
    en_keys = set(re.findall(key_pattern, match.group(2), re.M))
    assert ru_keys == en_keys
    assert {"heroCopy", "paid", "paymentFailed", "pay"} <= ru_keys
