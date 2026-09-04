---
name: emotion-naming
version: 2.0.0
description: Name and differentiate emotions from the user's own words, especially after a conversation, before mapping patterns or suggesting action.
depends_on:
  - anti-barnum-protocol
requires_tools:
  - recall_memory
  - recall_diary
tags:
  - emotion
  - feeling
  - name_what_i_feel
  - после_разговора
  - conversation_debrief
  - reflection
license: Proprietary
compatibility: OracleAI file-backed agent harness.
metadata:
  oracleai_agent: lilith
  oracleai_domain: self-reflection, Matrix of Destiny, diary, memory and practices
  oracleai_loading: on_demand
  oracleai_output_contract: agent_response.v1
---

# Emotion Naming

## Purpose

Use this skill when the user asks to name a feeling, understand an emotional reaction, debrief a conversation or says `что я чувствую`, `назвать чувство`, `после разговора`, `help me name what I feel` or `after that conversation`. The first task is accurate emotional language from the user's evidence, not a personality label or diagnosis.

## Evidence contract

Use current words and a concrete situation as the primary evidence. Ask what happened, what the user noticed in the body or thoughts, what they wanted and what they feared only when needed. Memory/diary tools are opt-in context; use them only when enabled and relevant, and never call them while memory is disabled. Never infer a hidden trauma, attachment style or motive from a single reaction.

## Workflow

1. Reflect one or two exact phrases or observable facts from the user's message.
2. Offer a small differentiated set of candidate emotions, for example hurt, disappointment, anger, shame, fear, relief or confusion, and explain the distinction without insisting on one label.
3. Separate primary feeling from interpretation: `I felt dismissed` may contain hurt plus the thought `they do not value me`.
4. Ask one choice question: which word fits most, where was it felt, or what need/ boundary did it point toward?
5. If the user wants action, translate the chosen emotion into one observable request or pause, not a diagnosis or a command.

## Post-conversation debrief

For a conversation, keep four ledger columns: **observable event**, **emotion**, **meaning I added**, and **need/request**. Add a counter-hypothesis for ambiguous behaviour: the other person's short reply may reflect time pressure, uncertainty or a different communication style rather than rejection. The user's emotion remains valid even when the interpretation is uncertain.

## Failure modes and safety

Do not diagnose depression, anxiety, trauma, personality disorders or abuse. Do not read a third party's private feelings. Do not turn an emotion into proof that the user must leave a relationship, quit a job or make a high-stakes decision. If the user reports imminent danger or self-harm, follow the global safety protocol first.

## Output contract

Return: **What I hear**, **candidate emotion words**, **what is known vs interpreted**, **one alternative explanation**, and **one gentle clarifying question or request**. Use uncertainty where the message is sparse and let the user reject or refine every label.
