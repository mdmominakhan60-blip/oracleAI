---
name: palm-technique-triangulation
description: Compare Western, Indian and Chinese palmistry lenses without blending their terminology or treating any school as factual science.
license: Proprietary
compatibility: OracleAI palm evidence schema and safety contract.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner
  oracleai_output_contract: agent_response.v1
---

# Palm-technique triangulation

## Purpose

Different palmistry schools use overlapping names but not identical rules. When a user asks for “all techniques”, first state which visual feature is shared and then separate the interpretive lens: Western chiromancy, Indian Hasta Samudrika vocabulary, or Chinese hand-reading terminology. Do not present the comparison as scientific validation.

## Method

Call `palm_scanner` once for the common evidence packet. Keep the observation invariant across traditions: visible path, position, continuity, depth, shape, hand side and confidence. Then give at most one short lens per requested tradition, with a label such as `Western tradition`, `Indian tradition` or `Chinese tradition`. If the schools disagree, preserve the disagreement instead of averaging it into a stronger claim.

## Required caveats

School-specific claims are tradition-based correspondences; keep them within the observed feature and safety boundary. Avoid claims about health, fate, age, marriage count, fertility, wealth, sexuality or fixed personality. Left/right-hand conventions vary across teachers; report the actual side only if the evidence says it and explain that the meaning is school-dependent.

## Response shape

`shared visual evidence → selected school lens → alternative school lens (if requested) → disagreement/uncertainty → reflective next step`.
