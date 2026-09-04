"""Palm-reading service: image contract, CV evidence, normalization, storage.

Вынесено из palm.py (ARCH-001). Публичный API — через app.core.palm (facade).
"""
from __future__ import annotations


import asyncio
import base64
import hashlib
import io
import json
import logging
import re
import time
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from ...repo import palm as palm_repo
from .. import agents, llm, palm_evidence, palm_full_scope, palm_landmarks, palm_lines, palm_vision
from .prompts import (  # noqa: F401  # PALM_* re-exported via package facade
    PALM_SYSTEM, PALM_SYSTEM_EN, PALM_USER, PALM_USER_EN, palm_prompts,
)

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_IMAGE_SIDE = 8_000
MIN_SIDE = 480
ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
EVIDENCE_CONTRACT_VERSION = "palm-evidence-v1"
EVIDENCE_STATES = {"observed", "inferred", "unknown", "not_supported"}
QUALITY_STATES = {"complete", "needs_photo", "failed", "deleted"}
_UNTRUSTED_TEXT = re.compile(
    r"(ignore\s+(?:all\s+)?previous\s+instructions?|disregard\s+(?:all\s+)?instructions?|"
    r"always\s+say|system\s+message|developer\s+message|jailbreak|prompt\s+injection|"
    r"игнорируй\s+(?:все\s+)?предыдущие\s+инструкции|всегда\s+говори|системное\s+сообщение)",
    re.IGNORECASE,
)



_PALM_TOPICS = {"heart_line", "head_line", "life_line", "fate_line", "sun_line",
                "mercury_line", "relationship_line", "children_lines", "travel_lines",
                "girdle_of_venus", "ring_of_solomon", "ring_of_apollo", "via_lasciva",
                "mars_lines", "influence_lines", "bracelets", "mounts", "fingers", "markings"}
_PALM_VISIBILITY = {"clear", "partial", "unclear", "not_visible"}
_PALM_HAND_SIDES = {"left", "right", "unknown"}
PALM_JSON_ATTEMPTS = 3
log = logging.getLogger("oracle.palm")


