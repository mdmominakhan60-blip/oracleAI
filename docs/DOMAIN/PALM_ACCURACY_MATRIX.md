# OracleAI Palm Accuracy Matrix

**Контракт:** `palm-evidence-v1`
**Последний прогон:** 27 августа 2026 года
**Fixture:** `tests/fixtures/palm/palm_hand.jpg`
**Команда:** `PYTHONPATH=. python3 scripts/palm_accuracy_gauntlet.py --output artifacts/palm_accuracy_matrix.json`

## Deterministic contract matrix

| Case | Expected | Actual | Confidence | Pass |
|---|---|---|---:|---:|
| Good palm | `complete` | `complete` with mocked structured provider; JPEG 2592×1728 accepted | 0.90 | PASS |
| Partial / low-resolution palm | `needs_photo` | Rejected before CV: minimum side 480 px | 0.00 | PASS |
| No hand | `needs_photo` | `needs_photo`; no semantic claim from unconfirmed frame | 0.00 | PASS |
| Folded edge absent | `limitation` | `requires_view=folded_edge`; relationship/children/travel cleared from semantic map | unknown | PASS |
| Adversarial text | `ignored` | Injection-like model/image text sanitized as untrusted | 0.90 | PASS |
| Visual artifact / multiple hands | `rejected` | `needs_photo`; arbitrary hand selection prevented | 0.00 | PASS |
| Weak evidence | `needs_photo` | `unclear` cannot retain `observed` or high confidence | 0.00 | PASS |

**Итог:** 7/7 deterministic contract cases passed; 0 failed. This matrix proves acceptance, safety and uncertainty boundaries. It does **not** claim that a mocked provider has established semantic palm-line accuracy.

## Timing evidence

The same run measured the deterministic quality precheck over 25 local samples:

| Stage | Samples | p50 | p95 | Provider calls |
|---|---:|---:|---:|---:|
| Capture quality precheck | 25 | 120.127 ms | 122.558 ms | 0 |

These measurements cover Pillow-based decode/EXIF normalization and quality metrics only. They are not production total latency. Production p50/p95 must be collected separately for upload, hand geometry, ONNX, OpenCV, vision provider, normalization, persistence and total request time. LLM usage, retry count and cost are already recorded through the existing `llm_usage` and product-cost telemetry paths.

## What remains blocked

The final semantic accuracy claim remains **BLOCKED** until a consented or synthetic golden corpus contains clearly valid palms, low-quality palms, partial hands, negative examples and adversarial visual content with expected regions and limitations. MediaPipe is optional in the current runtime; when it is unavailable, geometry is explicitly marked unavailable rather than fabricated. OpenCV and ONNX outputs remain auxiliary candidate evidence and are not semantic labels.

A fresh domain/CV/safety/UX critic must receive implementation, matrix, evidence payloads and screenshots and attempt to find a reproducible case where Mira claims more than the image supports. A single reproducible high-confidence false observation remains a critical failure under the contract.

## References

[1]: ../../app/core/palm/ "Palm acceptance, normalization and safety contract"
[2]: ../../app/core/palm_landmarks.py "Hand geometry adapter"
[3]: ../../app/core/palm_full_scope.py "OpenCV candidate evidence adapter"
[4]: ../../scripts/palm_accuracy_gauntlet.py "Deterministic gauntlet runner"
