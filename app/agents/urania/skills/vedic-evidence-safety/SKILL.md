---
name: vedic-evidence-safety
description: Enforce evidence-first, date-only and non-diagnostic safety rules across all Vedic workflows.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_vedic_chart
dependencies:
  - vedic-foundations
tags:
  - evidence
  - provenance
  - safety
  - anti_barnum
  - date_only
  - безопасность
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic evidence governance
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Vedic evidence and safety

Every concrete Vedic claim must be traceable to a returned deterministic field. Separate the answer into calculated evidence, traditional interpretation, uncertainty/limitations and an observable next step. If a tool fails or a field is absent, say so instead of filling the gap.

For date-only or unconfirmed-time inputs, never state lagna, houses, house lordship or exact time-dependent conclusions. Keep Western and Vedic conventions visibly separate. Never expose hidden chain-of-thought; user-facing proof may contain tool name, method, inputs, timestamp and limitations only.

Avoid Barnum language and certainty. Traditional astrology must not be presented as medical, psychological, legal, financial or safety diagnosis, and must not predict death, illness, pregnancy, guaranteed wealth, court outcomes or another person’s thoughts.
