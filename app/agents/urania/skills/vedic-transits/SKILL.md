---
name: vedic-transits
description: Read current or as-of-date sidereal Lahiri transit positions without mixing Western transits.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_vedic_transits
tags:
  - vedic_transits
  - gochara
  - transit
  - sidereal
  - транзиты
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic sidereal transits
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Vedic transits / Gochar

Call `get_vedic_transits` for the requested as-of date and identify the Lahiri sidereal tradition, UTC calculation date, ephemeris and returned positions. Do not merge these values with the Western Tropical transit tool or imply that a transit alone determines an event.

Use transit positions to frame themes, timing questions and practical preparation. Mention uncertainty from exact birth inputs and the traditional nature of interpretation. Never predict death, illness, legal outcomes, guaranteed wealth, marriage or another person’s actions.
