from __future__ import annotations

import ast
from pathlib import Path

from scripts.seed_load import _rows


ROOT = Path(__file__).resolve().parents[1]


def test_committed_qa_scripts_are_syntax_valid_and_data_safe():
    required_markers = {
        "load_test_api.py": ("synthetic", "production"),
        "telegram_webview_qa.py": ("safe-area", "visualviewport"),
        "summarize_palm_quality.py": ("ground-truth", "semantic_ground_truth_available"),
    }
    for name, markers in required_markers.items():
        path = ROOT / "scripts" / name
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        assert "/tmp/oracle.db" not in source
        lowered = source.lower()
        assert all(marker in lowered for marker in markers), name


def test_seed_load_full_http_profile_is_explicit_and_deterministic():
    rows = _rows(4, all_active=True,
                 active_subscription=True, force_onboarded=True)
    assert len(rows) == 4
    assert all(row[14] == 1 for row in rows)  # onboarded
    assert all(row[11] == "vip" for row in rows)
    assert all(row[20] == "active" for row in rows)
    assert [row[0] for row in rows] == [100_000_000 + i for i in range(4)]


def test_palm_summary_has_explicit_semantic_ground_truth_gate():
    source = (ROOT / "scripts" / "summarize_palm_quality.py").read_text(encoding="utf-8")
    assert "semantic_ground_truth_available" in source
    assert "semantic_precision_recall_f1_iou" in source
    assert "annotated" in source.lower()
