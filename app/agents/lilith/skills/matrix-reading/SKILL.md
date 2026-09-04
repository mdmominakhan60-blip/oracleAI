---
name: matrix-reading
description: Read deterministic Matrix of Destiny values through position, resource, shadow and choice without fate claims.
version: 2.0.0
license: Proprietary
compatibility: OracleAI file-backed agent harness.
requires_tools:
  - get_matrix
  - suggest_practice
tags:
  - matrix
  - arcana
  - destiny
  - position
  - reflective_choice
metadata:
  oracleai_agent: lilith
  oracleai_domain: self-reflection, Matrix of Destiny, diary, memory and practices
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Matrix Reading

## Purpose

Use this skill when the user asks about the Matrix of Destiny, arcana, purpose, lines, resources, shadows, family themes or a interpretive choice connected to a birth date. The number and position returned by `get_matrix` are deterministic outputs of the project's declared digit-reduction method; the meaning is a traditional interpretive interpretation, not a scientific diagnosis or a fixed description of the person.

## Evidence contract

Call `get_matrix` before making a concrete Matrix claim. Build a ledger containing the exact position name, numeric value, arcana label, returned meaning and any neighbouring positions included by the tool. Never infer an absent position from the date or from a familiar arcana story. If no birth date is available, say so and request only the date; do not manufacture a Matrix.

Keep three layers separate: **calculated value**, **traditional correspondence**, and **user-confirmed experience**. The value can support a question about a theme, but it cannot prove a trait, trauma, vocation, family debt or future event.

## Position synthesis

Start with the position the user actually asked about. For a broad reading, use no more than three positions and give each a role: resource/available capacity, shadow/overused or avoided expression, and choice/next experiment. Explain relationships between positions only when the payload exposes them; do not claim that one arcana causes another.

For a “purpose” question, translate destiny language into present agency: “a theme you can explore now” rather than “your mission”. For money, career, health or relationships, use the Matrix only to frame questions and observable behaviours; never produce a guaranteed outcome or a high-stakes recommendation.

## Counter-hypothesis protocol

For every strong interpretation, include an alternative explanation grounded in ordinary context: learning history, current workload, social expectations, chance or the user's own stated values. Ask which explanation better fits a recent concrete example. Reject universal statements such as “you are strong but doubt yourself” unless the user supplies specific evidence.

## Memory and practice integration

Do not call memory tools unless the user has opted in and the current question genuinely needs a previously saved fact. Do not save an arcana label, diagnosis or emotional state as a durable fact. If a practice is useful, call `suggest_practice` only after naming the Matrix evidence and offer one small, reversible action rather than a ritual obligation.

## Output shape

Return: **Matrix evidence** (position, number, arcana, method), **traditional reading** (resource/shadow/choice where relevant), **alternative explanation**, **one observable question**, and optionally **one gentle practice**. Name the limitation that Matrix is a traditional framework and invite the user to accept, reject or refine the interpretation.

## Safety

Do not present Matrix as validated psychology, medical assessment, legal/financial advice, proof of past lives or certainty about another person's thoughts. Do not predict death, illness, pregnancy, wealth, marriage, job loss or inevitable success. At a crisis signal, follow the global safety protocol before this skill.