def _palm_detail_schema() -> dict:
    nullable_string = {"type": ["string", "null"]}
    nullable_number = {"type": ["number", "null"]}
    return {
        "type": "object",
        "properties": {
            "visibility": {"type": "string", "enum": sorted(_PALM_VISIBILITY)},
            "evidence_state": {"type": "string", "enum": sorted(EVIDENCE_STATES)},
            "summary": nullable_string,
            "confidence": nullable_number,
            "continuity": nullable_string,
            "path": nullable_string,
            "shape": nullable_string,
            "prominence": nullable_string,
            "length": nullable_string,
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["visibility", "evidence_state", "summary", "confidence", "continuity",
                      "path", "shape", "prominence", "length"],
        "additionalProperties": False,
    }


_PALM_DETAIL = _palm_detail_schema()
_PALM_DETAIL_MAP = {
    key: _PALM_DETAIL for key in (
        "life", "head", "heart", "fate", "sun", "relationship",
        "venus", "jupiter", "saturn", "apollo", "mercury", "moon", "mars",
        "thumb", "index", "middle", "ring", "little",
    )
}

PALM_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "oracleai_palm_reading",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["complete", "needs_photo"]},
                "evidence_contract_version": {"type": "string"},
                "confidence_semantics": {"type": "string"},
                "image_quality": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "number", "minimum": 0, "maximum": 1},
                        "issues": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["score", "issues"],
                    "additionalProperties": False,
                },
                "hand_detected": {"type": "boolean"},
                "hand_side": {"type": "string", "enum": sorted(_PALM_HAND_SIDES)},
                "hand_shape_element": {"type": "string", "enum": [
                    "earth", "air", "fire", "water", "unknown"]},
                "requires_view": {"type": "array", "items": {"type": "string"}},
                "photo_assessment": {
                    "type": "object",
                    "properties": {
                        "view_type": {"type": "string",
                                      "enum": ["open_palm", "folded_edge", "unclear"]},
                        "missing_views": {"type": "array",
                                          "items": {"type": "string"}},
                        "advice": {"type": "array",
                                   "items": {"type": "string"}},
                    },
                    "required": ["view_type", "missing_views", "advice"],
                    "additionalProperties": False,
                },
                "observations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "enum": sorted(_PALM_TOPICS)},
                            "visibility": {"type": "string", "enum": sorted(_PALM_VISIBILITY)},
                            "evidence_state": {"type": "string", "enum": sorted(EVIDENCE_STATES)},
                            "summary": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["topic", "visibility", "evidence_state", "summary", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "lines": {
                    "type": "object",
                    "required": ["life", "head", "heart", "fate", "sun", "mercury",
                                 "girdle_of_venus", "ring_of_solomon", "ring_of_apollo",
                                 "via_lasciva", "mars_lines", "influence_lines", "bracelets",
                                 "relationship", "children", "travel"],
                    "properties": {
                        **{key: _PALM_DETAIL for key in
                           ("life", "head", "heart", "fate", "sun", "mercury",
                            "girdle_of_venus", "ring_of_solomon", "ring_of_apollo",
                            "via_lasciva", "mars_lines", "influence_lines", "bracelets")},
                        "relationship": {"type": "array", "items": _PALM_DETAIL},
                        "children": {"type": "array", "items": _PALM_DETAIL},
                        "travel": {"type": "array", "items": _PALM_DETAIL},
                    },
                    "additionalProperties": False,
                },
                "mounts": {
                    "type": "object",
                    "properties": {key: _PALM_DETAIL_MAP[key] for key in
                                   ("venus", "jupiter", "saturn", "apollo", "mercury", "moon", "mars")},
                    "required": ["venus", "jupiter", "saturn", "apollo", "mercury", "moon", "mars"],
                    "additionalProperties": False,
                },
                "fingers": {
                    "type": "object",
                    "properties": {key: _PALM_DETAIL_MAP[key] for key in
                                   ("thumb", "index", "middle", "ring", "little")},
                    "required": ["thumb", "index", "middle", "ring", "little"],
                    "additionalProperties": False,
                },
                "markings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "kind": {"type": "string"},
                            "location": {"type": "string"},
                            "visibility": {"type": "string", "enum": sorted(_PALM_VISIBILITY)},
                            "evidence_state": {"type": "string", "enum": sorted(EVIDENCE_STATES)},
                            "summary": {"type": "string"},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        },
                        "required": ["kind", "location", "visibility", "evidence_state", "summary", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "interpretive_prompts": {"type": "array", "items": {"type": "string"}},
                "narrative": {"type": "string"},
                "limitations": {"type": "array", "items": {"type": "string"}},
                "safety_flags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "image_quality", "hand_detected", "hand_side",
                         "hand_shape_element", "requires_view", "photo_assessment",
                         "observations", "lines", "mounts", "fingers", "markings",
                         "interpretive_prompts", "narrative",
                         "limitations", "safety_flags",
                         "evidence_contract_version", "confidence_semantics"],
            "additionalProperties": False,
        },
    },
}



_FORBIDDEN = re.compile(
    r"(диагноз|заболев|болезн|беремен|смерт|умр(ет|у|ла)?|продолжительность жизни|рак|диабет|психоз|суицид|diagnos|disease|pregnan|death|cancer|diabetes)",
    re.IGNORECASE,
)



