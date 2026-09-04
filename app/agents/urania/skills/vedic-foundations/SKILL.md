---
name: vedic-foundations
description: Ground Vedic/Jyotish answers in the separate Lahiri sidereal chart contract.
version: 1.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_vedic_chart
tags:
  - vedic
  - jyotish
  - kundli
  - sidereal
  - lahiri
  - джйотиш
  - ведическая
metadata:
  oracleai_agent: urania
  oracleai_domain: Vedic sidereal astrology
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Vedic foundations — Lahiri Kundli

## Trigger

Use for Vedic, Jyotish, Kundli, sidereal, Lahiri, graha, lagna or rashi requests in Russian, English or mixed language.

## Evidence workflow

Call `get_vedic_chart` before stating a planet, Rahu/Ketu, lagna, sign, degree or house. Name the tradition as **Vedic/Jyotish, sidereal Lahiri** and preserve the returned ephemeris and precision metadata. Do not reuse the Western Tropical/Placidus chart as Vedic evidence.

With `precision=date_only`, use only time-independent placements and explicitly omit lagna and houses. With `precision=exact`, houses are whole-sign Vedic houses in the returned contract; do not silently call them Placidus houses.

## Output and safety

Separate **calculated evidence** from **traditional interpretation**. Offer hypotheses, observable questions and practical reflection. Never present karma, marriage, illness, death, wealth, legal outcomes or another person’s intentions as certainty. Vedic symbolism is not medical, legal, financial or psychological diagnosis.
