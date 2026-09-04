---
name: combination-synthesis
description: Synthesize adjacent Tarot cards, orientation tension and suit/arcana patterns into a bounded traditional narrative.
license: Proprietary
compatibility: OracleAI tarot-ledger-v1 adjacent combination rules.
metadata:
  oracleai_agent: lenormand
  oracleai_domain: tarot
  oracleai_risk: medium
  oracleai_required_tools: draw_tarot
  oracleai_output_contract: agent_response.v1
---

# Combination synthesis

## Method

Read the spread as a sequence, not as isolated dictionary entries. Start with adjacent pairs from `adjacent_combinations`, then check repeated suit, major/minor balance, repeated orientation and the semantic role of each position. A combination is a traditional cue such as `same_suit_cluster` or `orientation_tension`; translate it into the spread's present theme and next step.

## Counter-reading

For every strong-sounding synthesis, provide one alternative reading grounded in a different feature of the ledger. For example, a difficult card next to a hopeful card can indicate tension and resource, not inevitable loss. Do not resolve ambiguity by inventing facts about the user or another person.

## Position discipline

A card’s meaning depends on its spread position. Do not move a “future” card into the present, and do not turn an advice position into a factual outcome. Reversed cards modify or block a traditional expression; they do not mean the opposite automatically.

## Safety

Never state that combinations prove an event, reveal someone’s mind, diagnose a condition or determine a legal/financial choice. Keep the reading reflective, contextual and user-controlled.

## Response shape

`adjacent pair evidence → pattern (suit/arcana/orientation) → position-aware synthesis → counter-reading → grounded question`.
