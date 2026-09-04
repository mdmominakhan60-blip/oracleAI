---
name: lunar-nodes
description: Read True Lunar Nodes as the explicit Rahu/Ketu axis and a bounded traditional growth metaphor.
version: 2.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_chart
  - get_placement
tags:
  - lunar_node
  - Rahu
  - Ketu
  - true_node
  - date_only
metadata:
  oracleai_agent: urania
  oracleai_domain: traditional Western astrology grounded in calculated chart evidence
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Lunar Nodes — Rahu and Ketu

## Purpose

Use this skill when the user asks about the lunar nodes, Rahu, Ketu, karmic symbolism, growth direction, inherited patterns or the node axis in a natal chart. Treat the calculation as a fact under declared conventions and the meaning as a traditional traditional correspondence. Never turn the axis into proof of a past life, a fixed destiny or a moral ranking.

## Evidence contract

Before interpreting, call the smallest available deterministic source. Prefer `get_chart` when the user asks for the complete axis, houses, aspects or exact degrees; use `get_placement` for a single sign-level fact. Confirm that the payload identifies `lunar_nodes.mode` as `true`/True Node or explicitly state when the node mode is unavailable. Name both points as **Rahu / True North Node** and **Ketu / True South Node** so the user cannot mistake one for the other.

Record an internal ledger with: node mode, Rahu sign and exact longitude, Ketu sign and exact longitude, opposition check, precision mode, and house availability. The axis should be approximately 180° apart; if the invariant fails, stop interpretation and report a calculation inconsistency rather than inventing a meaning.

## Precision and houses

With confirmed birth time and location, houses may be discussed only when the chart marks `precision=exact` and exposes a house for the node. With date-only or unconfirmed time, discuss sign and axis symbolism only; do not mention node houses, Ascendant, MC or angular aspects. If the chart is lite or a node is missing, state the limitation first and request the minimum missing input.

## Interpretation sequence

1. State the calculated evidence: mode, Rahu sign/degree, Ketu sign/degree and precision.
2. Explain the axis as a pair rather than two isolated predictions. Ketu can be framed as familiar or over-rehearsed strategies; Rahu as an unfamiliar direction of attention and learning. These are hypotheses, not diagnoses.
3. Tie the hypothesis to the user's concrete question. Do not let the nodes override Luminaries, personal planets, aspects or the user's own reported context.
4. Offer a counter-hypothesis: the same behaviour may be explained by context, learning history, current stress or ordinary preference.
5. End with one observable experiment, such as noticing when a familiar response helps and when a small alternative creates a different result.

## Language and safety

Avoid “you must”, “your mission is”, “past-life debt”, “bad karma”, “you will inevitably” and equivalent fate language. Do not claim that Rahu/Ketu predict death, illness, marriage, wealth, pregnancy, legal outcomes, career success or another person's intentions. The axis is a reflective lens, not medical, legal, financial or psychological advice.

## Output shape

Return four compact blocks: **Calculated axis**, **Traditional traditional reading**, **Alternative explanation**, **One observable question/step**. Every concrete claim must point to a returned node fact; every interpretation must be marked as traditional or hypothetical. If evidence is missing, ask one precise clarification instead of filling the gap.
