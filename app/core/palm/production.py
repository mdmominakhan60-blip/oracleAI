"""Production runtime guards for Mira's palm pipeline."""
from __future__ import annotations

import base64
import hashlib
import io
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

CANONICAL_MAX_SIDE = 1280
CANONICAL_JPEG_QUALITY = 90
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MIN_IMAGE_SIDE = 480
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
FORMAT_TO_MIME = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
PHOTO_INVALID = "PHOTO_INVALID"
PHOTO_LOW_QUALITY = "PHOTO_LOW_QUALITY"
HAND_NOT_FOUND = "HAND_NOT_FOUND"
MULTIPLE_HANDS = "MULTIPLE_HANDS"
CV_UNAVAILABLE = "CV_UNAVAILABLE"
VISION_UNAVAILABLE = "VISION_UNAVAILABLE"
VISION_SCHEMA_INVALID = "VISION_SCHEMA_INVALID"
INTERPRETATION_FAILED = "INTERPRETATION_FAILED"
STORAGE_FAILED = "STORAGE_FAILED"


@dataclass(frozen=True)
class PalmImage:
    raw_sha256: str
    normalized_sha256: str
    normalized_bytes: bytes
    mime: str
    width: int
    height: int
    format: str
    original_width: int
    original_height: int
    precheck: dict[str, Any]


_PRECHECK_CACHE: ContextVar[dict[str, dict[str, Any]] | None] = ContextVar("oracle_palm_precheck_cache", default=None)
_ORIGINAL_PRECHECK = None
_INSTALLED = False


def _cache() -> dict[str, dict[str, Any]]:
    value = _PRECHECK_CACHE.get()
    if value is None:
        value = {}
        _PRECHECK_CACHE.set(value)
    return value


def reset_request_cache() -> None:
    _PRECHECK_CACHE.set({})


def cached_precheck(image: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(image).hexdigest()
    cache = _cache()
    if digest not in cache:
        if _ORIGINAL_PRECHECK is None:
            raise RuntimeError("palm precheck runtime is not installed")
        cache[digest] = _ORIGINAL_PRECHECK(image)
    return dict(cache[digest])


def canonicalize(image: bytes, declared_content_type: str | None = None) -> PalmImage:
    if not image:
        raise ValueError("фото пустое")
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("фото слишком большое; максимум 8 МБ")
    declared = (declared_content_type or "").split(";", 1)[0].strip().lower()
    if declared and declared not in ALLOWED_MIME:
        raise ValueError("отправь изображение JPEG, PNG или WebP")
    raw_sha256 = hashlib.sha256(image).hexdigest()
    try:
        with Image.open(io.BytesIO(image)) as source:
            source.verify()
        with Image.open(io.BytesIO(image)) as source:
            actual_format = str(source.format or "").upper()
            mime = FORMAT_TO_MIME.get(actual_format)
            if mime is None:
                raise ValueError("поддерживаются только JPEG, PNG и WebP")
            if declared and declared != mime:
                raise ValueError("тип содержимого не совпадает с форматом изображения")
            if getattr(source, "n_frames", 1) > 1:
                raise ValueError("анимированные изображения не поддерживаются")
            original_width, original_height = source.size
            if original_width * original_height > MAX_IMAGE_PIXELS:
                raise ValueError("разрешение изображения слишком большое")
            frame = ImageOps.exif_transpose(source).convert("RGB")
            width, height = frame.size
            if min(width, height) < MIN_IMAGE_SIDE:
                raise ValueError(f"минимальная сторона фото — {MIN_IMAGE_SIDE}px")
            if max(width, height) > CANONICAL_MAX_SIDE:
                scale = CANONICAL_MAX_SIDE / float(max(width, height))
                frame = frame.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.LANCZOS)
            width, height = frame.size
            out = io.BytesIO()
            frame.save(out, format="JPEG", quality=CANONICAL_JPEG_QUALITY, optimize=True)
            normalized = out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise ValueError("изображение повреждено или не поддерживается") from exc
    precheck = cached_precheck(normalized)
    hard_quality_issues = {
        "underexposed", "overexposed", "low_contrast_or_flat_light", "soft_or_blurred_edges", "extreme_crop_or_aspect",
    }
    if precheck.get("status") == "invalid_image":
        raise ValueError("изображение повреждено или не читается")
    if precheck.get("status") == "reshoot_recommended" and (hard_quality_issues & set(precheck.get("issues") or [])):
        reasons = ", ".join(str(x) for x in (precheck.get("issues") or [])[:3])
        raise ValueError(f"кадр требует пересъёмки: {reasons or 'низкое качество'}")
    return PalmImage(
        raw_sha256=raw_sha256,
        normalized_sha256=hashlib.sha256(normalized).hexdigest(),
        normalized_bytes=normalized,
        mime="image/jpeg",
        width=width,
        height=height,
        format="JPEG",
        original_width=original_width,
        original_height=original_height,
        precheck=precheck,
    )


