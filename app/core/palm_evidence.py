"""Prepare bounded visual evidence views for Mira's semantic adjudicator.

The module creates short-lived JPEG data URLs in memory only. It never returns or
persists masks, edge maps, or source images. The original frame remains the
primary visual source; focus views are auxiliary crops used to make fine creases
and folded-edge zones easier for a vision model to inspect.
"""
from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError

ADAPTER_VERSION = "palm-evidence-views-v1"
MAX_VIEWS = 2
MAX_VIEW_SIDE = 1568
JPEG_QUALITY = 92
MOUNT_CROP_RATIO = 0.60  # upper portion of the hand crop for mount analysis


def _empty(reason: str) -> dict[str, Any]:
    return {
        "version": ADAPTER_VERSION,
        "status": "unavailable",
        "views": [],
        "view_count": 0,
        "issues": [reason],
        "raw_views_stored": False,
    }


def _box_from_landmarks(hand_geometry: dict[str, Any] | None, width: int, height: int) -> tuple[int, int, int, int] | None:
    hands = (hand_geometry or {}).get("hands") or []
    if not hands:
        return None
    points = hands[0].get("landmarks") or []
    if len(points) < 21:
        return None
    xs = [max(0.0, min(1.0, float(point.get("x", 0.0)))) for point in points]
    ys = [max(0.0, min(1.0, float(point.get("y", 0.0)))) for point in points]
    pad_x = 0.10
    pad_y = 0.12
    left = max(0, int((min(xs) - pad_x) * width))
    top = max(0, int((min(ys) - pad_y) * height))
    right = min(width, int((max(xs) + pad_x) * width))
    bottom = min(height, int((max(ys) + pad_y) * height))
    if right - left < 160 or bottom - top < 160:
        return None
    return left, top, right, bottom


def _pinky_edge_side(hand_geometry: dict[str, Any] | None) -> str:
    hands = (hand_geometry or {}).get("hands") or []
    points = hands[0].get("landmarks") if hands else []
    if len(points or []) < 21:
        return "right"
    # MediaPipe: index MCP=5, pinky MCP=17. The side closer to pinky is the
    # relevant edge for relationship/children creases in a folded view.
    return "left" if float(points[17].get("x", 1.0)) < float(points[5].get("x", 0.0)) else "right"


def _encode(frame: Image.Image) -> str:
    frame = ImageOps.exif_transpose(frame).convert("RGB")
    scale = min(1.0, MAX_VIEW_SIDE / max(frame.size))
    if scale < 1.0:
        frame = frame.resize((round(frame.width * scale), round(frame.height * scale)), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    frame.save(out, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def _enhance(frame: Image.Image) -> Image.Image:
    # Conservative deterministic enhancement: preserve geometry, increase local
    # contrast and edge readability; do not hallucinate or inpaint creases.
    image = frame.convert("RGB")
    try:
        import cv2
        import numpy as np
        rgb = np.asarray(image)
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = cv2.cvtColor(cv2.merge((clahe.apply(l_channel), a_channel, b_channel)), cv2.COLOR_LAB2RGB)
        image = Image.fromarray(enhanced)
    except Exception:
        image = ImageEnhance.Contrast(image).enhance(1.18)
    image = ImageEnhance.Sharpness(image).enhance(1.25)
    return image.filter(ImageFilter.UnsharpMask(radius=1.1, percent=115, threshold=3))


def prepare_views(image_bytes: bytes, *, hand_geometry: dict[str, Any] | None = None,
                  view_type: str = "unclear") -> tuple[dict[str, Any], list[str]]:
    """Return metadata and additional data URLs; source bytes are not retained."""
    if not image_bytes:
        return _empty("image_empty"), []
    try:
        with Image.open(io.BytesIO(image_bytes)) as source:
            source.verify()
        with Image.open(io.BytesIO(image_bytes)) as source:
            frame = ImageOps.exif_transpose(source).convert("RGB")
            width, height = frame.size
            hand_box = _box_from_landmarks(hand_geometry, width, height)
            if hand_box is None:
                metadata = {
                    "version": ADAPTER_VERSION,
                    "status": "ready",
                    "views": [{"id": "full_frame_enhanced", "role": "major_lines", "stored": False}],
                    "view_count": 1,
                    "source_image_size": {"width": width, "height": height},
                    "issues": ["hand_geometry_missing"],
                    "raw_views_stored": False,
                    "limitations": [
                        "Hand geometry was unavailable; no folded-edge crop was synthesized.",
                        "The enhanced full frame is a deterministic view and does not infer creases.",
                    ],
                }
                return metadata, [_encode(_enhance(frame))]
            left, top, right, bottom = hand_box
            hand_crop = frame.crop(hand_box)
            edge = _pinky_edge_side(hand_geometry)
            crop_width = max(180, int((right - left) * 0.58))
            if edge == "left":
                edge_box = (left, top, min(right, left + crop_width), bottom)
            else:
                edge_box = (max(left, right - crop_width), top, right, bottom)
            edge_crop = frame.crop(edge_box)
            # The full enhanced crop supports major lines; the edge crop is
            # prioritized for folded-edge-only zones. For an open palm, add a
            # mount-focused crop over the upper palm (finger-base mounts), which
            # a single whole-hand view renders too small to read relief well.
            candidates = [("hand_roi_enhanced", _enhance(hand_crop))]
            if view_type == "folded_edge":
                candidates.append(("pinky_edge_enhanced", _enhance(edge_crop)))
            else:
                mount_h = max(160, int((bottom - top) * MOUNT_CROP_RATIO))
                mount_crop = hand_crop.crop((0, 0, hand_crop.width, mount_h))
                candidates.append(("mounts_focus_enhanced", _enhance(mount_crop)))
            urls = [_encode(image) for _, image in candidates[:MAX_VIEWS]]
            metadata = {
                "version": ADAPTER_VERSION,
                "status": "ready",
                "views": [
                    {"id": name, "role": "mounts" if name.startswith("mounts_") else ("major_lines" if name.startswith("hand_") else "folded_edge_zones"), "stored": False}
                    for name, _ in candidates[:MAX_VIEWS]
                ],
                "view_count": len(urls),
                "source_image_size": {"width": width, "height": height},
                "hand_roi_normalized": {
                    "x1": round(left / width, 4), "y1": round(top / height, 4),
                    "x2": round(right / width, 4), "y2": round(bottom / height, 4),
                },
                "edge_side": edge,
                "raw_views_stored": False,
                "limitations": [
                    "Enhanced views are deterministic crops of the source; they do not add or infer creases.",
                    "The original image remains the primary source for semantic adjudication.",
                ],
            }
            return metadata, urls
    except (UnidentifiedImageError, OSError, ValueError):
        return _empty("image_decode_failed"), []
    except Exception:
        return _empty("evidence_view_runtime_error"), []
