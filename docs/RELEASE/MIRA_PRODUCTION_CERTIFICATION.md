# Mira Production Certification

## Executive Summary

Mira now has a single production intake path for Telegram palm media, a canonical RGB/JPEG image contract, one request-local capture precheck, process-local MediaPipe reuse, adaptive ONNX line inference and explicit failure classification. The existing evidence/interpretation contract remains the source of truth for semantic safety.

## Current Failure

The pre-fix implementation repeated capture prechecks through downstream CV adapters, created a MediaPipe detector inside each analysis call, always evaluated the FP16+INT8 line ensemble, accepted Telegram photos through the legacy handler only, and mapped several vision/provider failures to a generic `needs_photo` result.

## Root Causes

The dominant causes were pipeline ownership rather than prompt wording: image normalization and precheck were embedded in a legacy service, CV adapters independently re-opened the image, model lifecycle was request-scoped, and structured-output errors shared the same recovery state as bad captures.

## Architecture

Target runtime:

```text
Telegram photo/document
        ↓
Palm Intake
        ↓
PalmImage (canonical RGB JPEG ≤1280)
        ↓
CapturePrecheck (once/request)
        ↓
MediaPipe hand geometry
        ↓
Full-scope candidate evidence
        ↓
FP16 line evidence → INT8 only on uncertainty
        ↓
Vision adjudication
        ↓
validated canonical evidence
        ↓
Mira interpretation
        ↓
result
```

## Telegram Intake

`app.bot.palm` accepts both Telegram `photo` and image `document` messages and forwards both through the same `palm_core.analyze_and_save` entrypoint. Unsupported document MIME types receive explicit feedback instead of falling through silently. The new handler acknowledges receipt before expensive work.

## Palm Image Pipeline

`PalmImage` records raw and normalized SHA-256 values, normalized bytes, dimensions, MIME/format, original dimensions and the shared precheck result. Images are EXIF-transposed, converted to RGB and encoded as canonical JPEG, with processing side capped at 1280.

Oversized, malformed, unsupported and objectively poor captures are rejected before expensive CV/vision work.

## CV Engines

The existing CV modules retain their semantic boundaries: MediaPipe produces hand geometry, full-scope produces candidate evidence/view hints, and line segmentation remains auxiliary CV evidence. The runtime wrapper does not convert those signals into palmistry meaning.

## MediaPipe

`app/core/palm/mediapipe_runtime.py` provides a process-local singleton detector with a lock around lifecycle and inference. The detector is created once per model path and reused across requests; concurrent access is serialized because the binding is not assumed thread-safe.

## ONNX

The production wrapper runs FP16 first. INT8 is evaluated only when the FP16 result is empty/uncertain. For folded-edge views the principal-line ONNX model is not run because that model is outside its useful geometry domain.

## Evidence

Existing CV boundary normalization remains in the legacy service. The production wrapper preserves the rule that uncertainty/absence is explicit and downstream interpretation cannot turn missing visual evidence into observed facts.

## Vision Provider Matrix

| Provider | Vision | Strict JSON schema | Multiple images | Tool calling | Live verified |
|---|---:|---:|---:|---:|---:|
| Anthropic | configured in code | adapter path exists | provider/model dependent | yes | NO |
| OpenAI | configured in code | adapter path exists | provider/model dependent | yes | NO |
| Custom OpenAI-compatible | configurable | implementation-dependent | implementation-dependent | implementation-dependent | NO |

The repository exposes a common LLM abstraction, but live provider capability verification requires real credentials/model endpoints. No capability is claimed here as externally proven.

## JSON Reliability

The current pipeline already performs local JSON extraction and normalization. The production runtime caps Palm JSON attempts at one initial structured request plus one repair request (`PALM_JSON_ATTEMPTS = 2`). A schema failure remains distinguishable from a bad capture through explicit `VISION_SCHEMA_INVALID` classification.

## Parsing

Provider content is parsed as data and normalized before persistence. Fenced JSON and deterministic syntax cleanup are handled by the existing parser; arbitrary provider text is not persisted as canonical evidence.

## Interpretation

The existing separation is preserved: CV and vision describe observable evidence; Mira's interpretation layer is responsible for traditional meaning and reflective framing. No medical or fatalistic claim is produced from absent/uncertain evidence.

## Agent Routing

The existing agent routing remains responsible for domain selection. Palm-specific Telegram media is now intercepted by the dedicated palm intake router before the legacy feature router, preventing duplicate presentation paths.

## UX

The user receives an immediate acknowledgement and explicit recovery. Vision/schema failure is presented as a technical reading failure rather than a demand to reshoot a good image. Unsupported documents are explicitly rejected with JPEG/PNG/WebP guidance.

## Performance

The intended architecture removes duplicate precheck work, avoids unconditional dual ONNX inference, and reuses MediaPipe initialization. Exact latency targets still require live measurement. Required instrumentation should continue to be tracked per the acceptance budget in the project gauntlet.

## Cost

The main cost win is avoiding unnecessary second-model inference and avoiding repeated vision retries. The existing LLM usage accounting remains the accounting source. Live billing verification is still external.

## Billing

No new charge path was introduced by this hardening layer. Existing product billing remains outside the Palm runtime. Double-charge verification requires end-to-end live payment tests.

## Security

No raw image bytes, base64 payloads or provider responses are added to logs by the new modules. The canonical contract exposes hashes and bounded metadata. Provider capabilities are not guessed by the adapter layer.

## Privacy

The runtime uses in-memory normalization and temporary detector input files. It does not intentionally persist raw image content. Golden fixtures should continue to use synthetic, public, licensed or consented images only.

## Failure Injection

The added taxonomy covers bad/unsupported images, multiple/no hand, CV unavailability and structured vision failures. Live failure injection for Telegram/network/provider/database still requires environment access.

## Test Matrix

Added automated unit coverage for canonical image construction, JPEG normalization, original-dimension preservation, unsupported MIME rejection, FP16-only stable inference, and separation of vision schema failure from photo-quality failure.

The project acceptance matrix still requires live checks for Telegram photo/document events, provider timeout/schema behavior, CV/ONNX availability, duplicate requests and billing.

## Golden Fixtures

No private user photos were added. Representative fixtures should be synthetic/public/licensed/consented in the next test-data gate.

## Before / After

| Area | Before | After |
|---|---|---|
| Image | raw bytes reused by multiple engines | canonical RGB JPEG contract |
| Precheck | repeated by service/CV adapters | request-local shared cache |
| MediaPipe | detector per call | process-local singleton + lock |
| ONNX | FP16 + INT8 on every ensemble call | FP16 first, INT8 only on uncertainty |
| Telegram | photo handler path | photo + image document unified intake |
| Errors | several failures surfaced as `needs_photo` | explicit error taxonomy |
| JSON retries | 3 attempts | 1 initial + 1 repair |
| UX | generic reshoot on some technical failures | stage-specific recovery |

## Remaining External Gates

1. Real Telegram photo and document smoke tests.
2. Live provider capability matrix with the production model chain.
3. 5/10/20 concurrent palm requests with CPU/RAM/latency measurements.
4. Failure injection for real provider timeout, schema rejection and DB failure.
5. Live billing/idempotency verification.
6. Golden fixture evaluation on representative palm captures.

## Final Verdict

**PASS WITH EXTERNAL LIVE VERIFICATION**.

The code path now implements the requested production hardening, but this repository session cannot truthfully claim live Telegram/provider/load/billing verification. Those gates must pass in the deployment environment before the release is treated as fully production-certified.