def _data_url(image: bytes, declared_content_type: str | None = None) -> tuple[str, dict]:
    if not image:
        raise ValueError("фото пустое")
    if len(image) > MAX_IMAGE_BYTES:
        raise ValueError("фото слишком большое; максимум 8 МБ")
    declared = (declared_content_type or "").split(";", 1)[0].strip().lower()
    if declared and declared not in ALLOWED_MIME:
        raise ValueError("отправь изображение JPEG, PNG или WebP")
    digest = hashlib.sha256(image).hexdigest()
    try:
        # First pass verifies the container/signature before any expensive CV stage.
        with Image.open(io.BytesIO(image)) as original:
            original.verify()
        with Image.open(io.BytesIO(image)) as original:
            actual_format = str(original.format or "").upper()
            actual_mime = IMAGE_FORMATS.get(actual_format)
            if actual_mime is None:
                raise ValueError("поддерживаются только JPEG, PNG и WebP")
            if declared and declared != actual_mime:
                raise ValueError("тип содержимого не совпадает с форматом изображения")
            if getattr(original, "n_frames", 1) > 1:
                raise ValueError("анимированные изображения не поддерживаются")
            width, height = original.size
            if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
                raise ValueError("размер изображения слишком большой")
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("разрешение изображения слишком большое")
            normalized = ImageOps.exif_transpose(original).convert("RGB")
            width, height = normalized.size
            if width > MAX_IMAGE_SIDE or height > MAX_IMAGE_SIDE:
                raise ValueError("размер изображения слишком большой")
            if width * height > MAX_IMAGE_PIXELS:
                raise ValueError("разрешение изображения слишком большое")
            if min(width, height) < MIN_SIDE:
                raise ValueError(f"минимальная сторона фото — {MIN_SIDE}px")
            out = io.BytesIO()
            normalized.save(out, format="JPEG", quality=90, optimize=True)
    except (UnidentifiedImageError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ValueError("изображение слишком большое или повреждено") from exc
    # Quality classification begins only after the actual image contract passes.
    visual_precheck = palm_vision.analyze(image)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii"), {
        "sha256": digest, "size": len(image), "width": width, "height": height,
        "format": actual_format, "mime": actual_mime, "visual_precheck": visual_precheck,
    }


