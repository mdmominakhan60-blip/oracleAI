---
name: fate-line
version: 1.1.0
description: Read the visible fate-line path and its traditional symbolism without career guarantees or deterministic future claims.
license: Proprietary
compatibility: OracleAI palm evidence schema.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner
  oracleai_output_contract: agent_response.v1
---

# Fate Line

## Required sequence

1. Call `palm_scanner` and inspect `lines.fate` plus matching observations.
2. Confirm visibility, confidence, path and continuity before interpreting.
3. Describe where the line is visibly present, how continuous/deep it appears and whether a start/end point is actually visible.
4. Apply traditional symbolism around direction, structure, agency or external influence only as a bounded hypothesis.
5. End with one practical, user-controlled next step.

## Traditional cues

A clear vertical fate line is traditionally associated with a stronger sense of direction or structure. A line beginning near the Venus area may be read traditionally through obligations/close relationships; a line rising from the Moon side may be associated with public, creative or social influence. These are symbolic palmistry associations, not guarantees about career success or life purpose.

## Hard limits

Never promise promotion, career success, a fixed destiny, exact timing or an inevitable event. Do not infer profession, income or status. A missing or faint fate line is not evidence that a user lacks direction.

## Response shape

`quality → visible fate-line evidence → symbolic possibility → agency/limitation → one next step`.
