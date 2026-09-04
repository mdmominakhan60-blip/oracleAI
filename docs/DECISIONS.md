# OracleAI — актуальные архитектурные решения

Документ содержит только действующие решения. Исторические аудиты, браузерные snapshots, competitor research и промежуточные отчёты в репозитории не хранятся.

## ADR-001 — Единый источник астрологических расчётов

**Статус:** accepted

`app/core/astro.py` на базе закреплённого Kerykeion/Swiss Ephemeris является единственным production source of truth для натальных, synastry и transit calculations. Product contracts нормализуют результаты и явно фиксируют precision; UI и LLM не пересчитывают значения. `pyswisseph`, flatlib, Immanuel, Astrolog и другие engines могут использоваться только как внешние reference tools после отдельного review, но не как второй скрытый production path.

Натальная карта использует Tropical zodiac, Placidus `P`, Apparent Geocentric и True Node. Exact values сохраняются отдельно от округлённых UI values. Unknown-time режим не подставляет дома, ASC или MC.

## ADR-002 — Evidence-first interpretation

**Статус:** accepted

Deterministic calculation and evidence builders остаются отделены от LLM interpretation. Агент получает только факты из canonical chart/product contract, а safety, coverage и grounding checks применяются до возврата ответа. Модель не вычисляет планеты, дома, аспекты, узлы, Lilith, composite midpoints или return moments.

Memory остаётся opt-in; при выключенной памяти backend и agent runtime не передают сохранённые факты в контекст. Медицинские, юридические, финансовые гарантии и deterministic predictions запрещены.

## ADR-003 — Mode P для натального изображения

**Статус:** accepted; commercial release требует legal/licensing review

Натальный визуал строится серверно через Kerykeion `ChartDrawer` во временном SVG в памяти процесса и сразу преобразуется `resvg_py` в PNG/WebP. Raw SVG не сохраняется, не логируется, не возвращается API, не передаётся в Mini App, share flow или PDF.

Клиент получает только authenticated `GET /api/chart/image`. Birth data не помещаются в URL; raster cache использует приватные headers, ETag и HMAC-derived keys. Колесо доступно только для `precision == exact`. Доступность HTML placement list и recovery states не зависит от изображения.

## ADR-004 — Версионированные chart product contracts

**Статус:** accepted for natal/synastry/transit; composite/returns planned

Текущие product contracts описаны в [CHART_PRODUCT_CONTRACTS.md](CHART_PRODUCT_CONTRACTS.md) и capability matrix в [CHART_TYPE_CAPABILITIES.md](CHART_TYPE_CAPABILITIES.md).

- `natal_schema_version = 2` сохраняет полную exact natal карту и честные ограничения unknown-time режима.
- `synastry_schema_version = 1` принимает owner-scoped saved `partner_id`, требует две exact карты и возвращает planetary positions plus major cross-chart aspects.
- `transit_schema_version = 1` принимает explicit ISO date and optional UTC time, маркирует `day` или `instant`, возвращает geocentric transit planets and aspects to natal planets, но не создаёт transit houses или angles.
- `composite_schema_version = 1` и `returns_schema_version = 1` пока не enabled. Их входы, midpoint/search semantics, precision-gates, privacy boundaries and acceptance tests описаны в [COMPOSITE_AND_RETURNS_PRODUCT_SPEC.md](COMPOSITE_AND_RETURNS_PRODUCT_SPEC.md).

Первый релиз новых типов JSON-first. Изображения, PDF, share artifacts, periods/ingresses и автоматические predictions требуют отдельных решений.

## ADR-005 — Production release governance

**Статус:** accepted; public launch не подтверждён

Перед коммерческим запуском требуются внешние проверки, которые нельзя закрыть локальным unit suite: production deployment and Docker image validation, real Telegram iOS/Android device QA, live LLM/provider quality, privacy/legal review, payment/reconciliation testing, backup/restore drill and licensing decision for Kerykeion AGPL-3.0 and Swiss Ephemeris dual licensing.

До закрытия этих gates продукт считается controlled-beta candidate, а не public-launch-ready.

## Palmistry engine research (verified 2026-08-27)

The repository was compared with open-source end-to-end palmistry projects, hand-landmark components, line-segmentation models and commercial APIs. The distinction between **palmprint/biometric recognition** and **palmistry interpretation** is material: the former can supply reusable geometry, but does not establish meanings about personality or fate.