def canonical_data_url(image: bytes, declared_content_type: str | None = None) -> tuple[str, dict[str, Any]]:
    canonical = canonicalize(image, declared_content_type)
    return (
        "data:image/jpeg;base64," + base64.b64encode(canonical.normalized_bytes).decode("ascii"),
        {
            "sha256": canonical.raw_sha256,
            "normalized_sha256": canonical.normalized_sha256,
            "size": len(image),
            "normalized_size": len(canonical.normalized_bytes),
            "width": canonical.width,
            "height": canonical.height,
            "original_width": canonical.original_width,
            "original_height": canonical.original_height,
            "format": canonical.format,
            "mime": canonical.mime,
            "visual_precheck": canonical.precheck,
        },
    )


def _adaptive_original():
    from .. import palm_lines
    return palm_lines.analyze, palm_lines.CLASS_NAMES, palm_lines._bbox_iou


def adaptive_line_ensemble(image_bytes: bytes, *, view_type: str | None = None) -> dict[str, Any]:
    """FP16 first; INT8 is a bounded uncertainty cross-check only."""
    from .. import palm_lines
    if view_type == "folded_edge":
        return {
            "version": palm_lines.ADAPTER_VERSION,
            "status": "not_applicable",
            "model": "fp16_only",
            "models": [palm_lines.MODEL_FILENAME],
            "lines": {},
            "ensemble": {"status": "out_of_domain", "disagreements": [], "raw_masks_stored": False},
            "limitations": ["Principal-line ONNX model is not applied to folded-edge geometry."],
            "raw_mask_stored": False,
        }
    analyze, class_names, bbox_iou = _adaptive_original()
    fp16 = analyze(image_bytes)
    if fp16.get("status") not in {"detected", "no_lines"}:
        return {**fp16, "ensemble": {"status": "fallback_single_model", "models": [fp16.get("model")]}}
    lines = fp16.get("lines") or {}
    uncertain = (
        fp16.get("status") == "no_lines"
        or not any(isinstance(item, dict) and item.get("detected") for item in lines.values())
        or any(isinstance(item, dict) and item.get("detected") and float(item.get("confidence", 0)) < 0.45 for item in lines.values())
    )
    if not uncertain:
        return {**fp16, "ensemble": {"status": "fp16_stable", "models": [fp16.get("model")], "disagreements": [], "raw_masks_stored": False}}
    int8_path = str(palm_lines.Path(__file__).resolve().parents[2] / "models" / "palm_line_student_int8.onnx")
    int8 = analyze(image_bytes, model_path=int8_path)
    if int8.get("status") not in {"detected", "no_lines"}:
        return {**fp16, "ensemble": {"status": "int8_unavailable", "models": [fp16.get("model")], "disagreements": [], "raw_masks_stored": False}}
    merged, disagreements = {}, []
    for name in class_names.values():
        first = (fp16.get("lines") or {}).get(name) or {}
        second = (int8.get("lines") or {}).get(name) or {}
        iou = bbox_iou(first.get("bbox"), second.get("bbox")) if first.get("bbox") and second.get("bbox") else 0.0
        stable = bool(first.get("detected")) == bool(second.get("detected")) and (not first.get("detected") or iou >= 0.35)
        if not stable:
            disagreements.append(name)
        merged[name] = {
            **first,
            "detected": bool(first.get("detected")) and bool(second.get("detected")) and iou >= 0.35,
            "ensemble_agreement": stable,
            "bbox_iou_fp16_int8": round(iou, 4),
            "confidence": round(min(float(first.get("confidence", 0)), float(second.get("confidence", 0))), 4),
        }
    return {
        **fp16,
        "model": "fp16_int8_ensemble",
        "models": [fp16.get("model"), int8.get("model")],
        "lines": merged,
        "status": "needs_vision_review" if disagreements else ("detected" if any(x.get("detected") for x in merged.values()) else "no_lines"),
        "ensemble": {"status": "disagreement" if disagreements else "agreement", "models": [fp16.get("model"), int8.get("model")], "disagreements": disagreements, "raw_masks_stored": False},
    }


