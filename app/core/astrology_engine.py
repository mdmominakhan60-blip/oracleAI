"""Improved deterministic engine boundary for OracleAI astrology.

This module owns request normalization and reproducibility metadata. The actual
astronomical backend remains Kerykeion over Swiss Ephemeris in ``astro.py``;
callers must not infer precision from a non-empty clock string or from a city
label. The engine deliberately does not interpret results and never calls an
LLM.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .chart_contract import (
    ASPECT_ORBS,
    ASPECT_POLICY,
    ORACLE_ENGINE_ADAPTER_VERSION,
    CalculationConfig,
    configuration_fingerprint,
)

ENGINE_ADAPTER_VERSION = ORACLE_ENGINE_ADAPTER_VERSION
_ASPECT_LABEL_TO_CODE = {
    "соединение": "conjunction",
    "оппозиция": "opposition",
    "трин": "trine",
    "квадрат": "square",
    "секстиль": "sextile",
}
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class AstrologyInputError(ValueError):
    """Raised when an astrology request cannot be interpreted safely."""


class AstrologyOutputError(ValueError):
    """Raised when the backend returns an unsafe or internally inconsistent chart."""


@dataclass(frozen=True)
class ChartRequest:
    """Canonicalized request passed to the Kerykeion calculator."""

    birth_date: date
    birth_time: tuple[int, int] | None
    original_birth_time: str | None
    city: str | None
    lat: float | None
    lon: float | None
    tz: str | None
    coordinates_known: bool
    location_reason: str
    coordinate_source: str
    coordinate_confidence: float | None
    timezone_source: str
    local_time_status: str
    candidate_instants: tuple[str, ...]
    ambiguity_mode: str
    time_confirmed: bool
    precision_reason: str
    active_points: tuple[str, ...]

    @property
    def precision(self) -> str:
        if self.local_time_status == "ambiguous" and self.ambiguity_mode == "interval":
            return "interval"
        if self.time_confirmed and self.coordinates_known:
            return "exact"
        if self.time_confirmed:
            return "time_without_location"
        return "date_only"

    @property
    def angular_data_available(self) -> bool:
        return bool(self.time_confirmed and self.coordinates_known and self.tz)

    @property
    def effective_time(self) -> tuple[int, int]:
        """Technical noon for date snapshots; never reported as birth time."""
        return self.birth_time or (12, 0)

    @property
    def fingerprint(self) -> str:
        payload = {
            "engine_adapter_version": ENGINE_ADAPTER_VERSION,
            "configuration_fingerprint": self.configuration_fingerprint,
            "birth_date": self.birth_date.isoformat(),
            "birth_time": self.birth_time,
            "city": self.city,
            "lat": self.lat,
            "lon": self.lon,
            "tz": self.tz,
            "coordinates_known": self.coordinates_known,
            "location_reason": self.location_reason,
            "coordinate_source": self.coordinate_source,
            "coordinate_confidence": self.coordinate_confidence,
            "timezone_source": self.timezone_source,
            "local_time_status": self.local_time_status,
            "candidate_instants": self.candidate_instants,
            "ambiguity_mode": self.ambiguity_mode,
            "time_confirmed": self.time_confirmed,
            "precision_reason": self.precision_reason,
            "active_points": self.active_points,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]

    @property
    def configuration_fingerprint(self) -> str:
        config = CalculationConfig(active_points=self.active_points, aspect_policy=ASPECT_POLICY).as_dict()
        return configuration_fingerprint(config)

    def metadata(self) -> dict[str, Any]:
        return {
            "adapter_version": ENGINE_ADAPTER_VERSION,
            "request_fingerprint": self.fingerprint,
            "configuration_fingerprint": self.configuration_fingerprint,
            "location_reason": self.location_reason,
            "coordinate_source": self.coordinate_source,
            "coordinate_confidence": self.coordinate_confidence,
            "timezone_source": self.timezone_source,
            "local_time_status": self.local_time_status,
            "candidate_instants": list(self.candidate_instants),
            "ambiguity_mode": self.ambiguity_mode,
            "precision_state": self.precision,
            "original_birth_time": self.original_birth_time,
            "uncertainty": {
                "kind": ("ambiguous_local_time" if self.local_time_status == "ambiguous"
                         else "nonexistent_local_time" if self.local_time_status == "nonexistent"
                         else "none"),
                "candidate_instants": list(self.candidate_instants),
                "angular_data_available": self.angular_data_available,
            },
        }


class OracleKerykeionEngine:
    """Request boundary and bounded result cache around the Kerykeion backend."""

    def __init__(self, *, max_cache_entries: int = 256) -> None:
        self.max_cache_entries = max(1, int(max_cache_entries))
        self._cache: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _coordinates_known(lat: float | None, lon: float | None) -> bool:
        if lat is None or lon is None:
            return False
        try:
            lat_value, lon_value = float(lat), float(lon)
        except (TypeError, ValueError):
            return False
        return (
            math.isfinite(lat_value)
            and math.isfinite(lon_value)
            and -90 <= lat_value <= 90
            and -180 <= lon_value <= 180
        )

    @staticmethod
    def _validate_timezone(tz: str | None) -> None:
        if tz is None or tz == "":
            return
        if not isinstance(tz, str):
            raise AstrologyInputError("Часовой пояс указывается как корректный IANA identifier")
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, TypeError, ValueError) as exc:
            raise AstrologyInputError("Часовой пояс указывается как корректный IANA identifier") from exc

    @staticmethod
    def _parse_time(value: str | None) -> tuple[int, int] | None:
        if value in (None, ""):
            return None
        if not isinstance(value, str):
            raise AstrologyInputError("Время рождения указывается в формате ЧЧ:ММ")
        value = value.strip()
        if not _TIME_RE.fullmatch(value):
            raise AstrologyInputError("Время рождения указывается в формате ЧЧ:ММ")
        hour, minute = value.split(":")
        return int(hour), int(minute)

    @staticmethod
    def _local_time_status(parsed_date: date, parsed_time: tuple[int, int] | None, tz: str | None) -> str:
        if parsed_time is None:
            return "not_applicable"
        if not tz:
            return "no_timezone"
        zone = ZoneInfo(tz)
        naive = datetime.combine(parsed_date, time(*parsed_time))
        candidates = [naive.replace(tzinfo=zone, fold=fold) for fold in (0, 1)]
        valid = [
            candidate.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == naive
            for candidate in candidates
        ]
        if not any(valid):
            return "nonexistent"
        if all(valid) and candidates[0].utcoffset() != candidates[1].utcoffset():
            return "ambiguous"
        return "normal"

    def normalize(
        self,
        birth_date: str,
        birth_time: str | None,
        city: str | None,
        lat: float | None,
        lon: float | None,
        tz: str | None,
        *,
        time_known: bool | None = None,
        coordinate_source: str | None = None,
        coordinate_confidence: float | None = None,
        timezone_source: str | None = None,
        ambiguity_mode: str = "safe_date_only",
        active_points: tuple[str, ...] = (),
    ) -> ChartRequest:
        try:
            parsed_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
        except (TypeError, ValueError) as exc:
            raise AstrologyInputError("Дата рождения указывается в формате YYYY-MM-DD") from exc
        normalized_time = birth_time.strip() if isinstance(birth_time, str) else birth_time
        normalized_tz = tz.strip() if isinstance(tz, str) else tz
        normalized_city = " ".join(city.split()) if isinstance(city, str) and city.strip() else None
        parsed_time = self._parse_time(normalized_time)
        self._validate_timezone(normalized_tz)
        if ambiguity_mode not in {"safe_date_only", "interval"}:
            raise AstrologyInputError("Режим неоднозначного времени должен быть safe_date_only или interval")
        if coordinate_source is not None and coordinate_source not in {
            "user", "manual", "geocoder", "builtin", "neutral_reference", "unknown",
        }:
            raise AstrologyInputError("Источник координат не распознан")
        if coordinate_confidence is not None:
            try:
                coordinate_confidence = float(coordinate_confidence)
            except (TypeError, ValueError) as exc:
                raise AstrologyInputError("Уверенность координат должна быть числом от 0 до 1") from exc
            if not math.isfinite(coordinate_confidence) or not 0 <= coordinate_confidence <= 1:
                raise AstrologyInputError("Уверенность координат должна быть числом от 0 до 1")
        local_time_status = self._local_time_status(parsed_date, parsed_time, normalized_tz)
        coordinates_known = self._coordinates_known(lat, lon)
        normalized_lat = float(lat) if coordinates_known else None
        normalized_lon = float(lon) if coordinates_known else None
        location_reason = (
            "valid" if coordinates_known else
            "missing" if lat is None and lon is None else
            "partial_or_invalid"
        )
        coordinate_source = coordinate_source or ("unknown" if coordinates_known else "neutral_reference")
        timezone_source = timezone_source or ("provided" if normalized_tz else "missing")
        candidate_instants: tuple[str, ...] = ()
        if parsed_time and normalized_tz and local_time_status in {"normal", "ambiguous"}:
            zone = ZoneInfo(normalized_tz)
            naive = datetime.combine(parsed_date, time(*parsed_time))
            candidates = [naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc).isoformat()
                          for fold in ((0, 1) if local_time_status == "ambiguous" else (0,))]
            candidate_instants = tuple(candidates)
        time_confirmed = bool(
            parsed_time and time_known is not False and normalized_tz
            and local_time_status == "normal"
        )
        precision_reason = (
            "exact" if time_confirmed and coordinates_known else
            "time_without_location" if time_confirmed else
            "date_only_nonexistent_local_time" if local_time_status == "nonexistent" else
            "date_only_ambiguous_local_time" if local_time_status == "ambiguous" else
            "date_only_missing_timezone" if parsed_time and not normalized_tz else
            "date_only_unconfirmed" if parsed_time else
            "date_only"
        )
        return ChartRequest(
            birth_date=parsed_date,
            birth_time=parsed_time if time_confirmed else None,
            original_birth_time=normalized_time,
            city=normalized_city,
            lat=normalized_lat,
            lon=normalized_lon,
            tz=normalized_tz,
            coordinates_known=coordinates_known,
            location_reason=location_reason,
            coordinate_source=coordinate_source,
            coordinate_confidence=coordinate_confidence,
            timezone_source=timezone_source,
            local_time_status=local_time_status,
            candidate_instants=candidate_instants,
            ambiguity_mode=ambiguity_mode,
            time_confirmed=time_confirmed,
            precision_reason=precision_reason,
            active_points=tuple(active_points),
        )

    def calculate(
        self,
        request: ChartRequest,
        calculator: Callable[[ChartRequest], dict[str, Any]],
        validator: Callable[[ChartRequest, dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Run or retrieve a calculator result and return a defensive copy.

        ``validator`` is deliberately applied to both fresh and cached results;
        cache hits must not bypass output-integrity checks.
        """
        cached = self._cache.get(request.fingerprint)
        if cached is not None:
            result = copy.deepcopy(cached)
            if validator is not None:
                validator(request, result)
            return result
        result = calculator(request)
        if not isinstance(result, dict):
            raise TypeError("astrology calculator must return an object")
        if validator is not None:
            validator(request, result)
        self._cache[request.fingerprint] = copy.deepcopy(result)
        if len(self._cache) > self.max_cache_entries:
            self._cache.pop(next(iter(self._cache)))
        return copy.deepcopy(result)

    def clear_cache(self) -> None:
        self._cache.clear()


