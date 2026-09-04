---
name: image-quality-protocol
version: 1.1.0
description: Assess palm-photo focus, lighting, framing, resolution and view coverage before interpretation.
depends_on:
  - anti-barnum-protocol
requires_tools: palm_scanner palm_photo_guide
tags: ['image', 'quality']
license: Proprietary
compatibility: OracleAI palm evidence schema and capture precheck.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# image-quality-protocol

## Purpose

Use this skill when the user asks whether a palm photo is good enough, why a reshoot was requested, or how to photograph a missing zone. This skill evaluates capture quality; it must not turn low-quality pixels into a palmistry interpretation.

## Required sequence

1. Call `palm_scanner` to inspect the saved quality/evidence state.
2. Read `image_quality`, `visual_precheck`, `photo_assessment`, `requires_view` and limitations.
3. Separate objective capture issues from semantic hand/line detection. Precheck measures conditions such as brightness, contrast, edge sharpness and crop; it does not prove a hand or palm line exists.
4. If another angle is required, call `palm_photo_guide` and give one concrete reshoot recipe.
5. Do not promise that a better score guarantees a successful reading; it only improves capture conditions.

## Quality checklist

Check focus/sharpness, lighting and glare, full framing, visible wrist/fingertips, single-hand framing, and correct open/folded view. Treat a low-resolution, clipped, overexposed, underexposed or blurred frame as a capture problem, not a personality signal.

## Output

`quality findings → quality gate → exact reshoot instruction → what the next photo enables`.

Never guess what a blurred line means. Never claim health, age, fertility, death, future or character from capture artifacts.
