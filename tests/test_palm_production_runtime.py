from __future__ import annotations

import io

from PIL import Image

from app.core.palm import production


def _image_bytes(size=(900, 700), fmt="PNG"):
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            value = (x * 13 + y * 7) % 256
            pixels[x, y] = (value, (value * 3) % 256, (255 - value))
    out = io.BytesIO()
    image.save(out, format=fmt)
    return out.getvalue()


def test_canonical_image_contract_normalizes_to_jpeg_and_preserves_original_dimensions(monkeypatch):
    calls = {"count": 0}

    def precheck(_image):
        calls["count"] += 1
        return {"status": "usable", "score": 0.91, "issues": []}

    monkeypatch.setattr(production, "_ORIGINAL_PRECHECK", precheck)
    production.reset_request_cache()
    raw = _image_bytes((1800, 1000), "PNG")
    item = production.canonicalize(raw, "image/png")

    assert item.mime == "image/jpeg"
    assert item.format == "JPEG"
    assert item.original_width == 1800
    assert item.original_height == 1000
    assert max(item.width, item.height) == production.CANONICAL_MAX_SIDE
    assert item.raw_sha256
    assert item.normalized_sha256
    assert calls["count"] == 1

    production.cached_precheck(item.normalized_bytes)
    assert calls["count"] == 1


def test_canonical_image_rejects_unsupported_document_mime():
    try:
        production.canonicalize(_image_bytes(), "application/pdf")
    except ValueError as exc:
        assert "JPEG" in str(exc)
    else:
        raise AssertionError("unsupported mime must be rejected")


def test_adaptive_lines_do_not_run_int8_for_stable_fp16(monkeypatch):
    calls = []
    original = production._adaptive_original

    def stable_analyze(_image, *, model_path=None):
        calls.append(model_path)
        model = "palm_line_student_fp16.onnx" if model_path is None else "palm_line_student_int8.onnx"
        return {
            "status": "detected",
            "model": model,
            "lines": {
                "heart_line": {"detected": True, "confidence": 0.9, "bbox": {"x_min": 10, "y_min": 10, "x_max": 100, "y_max": 100}},
                "head_line": {"detected": False, "confidence": 0.8, "bbox": None},
                "life_line": {"detected": False, "confidence": 0.8, "bbox": None},
            },
        }

    monkeypatch.setattr(production, "_adaptive_original", lambda: (stable_analyze, {1: "heart_line", 2: "head_line", 3: "life_line"}, lambda a, b: 1.0))
    result = production.adaptive_line_ensemble(b"image")
    monkeypatch.setattr(production, "_adaptive_original", original)

    assert result["ensemble"]["status"] == "fp16_stable"
    assert calls == [None]


def test_error_taxonomy_distinguishes_vision_schema_failure_from_photo_failure():
    good = {
        "status": "needs_photo",
        "visual_precheck": {"status": "usable", "score": 0.9, "issues": []},
        "computer_vision": {"hand_geometry": {"status": "detected"}},
        "safety_flags": ["vision_json_invalid"],
    }
    assert production.classify_result(good) == production.VISION_SCHEMA_INVALID

    bad = {
        "status": "needs_photo",
        "visual_precheck": {"status": "reshoot_recommended", "score": 0.2, "issues": ["underexposed"]},
        "computer_vision": {},
        "safety_flags": [],
    }
    assert production.classify_result(bad) == production.PHOTO_LOW_QUALITY
