---
name: nakshatra-pada
description: Explain Moon or graha nakshatra, pada and lord from deterministic Lahiri longitude.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_vedic_chart
  - get_nakshatra
tags:
  - nakshatra
  - pada
  - lunar_mansion
  - moon
  - накшатра
  - пада
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic lunar mansion evidence
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Nakshatra and pada

Call the chart tool for a graha longitude or `get_nakshatra` when the user supplies a longitude. Confirm the 0–360° range, the nakshatra span and pada number before interpreting. At exact boundaries preserve the implementation’s half-open interval rule and do not round a longitude before classification.

Report graha, sidereal longitude, nakshatra, pada and ruling planet as calculated facts. Explain the traditional correspondence as a hypothesis and distinguish the Moon’s nakshatra from a planet’s nakshatra. Nakshatra language must not become personality diagnosis, fate, guaranteed compatibility or prediction.

For unknown birth time, use only placements robust to the declared snapshot and state that a time change may move fast points or house-dependent conclusions. Ask one clarification when the user has not supplied the longitude or birth data required for the requested point.