| Название / ссылка | Тип | Актуальность | Точность / практический тест | Лицензия | Вердикт |
|---|---|---|---|---|---|
| [yeonsumia/palmistry][8] | End-to-end research pipeline: warping, principal-line detection, K-means classification, length measurement | 52 stars, 25 forks, 46 commits; latest visible commit 2026-04-30; notebook-heavy | README describes four sample inputs and the pipeline, but no independent production benchmark; not run as a drop-in service | Apache-2.0 | Не подходит как production engine; оставить research reference |
| [samuelwbarber/palm-line-reader][9] | ONNX U-Net segmentation | 0 stars, 2 commits; reproducible browser demo and model/training pack | Local run on the same 15 real images: fp16 detected 12/15; int8 detected 12/15; status agreement 15/15. No annotated ground truth, so this is operational evidence, not accuracy | MIT | Использовать как auxiliary evidence; не интерпретировать напрямую |
| [MediaPipe Hand Landmarker][10] | Hand detection, handedness and geometry | Official Google AI Edge task documentation; supports image/video/live stream; 21 keypoints | Local run on the same 15 images: hand detected 13/15. It does not segment palm creases | Official task/model terms; review before distribution | Использовать для capture gate, hand presence, side and geometry |
| [OpenPose][11] | Hand keypoints, 2×21 points | 34.4k stars, 8k forks, 716 commits; mature but heavy | No local run required after license review; it supplies pose, not palm lines | Free non-commercial use; commercial license required | Не использовать в commercial product without separate license; MediaPipe is sufficient |
| [AstrologyAPI Palmistry API][12] | Commercial end-to-end palm scan + readings + overlay | Public developer landing page and REST example | No independent benchmark or sandbox response verified; vendor describes structured features and overlay | Commercial terms | Не выбирать без vendor trial, DPA/privacy review and quality acceptance |
| [Astrology-API.io Palm Reading API][13] | Commercial detection/readings API | Public product/pricing page | Vendor claims 77–88% line detection confidence and <900ms detection; not independently verified | Commercial terms | Экономически возможная fallback option: $0.067/request Ultra or $0.045/request Business by vendor page, but not primary |

## ADR-006 — Гибридный CV-пайплайн Миры

**Статус:** accepted for controlled beta; production quality claims require an annotated, consented capture set and legal review.

Выбран **вариант B**: `palm_vision` capture precheck + MediaPipe Hand Landmarker + `palm-line-reader` ONNX helper + vision-LLM interpretation. Готового end-to-end движка с доказанной точностью, живым SDK и безопасными production boundaries не найдено. `yeonsumia/palmistry` полезен для исследования, но notebook-heavy; `palm-line-reader` воспроизводим и MIT-licensed, однако покрывает только heart/head/life и прямо отделяет segmentation от palmistry reading. OpenPose не проходит commercial license gate.

Поток данных: изображение нормализуется и проверяется по размеру/качеству; низкокачественный кадр получает `needs_photo` с конкретным советом и не вызывает дорогую vision-модель. Для остальных кадров MediaPipe возвращает только hand presence/handedness/21 landmarks, а ONNX — только bounded summaries для heart/head/life (`coverage`, `bbox`, `confidence`, без raw mask). Эти данные передаются vision-LLM как auxiliary untrusted evidence. Vision-LLM обязан вернуть strict JSON; сервер sanitizes forbidden claims, сохраняет только структурированный результат и публикует безопасную recommendation event в Shared Context.

Существующее поведение «только vision-LLM» не удаляется: при отсутствии MediaPipe/model dependency или runtime error pipeline остаётся работоспособным через явный non-fatal status и conservative fallback. Но precheck всегда выполняется до expensive call. До публичного запуска необходимы 15–20 дополнительных consented photos с человеческой разметкой линий, folded-edge cases, left/right labels и объективные acceptance metrics; текущие 15 public/repository fixtures подтверждают запускаемость компонентов, но не их palmistry accuracy.

## References

[1]: https://kerykeion.net/content/docs "Kerykeion official documentation"
[2]: https://github.com/g-battaglia/kerykeion "Kerykeion source repository"
[3]: https://www.astro.com/swisseph/ "Swiss Ephemeris licensing"
[4]: ../app/core/astro.py "OracleAI canonical calculations"
[5]: ../app/core/chart_rendering.py "OracleAI Mode P raster adapter"
[6]: CHART_PRODUCT_CONTRACTS.md "OracleAI current chart product contracts"
[7]: COMPOSITE_AND_RETURNS_PRODUCT_SPEC.md "OracleAI planned composite and returns specification"
[8]: https://github.com/yeonsumia/palmistry "yeonsumia palmistry research repository"
[9]: https://github.com/samuelwbarber/palm-line-reader "samuelwbarber palm-line-reader"
[10]: https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker "Google AI Edge Hand Landmarker"
[11]: https://github.com/CMU-Perceptual-Computing-Lab/openpose "OpenPose repository and licensing"
[12]: https://astrologyapi.com/palm-reading-api "AstrologyAPI palm reading API"
[13]: https://astrology-api.io/p/palm-reading-api "Astrology-API.io palm reading API and pricing"