def validate_chart_result(request: ChartRequest, result: dict[str, Any]) -> None:
    """Validate canonical Kerykeion output before it reaches API, UI or LLM.

    The validator is intentionally conservative: a malformed backend response is
    downgraded by ``astro.compute_chart`` to bounded Sun-only fallback rather than
    being partially persisted or interpreted.
    """
    if result.get("mode") != "full":
        raise AstrologyOutputError("astrology backend returned an unexpected mode")
    expected_precision = request.precision
    if result.get("precision") != expected_precision:
        raise AstrologyOutputError("backend precision disagrees with normalized request")
    calculation = result.get("calculation")
    if not isinstance(calculation, dict):
        raise AstrologyOutputError("backend calculation metadata is missing")
    if bool(calculation.get("angular_data_available")) != request.angular_data_available:
        raise AstrologyOutputError("backend angular-data state disagrees with request")

    def finite(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))

    def point_is_valid(point: Any, label: str, *, require_house: bool = False) -> None:
        if not isinstance(point, dict):
            raise AstrologyOutputError(f"{label} is not an object")
        if not isinstance(point.get("name", label), str) or not point.get("sign"):
            raise AstrologyOutputError(f"{label} has no canonical name or sign")
        for key in ("deg_exact", "abs_deg_exact"):
            if not finite(point.get(key)):
                raise AstrologyOutputError(f"{label}.{key} is not finite")
        if not 0 <= float(point["deg_exact"]) < 30:
            raise AstrologyOutputError(f"{label}.deg_exact is outside sign bounds")
        if not 0 <= float(point["abs_deg_exact"]) < 360:
            raise AstrologyOutputError(f"{label}.abs_deg_exact is outside zodiac bounds")
        if require_house and not isinstance(point.get("house"), int):
            raise AstrologyOutputError(f"{label}.house is missing")
        if require_house and not 1 <= point["house"] <= 12:
            raise AstrologyOutputError(f"{label}.house is outside 1..12")
        if not request.angular_data_available and point.get("house") is not None:
            raise AstrologyOutputError(f"{label}.house is exposed without angular precision")

    planets = result.get("planets")
    if not isinstance(planets, list) or len(planets) != 10:
        raise AstrologyOutputError("backend returned an unexpected planet inventory")
    names = [point.get("name") if isinstance(point, dict) else None for point in planets]
    if len(set(names)) != len(names) or any(name is None for name in names):
        raise AstrologyOutputError("backend returned duplicate or unnamed planets")
    for point in planets:
        point_is_valid(point, str(point.get("name", "planet")), require_house=request.angular_data_available)

    nodes = result.get("nodes") or []
    for point in nodes:
        point_is_valid(point, str(point.get("name", "node")), require_house=request.angular_data_available)
    north = next((point for point in nodes if str(point.get("name", "")).startswith("Раху")), None)
    south = next((point for point in nodes if str(point.get("name", "")).startswith("Кету")), None)
    if north and south:
        node_delta = abs(float(north["abs_deg_exact"]) - float(south["abs_deg_exact"])) % 360
        node_delta = min(node_delta, 360 - node_delta)
        if abs(node_delta - 180.0) > 1e-6:
            raise AstrologyOutputError("true lunar nodes are not opposite")
    for point in result.get("additional_points") or []:
        point_is_valid(point, str(point.get("name", "point")), require_house=request.angular_data_available)

    houses = result.get("houses") or []
    if request.angular_data_available:
        if len(houses) != 12 or [house.get("n") for house in houses] != list(range(1, 13)):
            raise AstrologyOutputError("backend house inventory or ordering is invalid")
        for house in houses:
            if not isinstance(house, dict) or not finite(house.get("deg_exact")):
                raise AstrologyOutputError("backend house cusp is invalid")
            if not 0 <= float(house["deg_exact"]) < 30:
                raise AstrologyOutputError("backend house cusp is outside sign bounds")
    elif houses:
        raise AstrologyOutputError("backend exposed houses without angular precision")

    if request.angular_data_available:
        for key in ("ascendant", "mc"):
            point_is_valid(result.get(key), key)
    elif result.get("ascendant") is not None or result.get("mc") is not None:
        raise AstrologyOutputError("backend exposed angles without angular precision")

    for aspect in result.get("aspects") or []:
        if not isinstance(aspect, dict):
            raise AstrologyOutputError("backend returned an invalid aspect")
        code = aspect.get("code") or _ASPECT_LABEL_TO_CODE.get(aspect.get("aspect"))
        if code not in ASPECT_ORBS:
            raise AstrologyOutputError("backend returned an unsupported aspect")
        if not finite(aspect.get("orb_exact")) or float(aspect["orb_exact"]) > ASPECT_ORBS[code] + 1e-9:
            raise AstrologyOutputError("backend aspect orb exceeds the public policy")


ENGINE = OracleKerykeionEngine()
