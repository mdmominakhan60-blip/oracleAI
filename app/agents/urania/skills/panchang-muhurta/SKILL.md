---
name: panchang-muhurta
description: Use local Panchang, sunrise/sunset and Rahu Kaal for criteria-based planning.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_panchang
  - get_rahu_kaal
  - get_muhurta
tags:
  - panchang
  - tithi
  - vara
  - yoga
  - karana
  - muhurta
  - rahu_kaal
  - панчанг
  - мухурта
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic calendar and criteria-based timing
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Panchang, Rahu Kaal and Muhurta

Call `get_panchang` for the requested local date and coordinates, and `get_rahu_kaal` only when the user asks about that interval. Report timezone, coordinates, sunrise/sunset and the calculation timestamp. Do not substitute the Western moon-week tool for a Vedic Panchang.

For comparing dates, call `get_muhurta` with the user’s explicit criterion and show both candidate inputs and the reason for any preference. A preferred date is only a transparent traditional planning signal; it is never “guaranteed auspicious”, a prohibition or a substitute for practical constraints.

If location or timezone is missing, ask for it rather than fabricating local times. Avoid medical, legal, financial or safety-critical recommendations based on Panchang symbolism.
