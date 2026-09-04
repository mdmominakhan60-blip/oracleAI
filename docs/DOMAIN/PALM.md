# OracleAI Palm / Mira Evidence Contract

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Define what the palm surface can observe, retain and explain. |
| **Source of truth** | `app/core/palm/`, `app/core/palm_vision.py`, `app/core/palm_lines.py`, `app/core/palm_full_scope.py` and `app/api/routers/placements.py`. |
| **Scope** | Upload validation, capture quality, geometry/vision evidence, normalization, persistence and user-facing limitations. |
| **Do not change** | Do not retain raw uploads or raw masks as product evidence, accept unbounded file input, or present palm observations as diagnosis or guaranteed prediction. |
| **Validation** | `pytest -q tests/test_palm_vision.py tests/test_palm_integration.py tests/test_placements_palm.py tests/test_palm_gauntlet.py`. |

## Purpose and epistemic boundary

Palm/Mira is a **visual reflection over a photograph**, not medical diagnosis, identity recognition or prediction of a fixed future. The image is evidence; vision-model text and Mira’s interpretation are not evidence by themselves.

> Главный инвариант: `UNKNOWN` никогда не преобразуется в `OBSERVED`.

Each statement follows `IMAGE → OBSERVABLE EVIDENCE → QUALITY/CONFIDENCE → STRUCTURED EVIDENCE → INTERPRETATION → REFLECTIVE NEXT STEP`. If one stage lacks sufficient support, the result is downgraded, marked as a limitation or returned as `needs_photo`.

## Evidence pipeline

The current path is layered: upload MIME/size validation and image normalization, capture-quality precheck, MediaPipe geometry where configured, ONNX line evidence, bounded OpenCV full-scope candidate search, optional focus views, vision adjudication, strict JSON normalization and a final Mira explanation over normalized observations. Candidate edges, masks, landmarks and model confidence never become semantic line identities automatically.

The supported view matters. An open-palm image must not silently be treated as evidence for a folded-edge zone. Low-quality, incomplete and multi-hand captures produce a bounded recovery state instead of invented observations.

## Evidence states

| State | Meaning | Permitted Mira behavior |
|---|---|---|
| `observed` | The feature is directly distinguishable on the accepted frame. | Describe what is visible, then use cautious traditional interpretation. |
| `inferred` | A qualified interpretation of a visible partial feature. | Say explicitly that it is an inference, not a fact. |
| `unknown` | The image, view, geometry or consistency is insufficient. | Do not claim presence or absence; state what should be reshot. |
| `not_supported` | The request is outside supported scope or asks for an impermissible conclusion. | Decline that conclusion and offer a safe reflective alternative. |

`visibility` (`clear`, `partial`, `unclear`, `not_visible`) describes readability. `evidence_state` describes epistemic status. A CV edge or confidence value is never a semantic line truth.

## Confidence semantics

The canonical result bounds `confidence` to `0..1` and includes `confidence_semantics`:

| Range | Meaning |
|---|---|
| `0` | No visual confirmation. |
| `0.01–0.49` | Weak or partial signal; only a qualified observation is allowed. |
| `0.50–0.79` | Moderate visual support with an explicit limitation. |
| `0.80–1.00` | Clear frame-supported observation; it is not certainty about a person or future. |

High confidence never permits diagnosis, age/fertility/pregnancy/mortality claims, exact dates, guaranteed relationships or guaranteed wealth/travel.

## Input acceptance and normalization

The API accepts only `image/jpeg`, `image/png` and `image/webp`, up to 8 MiB, with a minimum side of 480 px, maximum side of 8000 px and maximum area of 20 MP. The declared MIME type is compared with the actual Pillow-detected signature. Corrupt, empty, unsupported, mismatched-MIME and animated files are rejected before quality/CV processing. EXIF orientation is applied before RGB conversion and bounded JPEG data-URL generation. The raw upload is not persisted.

Client-side checks exist for friendly UX; server-side validation is authoritative. An unsupported content type is an input rejection, not a `no_hand` result.

## Quality and pipeline states

| State | Meaning | User contract |
|---|---|---|
| `complete` | Structured response passed normalization and at least one supported observation remains. | Show observations, confidence, limitations and reflective prompts. |
| `needs_photo` | Weak precheck, no/multiple hand, absent required view, malformed JSON or no supported observation. | Do not show confident reading; provide a concrete reshoot instruction. |
| `failed` | Unrecoverable internal/provider failure. | Return retry/error; never present false success. |
| `deleted` | Owner deletion scrubbed the persisted row. | Evidence and fingerprint are no longer available. |

