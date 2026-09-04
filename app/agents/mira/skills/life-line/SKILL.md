---
name: life-line
version: 1.1.0
description: Read a visible life-line pattern using traditional palmistry without lifespan or health claims.
license: Proprietary
compatibility: OracleAI palm evidence schema.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner
  oracleai_output_contract: agent_response.v1
---

# Life Line

## Required sequence

1. Call `palm_scanner` and inspect `lines.life` plus any matching observation.
2. Confirm visibility, evidence_state, confidence, hand side and image quality.
3. Describe the visible arc, continuity, depth/prominence, breaks or branches only when supported.
4. Apply traditional palmistry symbolism as a hypothesis, not as a fact.
5. End with one reflective question or one user-controlled next step.

## Traditional reading cues

The life line traditionally relates to vitality, grounding and how broadly a person engages with life. A clear deep arc may be framed as strong traditional symbolism around available energy; islands or interruptions may be discussed as periods traditionally associated with strain or change. These meanings are symbolic and should never be presented as medical evidence.

## Hard limits

Never infer lifespan, mortality, disease, disability, pregnancy, fertility, trauma, age or danger. Never say that a shorter line means a shorter life. A faint/missing line is a visibility limitation, not a trait.

## Response shape

`quality → visible life-line evidence → traditional possibility → limitation → one reflection question`.
