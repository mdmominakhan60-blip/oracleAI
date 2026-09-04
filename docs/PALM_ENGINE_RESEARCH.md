# Palm-analysis engine research

**Дата исследования:** 27 августа 2026; semantic hardening update: 27 августа 2026

## Вывод

OracleAI не должен обещать, что текущая или любая найденная модель «понимает хиромантию». Зрелые CV-компоненты дают hand pose, handedness, геометрию и ограниченную сегментацию основных линий; смысловое чтение остаётся отдельным multimodal LLM use case с safety-правилами. Выбран паттерн **capture precheck → CV evidence helper → strict multimodal LLM interpretation → bounded structured persistence**.

## Кандидаты и лицензии

| Источник | Что реально делает | Сигнал зрелости | Лицензия/экономика | Решение OracleAI |
|---|---|---|---|---|
| [yeonsumia/palmistry][1] | Warping, principal-line detection, classification и length measurement; MediaPipe + deep model + K-means | 52 stars, 25 forks, 46 commits; latest visible commit 30 Apr 2026; notebook-heavy | Apache-2.0 | Research reference; не production dependency |
| [samuelwbarber/palm-line-reader][2] | ONNX U-Net, 5.55M params; fixed 512×512 RGB; classes background/heart/head/life; browser WASM/WebGPU demo | 0 stars, 2 commits; reproducible model contract; README explicitly separates segmentation from palmistry reading | MIT | Лучший local helper; только auxiliary evidence |
| [MediaPipe Hand Landmarker][3] | Hand presence, handedness, image/world landmarks, 21 keypoints; still/video/live-stream API | Official Google AI Edge task; documented CPU benchmark for full model | Official model/task terms; review before redistribution | Use for geometry, crop, hand side and capture guidance |
| [OpenPose][4] | 2×21 hand keypoints and broader pose stack | 34.4k stars, 8k forks, 716 commits; mature but heavy | Free for non-commercial use; commercial license required | Не использовать commercial без отдельной лицензии |
| [AstrologyAPI Palm Reading][5] | Commercial end-to-end palm scan, structured reading and overlay claims | Public REST/API landing page; no independent benchmark verified | Commercial terms | Fallback only after vendor trial, DPA/privacy and quality review |
| [Astrology-API.io Palm Reading][6] | Commercial detection/readings API; advertises 4 major lines and confidence scores | Public product/pricing page; no independent benchmark verified | Vendor page: 100 credits/request, Ultra $37/mo/550 requests, Business $99/mo/2,200 requests | Not primary; claims are vendor claims, not accepted accuracy |

## Practical same-image benchmark

`scripts/benchmark_palm_cv.py` runs the same 15 real repository/public fixture images through `palm_vision`, MediaPipe, the vendored ONNX fp16/int8 models and `palm_full_scope` OpenCV candidate search. The full JSON report is emitted to stdout; generated output belongs in ignored `artifacts/` or external evidence storage. It contains no user-uploaded images and is not a labelled accuracy set.

| Component | Result on 15 images |
|---|---:|
| Capture precheck classified `usable` | 4/15 |
| MediaPipe hand detected | 13/15 |
| ONNX fp16 line status `detected` | 12/15 |
| ONNX int8 line status `detected` | 12/15 |
| fp16/int8 status agreement | 15/15 |
| Full-scope candidate evidence | 15/15 |
| Candidate segments | 798 total |
| Named line catalog | 16 line zones |

The result proves that the local adapters execute and that fp16/int8 have stable coarse status agreement on this fixture set. It does **not** prove line-detection accuracy because no human ground truth exists. The strict `usable` gate is intentionally conservative: weak or flat captures receive reshoot guidance rather than a fabricated palm reading.

## Candidate ONNX contract

The inspected `palm-line-reader` fp16 model is SHA-256 `e2c9f826676b3aaf0a715f3087fcd4fc0b4dccd8c53de05fd26696a8399f8dd6`; the int8 model is SHA-256 `14bcf11d75c790ac0c147f3335b2772d53bc558e8af54aaadc7a148f8cf8db0c`. Input is float32 NCHW `[1,3,512,512]`, RGB, plain resize, ImageNet mean/std normalization. Output is float32 logits `[1,4,512,512]`; classes are `0=background`, `1=heart_line`, `2=head_line`, `3=life_line`. OracleAI verifies these checksums and never persists or returns a raw mask.

## Final integration boundary

The production path is a hybrid: `palm_vision` checks decoding, exposure, contrast, blur, crop and aspect; MediaPipe supplies hand geometry and handedness; the fp16/int8 ONNX ensemble supplies conservative summaries (`coverage`, `bbox`, `confidence`, margin, component ratio and model agreement) for heart/head/life; `palm_full_scope` combines CLAHE/Canny with blackhat-ridge candidate search, emits at most 32 stable-ID segments across all 16 named line zones plus mounts, fingers and markings; `palm_evidence` creates bounded in-memory hand ROI and folded-edge focus views; the vision LLM sees the normalized primary image plus up to two focus views and receives all CV results as untrusted evidence. The vision model is the final visual adjudicator and the LLM explains only confirmed observations. Details may include `evidence_refs`; normalized output exposes a semantic support/abstention summary so unsupported zones remain explicit. A disagreement or weak capture becomes `needs_photo`. Relationship, children and travel lines are flagged as folded-edge dependent when the capture is an open palm.

The LLM may interpret only visible, supported evidence. It must not infer health, age, pregnancy, death, income, profession, exact timing, guaranteed relationships or deterministic fate. Any malformed or unsafe model JSON is repaired/normalized or converted to a safe `needs_photo` result. Raw image bytes and raw segmentation masks are not stored.

## Release gates

Before public launch, collect at least 15–20 additional consented images with human labels for line visibility/continuity, left/right hand and folded-edge cases. Report per-line precision/recall or IoU, hand detection failure rate, `needs_photo` false-positive rate and latency. Also complete legal/privacy review of palm images, model redistribution review, mobile-device QA and live vision-provider evaluation.

## References

[1]: https://github.com/yeonsumia/palmistry "Fortune On Your Hand: View-Invariant Machine Palmistry"
[2]: https://github.com/samuelwbarber/palm-line-reader "Palm Line Reader"
[3]: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker "MediaPipe Hand Landmarker"
[4]: https://github.com/CMU-Perceptual-Computing-Lab/openpose "OpenPose repository and licensing"
[5]: https://astrologyapi.com/palm-reading-api "AstrologyAPI Palm Reading API"
[6]: https://astrology-api.io/p/palm-reading-api "Astrology-API.io Palm Reading API and pricing"
