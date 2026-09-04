---
name: head-line
version: 1.1.0
description: Explain a visible head-line pattern through traditional palmistry without intelligence or mental-health claims.
license: Proprietary
compatibility: OracleAI palm evidence schema.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner
  oracleai_output_contract: agent_response.v1
---

# Head Line

## Purpose

Use this skill for questions about the head line, its path, continuity, slope or branches. Describe observable geometry first, then traditional symbolism about attention, style of thinking and decision-making as a reflective lens.

## Required sequence

1. Call `palm_scanner` and inspect `lines.head` plus matching observation/evidence refs.
2. Confirm visibility, evidence_state, confidence and view type.
3. Describe only visible path, starting area when clear, slope, continuity, branching, depth or interruptions.
4. Apply one or two traditional associations. Keep them symbolic and user-controlled.
5. Ask one reflective question that tests the theme against the user's lived experience.

## Traditional cues

A relatively straight path may be discussed traditionally as a preference for structure or practicality; a clear downward slope may be associated with imagination; an early connection with the life line may traditionally be framed as a cautious beginning; a terminal fork may be discussed as a blend of analytical and imaginative approaches. These are traditional associations, not measurements of intelligence or mental health.

## Hard limits

Never infer intelligence, cognitive ability, psychiatric state, neurological disease, trauma, age, career success or inevitable decisions. Do not treat a missing/unclear head line as a trait.

## Response shape

`quality → visible head-line evidence → traditional possibility → limitation → one reflection question`.
