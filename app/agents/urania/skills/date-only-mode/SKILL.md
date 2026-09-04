---
name: date-only-mode
description: Handle unknown or approximate birth time by restricting houses, Ascendant, MC and node-house claims to supported precision.
version: 2.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_chart
tags:
  - date_only
  - unknown_birth_time
  - approximate_time
  - no_houses
  - Rahu_house
  - Ketu_house
  - journal
metadata:
  oracleai_agent: urania
  oracleai_domain: traditional Western astrology grounded in calculated chart evidence
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Date Only Mode

## Purpose

Use this skill when the user says the birth time is unknown, missing, approximate, uncertain or not recorded (`no birth time`, `date-only`, `время рождения неизвестно`, `без времени`, `примерное время`). It protects the user from false precision rather than trying to complete a chart by guesswork.

## Evidence contract

Use `get_chart` only with the precision mode supported by the input. Record date, location quality, timezone status and whether the payload marks `precision=date_only` or `precision=approximate`. Treat the absence of time as evidence that houses, Ascendant, MC and time-sensitive angles are not determinable. If the engine returns a house despite date-only input, do not repeat it as fact; report a contract inconsistency.

## Workflow

1. Confirm whether the time is fully unknown or approximate and whether the location/timezone is reliable.
2. State what remains usable: cautious sign-level positions and slow-object themes when they are not near a sign boundary.
3. State what is unavailable: houses, Ascendant, MC, house rulers, exact angles and **Rahu/Ketu houses**. Rahu and Ketu may be named by sign/axis only when the node payload is present.
4. Ask one precise clarification only if it changes the calculation, such as an approximate time range or a timezone/location correction.
5. If the user wants a reflective reading, keep it traditional and label the uncertainty prominently.

## Failure modes

Never infer a birth time from personality, life events, a screenshot or a prior generic reading. Never average two possible houses or silently fall back to a default timezone. Do not claim that a node is in a specific house from date-only data. If the date itself is missing or invalid, stop and request it.

## Output shape

Return four blocks: **Data quality**, **Allowed reading**, **Unavailable precision**, and **Next clarification**. For a node question, use the explicit phrase `Rahu/Ketu sign axis available; Rahu/Ketu houses unavailable in date-only mode` when applicable. Do not fill missing data with certainty.

## Safety and traditional boundary

A date-only chart cannot diagnose health, determine a relationship outcome, guarantee career or financial events, or establish another person's intent. Astrology is a traditional framework; calculated positions are not causal proof. Every interpretation must remain a bounded hypothesis that the user may accept, reject or test through real observations.
