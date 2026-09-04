---
name: vimshottari-dasha
description: Calculate and interpret Vimshottari Mahadasha and bounded Antardasha timeline.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_vimshottari_dasha
tags:
  - dasha
  - vimshottari
  - mahadasha
  - antardasha
  - timeline
  - даша
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic planetary-period timeline
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Vimshottari Dasha

Use when the user asks about Mahadasha, Antardasha, planetary periods or Vedic life timing. Call `get_vimshottari_dasha` and report the Moon nakshatra, starting lord, balance at birth, as-of date and current period exactly from the evidence payload.

The timeline requires a confirmed birth time. If time is missing or unconfirmed, explain why a precise dasha start cannot be asserted and request the minimum input. Validate that periods are chronological, contiguous and tied to the declared 120-year cycle before interpretation.

Interpret periods as a traditional lens for themes, priorities and reflective planning. Never convert a dasha into a guaranteed marriage, death, illness, wealth, legal or career event. Offer practical questions and reversible experiments; the user retains agency.
