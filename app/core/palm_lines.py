"""Optional palm-crease segmentation evidence adapter.

The vendored model is an auxiliary computer-vision signal only. It does not
interpret palmistry, personality, health, relationships or future events.
Missing dependencies, model files and runtime failures are explicit non-fatal
statuses so Mira can ask for a better photo or fall back to multimodal vision.
"""
from __future__ import annotations

import hashlib
import io
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from . import palm_vision

ADAPTER_VERSION = "palm-line-onnx-evidence-v1"
MODEL_FILENAME = "palm_line_student_fp16.onnx"
MODEL_CHECKSUMS = {
    "e2c9f826676b3aaf0a715f3087fcd4fc0b4dccd8c53de05fd26696a8399f8dd6": "palm_line_student_fp16.onnx",
    "14bcf11d75c790ac0c147f3335b2772d53bc558e8af54aaadc7a148f8cf8db0c": "palm_line_student_int8.onnx",
}
INPUT_SIZE = 512
CLASS_NAMES = {1: "heart_line", 2: "head_line", 3: "life_line"}
MIN_LINE_PIXELS = 80


def _enabled() -> bool:
    return os.getenv("ORACLEAI_PALM_LINE_ENABLED", "1").strip().lower() not in {
        "0", "false", "off", "no",
    }


def _model_path() -> Path:
    configured = os.getenv("ORACLEAI_PALM_LINE_MODEL", "").strip()
    return Path(configured).expanduser() if configured else (
        Path(__file__).resolve().parents[2] / "models" / MODEL_FILENAME
    )


def _empty(status: str, issues: list[str], *, model_path: Path | None = None) -> dict[str, Any]:
    # `model_path` is accepted internally for call-site clarity but never exposed.
    del model_path
    return {
        "version": ADAPTER_VERSION,
        "status": status,
        "model": MODEL_FILENAME,
        "classes": list(CLASS_NAMES.values()),
        "lines": {},
        "issues": issues[:8],
        "raw_mask_stored": False,
    }


def _preprocess(image_bytes: bytes) -> tuple[Any, tuple[int, int]]:
    import numpy as np

    with Image.open(io.BytesIO(image_bytes)) as source:
        frame = ImageOps.exif_transpose(source).convert("RGB")
        original_size = frame.size
        frame = frame.resize((INPUT_SIZE, INPUT_SIZE), Image.Resampling.BILINEAR)
        pixels = np.asarray(frame, dtype=np.float32) / 255.0
    mean = np.asarray([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.asarray([0.229, 0.224, 0.225], dtype=np.float32)
    chw = ((pixels - mean) / std).transpose(2, 0, 1)[None, ...]
    return chw, original_size


@lru_cache(maxsize=2)
def _session(path: str):
    import onnxruntime as ort

    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])


def _line_summary(mask, probabilities, class_index: int) -> dict[str, Any]:
    import cv2
    import numpy as np

    selected = mask == class_index
    count = int(selected.sum())
    if count == 0:
        return {
            "detected": False,
            "coverage": 0.0,
            "confidence": 0.0,
            "bbox": None,
        }
    ys, xs = np.where(selected)
    selected_u8 = selected.astype(np.uint8)
    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(selected_u8, 8)
    component_areas = stats[1:, cv2.CC_STAT_AREA] if component_count > 1 else np.asarray([], dtype=np.int32)
    largest_component_ratio = (float(component_areas.max()) / float(count)
                               if component_areas.size else 0.0)
    top_two = np.partition(probabilities[:, selected], -2, axis=0)[-2:]
    confidence = float(probabilities[class_index][selected].mean())
    margin = float((top_two[-1] - top_two[-2]).mean()) if top_two.size else 0.0
    return {
        "detected": count >= MIN_LINE_PIXELS,
        "pixel_count": count,
        "coverage": round(count / float(mask.size), 6),
        "confidence": round(max(0.0, min(1.0, confidence)), 4),
        "confidence_margin": round(max(0.0, min(1.0, margin)), 4),
        "component_count": max(0, int(component_count - 1)),
        "largest_component_ratio": round(max(0.0, min(1.0, largest_component_ratio)), 4),
        "bbox": {
            "x_min": int(xs.min()),
            "y_min": int(ys.min()),
            "x_max": int(xs.max()),
            "y_max": int(ys.max()),
        },
    }


