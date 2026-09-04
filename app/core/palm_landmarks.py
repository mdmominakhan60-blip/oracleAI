"""Optional MediaPipe hand geometry adapter for Mira.

This module detects hand pose only. It deliberately does not infer palm lines,
health, personality or fate. The adapter is lazy so the existing offline and
image-quality paths remain usable when the optional model/package is absent.
"""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from . import palm_vision

ADAPTER_VERSION = "mediapipe-hand-landmarker-v1"
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "hand_landmarker.task"
MAX_DETECTION_SIDE = 1280
DETECTOR_ATTEMPTS = 2


def _empty(status: str, issues: list[str], *, model_path: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "version": ADAPTER_VERSION,
        "status": status,
        "hands": [],
        "hand_count": 0,
        "issues": issues[:8],
        "model": "hand_landmarker_full_float16",
    }
    return result


def _model_path() -> Path:
    configured = os.getenv("ORACLEAI_MEDIAPIPE_MODEL", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_MODEL_PATH


def _landmark(item: Any) -> dict[str, float]:
    return {
        "x": round(float(item.x), 6),
        "y": round(float(item.y), 6),
        "z": round(float(item.z), 6),
    }


def analyze(image_bytes: bytes, *, model_path: str | None = None) -> dict[str, Any]:
    """Return bounded hand geometry evidence for one still image.

    The provider/model are imported and initialized only when a valid task model
    is available. Any dependency/model/runtime problem becomes an explicit
    non-fatal status, never a fabricated hand result.
    """
    path = Path(model_path).expanduser() if model_path else _model_path()
    if not image_bytes:
        return _empty("invalid_image", ["image_empty"], model_path=str(path))
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            source.verify()
        with Image.open(io.BytesIO(image_bytes)) as source:
            rgb = source.convert("RGB")
            width, height = rgb.size
            # Hand Landmarker does not need full camera resolution. A bounded,
            # owned contiguous array avoids intermittent mp.Image constructor
            # failures on large frames in hosted runners while preserving the
            # original dimensions in the public evidence.
            scale = min(1.0, MAX_DETECTION_SIDE / max(width, height))
            detector_frame = rgb
            if scale < 1.0:
                detector_frame = rgb.resize(
                    (max(1, round(width * scale)), max(1, round(height * scale))),
                    Image.Resampling.LANCZOS,
                )
    except Exception:
        return _empty("invalid_image", ["image_decode_failed"], model_path=str(path))

    # Do not invoke the native detector for a frame that is objectively too flat
    # and soft to support a reliable hand decision. Besides being cheaper, this
    # avoids a MediaPipe 0.10.35 binding failure observed on hosted runners for
    # the same class of macro-texture frames. This is a capture-quality gate, not
    # a claim that the pixels prove absence of a hand.
    precheck = palm_vision.analyze(image_bytes)
    precheck_issues = set(precheck.get("issues") or [])
    # Fail early if the frame is objectively too poor for a reliable hand decision.
    if (precheck.get("status") == "reshoot_recommended" and
        {"low_contrast_or_flat_light", "soft_or_blurred_edges", "underexposed", "overexposed"} & precheck_issues):
        return _empty("quality_limited", ["hand_detection_skipped_for_quality"], model_path=str(path))

    if not path.exists():
        return _empty("model_missing", ["mediapipe_model_missing"], model_path=str(path))
    try:
        import mediapipe as mp  # type: ignore[import-not-found]
        from mediapipe.tasks import python  # type: ignore[import-not-found]
        from mediapipe.tasks.python import vision  # type: ignore[import-not-found]
    except Exception:
        return _empty("unavailable", ["mediapipe_not_installed"], model_path=str(path))
    try:
        base_options = python.BaseOptions(model_asset_path=str(path))
        options = vision.HandLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=0.65,
            min_hand_presence_confidence=0.65,
            min_tracking_confidence=0.65,
        )
        detected = None
        last_runtime_error: Exception | None = None
        # `mp.Image(data=numpy_array)` intermittently raises inside the Python
        # binding on hosted runners and then emits an unsafe __del__ warning.
        # Feeding a temporary JPEG through the supported file constructor avoids
        # that native-buffer lifetime issue. The file is unlinked immediately by
        # the context manager; raw image bytes are never persisted by the app.
        with tempfile.NamedTemporaryFile(suffix=".jpg") as detector_file:
            detector_frame.save(detector_file, format="JPEG", quality=92, optimize=True)
            detector_file.flush()
            for _attempt in range(DETECTOR_ATTEMPTS):
                try:
                    mp_image = mp.Image.create_from_file(detector_file.name)
                    with vision.HandLandmarker.create_from_options(options) as landmarker:
                        detected = landmarker.detect(mp_image)
                    break
                except (RuntimeError, ValueError, TypeError) as exc:
                    last_runtime_error = exc
                    continue
        if detected is None:
            raise last_runtime_error or RuntimeError("mediapipe detection failed")
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
            "issues": (["multiple_hands_in_frame"] if len(hands) > 1
                       else ([] if hands else ["hand_not_detected"])),
            "model": "hand_landmarker_full_float16",
            "image_size": {"width": width, "height": height},
        }
    except Exception:
        # Keep provider internals and image content out of API/log responses.
        return _empty("runtime_error", ["mediapipe_runtime_error"], model_path=str(path))
