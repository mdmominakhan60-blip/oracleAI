from __future__ import annotations

from pathlib import Path

from app.core import palm_evidence, palm_landmarks

FIXTURE = Path(__file__).parent / "fixtures" / "palm" / "palm_hand.jpg"


def _geometry():
    points = [{"x": 0.24 + (index % 5) * 0.12,
               "y": 0.18 + (index // 5) * 0.15} for index in range(21)]
    return {"status": "detected", "hand_count": 1,
            "hands": [{"landmarks": points}]}


def test_prepare_views_returns_bounded_in_memory_hand_roi_without_raw_storage():
    image = FIXTURE.read_bytes()
    metadata, urls = palm_evidence.prepare_views(
        image, hand_geometry=_geometry(), view_type="folded_edge"
    )
    assert metadata["status"] == "ready"
    assert metadata["view_count"] == 2
    assert [view["role"] for view in metadata["views"]] == ["major_lines", "folded_edge_zones"]
    assert all(url.startswith("data:image/jpeg;base64,") for url in urls)
    assert metadata["raw_views_stored"] is False
    assert "palm_edge_map" not in metadata


def test_prepare_views_does_not_create_folded_edge_claim_for_open_palm():
    image = FIXTURE.read_bytes()
    hand = palm_landmarks.analyze(image)
    metadata, urls = palm_evidence.prepare_views(
        image, hand_geometry=hand, view_type="open_palm"
    )
    assert metadata["status"] == "ready"
    assert metadata["view_count"] == 1
    assert metadata["views"][0]["role"] == "major_lines"
    assert len(urls) == 1
    assert metadata["raw_views_stored"] is False


def test_prepare_views_adds_mounts_focus_for_open_palm_with_hand_box():
    image = FIXTURE.read_bytes()
    metadata, urls = palm_evidence.prepare_views(
        image, hand_geometry=_geometry(), view_type="open_palm"
    )
    assert metadata["status"] == "ready"
    assert metadata["view_count"] == 2
    assert [v["role"] for v in metadata["views"]] == ["major_lines", "mounts"]
    assert len(urls) == 2
    assert metadata["raw_views_stored"] is False
