---
name: capture-rectification
description: Decide whether a palm capture has the view, orientation and quality needed for the requested palmistry zone.
license: Proprietary
compatibility: OracleAI palm-precheck-v1, photo assessment and palm guide.
metadata:
  oracleai_agent: mira
  oracleai_domain: palmistry
  oracleai_risk: high
  oracleai_required_tools: palm_scanner palm_photo_guide
  oracleai_output_contract: agent_response.v1
---

# Capture and rectification

## Capture decision tree

First check the deterministic precheck and the stored `photo_assessment`. A full open palm can support major-line, mount, finger and hand-shape observations. A folded edge view is required for many relationship/marriage, children and edge-of-hand travel-line questions. Never infer a side view from an open-palm photo.

Second check orientation and hand side. If side is unknown, say unknown; do not guess left/right from the viewer’s perspective. If the palm is tilted, partially cropped, blurred, overexposed or occluded by jewelry, report the limitation and request a new image rather than “correcting” it imaginatively.

Third, call `palm_photo_guide` when the requested zone is missing. Give one concrete instruction: one hand, whole frame, relaxed fingers, even light, no filter, camera parallel to palm; for edge-only lines, bend the fingers and show the little-finger edge.

## Boundary

Rectification can improve framing and perspective; it cannot create hidden skin lines. Capture quality and hand landmarks are evidence about the image, not a diagnosis, biometric identity or prediction.

## Response shape

`requested zone → view sufficiency → measurable quality → proceed or reshoot → exact next photo instruction`.
