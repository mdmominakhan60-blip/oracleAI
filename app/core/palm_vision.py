"""Deterministic, privacy-safe preflight metrics for palm images.

This module does not claim to detect a hand or interpret palm lines. It scores
capture conditions only, so the multimodal model receives measurable context and
the user can see why a reshoot is requested. Raw pixels never leave this module.
"""
from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageFilter, ImageOps, ImageStat, UnidentifiedImageError

PRECHECK_VERSION = "palm-precheck-v1"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return round(max(low, min(high, value)), 3)


def analyze(image: bytes) -> dict[str, Any]:
    """Return bounded capture metrics; never infer hand presence or palm lines."""
    try:
        with Image.open(io.BytesIO(image)) as original:
            original.verify()
        with Image.open(io.BytesIO(image)) as original:
            frame = ImageOps.exif_transpose(original).convert("RGB")
            width, height = frame.size
            gray = frame.convert("L")
            brightness = ImageStat.Stat(gray).mean[0]
            contrast = ImageStat.Stat(gray).stddev[0]
            edges = gray.filter(ImageFilter.FIND_EDGES)
            edge_mean = ImageStat.Stat(edges).mean[0]
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return {
            "version": PRECHECK_VERSION,
            "status": "invalid_image",
            "score": 0.0,
            "issues": ["image_decode_failed"],
            "error_type": type(exc).__name__,
            "hand_detection": "not_attempted",
            "line_segmentation": "not_attempted",
        }

    aspect = width / max(height, 1)
    # A palm can be portrait or landscape; only extreme banner/square crops are
    # suspicious. This is a capture heuristic, not a hand detector.
    aspect_score = 1.0 if 0.45 <= aspect <= 1.8 else 0.55 if 0.3 <= aspect <= 2.4 else 0.2
    brightness_score = _clamp(1.0 - abs(brightness - 128.0) / 128.0)
    contrast_score = _clamp((contrast - 24.0) / 82.0)
    sharpness_score = _clamp((edge_mean - 12.0) / 42.0)
    score = _clamp(
        0.25 * aspect_score + 0.3 * brightness_score +
        0.25 * contrast_score + 0.2 * sharpness_score
    )
    issues = []
    if min(width, height) < 480:
        issues.append("low_resolution")
    if brightness < 35:
        issues.append("underexposed")
    elif brightness > 225:
        issues.append("overexposed")
    if contrast < 24:
        issues.append("low_contrast_or_flat_light")
    if edge_mean < 12:
        issues.append("soft_or_blurred_edges")
    if aspect < 0.3 or aspect > 2.4:
        issues.append("extreme_crop_or_aspect")
    return {
        "version": PRECHECK_VERSION,
        "status": "usable" if score >= 0.55 and not {
            "underexposed", "overexposed", "low_contrast_or_flat_light",
            "soft_or_blurred_edges",
        } & set(issues) else "reshoot_recommended",
        "score": score,
        "issues": issues,
        "width": width,
        "height": height,
        "aspect": round(aspect, 3),
        "brightness": round(brightness, 1),
        "contrast": round(contrast, 1),
        "edge_mean": round(edge_mean, 1),
        "hand_detection": "not_attempted",
        "line_segmentation": "not_attempted",
    }
