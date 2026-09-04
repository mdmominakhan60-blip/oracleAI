---
name: lunar-phases
version: 2.0.0
description: Use calculated lunar phase cycles as a bounded reflective planning and observation-journal lens.
depends_on:
  - anti-barnum-protocol
requires_tools:
  - get_chart
  - get_all_placements
tags:
  - moon
  - lunar_phase
  - cycles
  - лунные_фазы
  - дневник
  - journal
  - week
  - weekly_tracking
license: Proprietary
compatibility: OracleAI file-backed agent harness.
metadata:
  oracleai_agent: urania
  oracleai_domain: traditional Western astrology grounded in calculated chart evidence
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Lunar Phases

## Purpose

Use this skill for questions about the New Moon, Full Moon, waxing/waning phases, lunar cycles, weekly planning, a moon journal or observation tracking (`лунные фазы`, `дневник наблюдений`, `неделя`, `journal`, `weekly tracking`). The phase is a calculated astronomical timestamp/context; the traditional association is a reflective planning lens, not a forecast of mood, fertility or events.

## Evidence contract

Use the smallest deterministic source that returns phase, date/time and timezone. Keep a ledger with calculated phase, relevant date window, the user's stated goal, observed behaviour and unknowns. If the question asks for a week, define the start/end window instead of giving an unbounded prediction. If no date or timezone is available, ask one clarification.

## Workflow

1. Confirm the requested window: today, a named week or a specific lunar event.
2. State the calculated phase and the relevant local date/time when available.
3. Translate the traditional phase association into a low-pressure planning option, such as starting, reviewing, resting or releasing; do not treat it as an instruction.
4. Build a simple observation journal with date, expectation, actual observation and alternative explanation.
5. At the end of the window, compare hits and misses. Do not cherry-pick events that fit the symbolism and ignore the rest.

## Domain-specific failure modes

Do not promise that a phase will cause a relationship event, money result, fertility change, energy level or emotional state. Do not convert a phase into an exact appointment recommendation without real-world constraints. A lunar phase may be discussed alongside a natal chart only when the chart evidence is actually available and the two evidence classes remain separate.

## Output contract

Return: **Calculated phase/window**, **traditional planning lens**, **journal template**, **counter-hypothesis**, and **one observable step**. Explicitly label the phase as calculated and the meaning as traditional/traditional. If the user asks for a guaranteed prediction, refuse that part and offer an observation-based alternative.
