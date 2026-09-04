from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw

from app.core import palm_full_scope, palm_landmarks, palm_lines, palm_vision


def _image_bytes(kind: str) -> bytes:
    image = Image.new("RGB", (640, 640), "gray" if kind == "flat" else "white")
    if kind == "checker":
        draw = ImageDraw.Draw(image)
        for row in range(0, 640, 40):
            for col in range(0, 640, 40):
                if (row // 40 + col // 40) % 2:
                    draw.rectangle((col, row, col + 39, row + 39), fill="black")
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()



def test_full_scope_catalogs_all_line_zones_and_requires_vision_adjudication():
    fixture = (Path(__file__).parent / "fixtures" / "palm" / "palm_hand.jpg").read_bytes()
    hand = palm_landmarks.analyze(fixture)
    result = palm_full_scope.analyze(fixture, hand_geometry=hand)
    assert result["version"] == "palm-full-scope-cv-v1"
    assert len(result["line_catalog"]) == 16
    assert {"fate_line", "mercury_line", "girdle_of_venus", "ring_of_solomon", "mars_lines"}.issubset(result["line_catalog"])
    assert set(result["zone_evidence"]) >= {"mounts", "fingers", "markings", "relationship_lines", "travel_lines"}
    assert all(item["semantic_labeling"] == "vision_llm" for item in result["zone_evidence"].values())
    assert result["raw_edge_map_stored"] is False
    assert result["raw_mask_stored"] is False


def test_onnx_ensemble_returns_explicit_model_agreement_and_no_raw_masks():
    fixture = (Path(__file__).parent / "fixtures" / "palm" / "palm_hand.jpg").read_bytes()
    result = palm_lines.analyze_ensemble(fixture)
    assert result["model"] == "palm_line_student_int8.onnx"
    assert result["status"] in {"detected", "no_lines"}
    assert result["ensemble"]["raw_masks_stored"] is False
    assert set(result["lines"]) == {"heart_line", "head_line", "life_line"}
    assert all("ensemble_agreement" in item for item in result["lines"].values())


def test_precheck_rejects_invalid_image_without_guessing():
    result = palm_vision.analyze(b"not-an-image")
    assert result["status"] == "invalid_image"
    assert result["score"] == 0.0
    assert result["hand_detection"] == "not_attempted"


def test_precheck_flags_flat_capture():
    result = palm_vision.analyze(_image_bytes("flat"))
    assert result["status"] == "reshoot_recommended"
    assert "low_contrast_or_flat_light" in result["issues"]
    assert result["line_segmentation"] == "not_attempted"


def test_precheck_produces_bounded_metrics_for_usable_capture():
    result = palm_vision.analyze(_image_bytes("checker"))
    assert result["status"] == "usable"
    assert 0.0 <= result["score"] <= 1.0
    assert result["width"] == 640 and result["height"] == 640
    assert 0.0 <= result["brightness"] <= 255.0
    assert result["version"] == "palm-precheck-v1"