def _bbox_iou(first: dict[str, Any] | None, second: dict[str, Any] | None) -> float:
    if not first or not second:
        return 0.0
    left = max(first.get("x_min", 0), second.get("x_min", 0))
    top = max(first.get("y_min", 0), second.get("y_min", 0))
    right = min(first.get("x_max", 0), second.get("x_max", 0))
    bottom = min(first.get("y_max", 0), second.get("y_max", 0))
    intersection = max(0, right - left + 1) * max(0, bottom - top + 1)
    area_first = max(0, first.get("x_max", 0) - first.get("x_min", 0) + 1) * max(0, first.get("y_max", 0) - first.get("y_min", 0) + 1)
    area_second = max(0, second.get("x_max", 0) - second.get("x_min", 0) + 1) * max(0, second.get("y_max", 0) - second.get("y_min", 0) + 1)
    union = area_first + area_second - intersection
    return intersection / union if union else 0.0


def analyze_ensemble(image_bytes: bytes, *, view_type: str | None = None) -> dict[str, Any]:
    """Fuse both ONNX variants conservatively; skip open-line model off-domain views."""
    if view_type == "folded_edge":
        return {
            "version": ADAPTER_VERSION,
            "status": "not_applicable",
            "model": "fp16_int8_ensemble",
            "models": [MODEL_FILENAME, "palm_line_student_int8.onnx"],
            "lines": {},
            "ensemble": {
                "status": "out_of_domain",
                "disagreements": [],
                "raw_masks_stored": False,
            },
            "limitations": [
                "Principal-line ONNX model is not applied to folded-edge geometry.",
                "Use full-scope candidate evidence and folded-edge vision views for this capture.",
            ],
            "raw_mask_stored": False,
        }
    fp16 = analyze(image_bytes)
    int8 = analyze(image_bytes, model_path=str(Path(__file__).resolve().parents[2] / "models" / "palm_line_student_int8.onnx"))
    if fp16.get("status") in {"invalid_image", "model_missing", "model_integrity_error", "unavailable", "runtime_error"}:
        return {**fp16, "ensemble": {"status": "fallback_single_model", "models": [fp16.get("model")]}}
    if int8.get("status") in {"invalid_image", "model_missing", "model_integrity_error", "unavailable", "runtime_error"}:
        return {**fp16, "ensemble": {"status": "fallback_single_model", "models": [fp16.get("model"), int8.get("model")]}}
    lines: dict[str, Any] = {}
    disagreements = []
    for name in CLASS_NAMES.values():
        first = (fp16.get("lines") or {}).get(name) or {}
        second = (int8.get("lines") or {}).get(name) or {}
        same_detected = bool(first.get("detected")) == bool(second.get("detected"))
        iou = _bbox_iou(first.get("bbox"), second.get("bbox")) if first.get("bbox") and second.get("bbox") else 0.0
        stable = bool(first.get("detected")) and bool(second.get("detected")) and iou >= 0.35
        if not same_detected or (first.get("detected") and second.get("detected") and iou < 0.35):
            disagreements.append(name)
        combined = dict(first)
        combined["detected"] = stable
        combined["ensemble_agreement"] = name not in disagreements
        combined["bbox_iou_fp16_int8"] = round(iou, 4)
        combined["confidence"] = round(min(float(first.get("confidence", 0)), float(second.get("confidence", 0))), 4)
        lines[name] = combined
    status = "needs_vision_review" if disagreements else ("detected" if any(item["detected"] for item in lines.values()) else "no_lines")
    return {
        "version": ADAPTER_VERSION,
        "status": status,
        "model": "fp16_int8_ensemble",
        "models": [fp16.get("model"), int8.get("model")],
        "model_sha256": fp16.get("model_sha256"),
        "input_size": fp16.get("input_size"),
        "image_size": fp16.get("image_size"),
        "precheck": fp16.get("precheck") or {},
        "lines": lines,
        "ensemble": {
            "status": "agreement" if not disagreements else "disagreement",
            "disagreements": disagreements,
            "raw_masks_stored": False,
        },
        "limitations": [
            "Auxiliary ensemble evidence only; not a palmistry interpretation.",
            "A model disagreement lowers trust and requires image-level vision adjudication.",
            "Model covers heart/head/life lines only; other zones require full-scope evidence and vision review.",
        ],
        "raw_mask_stored": False,
    }


