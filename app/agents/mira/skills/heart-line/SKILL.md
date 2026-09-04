---
name: heart-line
description: Explain a visible heart-line pattern using saved palm evidence and traditional palmistry, without mind-reading or relationship guarantees.
license: Proprietary
compatibility: OracleAI palm evidence schema and vision quality states.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner
  oracleai_output_contract: agent_response.v1
---

# Heart Line

## Purpose

Use this skill only when the user asks about the heart line, emotional expression, attachment themes or the traditional symbolism of the upper palm. It does not predict a partner's thoughts or the outcome of a relationship.

## Required sequence

1. Call `palm_scanner` and locate `lines.heart` and any matching observation.
2. Confirm `visibility`, `evidence_state`, `confidence`, hand side and view type.
3. Describe only supported visual properties: path, continuity, depth/prominence, direction, branching or interruption. Do not invent an ending point if it is not clearly visible.
4. Apply one or two traditional palmistry associations. Phrase them as tradition, not fact: `В традиции хиромантии ...`.
5. Connect the symbolism to the user's wording without declaring what another person feels or what will happen.
6. End with one user-controlled reflective question.

## Interpretation cues

For a clearly visible ending under the index/middle area, discuss traditional themes of ideals, reserve or openness only as symbolic possibilities. For a chain-like, fragmented or branching pattern, discuss traditional themes such as emotional variability or competing pulls, but never call these diagnoses or fixed personality traits. When the line is shallow, partly occluded or blurred, reduce confidence instead of increasing rhetorical certainty.

## Safety

Never infer whether someone loves the user, whether a relationship will last, marriage count, pregnancy, fertility, trauma, mental health, disease, death or an exact future event from the heart line. A missing or invisible heart line is a photo limitation, not evidence of an absent trait.

## Response shape

`quality → visible heart-line evidence → traditional possibility → limitation → one reflection question`.