def _json_text(text: str) -> dict[str, Any]:
    """Извлекает JSON object из vision-ответа без выполнения произвольного кода.

    В идеальном случае proxy возвращает strict JSON-schema content. На практике
    некоторые vision-провайдеры добавляют fence/префикс или оставляют trailing
    comma. Здесь разрешены только детерминированные repairs: markdown fence,
    извлечение первого JSON object и удаление запятых перед `}`/`]`.
    Любой другой ответ отклоняется и уходит в semantic retry.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        raise ValueError("vision-модель вернула пустой ответ")
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE).strip()

    candidates = [cleaned]
    start = cleaned.find("{")
    if start >= 0 and start != 0:
        candidates.append(cleaned[start:])

    decoder = json.JSONDecoder()
    last_error: Exception | None = None
    for candidate in candidates:
        for value_text in (candidate, re.sub(r",\s*([}\]])", r"\1", candidate)):
            try:
                value, _end = decoder.raw_decode(value_text.lstrip())
            except (TypeError, ValueError) as exc:
                last_error = exc
                continue
            if not isinstance(value, dict):
                last_error = ValueError("vision-модель вернула не объект")
                continue
            return value
    raise ValueError("vision-модель вернула невалидный JSON") from last_error


def _needs_photo_result(reason: str) -> dict[str, Any]:
    """Безопасный результат при невозможности получить структурированный ответ.

    Raw provider content намеренно не попадает ни в response, ни в SQLite. В
    `reason` передаётся только внутренний тип ошибки, а пользователь получает
    понятную инструкцию повторить снимок.
    """
    return {
        "status": "needs_photo",
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "confidence_semantics": (
            "0=нет визуального подтверждения; 0.01–0.49=слабое/частичное; "
            "0.50–0.79=умеренное; 0.80–1.00=чёткое наблюдение, подтверждённое кадром"
        ),
        "image_quality": {"score": 0.0, "issues": [
            "Не удалось получить структурированное чтение; попробуй отправить фото ещё раз.",
        ]},
        "hand_detected": False,
        "hand_side": "unknown",
        "hand_shape_element": "unknown",
        "requires_view": ["open_palm", "folded_edge"],
        "photo_assessment": {"view_type": "unclear", "missing_views": ["folded_edge"],
                             "advice": ["Согни ладонь ребром к камере — так видны линии брака, отношений и детей."]},
        "observations": [],
        "lines": _normalize_line_map({}),
        "mounts": _normalize_zone_map({}, ("venus", "jupiter", "saturn", "apollo", "mercury", "moon", "mars")),
        "fingers": _normalize_zone_map({}, ("thumb", "index", "middle", "ring", "little")),
        "markings": [],
        "semantic_summary": _semantic_summary(
            _normalize_line_map({}),
            _normalize_zone_map({}, ("venus", "jupiter", "saturn", "apollo", "mercury", "moon", "mars")),
            _normalize_zone_map({}, ("thumb", "index", "middle", "ring", "little")),
            [],
        ),
        "interpretive_prompts": [],
        "limitations": [
            "Ответ vision-провайдера не прошёл проверку формата.",
            "Пересними одну ладонь целиком при ровном свете, без бликов и фильтров.",
        ],
        "safety_flags": ["vision_json_invalid", reason[:80]],
        "source": "vision_llm_observation",
    }


def _safe_text(value: Any) -> str:
    text = str(value or "").strip()
    text = _UNTRUSTED_TEXT.sub("[инструкция изображения/модели проигнорирована]", text)
    return _FORBIDDEN.sub("[скрыто правилами безопасности]", text)[:800]


def _scrub(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[данные сокращены]"
    if isinstance(value, dict):
        return {str(key)[:80]: _scrub(item, depth + 1)
                for key, item in list(value.items())[:40]}
    if isinstance(value, list):
        return [_scrub(item, depth + 1) for item in value[:40]]
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _safe_text(value)


def _coerce_evidence_state(value: Any, visibility: str) -> str:
    state = str(value or "").strip().lower()
    if state not in EVIDENCE_STATES:
        state = "observed" if visibility == "clear" else "inferred" if visibility == "partial" else "unknown"
    if visibility == "not_visible" and state in {"observed", "inferred"}:
        return "unknown"
    if visibility == "unclear" and state == "observed":
        return "unknown"
    return state


def _empty_detail() -> dict[str, Any]:
    return {
        "visibility": "not_visible",
        "evidence_state": "unknown",
        "summary": "Зона не различима на этом кадре; не делаю выводов.",
        "confidence": 0.0,
        "continuity": None,
        "path": None,
        "shape": None,
        "prominence": None,
        "length": None,
        "evidence_refs": [],
    }


def _normalize_detail(value: Any) -> dict[str, Any]:
    detail = _empty_detail()
    if not isinstance(value, dict):
        return detail
    visibility = str(value.get("visibility") or "not_visible").strip().lower()
    detail["visibility"] = visibility if visibility in _PALM_VISIBILITY else "unclear"
    detail["evidence_state"] = _coerce_evidence_state(value.get("evidence_state"), detail["visibility"])
    detail["summary"] = _safe_text(value.get("summary")) or detail["summary"]
    try:
        detail["confidence"] = round(max(0.0, min(1.0, float(value.get("confidence", 0)))), 2)
    except (TypeError, ValueError):
        detail["confidence"] = 0.0
    for field in ("continuity", "path", "shape", "prominence", "length"):
        raw = value.get(field)
        detail[field] = _safe_text(raw) if raw is not None else None
    refs = value.get("evidence_refs") if isinstance(value.get("evidence_refs"), list) else []
    detail["evidence_refs"] = [_safe_text(ref)[:120] for ref in refs[:8]]
    return detail


def _normalize_line_map(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    scalar_lines = (
        "life", "head", "heart", "fate", "sun", "mercury",
        "girdle_of_venus", "ring_of_solomon", "ring_of_apollo", "via_lasciva",
        "mars_lines", "influence_lines", "bracelets",
    )
    lines = {name: _normalize_detail(source.get(name)) for name in scalar_lines}
    for name in ("relationship", "children", "travel"):
        raw_items = source.get(name) if isinstance(source.get(name), list) else []
        lines[name] = [_normalize_detail(item) for item in raw_items[:20]]
    return lines


def _normalize_zone_map(value: Any, names: tuple[str, ...]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {name: _normalize_detail(source.get(name)) for name in names}


def _normalize_photo_assessment(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    view = str(source.get("view_type") or "unclear").strip().lower()
    if view not in {"open_palm", "folded_edge", "unclear"}:
        view = "unclear"
    missing = source.get("missing_views") if isinstance(source.get("missing_views"), list) else []
    advice = source.get("advice") if isinstance(source.get("advice"), list) else []
    return {
        "view_type": view,
        "missing_views": [_safe_text(item)[:160] for item in missing[:8]],
        "advice": [_safe_text(item)[:240] for item in advice[:8]],
    }


def _normalize_markings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        detail = _normalize_detail(item)
        result.append({
            "kind": _safe_text(item.get("kind")) or "other",
            "location": _safe_text(item.get("location")),
            "visibility": detail["visibility"],
            "evidence_state": detail["evidence_state"],
            "summary": detail["summary"],
            "confidence": detail["confidence"],
        })
    return result


def _semantic_summary(lines: dict[str, Any], mounts: dict[str, Any], fingers: dict[str, Any], markings: list[dict[str, Any]]) -> dict[str, Any]:
    details: list[tuple[str, dict[str, Any]]] = []
    for group_name, group in (("lines", lines), ("mounts", mounts), ("fingers", fingers)):
        for name, value in group.items():
            values = value if isinstance(value, list) else [value]
            for index, item in enumerate(values):
                if isinstance(item, dict):
                    suffix = f"[{index}]" if isinstance(value, list) else ""
                    details.append((f"{group_name}.{name}{suffix}", item))
    for index, item in enumerate(markings):
        if isinstance(item, dict):
            details.append((f"markings[{index}]", item))
    supported = [name for name, item in details
                 if item.get("visibility") in {"clear", "partial"}
                 and item.get("evidence_refs")]
    abstained = [name for name, item in details
                 if item.get("visibility") in {"unclear", "not_visible"}]
    return {
        "supported_zone_count": len(supported),
        "abstained_zone_count": len(abstained),
        "supported_zones": supported[:80],
        "abstained_zones": abstained[:80],
        "rule": "Only zones with visible status and explicit evidence_refs are supported; other zones require review or another view.",
    }


def _normalize(data: dict[str, Any], quality: dict) -> dict[str, Any]:
    observations = []
    for item in data.get("observations") or []:
        if not isinstance(item, dict):
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        topic = str(item.get("topic") or "unknown").strip().lower()
        visibility = str(item.get("visibility") or "unclear").strip().lower()
        visibility = visibility if visibility in _PALM_VISIBILITY else "unclear"
        evidence_state = _coerce_evidence_state(item.get("evidence_state"), visibility)
        if evidence_state in {"unknown", "not_supported"}:
            confidence = 0.0
        observations.append({
            "topic": topic if topic in _PALM_TOPICS else "unknown",
            "visibility": visibility,
            "evidence_state": evidence_state,
            "summary": _safe_text(item.get("summary")),
            "confidence": round(confidence, 2),
        })
    flags = [_safe_text(flag)[:120] for flag in (data.get("safety_flags") or [])]
    for item in observations:
        if "[скрыто" in item["summary"]:
            flags.append("model_claim_sanitized")
    status = "needs_photo" if data.get("status") == "needs_photo" else "complete"
    score = quality.get("score", 0.0)
    try:
        score = max(0.0, min(1.0, float(score)))
    except (TypeError, ValueError):
        score = 0.0
    result = {
        "status": status,
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "confidence_semantics": (
            "0=нет визуального подтверждения; 0.01–0.49=слабое/частичное; "
            "0.50–0.79=умеренное; 0.80–1.00=чёткое наблюдение, подтверждённое кадром"
        ),
        "image_quality": {"score": round(score, 2),
                           "issues": [_safe_text(x)[:160] for x in (quality.get("issues") or [])]},
        "hand_detected": bool(data.get("hand_detected")),
        "hand_side": (str(data.get("hand_side") or "unknown").strip().lower()
                      if str(data.get("hand_side") or "unknown").strip().lower() in _PALM_HAND_SIDES
                      else "unknown"),
        "hand_shape_element": (str(data.get("hand_shape_element") or "unknown").strip().lower()
                               if str(data.get("hand_shape_element") or "unknown").strip().lower()
                               in {"earth", "air", "fire", "water", "unknown"}
                               else "unknown"),
        "requires_view": [
            _safe_text(item)[:80] for item in (data.get("requires_view") or [])[:8]
            if isinstance(item, (str, int, float))
        ],
        "photo_assessment": _normalize_photo_assessment(data.get("photo_assessment")),
        "observations": observations,
        "lines": _normalize_line_map(data.get("lines")),
        "mounts": _normalize_zone_map(
            data.get("mounts"), ("venus", "jupiter", "saturn", "apollo", "mercury", "moon", "mars")
        ),
        "fingers": _normalize_zone_map(
            data.get("fingers"), ("thumb", "index", "middle", "ring", "little")
        ),
        "markings": _normalize_markings(data.get("markings")),
        "interpretive_prompts": [_safe_text(x) for x in (data.get("interpretive_prompts") or [])[:8]],
        "narrative": _safe_text(data.get("narrative")) or "",
        "limitations": [_safe_text(x) for x in (data.get("limitations") or [])[:10]],
        "safety_flags": flags[:20],
        "source": "vision_llm_observation",
    }
    result["semantic_summary"] = _semantic_summary(
        result["lines"], result["mounts"], result["fingers"], result["markings"]
    )
    if not result["hand_detected"]:
        result["status"] = "needs_photo"
        result["limitations"].append("Ладонь не распознана; пересними ладонь целиком при ровном свете.")
    supported_observations = [
        item for item in result["observations"]
        if item["evidence_state"] in {"observed", "inferred"} and item["confidence"] >= 0.5
    ]
    if not result["observations"] or not supported_observations:
        result["status"] = "needs_photo"
        result["limitations"].append(
            "Ни одно наблюдение не достигло минимальной опоры; пересними ладонь при ровном свете."
        )
    return result


def _apply_cv_boundaries(result: dict[str, Any], cv_evidence: dict[str, Any]) -> dict[str, Any]:
    """Apply only deterministic safety boundaries; CV candidates remain non-semantic."""
    geometry = cv_evidence.get("hand_geometry") or {}
    full_scope = cv_evidence.get("full_scope") or {}
    view_type = str(full_scope.get("view_type") or "unclear")
    photo = result.get("photo_assessment")
    if not isinstance(photo, dict):
        photo = {"view_type": "unclear", "missing_views": [], "advice": []}
    if view_type in {"open_palm", "folded_edge"}:
        photo["view_type"] = view_type
    missing = [str(item) for item in (photo.get("missing_views") or [])]
    advice = [str(item) for item in (photo.get("advice") or [])]
    required = [str(item) for item in (result.get("requires_view") or [])]
    if view_type == "open_palm":
        if "folded_edge" not in missing:
            missing.append("folded_edge")
        if "folded_edge" not in required:
            required.append("folded_edge")
        folded_advice = "Для линий отношений, детей и путешествий нужен отдельный кадр согнутой ладони ребром к камере."
        if folded_advice not in advice:
            advice.append(folded_advice)
        lines = result.setdefault("lines", {})
        for line_name in ("relationship", "children", "travel"):
            lines[line_name] = []
        result.setdefault("limitations", []).append(
            "Открытый кадр не подтверждает зоны ребра ладони: relationship/children/travel помечены unknown."
        )
    if geometry.get("status") == "multiple_hands" or geometry.get("hand_count", 0) > 1:
        result["status"] = "needs_photo"
        result["hand_detected"] = False
        result["hand_side"] = "unknown"
        result.setdefault("limitations", []).append(
            "В кадре обнаружено несколько рук; оставь одну ладонь целиком и пересними фото."
        )
    elif geometry.get("status") == "no_hand":
        result["status"] = "needs_photo"
        result["hand_detected"] = False
        result["hand_side"] = "unknown"
        result.setdefault("limitations", []).append(
            "Ладонь не подтверждена; не делаю выводов по случайным контурам."
        )
    photo["missing_views"] = missing[:8]
    photo["advice"] = advice[:8]
    result["requires_view"] = required[:8]
    result["photo_assessment"] = photo
    result["limitations"] = list(dict.fromkeys(result.get("limitations") or []))[:12]
    return result


async def analyze_and_save(
    db, user: dict, image: bytes, *, surface: str = "miniapp",
    content_type: str | None = None,
) -> dict:
    started = time.perf_counter()
    data_url, meta = _data_url(image, content_type)
    accepted_ms = round((time.perf_counter() - started) * 1000, 2)
    precheck = meta["visual_precheck"]
    raw: dict[str, Any] | None = None
    additional_view_urls: list[str] = []
    last_error: Exception | None = None
    hard_capture_issues = {"image_decode_failed", "underexposed", "overexposed", "extreme_crop_or_aspect"}
    preflight_rejected = (
        precheck["status"] == "invalid_image"
        or precheck["score"] < 0.25
        or bool(hard_capture_issues & set(precheck.get("issues") or []))
    )
    if preflight_rejected:
        last_error = ValueError("deterministic_precheck")
    if preflight_rejected:
        cv_evidence = {
            "line_segmentation": {
                "version": palm_lines.ADAPTER_VERSION,
                "status": "skipped",
                "issues": ["capture_precheck_rejected"],
                "raw_mask_stored": False,
            },
            "hand_geometry": {
                "version": palm_landmarks.ADAPTER_VERSION,
                "status": "skipped",
                "issues": ["capture_precheck_rejected"],
            },
            "full_scope": {
                "version": palm_full_scope.ADAPTER_VERSION,
                "status": "skipped",
                "issues": ["capture_precheck_rejected"],
                "raw_edge_map_stored": False,
                "raw_mask_stored": False,
            },
        }
    else:
        cv_started = time.perf_counter()
        hand_result = await asyncio.to_thread(palm_landmarks.analyze, image)
        full_scope = await asyncio.to_thread(
            palm_full_scope.analyze, image, hand_geometry=hand_result
        )
        line_result = await asyncio.to_thread(
            palm_lines.analyze_ensemble, image, view_type=full_scope.get("view_type")
        )
        evidence_views, additional_view_urls = palm_evidence.prepare_views(
            image, hand_geometry=hand_result, view_type=full_scope.get("view_type", "unclear")
        )
        cv_evidence = {
            "line_segmentation": line_result,
            "hand_geometry": hand_result,
            "full_scope": full_scope,
            "vision_views": evidence_views,
        }
        cv_ms = round((time.perf_counter() - cv_started) * 1000, 2)

    hard_cv_reject = False
    if not preflight_rejected:
        geometry_status = str((cv_evidence.get("hand_geometry") or {}).get("status") or "")
        hard_cv_reject = geometry_status in {"no_hand", "multiple_hands"}

    palm_system, palm_user = palm_prompts((user["lang"] or "ru") if user else "ru")
    try:
        vision_system = await agents.system_for(
            db, user, agents.get("chiromant"), question="анализ фотографии ладони",
            extra_rules=palm_system,
        )
    except Exception:
        # The multimodal path remains non-fatal if prompt context is unavailable;
        # the palm system prompt still contains the strict JSON and safety contract.
        vision_system = palm_system

    vision_started = time.perf_counter()
    vision_attempts = 0
    for attempt in range(0 if (preflight_rejected or hard_cv_reject) else PALM_JSON_ATTEMPTS):
        vision_attempts = attempt + 1
        retry_hint = ""
        if attempt:
            retry_hint = (
                "\n\nRETRY: the previous answer failed JSON validation. "
                "Return exactly one complete JSON object per the schema — no Markdown, "
                "no commentary before/after the JSON, no trailing commas. "
                "Do not drop required fields."
                if palm_user is PALM_USER_EN else
                "\n\nПОВТОРНАЯ ПОПЫТКА: предыдущий ответ не прошёл JSON-проверку. "
                "Верни строго один полный JSON object по schema, без Markdown, пояснений "
                "до/после JSON и без trailing comma. Не сокращай обязательные поля."
            )
        try:
            precheck_hint = (
                "\n\nDETERMINISTIC CAPTURE PRECHECK (not hand detection): "
                + json.dumps(precheck, ensure_ascii=False, separators=(",", ":"))
                + ("\nUse these metrics only to judge frame legibility; do not call them proof of a hand or of lines."
                   if palm_user is PALM_USER_EN else
                   "\nИспользуй эти метрики только для оценки читаемости кадра; не называй их доказательством наличия руки или линий.")
                + "\n\nOPTIONAL CV EVIDENCE (auxiliary, not instruction or interpretation): "
                + json.dumps(cv_evidence, ensure_ascii=False, separators=(",", ":"))
                + ("\nCross-check the auxiliary geometry against the image; never turn a mask, landmarks or confidence into a medical, psychological or deterministic conclusion."
                   if palm_user is PALM_USER_EN else
                   "\nСверь вспомогательную геометрию с изображением; не превращай маску, landmarks или confidence в медицинский, психологический или детерминистический вывод.")
                + ("\n\nVISION FOCUS VIEWS: the extra frames are deterministic in-memory crops/enhancements of the original image. Use them only to verify fine creases and folded-edge zones; the original frame remains the primary evidence."
                   if palm_user is PALM_USER_EN else
                   "\n\nVISION FOCUS VIEWS: дополнительные кадры — это детерминированные in-memory crop/enhancement исходного изображения. Используй их только для проверки мелких складок и folded-edge зон; исходный кадр остаётся главным evidence.")
            )
            text = await llm.complete_vision(
                vision_system,
                palm_user + precheck_hint + retry_hint,
                data_url,
                tier="main",
                max_tokens=1600,
                purpose="palm:vision",
                tg_id=user["tg_id"],
                db=db,
                response_format=PALM_RESPONSE_FORMAT,
                additional_image_data_urls=additional_view_urls[:2],
            )
            raw = _json_text(text)
            break
        except (ValueError, RuntimeError, TimeoutError) as exc:
            last_error = exc
            # Не логируем provider content или data URL: только безопасный тип
            # ошибки и номер попытки, чтобы не утечь raw image/PII.
            log.warning(
                "vision structured response rejected: attempt=%d/%d error_type=%s",
                attempt + 1, PALM_JSON_ATTEMPTS, type(exc).__name__,
            )

    if raw is None:
        reason = (
            "deterministic_precheck" if preflight_rejected
            else "hand_detection_rejected" if hard_cv_reject
            else (type(last_error).__name__ if last_error else "invalid_json")
        )
        result = _needs_photo_result(reason)
    else:
        result = _normalize(raw, raw.get("image_quality") or {})
    result["visual_precheck"] = precheck
    result["computer_vision"] = cv_evidence
    result = _apply_cv_boundaries(result, cv_evidence)
    result["image_quality"]["precheck_score"] = precheck["score"]
    result["image_quality"]["precheck_issues"] = precheck["issues"]
    result["processing_metrics"] = {
        "acceptance_precheck_ms": accepted_ms,
        "cv_ms": round(locals().get("cv_ms", 0.0), 2),
        "vision_ms": round((time.perf_counter() - vision_started) * 1000, 2),
        "vision_attempts": vision_attempts,
        "vision_skipped": bool(preflight_rejected or hard_cv_reject),
        "provider_content_stored": False,
    }
    if preflight_rejected:
        result["status"] = "needs_photo"
        result["limitations"].append(
            "Детерминированная проверка кадра рекомендует пересъёмку: "
            + ", ".join(precheck["issues"] or ["низкая совокупная читаемость"])
        )
    result["processing_metrics"]["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
    reading_id = await palm_repo.save_reading(
        db, user["tg_id"], result, image_sha256=meta["sha256"],
        image_size=meta["size"], hand_side=result["hand_side"],
        status=result["status"], surface=surface,
    )
    result["id"] = reading_id
    result["image_meta"] = {"width": meta["width"], "height": meta["height"],
                             "size": meta["size"], "raw_stored": False}
    return result


async def latest(db, user: dict) -> dict | None:
    return await palm_repo.decode_row(await palm_repo.latest_reading(db, user["tg_id"]))



async def get(db, user: dict, reading_id: int) -> dict | None:
    return await palm_repo.decode_row(await palm_repo.get_reading(db, reading_id, user["tg_id"]))
