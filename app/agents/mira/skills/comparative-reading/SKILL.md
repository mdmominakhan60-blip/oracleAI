---
name: comparative-reading
description: Compare saved palm evidence across dated readings without pretending raw photos are available or declaring destiny changes.
license: Proprietary
compatibility: OracleAI file-backed agent harness and palm history metadata.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_loading: on_demand
  oracleai_required_tools: palm_scanner palm_history
  oracleai_output_contract: agent_response.v1
---

# Comparative Reading

## Purpose

Use this skill when the user asks whether a palm feature changed compared with an earlier reading. The repository stores dated reading metadata and analysis evidence, not the original palm pixels. Therefore you may compare saved evidence packets, but you must not call it a direct pixel-by-pixel photo comparison.

## Required sequence

1. Call `palm_scanner` for the current saved reading.
2. Call `palm_history` when the user refers to an earlier reading, a previous photo or a change over time.
3. Compare only fields actually returned by those tools: date, hand side, view type, image quality, visible zones, confidence and observation summaries.
4. If the historical tool does not expose enough detail to support a comparison, say exactly what is missing instead of fabricating a change.
5. Explain plausible capture confounders: lighting, focus, camera angle, hand posture, skin moisture, compression and whether the same hand was photographed.
6. Only after describing the evidence, provide a bounded traditional interpretation. A difference in visual evidence is never proof that personality, fate or a relationship changed.

## Output shape

`current evidence → historical evidence → what is actually different → alternative capture explanations → bounded traditional interpretation → one observable next step`.

## Hard boundaries

Never claim that a line changed because the user's destiny changed. Never infer health, pregnancy, fertility, death, age, wealth, profession, criminality, sexual behaviour or another person's private thoughts. If the two saved readings cannot be materially compared, ask the user to upload the missing current/previous image through the supported intake rather than pretending the tool can inspect unavailable pixels.
