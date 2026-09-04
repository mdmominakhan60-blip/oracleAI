# RU/EN localization glossary

**Дата:** 26 августа 2026

This glossary is the canonical language layer for UI, agent prompts and PDF labels. Technical terms remain stable across locales; user-facing copy must not fall back from English to Russian.

| Concept | RU | EN | Rule |
|---|---|---|---|
| Date-only chart | Только дата / дата без времени | Date only | Never imply houses, ASC or MC. |
| Exact chart | Точная карта | Exact chart | Requires confirmed time, coordinates and timezone. |
| Unknown time | Время не указано | Birth time is not set | Use an explicit limitation, never a guessed time. |
| Ascendant | Асцендент | Ascendant | Keep the technical label; hide it for date-only charts. |
| Midheaven | MC / МС | MC | Keep the canonical abbreviation in data; localize surrounding copy. |
| North node | Раху · северный узел | Rahu · north node | Vedic and Western semantics remain separate. |
| South node | Кету · южный узел | Ketu · south node | Same school-boundary rule as Rahu. |
| Tarot reading | Расклад Таро | Tarot reading | Tarot is not Lenormand. |
| Reversed card | Перевёрнутая карта | Reversed card | Orientation is persisted evidence, not model choice. |
| Memory paused | Память на паузе | Memory is paused | New facts are not saved or used in AI replies. |
| Account deletion | Удаление данных / аккаунта | Delete account / data | Confirmation and idempotent result are required. |
| Next step | Следующий шаг | Next step | Every reflective answer ends with an actionable but non-guaranteed step. |

Pluralization rules are tested in the existing RU/EN static regression and must be reviewed for counts 0, 1, 2–4, 5+ and 21+. PDF labels must use embedded project fonts or a verified fallback; unsupported glyphs must be caught by the PDF golden-case runner. Long labels are allowed to wrap; they must never be clipped or silently truncated.
