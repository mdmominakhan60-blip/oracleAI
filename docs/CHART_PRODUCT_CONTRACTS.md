# Контракты продуктовых путей: natal, synastry, transit, composite и returns

## Document orientation

| Field | Definition |
|---|---|
| **Purpose** | Versioned chart-product request/response contracts. |
| **Source of truth** | `app/core/chart_products.py`, `app/api/contracts/chart_products.py`. |
| **Scope** | Natal-adjacent product shapes: synastry, transit, composite and returns. |
| **Do not change** | Do not imply visual/PDF support or unsupported precision from a JSON-first contract. |
| **Key files** | `app/core/chart_products.py`, `app/api/routers/chart_products.py`, `tests/test_chart_products.py`. |
| **Validation** | `pytest -q tests/test_chart_products.py`. |


**Дата обновления:** 2026-08-26
**Статус:** natal, synastry, transit, composite и solar returns реализованы как JSON-first product paths; изображения, PDF и share-визуалы для новых типов не включены.

## Общие правила

Канонический источник позиций — существующий `app.core.astro` на базе закреплённого Kerykeion/Swiss Ephemeris. Product builders находятся в `app/core/chart_products.py`, не зависят от FastAPI, базы или LLM и возвращают JSON-ready dictionaries. LLM получает только deterministic evidence и не пересчитывает долготы, midpoints, аспекты или моменты возврата.

Новые маршруты используют только owner-scoped сохранённые данные. Birth data, raw SVG и render artifacts не принимаются и не возвращаются через публичные URL. Если данные недостаточны, API возвращает structured `422` с `detail.code`, `detail.message` и `detail.missing`.

| Путь | Request | Calculation | Current response | Not included |
|---|---|---|---|---|
| `synastry_schema_version=1` | Saved `partner_id` | Major cross-chart aspects between ten traditional planets | Two planet lists and labeled aspects | Houses, angles, composite, image |
| `transit_schema_version=1` | Saved natal + `as_of` + optional UTC `time` | Geocentric transit snapshot and aspects to natal planets | Transit planets, natal aspects, `day`/`instant` precision | Transit houses, angles, periods/ingresses |
| `composite_schema_version=1` | Saved `partner_id` | Circular midpoints of ten traditional planets and internal major aspects | Composite points with both source longitudes | Houses, ASC/MC, nodes/additional points, wheel |
| `returns_schema_version=1` | `planet=Sun` + target `year` | Bounded 12-hour ephemeris scan plus minute-level crossing refinement | UTC/local moment(s), match count, timezone and limitations | Other planets, return houses, wheel, predictions |

## Synastry v1

`POST /api/synastry` принимает `{ "partner_id": 42 }`. Партнёр должен принадлежать текущему владельцу; отсутствующий и чужой id дают единый `404 partner_not_found`. Обе карты должны иметь `mode=full`, `precision=exact` и planetary longitudes. Иначе возвращается `422 exact_charts_required`.

Ответ содержит `person.planets`, `partner.planets` и `aspects`. Каждый aspect использует `first`, `first_label`, `first_role`, `second`, `second_label`, `second_role`, `code`, `label`, `glyph` и `orb_deg`. В первом релизе отображаются только десять традиционных планет и major cross-chart aspects.

## Transit v1

`POST /api/transits` принимает обязательную ISO date `as_of` и необязательное UTC `time` в формате `HH:MM`. Без времени используется детерминированный срез `12:00 UTC` с `precision=day`; с временем — `precision=instant`. Transit houses и angles не строятся. Натальная карта может быть `exact` или `date_only`, а `natal_precision` обязательно отражается в ответе.

## Composite v1

`POST /api/composite` принимает `{ "partner_id": 42 }` и использует те же owner-scoped partner records, что и synastry. Обе карты проходят `mode=full` и `precision=exact` gate. Расчёт реализован pure-функцией `circular_midpoint(first, second)`: долготы нормализуются в `[0, 360)`, а короткая дуга корректно проходит через 0°.

Ответ имеет форму:

```json
{
  "composite_schema_version": 1,
  "product": "composite",
  "precision": "exact",
  "sources": {
    "owner": {"role": "owner", "chart_precision": "exact"},
    "partner": {"role": "partner", "partner_id": 42, "label": "Имя"}
  },
  "points": [
    {
      "id": "Sun",
      "label": "Солнце",
      "source": {"owner_abs_deg_exact": 10.0, "partner_abs_deg_exact": 30.0},
      "sign": "Овен",
      "deg": 20.0,
      "deg_exact": 20.0,
      "abs_deg": 20.0,
      "abs_deg_exact": 20.0,
      "retro": false
    }
  ],
  "aspects": [],
  "limitations": []
}
```

Composite aspects переиспользуют canonical `astro.synastry_aspects` policy по orb/major aspect types с удалением reverse duplicates. Узлы, дополнительные точки, ASC/MC и дома сознательно не включены в v1.

## Returns v1

`POST /api/returns` принимает `{ "planet": "Sun", "year": 2027 }`. В первой версии разрешён только `Sun`, а год ограничен 1900–2200. Владелец должен иметь сохранённую `mode=full`, `precision=exact` карту, а также сохранённые `birth_lat`, `birth_lon` и IANA `tz` для локального timestamp. Иначе используются стабильные ошибки `unsupported_planet`, `invalid_year`, `chart_required`, `exact_charts_required` или `return_location_required`.

Расчёт ищет пересечения натальной долготы планеты с геоцентрической долготой той же планеты в UTC. Coarse scan выполняется с шагом 12 часов; crossing уточняется до минут через bounded bracket refinement. Интервал включает `[01 Jan target_year, 01 Jan target_year + 1)` и timezone-aware timestamps. `match_count` и `matches` не позволяют скрыть несколько пересечений в одном году.

Ответ содержит `natal_longitude_deg`, первый `return_longitude_deg`, `return_at_utc`, `return_at_local`, `timezone`, `search_window`, `match_count`, полный `matches` и `limitations`. Тексты явно сообщают, что return moment является астрономическим расчётом, а не гарантией события.

## Agent и Mini App

`get_composite` принимает только saved `partner_id`; `get_returns` принимает `planet=Sun` и explicit `year`. Оба инструмента возвращают versioned deterministic evidence или stable limitation error и не раскрывают birth PII. Astrologer toolbox содержит отдельные journeys `featureComposite` и `featureReturns`; UI показывает selection/loading/result/error states и JSON-derived cards без нового колеса.

## Ошибки и release limitations

Коды ошибок стабильны внутри версии: `chart_required`, `exact_charts_required`, `partner_not_found`, `return_location_required`, `unsupported_planet`, `invalid_year`, `no_return_found` и `calculation_unavailable`. Composite и returns не добавляют автоматические predictions, houses, angles, payments, PDF/share images или raw SVG.

Полный exact natal contract `natal_schema_version=2` не изменён: он по-прежнему включает десять традиционных планет, дома, ASC/MC, Rahu/Ketu, Lilith, Chiron/Juno/Ceres/Vesta/Pallas, major aspects и retrograde flags. Unknown-time natal остаётся `date_only` без домов, ASC/MC и колеса.
