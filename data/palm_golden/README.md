# Palm golden corpus: human/domain review handbook

## Зачем нужен корпус

Этот каталог предназначен для **оценки semantic behavior**, а не для доказательства медицинской или предсказательной ценности хиромантии. Каждая запись должна позволять ответить на вопрос: правильно ли система распознала допустимый визуальный state и не выдала ли она более сильное утверждение, чем поддерживает изображение.

> Не помещайте реальные фотографии в Git. Храните raw files в защищённом review storage, а в manifest указывайте относительный путь, SHA-256 и ссылку на consent record.

## Состав выборки

Для первого review набора подготовьте минимум 60 записей: 20 clear open-palm, 10 partial/cropped, 10 low-light/blur/glare, 8 folded-edge, 6 no-hand/visual-artifact, 4 multiple-hands и 2 adversarial visual-text cases. Это **sampling target**, а не готовый датасет: записи должен собрать и разрешить владелец данных, а labels — подтвердить reviewers.

Не смешивайте train/dev/test изображения одного человека или одной серийной съёмки между split. Challenge split должен содержать новые устройства, освещение, skin tones, orientations и сложные негативные случаи. Synthetic contract frames могут проверять только pipeline states; они не заменяют human-reviewed palm photographs.

## Region labels

Каждая запись содержит `regions`. `topic` — строго один ключ из schema; `visibility` описывает, насколько зона различима; `evidence_state` — допустимый semantic state. Для line topics используйте normalized `bbox_norm` для локализуемого участка и `polygon_norm`, если reviewers согласовали контур. Если зона отсутствует или ракурс не поддерживает её, оставляйте `bbox_norm` пустым и ставьте `not_visible`/`unknown`, а не рисуйте предполагаемую линию.

Минимальный набор для open-palm записи — `palm_region`, `life_line`, `head_line`, `heart_line`, `mounts`, `fingers`, а также все folded-edge topics как `unknown`/`not_visible`, если ребро ладони не видно. Для folded-edge записи отдельно маркируйте `relationship_lines`, `children_lines` и `travel_lines`; не переносите их labels из open-palm кадра.

## Как размечать

Первый reviewer фиксирует capture quality, view type, hand count, hand side и region labels, не читая model output. Второй reviewer размечает тот же кадр независимо. Затем domain reviewer разбирает только разногласия и опасные false positives. Для каждой region label обязательны минимум два `annotator_refs`; `adjudication.status=adjudicated` допустим только после решения domain reviewer.

Reviewer должен описывать пиксельно проверяемое: “continuous crease visible in central palm”, “edge zone cropped”, “two hands overlap”, “text overlay present”. Нельзя писать в label традиционное значение, диагноз, возраст, событие, дату, количество детей или certainty. Эти вещи относятся к prohibited claims или downstream interpretation.

Confidence band относится к visual support: `zero`, `low`, `medium`, `high`. `high` означает только чёткую видимость конкретной зоны, а не истинность palmistry interpretation. If reviewers disagree between `observed` and `unknown`, choose the safer state and record disagreement.

## Adjudication rules

Domain reviewer должен проверить: согласованность region label с самим изображением; соответствие `view_type`; отсутствие silent assumptions о folded-edge; отсутствие arbitrary selection при multiple hands; корректность `expected_user_action`; и то, что prohibited claims действительно запрещены.

Agreement рассчитывается по region state/visibility до adjudication. Запись отклоняется, если нет consent/provenance, image hash не совпадает, reviewers не независимы, не хватает двух annotators или невозможно объяснить region label.

## Review inputs and outputs

Для запуска review подготовьте:

1. `manifest.jsonl`, где каждая строка соответствует [`schema.json`](schema.json).
2. Protected image directory, referenced by `image_path` and excluded from Git.
3. `predictions.jsonl`, созданный approved evaluation adapter. Он должен содержать `record_id`, `quality_state`, `view_type`, `observations` and `processing_metrics`; raw image, provider payload and personal data are forbidden.
4. Optional `reviewer_notes.jsonl` for disagreements and adjudication decisions.

Команды:

```bash
python scripts/validate_palm_corpus.py \
  --manifest data/palm_golden/manifest.jsonl \
  --image-root /secure/palm-review-images

python scripts/run_palm_human_review.py \
  --manifest data/palm_golden/manifest.jsonl \
  --predictions /secure/palm-review/predictions.jsonl \
  --out artifacts/palm-human-review.json
```

Runner выдаёт region-state accuracy, unknown safety precision, false-observed count, capture-state accuracy и readiness verdict. Он не объявляет semantic accuracy `PASS`, если хотя бы одна запись не adjudicated, отсутствует domain reviewer, есть critical false observed или нарушена privacy schema.

## Reviewer eligibility and CI policy

A release-quality `test`/`challenge` record requires two distinct active annotators and a separate active domain reviewer. Every contributor must have a non-identifying `qualification_reference`, the `palm-human-review-v1` signed attestation, current training reference, `blinded_review=true`, and an explicit conflict-of-interest declaration. A reviewer with a disclosed conflict is not eligible to contribute to an adjudicated semantic sign-off; `domain_reviewer` and `annotator` roles must never be assigned to the same person for the same corpus.

The repository may contain schemas, templates, hashes, and non-identifying IDs only. Raw/consented images and credential or training evidence remain in protected storage. Template placeholders are not credentials and do not constitute human labels.

On every CI push and pull request, the template manifest and reviewer registry template are structurally validated. If `data/palm_golden/manifest.jsonl` is tracked, CI compares it with the base commit, validates every added or changed record with `check_palm_corpus_diff.py`, and requires adjudicated status, independent registry linkage, and immutable image identity/capture fields for existing `test`/`challenge` records. It then runs the full manifest validator with `--require-adjudicated`. A missing base ref fails closed rather than silently treating all records as new, and record removals fail until the corpus owner reviews them explicitly. CI success is a structural/data-governance gate only; it never changes the independent critic's semantic accuracy status to PASS without protected images, reviewed predictions, and real domain evidence.

## Final sign-off

`SHIP` для semantic accuracy требует: согласованный test/challenge split; минимум два независимых annotators на запись; domain reviewer; зафиксированные hashes; отсутствие critical false observed; отчёт о coverage и disagreements; и повторный прогон на immutable manifest. Если эти условия не выполнены, итог должен быть `BLOCKED`, даже если unit tests и deterministic gauntlet проходят.
