---
name: values-conflict
version: 2.0.0
description: Map a real choice such as stability versus an exciting project to explicit values, trade-offs, constraints and a user-owned experiment.
depends_on:
  - anti-barnum-protocol
requires_tools:
  - recall_memory
  - recall_diary
tags:
  - values
  - decision
  - choice
  - stability
  - exciting_project
  - trade_off
  - option_a_vs_b
  - выбор
license: Proprietary
compatibility: OracleAI file-backed agent harness.
metadata:
  oracleai_agent: lilith
  oracleai_domain: self-reflection, Matrix of Destiny, diary, memory and practices
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Values Conflict

## Purpose

Use this skill when the user is choosing between options, comparing stability and an exciting project, weighing `option A vs option B`, or asking for a trade-off analysis. The objective is not to choose for the user; it is to make the user's values, constraints and uncertainty visible enough for a reversible next step.

## Evidence contract

Use only values and constraints stated by the user. Capture each option, desired benefit, feared cost, non-negotiable constraint, time horizon and unknown. Memory/diary may be recalled only with consent and only to surface a previously stated durable value or constraint; it must never become a hidden vote for one option.

## Workflow

1. Restate the choice neutrally: `stability` versus `learning/adventure`, or the actual terms the user used.
2. Build a two-column trade-off map: what each option protects, enables and costs.
3. Separate reversible from irreversible steps and identify the smallest information-gathering experiment.
4. Add a counter-hypothesis: the apparent values conflict may be a capacity, timing, money, safety or information problem rather than a deep identity conflict.
5. Ask which criterion is non-negotiable and propose a decision rule owned by the user.

## Quality and safety

Do not label a preference as personality, destiny or fear of success. Do not make the final decision, predict career/financial outcomes or give legal/medical advice. For high-stakes money, employment or safety questions, provide criteria and suggest qualified professional input rather than certainty.

## Output contract

Return: **Choice as stated**, **values/constraints**, **trade-off table**, **unknowns and counter-hypothesis**, **reversible experiment**, and **one clarifying question**. Use the user's language where possible and let the user accept, reject or reorder the criteria.
