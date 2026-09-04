---
name: hand-side-context
version: 1.1.0
description: Identify the photographed hand when evidence supports it and explain left/right traditions without treating them as universal laws.
license: Proprietary
compatibility: OracleAI palm evidence schema.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner
  oracleai_output_contract: agent_response.v1
---

# Hand Side Context

## Required sequence

1. Call `palm_scanner` and read `hand_side` plus confidence/quality context.
2. Report left/right only when the evidence supports it; otherwise say unknown.
3. Explain that classical palmistry schools use different left/right conventions. Do not present one convention as a biological or universal truth.
4. Keep the photographed hand distinct from the hand the user describes in words if they conflict; ask for clarification rather than silently choosing.

## Response shape

`which hand is supported → what the tradition says about that convention → explicit non-universality → one clarifying question`.

Never turn hand side into destiny, innate character, health, age or relationship certainty.
