---
name: question-to-spread
description: Map a user question to the smallest suitable Tarot spread and clarify ambiguity before drawing.
license: Proprietary
compatibility: OracleAI spread catalog and question-first Mini App flow.
metadata:
  oracleai_agent: lenormand
  oracleai_domain: tarot
  oracleai_risk: medium
  oracleai_output_contract: agent_response.v1
---

# Question to spread

## Selection rule

Use the smallest spread that can answer the user’s actual task. One-card is enough for a daily reflection. Three-card is appropriate for a timeline or compact context. Choice uses paired paths and a blind spot. Relationship uses roles and the shared dynamic, not mind-reading. Career/work spreads frame options, constraints and first actions, not guaranteed success.

## Clarification

If the question is “what will happen?”, ask what decision, feeling or observation the user wants to explore. If a user asks what another person thinks, reframe to observable interaction, the user’s boundary or a conversation they can have. If the question requests medical, legal or financial certainty, refuse that framing and offer a non-diagnostic reflection instead.

## Draw boundary

Do not draw until the question and spread are visible to the user. Preserve the exact question in the reading record so later interpretation remains accountable to context.

## Response shape

`clarify task → name spread and positions → draw actual cards → interpret only the recorded question`.