Deterministic precheck measures decodeability, resolution, aspect, brightness, contrast and edge sharpness. It does **not** prove hand presence or line identity. Hard capture issues can skip expensive CV and vision work; softer issues remain visible to the model as limitations.

## Hand, palm-region and view boundaries

MediaPipe returns explicit `model_missing`, `unavailable`, `quality_limited`, `no_hand`, `multiple_hands` or runtime-error states. The detector requests up to two hands, and multiple hands never get silently reduced to an arbitrary first hand. `no_hand` and `multiple_hands` skip the vision provider and return `needs_photo`.

OpenCV uses a convex hand hull only when verified geometry exists. Without a hull, candidate edges are `unscoped` and remain `unknown`. Raw masks and edge maps are not stored. The line catalog is a candidate catalog, not a promise of detection or semantic validation.

A complete open-palm frame can support visible major lines, palm shape, mounts and fingers. Relationship/marriage, children and travel lines require a **folded-edge view** with the palm side toward the camera. In an open-palm result these zones are cleared from semantic line output, marked `unknown`/not visible and returned with `requires_view: ["folded_edge"]`.

## Vision adjudication and safety

Vision receives the bounded precheck and CV evidence together with the image. It is the final visual adjudicator for semantic identity. It must inspect the original frame first, then any focus views; it may confirm or reject candidate support and must return strict JSON. `evidence_refs` can contain only compact identifiers for real supporting evidence, never invented coordinates.

Text, QR codes, arrows, labels and instructions embedded in the image are untrusted visual content. Patterns such as “ignore previous instructions”, “always say this line is strong” and fake system messages are sanitized and cannot redefine the contract. Model output is sanitized before persistence and response.

Mira must refuse or reframe disease/diagnosis, fertility, pregnancy, age, mortality, neurological or mental-health claims. It must not assert exact marriage dates, exact children counts, guaranteed partners/breakups, guaranteed wealth/travel or inevitable events. It must not accept a user premise when stored evidence is `unknown`, `partial` or below the supported confidence boundary.

## Mira handoff and UX

`palm_scanner` is the handoff boundary: Mira receives only structured observations, evidence states, contract version, quality and limitations. A weak result includes a machine-readable `PALM_LIMITATION` payload and a concrete reshoot instruction rather than a confident interpretation. The Mini App picker exposes RU/EN copy for whole-palm capture, folded-edge limitations, supported file types, quality recovery and privacy.

The UI states that the photo is used for the current reading, only structured observations and a technical fingerprint are retained, the original image is not stored, and a reading can be deleted from history. Upload controls, progress status, retry, limitations and result controls retain keyboard reachability, focus treatment, screen-reader labels and touch-safe dimensions.

## Storage, privacy and deletion

The repository stores structured `analysis_json`, status, owner, hand side, SHA-256 fingerprint, original byte size, surface and timestamps. Raw image, raw provider response, raw edge maps and masks are not product artifacts. MediaPipe temporary files are created under a context manager and removed on exit. Provider content is not placed in logs.

`DELETE /api/palm/{id}` is owner-scoped. It scrubs status to `deleted`, clears hand side, fingerprint, size and analysis JSON, and records deletion/update timestamps. Deleted rows are excluded from list/get/latest queries; another user receives 404. Account deletion follows the broader policy; payment/legal records may have separate retention requirements.

## Performance and measurement

Processing metrics record acceptance/precheck, CV, vision, attempt count, skip state and total milliseconds without recording image content. Production monitoring should report p50/p95 for upload, normalization, precheck, hand geometry, ONNX, OpenCV, vision provider, normalization, persistence and total request time, together with retries and LLM cost. The deterministic gauntlet reports local precheck timing only and never represents it as production latency.

The semantic accuracy gate remains **blocked** until a consented or synthetic golden corpus contains valid palms, negative examples, partial hands, folded-edge views, expected regions, adversarial visual text and expected limitations. The current suite proves boundaries and safety, not semantic palm-reading accuracy.

## References

[1]: ../../app/core/palm/ "Palm service: acceptance, normalization, safety and persistence boundary"
[2]: ../../app/core/palm_vision.py "Deterministic capture-quality precheck"
[3]: ../../app/core/palm_landmarks.py "Optional hand geometry adapter"
[4]: ../../app/core/palm_lines.py "Auxiliary ONNX line segmentation"
[5]: ../../app/core/palm_full_scope.py "OpenCV candidate search and palm-region evidence"
[6]: ../../app/core/tool_registry.py "Mira palm handoff and limitations"
[7]: ../../tests/test_palm_gauntlet.py "Adversarial and uncertainty regression tests"