def analyze(image_bytes: bytes, *, model_path: str | None = None) -> dict[str, Any]:
    """Return bounded line-segmentation evidence; never persist or return a mask."""
    path = Path(model_path).expanduser() if model_path else _model_path()
    if not _enabled():
        return _empty("disabled", ["palm_line_engine_disabled"], model_path=path)
    if not image_bytes:
        return _empty("invalid_image", ["image_empty"], model_path=path)
    precheck = palm_vision.analyze(image_bytes)
    if precheck.get("status") == "invalid_image":
        return _empty("invalid_image", ["image_decode_failed"], model_path=path)
    if not path.is_file():
        return _empty("model_missing", ["palm_line_model_missing"], model_path=path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        model_name = MODEL_CHECKSUMS.get(digest)
        if model_name is None:
            return _empty("model_integrity_error", ["palm_line_model_checksum_mismatch"], model_path=path)
        tensor, original_size = _preprocess(image_bytes)
        session = _session(str(path))
        input_name = session.get_inputs()[0].name
        output_name = session.get_outputs()[0].name
        outputs = session.run([output_name], {input_name: tensor})
        logits = outputs[0]
        import numpy as np

        if getattr(logits, "shape", ()) != (1, 4, INPUT_SIZE, INPUT_SIZE):
            return _empty("invalid_output", ["palm_line_model_shape_unexpected"], model_path=path)
        logits = np.asarray(logits, dtype=np.float32)[0]
        shifted = logits - logits.max(axis=0, keepdims=True)
        probabilities = np.exp(shifted)
        probabilities /= probabilities.sum(axis=0, keepdims=True).clip(min=1e-8)
        mask = logits.argmax(axis=0)
        lines = {name: _line_summary(mask, probabilities, index)
                 for index, name in CLASS_NAMES.items()}
        detected_count = sum(1 for item in lines.values() if item["detected"])
        return {
            "version": ADAPTER_VERSION,
            "status": "detected" if detected_count else "no_lines",
            "model": model_name,
            "model_sha256": digest,
            "input_size": [INPUT_SIZE, INPUT_SIZE],
            "image_size": {"width": original_size[0], "height": original_size[1]},
            "precheck": {
                "score": precheck.get("score", 0.0),
                "issues": precheck.get("issues") or [],
            },
            "lines": lines,
            "limitations": [
                "Auxiliary segmentation evidence only; not a palmistry interpretation.",
                "Model covers heart/head/life lines only; folded-edge relationship, children and travel lines are not covered.",
                "Validate on OracleAI’s consented capture distribution before making confidence claims.",
            ],
            "raw_mask_stored": False,
        }
    except (UnidentifiedImageError, OSError, ValueError):
        return _empty("invalid_image", ["image_decode_failed"], model_path=path)
    except ImportError:
        return _empty("unavailable", ["onnxruntime_not_installed"], model_path=path)
    except Exception:
        return _empty("runtime_error", ["palm_line_model_runtime_error"], model_path=path)
