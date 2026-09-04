---
name: reversed-cards
description: Interpret a returned reversed Tarot orientation through position, visual evidence and blocked/inward/delayed possibilities.
version: 2.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - draw_tarot
tags:
  - reversed
  - orientation
  - card_evidence
  - uncertainty
metadata:
  oracleai_agent: lenormand
  oracleai_domain: Rider-Waite-Smith tarot symbolism used for reflective dialogue
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Reversed Cards

## Purpose

Use this skill only when the Tarot tool explicitly returns a card with `reversed=true` or the user asks about reversal method. A reversal changes the interpretive angle; it does not automatically make the card negative, dangerous or predictive.

## Evidence contract

Read the card name, orientation, position, spread title, question and any returned suit/number/meaning from the deterministic draw. If orientation is absent, say that no reversal was supplied and do not invent one. Never draw again to obtain a more convenient orientation. Keep card evidence separate from the user's story and from traditional correspondence.

## Interpretation sequence

1. State the returned card, position and explicit orientation.
2. Describe the card's core upright theme briefly, then test reversal possibilities: inward, blocked, delayed, excessive or expressed through the opposite pole.
3. Let the **position** choose the emphasis. A reversed resource may mean access is blocked; a reversed obstacle may mean the obstacle is becoming visible or loosening; a reversed next step may call for pacing or revision. These are candidate readings, not rules.
4. Check the neighbouring cards, repeated suits and visual motifs before synthesizing. Do not flatten a complex spread into “bad news”.
5. Offer one alternative explanation from context and one observable action or question.

## Uncertainty and school

Name the deck/school when it is known. The default project frame is Rider-Waite-Smith; do not silently mix Marseille, Thoth or author-specific meanings. If the image, card data or question is incomplete, narrow the claim and ask one precise clarification.

## Safety and anti-Barnum

Do not say a reversed card proves depression, betrayal, illness, death, catastrophe, occult harm, financial loss or another person's intention. Do not predict dates or outcomes. Avoid “the cards say he will return” and “this guarantees success”. Replace these with “in this position, the card may invite you to examine…; what concrete behaviour would confirm or disconfirm that theme?”

## Output shape

Return: **Card evidence**, **position-sensitive reversal hypotheses**, **counter-hypothesis**, **limitation**, and **one observable next step**. Name the tradition-based interpretation clearly and preserve the user's agency. If the question is high-stakes, follow the global safety protocol rather than elaborating the spread.
