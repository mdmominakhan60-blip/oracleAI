# Composite и planetary returns: продуктовая спецификация

**Статус:** implemented as JSON-first product paths; visual extensions remain planned.
**Дата:** 2026-08-26

Этот документ фиксирует реализованные контракты и задачи расчёта. Наличие возможностей upstream-библиотеки не считается реализацией OracleAI. Composite и solar returns включены в API, agent evidence и Mini App только в ограниченном JSON-first scope, описанном ниже.

## Общие ограничения

Оба пути должны использовать сохранённые owner-scoped данные и существующий canonical calculation layer. Клиент не передаёт натальные birth data через GET-URL, image URL или публичный cache key. LLM получает только deterministic evidence и не вычисляет долготы, моменты возврата, дома или аспекты самостоятельно. Первый релиз каждого пути — JSON-first; новый wheel, raw SVG, share image и PDF добавляются отдельными решениями.

## Composite v1 — implemented JSON-first

### Вход

```json
{
  "partner_id": 42
}
```

`partner_id` должен принадлежать текущему владельцу. Обе карты должны быть сохранены, иметь `mode=full`, `precision=exact` и необходимые planetary longitudes. Ошибки должны использовать стабильные коды `partner_not_found`, `chart_required`, `exact_charts_required` и `calculation_unavailable`.

### Ответ

```json
{
  "composite_schema_version": 1,
  "product": "composite",
  "precision": "exact",
  "sources": {
    "owner": {"role": "owner", "chart_precision": "exact"},
    "partner": {"role": "partner", "partner_id": 42, "chart_precision": "exact"}
  },
  "points": [],
  "aspects": [],
  "limitations": []
}
```

### Канонический расчёт

Для десяти традиционных планет вычисляется круговая середина двух абсолютных долгот. Переход через 0° обязан обрабатываться как кратчайшая дуга: для пары 359° и 1° результатом является 0°, а не 180°. В ответе для каждой точки возвращаются stable id, label, обе исходные долготы, midpoint longitude, sign, rounded degree и exact degree.

Внутренние major aspects строятся между composite-планетами по существующей политике углов и орбов. Узлы, дополнительные точки, ASC/MC, дома и локальные углы не входят в v1 до отдельной parity-проверки и утверждения семантики. `limitations` обязан прямо сообщать об этом.

### Задачи расчёта и acceptance gates

| Этап | Требование |
|---|---|
| Нормализация | Переиспользовать canonical point normalization; не дублировать mapping знаков и долготы |
| Midpoint helper | Pure deterministic функция с wrap-around, `0°`, `180°`, missing-point и floating-point тестами |
| Aspects | Использовать общую major-aspect policy, без второй таблицы орбов |
| Privacy/API | Owner lookup через `partner_id`, единый 404 для отсутствующего/чужого партнёра, отсутствие birth PII в ответных ссылках |
| Agent | Добавить evidence tool только после успешного contract/API test; не выдавать интерпретацию как факт |
| UX | Выбор сохранённого exact партнёра и отдельное состояние unavailable; сначала structured card, без нового колеса |
| Release gate | Determinism, owner isolation, exactness gate, missing-point fixtures, regression natal suite и documentation link check |

## Planetary returns v1 — implemented as solar return

### Scope

Минимальный первый путь — **solar return** с `planet = Sun`. Jupiter, Saturn и другие returns добавляются только после расширения enum и отдельной проверки производительности. Нельзя принимать свободную строку планеты и молча выбирать другой объект.

### Вход

```json
{
  "planet": "Sun",
  "year": 2027
}
```

Требуются сохранённые натальные planetary longitudes. Для расчёта локального отображения нужны сохранённые координаты и IANA timezone владельца; если их нет, контракт возвращает `return_location_required`. Ошибки также включают `chart_required`, `invalid_year`, `unsupported_planet`, `no_return_found` и `calculation_unavailable`.

### Ответ

```json
{
  "returns_schema_version": 1,
  "product": "returns",
  "planet": "Sun",
  "planet_label": "Солнце",
  "target_year": 2027,
  "precision": "exact",
  "natal_longitude_deg": 88.123456,
  "return_longitude_deg": 88.123456,
  "return_at_utc": "2027-06-21T08:15:00+00:00",
  "return_at_local": "2027-06-21T11:15:00+03:00",
  "timezone": "Europe/Moscow",
  "search_window": {"start": "2027-01-01T00:00:00+00:00", "end": "2028-01-01T00:00:00+00:00"},
  "match_count": 1,
  "limitations": ["Это астрономический момент возврата, а не гарантия события."]
}
```

### Канонический расчёт

Алгоритм принимает натальную absolute longitude и ищет пересечение той же долготы в ограниченном интервале целевого года через Swiss Ephemeris/Kerykeion layer. Сначала выполняется coarse scan, затем bracketed refinement/root search до фиксированной angular tolerance и максимального числа итераций. Все timestamps сериализуются timezone-aware в UTC и локальную IANA timezone.

Расчёт обязан учитывать переход года, leap day, DST, ретроградность и несколько пересечений в одном году. Контракт возвращает `match_count`; результат не должен молча обрезаться до первого события. Если пересечение не найдено, возвращается `no_return_found`, а не приблизительная дата.

### Задачи расчёта и acceptance gates

| Этап | Требование |
|---|---|
| Ephemeris adapter | Проверить pinned Kerykeion/Swiss Ephemeris API и не добавлять второй production engine |
| Search | Определить scan step, angular tolerance, max iterations, wrap-around и boundary semantics |
| Timezones | Устойчиво обработать UTC/local conversion, DST и leap-year fixtures |
| Retrograde/multiple | Покрыть direct/retrograde crossings, несколько crossings и отсутствие crossing |
| Performance | Измерить worst-case year search и ограничить вычислительный бюджет |
| Privacy/API | Owner-scoped route, отсутствие произвольных клиентских coordinates в URL/cache key |
| Agent/UX | Только после deterministic result: evidence tool, planet/year picker, disclaimer without deterministic prediction claims |
| Release gate | Exact fixtures, timestamp round-trip, no-match/multi-match, owner isolation, full regression and legal review |

## Не входит в эту спецификацию

В v1 не включаются composite houses, composite ASC/MC, return houses, relocation-based returns, transit periods/ingresses, automatic event predictions, visual wheels, PDF/share images и платёжный entitlement. Каждый из них требует отдельного product decision и не появляется как скрытый fallback. Текущие endpoints: `POST /api/composite` и `POST /api/returns`; agent tools: `get_composite` и `get_returns`; Mini App journeys: `featureComposite` и `featureReturns`.
