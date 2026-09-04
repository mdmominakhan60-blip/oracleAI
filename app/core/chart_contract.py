"""Versioned canonical contract for deterministic natal-chart calculations.

The calculation engine remains in ``astro.py``. This module owns the explicit
product conventions and the metadata contract returned with every chart so that
UI, LLM and PDF consumers never infer settings from library defaults.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import importlib.metadata
import json
from typing import Any

CHART_CONTRACT_VERSION = 2
CONFIGURATION_SCHEMA_VERSION = 1
ORACLE_ENGINE_NAME = "OracleAI Engine"
ORACLE_ENGINE_ADAPTER_VERSION = "oracleai-kerykeion-engine-v2"
KERYKEION_VERSION = "5.12.9"
EPHEMERIS_BACKEND = "Kerykeion"
EPHEMERIS_NAME = "Swiss Ephemeris"


def _package_version(name: str, fallback: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return fallback


def runtime_versions() -> dict[str, str]:
    """Return versions that can change numerical or timezone semantics."""
    return {
        "kerykeion": _package_version("kerykeion", KERYKEION_VERSION),
        "swiss_ephemeris": _package_version("pyswisseph", "unknown"),
        "tzdata": _package_version("tzdata", "system-zoneinfo"),
    }

ASPECT_ANGLES: dict[str, float] = {
    "conjunction": 0.0,
    "opposition": 180.0,
    "trine": 120.0,
    "square": 90.0,
    "sextile": 60.0,
}

# Product policy is intentionally explicit and independently testable. Kerykeion
# supplies the Swiss Ephemeris positions; this layer decides what is exposed.
ASPECT_ORBS: dict[str, float] = {
    "conjunction": 8.0,
    "opposition": 8.0,
    "trine": 8.0,
    "square": 7.0,
    "sextile": 6.0,
}

ASPECT_POLICY = {
    "included": tuple(ASPECT_ANGLES),
    "angles": dict(ASPECT_ANGLES),
    "orbs_deg": dict(ASPECT_ORBS),
    "scope": "major aspects between active planets/points and angles",
}


@dataclass(frozen=True)
class CalculationConfig:
    """All choices that can change the meaning of a natal chart."""

    zodiac_type: str = "Tropical"
    house_system: str = "P"
    house_system_name: str = "Placidus"
    perspective_type: str = "Apparent Geocentric"
    node_mode: str = "true"
    node_mode_label: str = "True Node"
    ephemeris_engine: str = "Swiss Ephemeris via Kerykeion"
    active_points: tuple[str, ...] = ()
    aspect_policy: dict[str, Any] | None = None
    node_policy: str = "true_lunar_nodes_plus_true_lilith"
    precision_policy: str = "precision-state-v2"

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["active_points"] = list(self.active_points)
        data["aspect_policy"] = self.aspect_policy or ASPECT_POLICY
        data["runtime_versions"] = runtime_versions()
        data["configuration_schema_version"] = CONFIGURATION_SCHEMA_VERSION
        return data


def configuration_fingerprint(config: dict[str, Any]) -> str:
    """Hash every calculation-affecting setting, not presentation metadata."""
    encoded = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def build_calculation_metadata(*, active_points: list[str] | tuple[str, ...],
                               input_data: dict[str, Any],
                               precision: str,
                               angular_data_available: bool) -> dict[str, Any]:
    """Build serializable metadata without mutating calculated values."""
    config = CalculationConfig(
        active_points=tuple(active_points),
        aspect_policy=ASPECT_POLICY,
    )
    config_dict = config.as_dict()
    return {
        "contract_version": CHART_CONTRACT_VERSION,
        "configuration_fingerprint": configuration_fingerprint(config_dict),
        "config": config_dict,
        "input": dict(input_data),
        "precision": precision,
        "angular_data_available": bool(angular_data_available),
        "values": {
            "rounded_for_ui": True,
            "exact_fields_suffix": "_exact",
            "longitude_unit": "degrees",
            "orb_unit": "degrees",
        },
    }


def public_calculation_contract(chart: dict[str, Any]) -> dict[str, Any]:
    """Return the stable subset exposed to downstream clients."""
    metadata = chart.get("calculation") or {}
    config = metadata.get("config") or {}
    input_data = metadata.get("input") or {}
    adapter_version = input_data.get("adapter_version", ORACLE_ENGINE_ADAPTER_VERSION)
    return {
        "contract_version": metadata.get("contract_version", CHART_CONTRACT_VERSION),
        "engine": config.get("ephemeris_engine", chart.get("engine")),
        "engine_provenance": {
            "product_engine": ORACLE_ENGINE_NAME,
            "adapter_version": adapter_version,
            "backend": EPHEMERIS_BACKEND,
            "backend_version": KERYKEION_VERSION,
            "ephemeris": EPHEMERIS_NAME,
            "license_notice": "AGPL-3.0/commercial licensing obligations apply to the selected distribution model.",
        },
        "zodiac_type": config.get("zodiac_type", chart.get("zodiac_type")),
        "house_system": config.get("house_system", chart.get("house_system")),
        "house_system_name": config.get("house_system_name", chart.get("house_system_name")),
        "perspective_type": config.get("perspective_type", chart.get("perspective_type")),
        "node_mode": config.get("node_mode", chart.get("lunar_nodes", {}).get("mode", "true")),
        "active_points": list(config.get("active_points") or []),
        "aspect_policy": config.get("aspect_policy") or ASPECT_POLICY,
        "input": input_data,
        "precision": metadata.get("precision", chart.get("precision")),
        "angular_data_available": bool(metadata.get("angular_data_available")),
    }
