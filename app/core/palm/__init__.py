"""Palm-reading facade.

The public palm API remains backwards compatible while the production runtime
adds the canonical image/precheck/CV guards around the legacy service.
"""
# ruff: noqa: F401
from .. import agents, llm, palm_evidence, palm_full_scope, palm_landmarks, palm_lines, palm_vision  # noqa: F401
from ...config import settings
from .prompts import PALM_SYSTEM, PALM_SYSTEM_EN, PALM_USER, PALM_USER_EN, palm_prompts
from .service import (
    ALLOWED_MIME, EVIDENCE_CONTRACT_VERSION, EVIDENCE_STATES, IMAGE_FORMATS,
    MAX_IMAGE_BYTES, MAX_IMAGE_PIXELS, MAX_IMAGE_SIDE, MIN_SIDE,
    PALM_JSON_ATTEMPTS, PALM_RESPONSE_FORMAT, QUALITY_STATES, _UNTRUSTED_TEXT,
    _apply_cv_boundaries, _coerce_evidence_state, _data_url, _empty_detail,
    _json_text, _needs_photo_result, _normalize, _normalize_detail,
    _normalize_line_map, _normalize_markings, _normalize_photo_assessment,
    _normalize_zone_map, _palm_detail_schema, _safe_text, _scrub,
    _semantic_summary, get, latest, log,
)
from .production import (
    HAND_NOT_FOUND, MULTIPLE_HANDS, PHOTO_INVALID, PHOTO_LOW_QUALITY,
    CV_UNAVAILABLE, VISION_UNAVAILABLE, VISION_SCHEMA_INVALID,
    INTERPRETATION_FAILED, STORAGE_FAILED, PalmImage, analyze_and_save,
    canonicalize, classify_result, reset_request_cache,
)


_ORIGINAL_COMPLETE_VISION = llm.complete_vision


def _custom_provider_only() -> bool:
    chain = tuple(settings.provider_chain or ())
    return bool(chain) and all(provider == "custom" for provider in chain)


async def _complete_vision_compat(*args, **kwargs):
    """Avoid unsupported native JSON-schema parameters on custom proxies.

    The palm service still performs strict local JSON parsing/normalization and
    bounded semantic retries, so removing the transport-level schema is safe for
    OpenAI-compatible proxies that reject `response_format=json_schema`.
    """
    if kwargs.get("response_format") and _custom_provider_only():
        kwargs = dict(kwargs)
        kwargs["response_format"] = None
    return await _ORIGINAL_COMPLETE_VISION(*args, **kwargs)


llm.complete_vision = _complete_vision_compat

__all__ = [name for name in dir() if not name.startswith("__")]
