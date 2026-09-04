"""Process-local, thread-safe MediaPipe Hand Landmarker runtime."""
from __future__ import annotations

import io
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from PIL import Image

from .. import palm_vision

ADAPTER_VERSION = "mediapipe-hand-landmarker-v2"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "hand_landmarker.task"
MAX_DETECTION_SIDE = 1280
_LOCK = threading.Lock()
_DETECTOR: Any = None
_DETECTOR_KEY: str | None = None


def _model_path() -> Path:
    configured = os.getenv("ORACLEAI_MEDIAPIPE_MODEL", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_MODEL_PATH


def _empty(status: str, issues: list[str]) -> dict[str, Any]:
    return {
        "version": ADAPTER_VERSION,
        "status": status,
        "hands": [],
        "hand_count": 0,
        "issues": issues[:8],
        "model": "hand_landmarker_full_float16",
    }


def _get_detector(path: Path):
    global _DETECTOR, _DETECTOR_KEY
    key = str(path.resolve())
    with _LOCK:
        if _DETECTOR is not None and _DETECTOR_KEY == key:
            return _DETECTOR
        from mediapipe.tasks import python  # type: ignore[import-not-found]
        from mediapipe.tasks.python import vision  # type: ignore[import-not-found]

        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=key),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.65,
            min_tracking_confidence=0.65,
        )
        detector = vision.HandLandmarker.create_from_options(options)
        _DETECTOR = detector
        _DETECTOR_KEY = key
        return detector


def _landmark(item: Any) -> dict[str, float]:
    return {"x": round(float(item.x), 6), "y": round(float(item.y), 6), "z": round(float(item.z), 6)}


def analyze(image_bytes: bytes, *, model_path: str | None = None) -> dict[str, Any]:
    path = Path(model_path).expanduser() if model_path else _model_path()
    if not image_bytes:
        return _empty("invalid_image", ["image_empty"])
    quality = palm_vision.analyze(image_bytes)
    issues = set(quality.get("issues") or [])
    if quality.get("status") == "invalid_image":
        return _empty("invalid_image", ["image_decode_failed"])
    if quality.get("status") == "reshoot_recommended" and {
        "underexposed", "overexposed", "low_contrast_or_flat_light", "soft_or_blurred_edges",
    } & issues:
        return _empty("quality_limited", ["hand_detection_skipped_for_quality"])
    if not path.is_file():
        return _empty("model_missing", ["mediapipe_model_missing"])

    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            rgb = source.convert("RGB")
            original_width, original_height = rgb.size
            scale = min(1.0, MAX_DETECTION_SIDE / max(original_width, original_height))
            if scale < 1.0:
                rgb = rgb.resize(
                    (max(1, round(original_width * scale)), max(1, round(original_height * scale))),
                    Image.Resampling.LANCZOS,
                )
            detector = _get_detector(path)
            with tempfile.NamedTemporaryFile(suffix=".jpg") as detector_file:
                rgb.save(detector_file, format="JPEG", quality=92, optimize=True)
                detector_file.flush()
                mp_image = __import__("mediapipe").Image.create_from_file(detector_file.name)
                # MediaPipe Tasks Python bindings are not documented as concurrent;
                # serialize calls through the same lock used for model lifecycle.
                with _LOCK:
                    detected = detector.detect(mp_image)

        hands: list[dict[str, Any]] = []
        for index, landmarks in enumerate(detected.hand_landmarks):
            points = [_landmark(point) for point in landmarks]
            xs = [point["x"] for point in points]
            ys = [point["y"] for point in points]
            handedness = "unknown"
            score = None
            if index < len(detected.handedness) and detected.handedness[index]:
                category = detected.handedness[index][0]
                handedness = str(getattr(category, "category_name", None) or "unknown").lower()
                raw_score = getattr(category, "score", None)
                score = round(float(raw_score), 4) if raw_score is not None else None
            hands.append({
                "index": index,
                "handedness": handedness,
                "handedness_score": score,
                "landmarks": points,
                "landmark_count": len(points),
                "normalized_bbox": {
                    "x_min": round(min(xs), 6), "y_min": round(min(ys), 6),
                    "x_max": round(max(xs), 6), "y_max": round(max(ys), 6),
                },
            })
        return {
            "version": ADAPTER_VERSION,
            "status": "multiple_hands" if len(hands) > 1 else ("detected" if hands else "no_hand"),
            "hands": hands,
            "hand_count": len(hands),
            "issues": ["multiple_hands_in_frame"] if len(hands) > 1 else ([] if hands else ["hand_not_detected"]),
            "model": "hand_landmarker_full_float16",
            "model_key": str(path.resolve()),
            "image_size": {"width": original_width, "height": original_height},
        }
    except ImportError:
        return _empty("unavailable", ["mediapipe_not_installed"])
    except Exception:
        return _empty("runtime_error", ["mediapipe_runtime_error"])
