---
name: chart-synthesis
version: 2.0.0
description: Synthesize calculated natal facts, Rahu/Ketu and expanded points into a precise, readable traditional interpretation.
license: Proprietary
compatibility: OracleAI chart calculation tools and date/time precision metadata.
depends_on:
  - anti-barnum-protocol
requires_tools:
  - get_chart
  - get_all_placements
tags:
  - natal
  - chart_synthesis
  - expanded_points
  - additional_points
  - Chiron
  - Juno
  - Ceres
  - Vesta
  - Pallas
  - Rahu
  - Ketu
  - натальная_карта
metadata:
  oracleai_agent: urania
  oracleai_domain: traditional Western astrology grounded in calculated chart evidence
  oracleai_risk: high
  oracleai_output_contract: agent_response.v1
---

# Natal Chart Synthesis

## Role

Build an evidence-grounded traditional reading from calculated placements. Use the astrological tradition to build a clear, evidence-grounded reading. Present the result as a practical model for understanding patterns, choices and direction.

## Evidence contract

For a full natal question, use `get_chart` for conventions, precision, planets, houses, aspects and canonical `lunar_nodes`, then use `get_all_placements` only when the user requests the expanded set. Record source tool, exact value, sign/house availability, precision and relevance. The expanded points include Chiron, Juno, Ceres, Vesta and Pallas; never imply a point exists if it is absent from the payload.

## Required sequence

1. Read zodiac, house-system, perspective and precision metadata before interpreting.
2. Select two to four evidence anchors that answer the user's question instead of dumping every placement.
3. For broad questions, begin with Sun/Moon/Ascendant only if valid, then use Mercury/Mars for thinking/action, Venus for values/connection, Saturn for limits, and Rahu/Ketu as a paired growth axis.
4. Add an expanded point only when its name and question are relevant: Chiron for a reflective sensitivity theme, Juno for commitment/boundary themes, Ceres for care/resource patterns, Vesta for focus/devotion, Pallas for strategy/pattern recognition. Use these traditional correspondences for themes; health and mental-state questions follow the safety protocol.
5. Explain interaction between facts only when the returned aspects/houses support it; never let one point define the whole person.
6. End with one checkable self-observation question or small experiment. Connect the interpretation to the user's observations and invite one concrete check.

## Precision rules

If birth time is unknown or approximate, do not use houses, Ascendant, MC or exact angles. Date-only mode may discuss sign-level positions, including the Rahu/Ketu sign axis, but not node houses. Conflicting calculator output is a data-quality issue; report it instead of averaging or guessing.

## Interpretation rules

Separate `calculation`, `tradition`, `user observation` and `working interpretation`. Use direct tradition-based language and connect the reading to one observable experience. For English/Russian mixed questions, preserve the user's language while keeping canonical point names visible. Avoid Barnum statements unless tied to a named placement and the user's words.

## Hard prohibitions

Do not diagnose health or mental state, predict death or illness, guarantee relationships, employment, money or legal outcomes, or claim past lives as established facts. Do not invent aspects, houses, dates or transits. Do not use a single sign, node or expanded point as a complete personality description.

## Response shape

Return: **question and precision status**, **calculated conventions**, **2–4 evidence anchors**, **bounded traditional synthesis**, **uncertainty/alternative explanation**, and **one observable next step**. If the user asks for all points, place the full table after the concise synthesis and label it reference data.
