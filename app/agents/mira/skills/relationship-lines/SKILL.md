---
name: relationship-lines
description: Read relationship and marriage-line evidence only from the correct edge-of-hand view; never infer marriage count, fertility or partner outcomes.
license: Proprietary
compatibility: OracleAI palm evidence schema and folded-edge capture workflow.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner palm_photo_guide
  oracleai_output_contract: agent_response.v1
---

# Relationship Lines

## Purpose

Use this skill for questions about relationship/marriage lines, children lines or related edge-of-hand features. These zones require a folded-hand / edge-of-hand capture. Never infer a count of marriages, children, fertility or a partner's future behaviour.

## Required sequence

1. Call `palm_scanner` first.
2. Inspect `photo_assessment.view_type`, `lines.relationship`, and the relevant `requires_view` / limitation fields.
3. If the view is not `folded_edge`, call `palm_photo_guide` and stop the interpretation. Say clearly that the needed edge is not visible on the current frame.
4. If the folded-edge view exists, report only explicitly visible lines and their confidence. Never count faint marks that are not clearly classified as relationship-line evidence.
5. Apply only traditional symbolic associations after the visual observation; label them as tradition.

## Children-line boundary

Children lines are fine vertical marks associated traditionally with relationship lines. The system must not count them or convert them into predictions about number of children, fertility, pregnancy or parenthood. They may be described only as a traditional observation about fine markings when clearly visible.

## Response shape

`current view → visible edge evidence → traditional possibility → limitation → one next question or precise reshoot instruction`.
