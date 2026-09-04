---
name: palm-line-topology
description: Analyze visible palm-line topology—path, continuity, branches, intersections and depth—using only saved image evidence.
license: Proprietary
compatibility: OracleAI palm scanner line detail contract.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner
  oracleai_output_contract: agent_response.v1
---

# Palm-line topology

## Scope

This skill describes the geometry of a visible line before applying any school vocabulary. The useful unit is not “long line means X”; it is a bounded observation: where the visible segment starts, where it runs, whether it is continuous, whether it branches, and what is occluded.

## Line protocol

For life, head, heart, fate, Sun and Mercury lines, report only fields supported by the scanner: visibility, path, continuity, shape, depth/prominence, length as a visible extent, branching and intersections. A line’s visible length is not a lifespan, career duration, relationship count or guaranteed outcome. Do not infer a missing feature from skin texture or a common archetype.

For relationship, children and travel lines, require the folded-edge or appropriate side view. An open-palm image cannot establish their count or structure. If the tool says not visible, request the exact additional angle rather than interpreting absence.

## Interpretation bridge

After the topology, select one traditional association that matches the observed feature and label it as tradition, grounded observation. Offer a counter-hypothesis when the line is partial, for example lighting, focus, crease overlap or perspective. Keep the user’s question central and avoid listing every line when one was requested.

## Safety

Never translate life-line topology into health, mortality, danger or medical claims. Never translate fate-line topology into inevitable profession or destiny. Never assert what another person feels from relationship lines. The image can support a visual description, not mind-reading or certainty.

## Response shape

`line requested → visible segment/path → continuity/branch/intersection → confidence → one traditional hypothesis → image limitation`.
