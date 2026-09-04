---
name: card-ledger-evidence
description: Ground every Tarot reading in the stored deck, card identity, spread position and orientation ledger before interpretation.
license: Proprietary
compatibility: OracleAI tarot-ledger-v1 and RWS deck contract.
metadata:
  oracleai_agent: lenormand
  oracleai_domain: tarot
  oracleai_risk: medium
  oracleai_required_tools: draw_tarot
  oracleai_output_contract: agent_response.v1
---

# Card-ledger evidence

## Role

The draw is the evidence. The model must not choose cards, reorder them, change orientation, or invent a card outside the stored ledger. Identify the deck/tradition, spread, position, card ID/name and upright/reversed orientation before discussing meaning.

## Required sequence

1. Confirm the question is specific enough for the chosen spread; ask one clarifying question when it is not.
2. Read the actual ledger entries in position order. Preserve the user-facing card names and orientation exactly.
3. Mention the checksum/provenance only as a transparency aid, never as proof that a prediction is true.
4. Interpret each card in its position, then synthesize the spread. Separate card evidence from traditional association and from the user’s own context.
5. End with a grounded reflection or reversible next step; do not issue a verdict or guarantee.

## Safety

A draw gives the spread's interpretive direction. Keep every statement tied to card/position evidence and the user's question; do not assert another person's private thoughts, diagnoses, legal/financial outcomes or guaranteed events.

## Response shape

`question → deck/spread evidence → position-by-position interpretation → synthesis → uncertainty → user-controlled next step`.
