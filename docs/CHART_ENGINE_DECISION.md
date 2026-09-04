# Решение по chart engine: Mode P

**Дата:** 2026-08-25  
**Статус:** technical implementation accepted; commercial release **blocked pending legal/licensing sign-off**  
**Scope:** natal chart image for Mini App, authenticated share flow and PDF print output

## Решение

OracleAI использует **Mode P**: серверный `Kerykeion 5.12.9 ChartDrawer` строит зрелую натальную диаграмму во временной строке SVG в памяти процесса, после чего `resvg_py 0.5.0` немедленно превращает её в PNG или WebP. Для production выбран вариант **Classic dark · clean**: классический круг, тёмная тема, без дополнительного zodiac background ring. Сырой SVG не сохраняется в файл, не попадает в лог, не возвращается API, не передаётся в Mini App, share flow или PDF.

Клиент получает только бинарный ответ `GET /api/chart/image`. Запрос авторизуется через `X-Init-Data`; birth data не помещаются в URL. Ответы ограничены allowlist-параметрами `variant`, `format` и `locale`, имеют private cache headers, ETag и `Content-Length`. Серверный кэш содержит только raster bytes, а ключ — HMAC-дайджест канонических входов и версий движка; raw birth data не является именем файла или логируемым идентификатором.

## Почему это решение принято

При переходе на Mode P была выбрана конфигурация `Classic dark · clean` как наиболее читаемая и наименее перегруженная. Решение закреплено в production-коде и проверяется детерминированными тестами на raster signature, размеры, приватность и отсутствие raw SVG.

Выбор зрелого engine отменяет прежнее решение поддерживать собственный natal-wheel renderer. Старый custom natal-wheel renderer и legacy SVG path удалены из текущего кода. `matrix_svg()` и отдельная compatibility visual остаются самостоятельными продуктами и не используются для natal chart geometry.

## Границы точности

Колесо выдаётся только для `precision == exact`, то есть когда подтверждены время рождения, координаты и IANA timezone. Для `date_only` и `time_without_location` API возвращает типизированный `409 insufficient_precision`; Mini App показывает структурированное состояние и список фактических планет, а не подставное колесо с техническим полднем.

В расчёте и визуальном adapter сохраняются единые product conventions: Tropical zodiac, Placidus `P`, Apparent Geocentric, True Node и активные точки из `app/core/astro.py`. Визуальный engine не пересчитывает и не «подправляет» canonical DTO; он реконструирует subject только из серверных canonical inputs.

## Реализация

| Контур | Реализация | Проверка |
|---|---|---|
| Adapter | `app/core/chart_rendering.py` | exact fixture, typed precision error, safety validation |
| Rasterizer | `resvg_py==0.5.0` | PNG/WebP magic, dimensions, visual artifact |
| API | `/api/chart/image` | owner auth, private cache, ETag/304, no SVG |
| Mini App | `apiBlob()` + object URL + revocation | Node syntax check, no legacy natal symbols |
| PDF | 2400×2400 print PNG, full-width natal section | PDF HTML tests and selfcheck |
| Matrix | separate `matrix_svg()` block | intentionally not removed by natal migration |

## Открытые release gates

Technical migration is implemented, but public commercial release is not declared ready. Kerykeion is AGPL-3.0, and Swiss Ephemeris uses an AGPL/Professional dual-license model. The owner/legal reviewer must select and document a compliant distribution strategy before exposing the service commercially. The pinned dependency and Docker/runtime verification must also be completed in the target image; Docker was unavailable in the current sandbox.

## Источники

[1]: https://kerykeion.net/content/docs "Kerykeion official documentation"  
[2]: https://pypi.org/project/kerykeion/ "Kerykeion PyPI"  
[3]: https://github.com/g-battaglia/kerykeion "Kerykeion source repository"  
[4]: https://pypi.org/project/resvg_py/ "resvg_py PyPI"  
[5]: https://github.com/baseplate-admin/resvg-py "resvg-py source repository"  
[6]: https://www.astro.com/swisseph/ "Swiss Ephemeris official licensing page"  
[7]: ../app/core/chart_rendering.py "OracleAI chart rasterization adapter"  
