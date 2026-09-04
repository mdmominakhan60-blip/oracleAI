---
name: varga-charts
description: Read the documented D1, D9 and D10 Vedic divisional chart subset.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_vedic_chart
  - get_varga_chart
dependencies:
  - vedic-foundations
tags:
  - varga
  - divisional_chart
  - navamsa
  - dasamsa
  - d1
  - d9
  - d10
  - варга
  - навамша
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic divisional charts
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Varga charts

Use `get_vedic_chart` first, then `get_varga_chart` for the requested supported code: D1/Rasi, D9/Navamsa or D10/Dasamsa. State the method version and the fact that divisional-chart schools can differ. Never call D1, D9 or D10 “20+ vargas”; unsupported codes must be refused transparently.

Do not calculate houses or lagna-dependent divisional conclusions when birth time is unknown. Present placements as evidence, then give a bounded traditional interpretation tied to the user’s question. Do not make deterministic claims about marriage, career, wealth or life events from a varga alone.