def classify_result(result: dict[str, Any]) -> str | None:
    precheck = result.get("visual_precheck") or {}
    if precheck.get("status") == "invalid_image":
        return PHOTO_INVALID
    if result.get("status") == "needs_photo" and set(precheck.get("issues") or []) & {
        "underexposed", "overexposed", "extreme_crop_or_aspect", "low_resolution", "low_contrast_or_flat_light", "soft_or_blurred_edges",
    }:
        return PHOTO_LOW_QUALITY
    geometry = (result.get("computer_vision") or {}).get("hand_geometry") or {}
    if geometry.get("status") == "multiple_hands":
        return MULTIPLE_HANDS
    if geometry.get("status") == "no_hand":
        return HAND_NOT_FOUND
    if geometry.get("status") in {"unavailable", "model_missing", "runtime_error"}:
        return CV_UNAVAILABLE
    flags = {str(x).lower() for x in (result.get("safety_flags") or [])}
    if "vision_json_invalid" in flags or any(x in flag for flag in flags for x in ("timeout", "runtimeerror", "invalid_json")):
        return VISION_SCHEMA_INVALID
    if result.get("status") == "needs_photo" and result.get("computer_vision"):
        return VISION_UNAVAILABLE
    return None


async def analyze_and_save(db, user: dict, image: bytes, *, surface: str = "miniapp", content_type: str | None = None) -> dict[str, Any]:
    reset_request_cache()
    install()
    from . import service
    canonical = canonicalize(image, content_type)
    result = await service.analyze_and_save(db, user, canonical.normalized_bytes, surface=surface, content_type="image/jpeg")
    result["image_contract"] = {
        "raw_sha256": canonical.raw_sha256,
        "normalized_sha256": canonical.normalized_sha256,
        "mime": canonical.mime,
        "format": canonical.format,
        "width": canonical.width,
        "height": canonical.height,
        "original_width": canonical.original_width,
        "original_height": canonical.original_height,
        "normalized_size": len(canonical.normalized_bytes),
        "precheck": canonical.precheck,
    }
    error_code = classify_result(result)
    if error_code:
        result["error_code"] = error_code
        if error_code == VISION_SCHEMA_INVALID:
            result["limitations"] = list(dict.fromkeys((result.get("limitations") or []) + ["Фото прошло capture/CV-проверки, но структурированный vision-ответ не прошёл локальную проверку."]))[:12]
        elif error_code == VISION_UNAVAILABLE:
            result["limitations"] = list(dict.fromkeys((result.get("limitations") or []) + ["Фото уже принято; vision-провайдер сейчас недоступен. Пересъёмка не требуется."]))[:12]
    return result


def install() -> None:
    global _ORIGINAL_PRECHECK, _INSTALLED
    if _INSTALLED:
        return
    from .. import palm_landmarks, palm_lines, palm_vision
    from . import service
    _ORIGINAL_PRECHECK = palm_vision.analyze
    palm_vision.analyze = cached_precheck
    from . import mediapipe_runtime
    palm_landmarks.analyze = mediapipe_runtime.analyze
    palm_lines.analyze_ensemble = adaptive_line_ensemble
    service._data_url = canonical_data_url
    service.PALM_JSON_ATTEMPTS = 2
    _INSTALLED = True


def is_installed() -> bool:
    return _INSTALLED


install()
