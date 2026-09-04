---
name: graha-strengths
description: Present bounded sign-dignity strengths with formula/version metadata, not an unverified full Shadbala claim.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_vedic_chart
  - get_graha_strengths
dependencies:
  - vedic-foundations
tags:
  - graha_strength
  - dignity
  - shadbala
  - exaltation
  - debilitation
  - сила планет
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic sign dignity evidence
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Graha strengths

Call `get_graha_strengths` only after obtaining Vedic Lahiri placements. State `dignity-lite-v1`, show the returned sign status and bounded score, and explicitly say this is not full Shadbala. Do not imply that exaltation guarantees success or debilitation guarantees failure.

Interpret the result as one traditional lens among many. Balance each strength with context, aspects, divisional evidence and the user’s own observations. No medical, legal, financial or deterministic life-event conclusions are allowed.
