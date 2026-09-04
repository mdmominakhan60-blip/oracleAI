"""Server-side chart-engine rasterization.

The product boundary is intentionally narrow: Kerykeion is the only chart geometry
engine, its SVG exists only as a local transient string, and resvg converts it to
raster bytes before any caller can receive or cache the result. No SVG geometry,
path generation, label placement, or fallback wheel is implemented here.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from PIL import Image

from . import astro
from ..config import settings

try:
    import resvg_py
except ImportError as exc:  # pragma: no cover - exercised by deployment gate
    resvg_py = None
    _RESVG_IMPORT_ERROR = exc
else:
    _RESVG_IMPORT_ERROR = None


RenderFormat = Literal["png", "webp"]
RenderVariant = Literal["compact", "full", "share", "print"]
RenderLocale = Literal["ru", "en"]

VARIANT_DIMENSIONS: dict[str, tuple[int, int]] = {
    "compact": (900, 900),
    "full": (1200, 1200),
    "share": (1600, 1600),
    "print": (2400, 2400),
}
SUPPORTED_FORMATS = frozenset({"png", "webp"})
SUPPORTED_VARIANTS = frozenset(VARIANT_DIMENSIONS)
SUPPORTED_LOCALES = frozenset({"ru", "en"})
_CACHE_LIMIT = 64
_CACHE_LOCK = threading.RLock()
_RENDER_LOCK = threading.BoundedSemaphore(2)
_RASTER_CACHE: OrderedDict[str, bytes] = OrderedDict()
_EXTERNAL_REF_RE = re.compile(r"(?:href|xlink:href)\s*=\s*['\"](?:https?:|data:|//)", re.I)
_FORBIDDEN_SVG_RE = re.compile(r"<(?:script|foreignObject|iframe|object)\b", re.I)


class ChartRenderError(RuntimeError):
    """Base class for typed chart image failures."""


class InsufficientPrecisionError(ChartRenderError):
    code = "insufficient_precision"


class UnsupportedRenderError(ChartRenderError):
    code = "unsupported_render"


class RasterizerUnavailableError(ChartRenderError):
    code = "rasterizer_unavailable"


class EngineRenderError(ChartRenderError):
    code = "engine_render_failed"


@dataclass(frozen=True)
class RenderSpec:
    variant: RenderVariant
    image_format: RenderFormat
    locale: RenderLocale
    width: int
    height: int


def build_render_spec(*, variant: str = "compact", image_format: str = "png",
                      locale: str = "ru") -> RenderSpec:
    variant = (variant or "compact").lower()
    image_format = (image_format or "png").lower()
    locale = (locale or "ru").lower()
    if variant not in SUPPORTED_VARIANTS:
        raise UnsupportedRenderError(f"unknown chart image variant: {variant}")
    if image_format not in SUPPORTED_FORMATS:
        raise UnsupportedRenderError(f"unknown chart image format: {image_format}")
    if locale not in SUPPORTED_LOCALES:
        raise UnsupportedRenderError(f"unknown chart image locale: {locale}")
    width, height = VARIANT_DIMENSIONS[variant]
    return RenderSpec(variant=variant, image_format=image_format, locale=locale,
                      width=width, height=height)


def _cache_secret() -> bytes:
    # Production already requires BOT_TOKEN. The deterministic development fallback
    # keeps tests reproducible but is never a user identifier or birth-data value.
    return (settings.bot_token or "oracleai-chart-cache-development-key").encode("utf-8")


def cache_key(chart: dict, *, birth_date: str, birth_time: str | None,
              lat: float | None, lon: float | None, tz: str | None,
              spec: RenderSpec) -> str:
    """Return a keyed digest over chart version/conventions, never raw birth data."""
    calculation = chart.get("calculation") or {}
    runtime = (calculation.get("config") or {}).get("runtime_versions") or {}
    payload = "|".join([
        "chart-image-v2-classic-dark-clean", astro.EPHEMERIS_ENGINE,
        f"kerykeion-{runtime.get('kerykeion', 'unknown')}",
        f"swiss-{runtime.get('swiss_ephemeris', 'unknown')}",
        f"tzdata-{runtime.get('tzdata', 'unknown')}", "resvg_py-0.5.0",
        str(chart.get("natal_schema_version", 2)), str(chart.get("precision", "")),
        str(calculation.get("contract_version", "")),
        str(calculation.get("configuration_fingerprint", "")),
        str(calculation.get("request_fingerprint", "")), astro.ZODIAC_TYPE,
        astro.HOUSE_SYSTEM_IDENTIFIER, astro.PERSPECTIVE_TYPE, spec.variant,
        spec.image_format, spec.locale, str(spec.width), str(spec.height),
        # These values are only keyed, not emitted. HMAC prevents reversing them
        # from cache filenames/logs if a future backend stores cache metadata.
        birth_date or "", birth_time or "", str(lat), str(lon), tz or "",
    ]).encode("utf-8")
    return hmac.new(_cache_secret(), payload, hashlib.sha256).hexdigest()


def _subject_from_chart(chart: dict, *, birth_date: str, birth_time: str | None,
                        lat: float | None, lon: float | None, tz: str | None):
    calculation = chart.get("calculation") or {}
    config = calculation.get("config") or {}
    expected_config = {
        "zodiac_type": astro.ZODIAC_TYPE,
        "house_system": astro.HOUSE_SYSTEM_IDENTIFIER,
        "perspective_type": astro.PERSPECTIVE_TYPE,
    }
    if config and any(str(config.get(key)) != value for key, value in expected_config.items()):
        raise EngineRenderError("stored chart configuration is stale")
    if chart.get("precision") != "exact":
        raise InsufficientPrecisionError(
            "A natal wheel image requires confirmed birth time, coordinates, and timezone.")
    if not birth_time or lat is None or lon is None or not tz:
        raise InsufficientPrecisionError(
            "A natal wheel image requires confirmed birth time, coordinates, and timezone.")
    try:
        parsed = datetime.strptime(birth_time, "%H:%M")
        day = datetime.strptime(birth_date, "%Y-%m-%d").date()
    except (TypeError, ValueError) as exc:
        raise EngineRenderError("stored chart input is invalid") from exc
    try:
        from kerykeion import AstrologicalSubjectFactory
        return AstrologicalSubjectFactory.from_birth_data(
            name="oracle", year=day.year, month=day.month, day=day.day,
            hour=parsed.hour, minute=parsed.minute, city="-",
            lat=float(lat), lng=float(lon), tz_str=tz, online=False,
            zodiac_type=config.get("zodiac_type", astro.ZODIAC_TYPE),
            houses_system_identifier=config.get("house_system", astro.HOUSE_SYSTEM_IDENTIFIER),
            perspective_type=config.get("perspective_type", astro.PERSPECTIVE_TYPE),
            active_points=config.get("active_points") or astro.ACTIVE_POINTS,
        )
    except ChartRenderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise EngineRenderError("Kerykeion subject creation failed") from exc


def _transient_svg(subject, *, locale: RenderLocale, variant: RenderVariant) -> str:
    try:
        from kerykeion.chart_data_factory import ChartDataFactory
        from kerykeion.charts.chart_drawer import ChartDrawer
        data = ChartDataFactory.create_natal_chart_data(subject)
        drawer = ChartDrawer(chart_data=data, chart_language=locale.upper(), theme="dark", style="classic")
        # The SVG remains local to this call. remove_css_variables is required for
        # deterministic resvg rendering and does not change chart geometry.
        return drawer.generate_wheel_only_svg_string(
            remove_css_variables=True,
            style="classic",
            show_zodiac_background_ring=False,
        )
    except Exception as exc:  # noqa: BLE001
        raise EngineRenderError("Kerykeion chart rendering failed") from exc


def _validate_transient_svg(svg: str) -> None:
    if not svg or len(svg) > 2_000_000:
        raise EngineRenderError("chart engine returned an invalid SVG payload")
    lowered = svg.lower()
    if _FORBIDDEN_SVG_RE.search(svg) or _EXTERNAL_REF_RE.search(svg):
        raise EngineRenderError("chart engine SVG contains a forbidden active or external reference")
    if "<svg" not in lowered or "</svg>" not in lowered:
        raise EngineRenderError("chart engine output is not an SVG document")


def _rasterize(svg: str, spec: RenderSpec) -> bytes:
    if resvg_py is None:
        raise RasterizerUnavailableError("resvg_py is not installed") from _RESVG_IMPORT_ERROR
    try:
        png = resvg_py.svg_to_bytes(svg_string=svg, background="#0c0a1d", width=spec.width, height=spec.height)
        with Image.open(io.BytesIO(png)) as image:
            image.load()
            if image.size != (spec.width, spec.height):
                raise EngineRenderError("rasterizer returned unexpected dimensions")
            if spec.image_format == "png":
                out = io.BytesIO()
                image.save(out, format="PNG", optimize=True)
                result = out.getvalue()
            else:
                out = io.BytesIO()
                image.save(out, format="WEBP", lossless=True, method=6)
                result = out.getvalue()
        if not result:
            raise EngineRenderError("rasterizer returned an empty image")
        return result
    except ChartRenderError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise EngineRenderError("resvg rasterization failed") from exc


def render_chart_image(chart: dict, *, birth_date: str, birth_time: str | None,
                       lat: float | None, lon: float | None, tz: str | None,
                       variant: str = "compact", image_format: str = "png",
                       locale: str = "ru") -> tuple[bytes, RenderSpec, bool, str]:
    """Render and return raster bytes; raw SVG never leaves this function."""
    spec = build_render_spec(variant=variant, image_format=image_format, locale=locale)
    key = cache_key(chart, birth_date=birth_date, birth_time=birth_time,
                    lat=lat, lon=lon, tz=tz, spec=spec)
    with _CACHE_LOCK:
        cached = _RASTER_CACHE.get(key)
        if cached is not None:
            _RASTER_CACHE.move_to_end(key)
            return cached, spec, True, key
    with _RENDER_LOCK:
        with _CACHE_LOCK:
            cached = _RASTER_CACHE.get(key)
            if cached is not None:
                _RASTER_CACHE.move_to_end(key)
                return cached, spec, True, key
        subject = _subject_from_chart(chart, birth_date=birth_date, birth_time=birth_time,
                                       lat=lat, lon=lon, tz=tz)
        svg = _transient_svg(subject, locale=spec.locale, variant=spec.variant)
        _validate_transient_svg(svg)
        result = _rasterize(svg, spec)
        del svg
        with _CACHE_LOCK:
            _RASTER_CACHE[key] = result
            _RASTER_CACHE.move_to_end(key)
            while len(_RASTER_CACHE) > _CACHE_LIMIT:
                _RASTER_CACHE.popitem(last=False)
        return result, spec, False, key


def clear_render_cache() -> None:
    with _CACHE_LOCK:
        _RASTER_CACHE.clear()


def render_cache_stats() -> dict[str, int]:
    with _CACHE_LOCK:
        return {"entries": len(_RASTER_CACHE), "limit": _CACHE_LIMIT}
