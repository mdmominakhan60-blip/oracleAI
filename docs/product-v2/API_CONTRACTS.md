# OracleAI v2 — API Contracts

Контракты **переиспользуемых** эндпоинтов. Все пути и имена полей извлечены из кода и помечены источником (`файл:строка`). Новых эндпоинтов, кроме отмеченных как «v2-добавление», не создаётся.

Базовый URL — относительный. Никакого второго origin в проде.

---

## 1. Заголовки клиента

| Заголовок | Где обязателен | Источник |
|---|---|---|
| `X-Session-Token` | Все запросы после минта | `miniapp/js/01-utils.js:95` |
| `X-Init-Data` | Fallback, если токена нет | `01-utils.js:98` |
| `X-Dev-Key` | Только в DEV_MODE при `?dev_user=` | `01-utils.js:137-139` |
| `X-Idempotency-Key` | `POST /api/chat/oracle`, `POST /api/chat/{agent}` | `app/api/routers/chat.py:36,131` |
| `X-Start-Param` | `GET /api/me` (реферальный start_param, ≤64) | `05-app.js:90` |
| `Content-Type: application/json` | Все JSON-запросы | `01-utils.js:134` |

**Порядок разрешения личности** (`app/api/deps.py:117`): `X-Session-Token` → `x-init-data` → `?dev_user=` (только в DEV_MODE, требует `X-Dev-Key` через `compare_digest`).

**Rate-limit бакеты** (`deps.py:62-67`): `read` 120/60с, `write` 30/60с, `llm` 12/60с, `admin` 60/60с. Отказ → 429 с `Retry-After`.

---

## 2. Авторизация

### `POST /api/auth/session` — `app/api/routers/auth_router.py:117`

Request:
```json
{"init_data": "<строка Telegram WebApp initData>"}
```

Response 200:
```json
{"session_token": "<tg_id>:<unix_expiry>:<hmac_sha256_16hex>", "expires_in": 86400}
```

Ошибки: `401` — подпись не подтверждена; `401` — `initData уже использована (replay)`; `429` — чаще 10/мин (`Retry-After`); `503` — replay-store недоступен при `REPLAY_FAIL_CLOSED=1`.

Токен stateless: `HMAC_SHA256(bot_token, "tg_id:expiry")[:16]` (`app/api/auth_common.py:13-17`). Ротация `BOT_TOKEN` инвалидирует все живые сессии.

---

## 3. Bootstrap — `GET /api/me`

`app/api/routers/profile.py:120-180` (`_me_payload`). Контракт заморожен (BUS-807) — **не менять**. Один вызов при старте приложения.

Ключи верхнего уровня:
```json
{
  "tg_id": 1001,
  "name": "...", "username": "...", "oracle_name": "Лилит",
  "persona": "friend",
  "tz": "Europe/Moscow",
  "birth_date": "1994-05-12", "birth_city": "Москва",
  "birth_time_known": true,
  "birth_time": "14:30",                 // null если precision="unknown"
  "birth_time_precision": "exact",       // exact | approx | unknown
  "onboarding_step": null,
  "age_confirmed_at": "2026-10-10T09:12:00+00:00",   // null если 16+ не подтверждено (v2-поле)
  "natal_technique": "astrology",
  "onboarded": true,
  "sun": {"sign": "Телец", "symbol": "♉", "element": "земля"},
  "ascendant": "Лев",                    // null если нет точного времени
  "chart_mode": "full",                  // "full" | "lite"
  "chart_precision": "exact",
  "chart_note": "...",
  "planets": [ /* 10 планет, см. §6 */ ],
  "crystals": 40,
  "sub_active": true, "sub_days_left": 12,
  "plan": "premium",
  "allowance": { /* лимиты, см. §3.1 */ },
  "questions_left": 5, "questions_total": 10,
  "memories": ["...", "..."],            // пусто при memory_enabled=0
  "diary_streak": 3, "global_streak": 7,
  "morning_push": true,
  "memory_enabled": false,
  "lang": "ru",
  "gender": null,
  "entitlements": [],
  "reports": [],
  "canonical_entitlements": {"status": "...", "period_end": "...", "cancel_at_period_end": false, "grace_until": null},
  "subscription_lifecycle": {"status": "...", "period_end": "...", "cancel_at_period_end": false, "grace_until": null},
  "agents": [ /* список агентов — в v2 не используется для выбора */ ],
  "flags": {},
  "feedback_pending": false,
  "webapp_url": "https://..."
}
```

### 3.1 `allowance` (`app/services/limits.py`)
```json
{"plan": "free", "period": "day", "limit": 3, "left": 2, "used": 1,
 "charge": "plan", "followup_left": 2, "emergency_cost": 20}
```

### `GET /api/me/v2`
Тот же расчёт, сгруппированный в `profile` / `chart` / `subscription` / `activity`. Доступен только за флагом `r07_api_v2`, иначе 404. Для v2 предпочтителен `/api/me` (контракт стабилен и уже покрыт тестами).

---

## 4. Единый Oracle — `POST /api/chat/oracle`

`app/api/routers/chat.py:34-48` → `app/services/chat.py:101-253`.

**Это главный эндпоинт v2.** Он возвращает полный диагностический payload: домен, доказательную подпись и `thread_id` — то, что нужно фронту, чтобы нарисовать сцену.

> **Важное разделение. `POST /api/ask` НЕ подходит для v2**, несмотря на название. Это compat-ручка: `app/api/routers/chat.py:59-61` берёт результат `chat_svc.ask()` (который содержит `routing`, `proof`, `thread_id`, `charge`) и **возвращает только три ключа** — `{answer, questions_left, allowance}`. Вся диагностика теряется. Поэтому v2 зовёт `POST /api/chat/oracle` (тот же `DEFAULT_AGENT`, полный ответ).

Request:
```json
{"text": "что скажут карты про мой Сатурн в этом месяце"}
```
Контракт `AskIn` (`app/api/contracts/chat.py:7`): `text` (1..1000, `min_length=1, max_length=1000`), `allow_paid: bool = true`. Опционально заголовок `X-Idempotency-Key` (обрезается до 160 символов).

Response 200 — **полный payload** (`app/services/chat.py:241-253`):
```json
{
  "answer": "Текст ответа Oracle…",
  "agent": "tarot",                  // домен, выбранный роутером
  "requested_agent": "oracle",       // что запросили
  "routing": {
    "agent": "tarot",
    "confidence": 0.88,
    "score": 9,
    "runner_up_score": 3,
    "reason": "matched таро, карты",
    "candidates": ["tarot", "astro", "oracle"],
    "auto_route": true
  },
  "agent_profile": { /* AgentSpec.as_dict(user) */ },
  "proof": {
    "mode": "deterministic",        // deterministic | offline | safety
    "tools_used": ["draw_tarot"],
    "tools_available": ["draw_tarot", "save_memory", "recall_memory"],
    "quality": {"risk_level": "medium", "memory": "opt_in", "output_contract": "agent_response.v1", "skills_max_active": 3},
    "provider": "anthropic",        // null если LLM в этом процессе ещё не звался
    "model": "claude-sonnet-4-5"
  },
  "thread_id": 42,
  "charge": "plan",                 // plan | followup | ent_question | ent_spread | crystals | none
  "allowance": { /* после списания */ }
}
```

**Кризисный ответ — другой контракт** (`app/services/chat.py:258-290`): в payload остаются `answer`, `agent`, `agent_profile`, `proof`, `thread_id`, `charge: "none"`, `allowance`, `safety` (категория); **отсутствуют** только `requested_agent` и `routing`. Лимит не списывается. Фронт обязан показать контакты помощи, а не обычный пузырь.

Поведение `routing`:
- `routing.auto_route = true` только когда запрошен `oracle`, `safety_level != CRISIS` и роутер перенаправил (`chat.py:138-143`).
- При явном выборе агента ≠ `oracle`: `routing.reason = "explicit agent selection wins"`, `auto_route = false`. **В v2 этот путь не используется.**

Ошибки:
| Код | Причина | Поведение фронта |
|---|---|---|
| `400` | Пустой текст / >1000 символов / `request too long` | Инлайн-ошибка, ввод сохранён |
| `402` | `access_denied`, `reason="sub_over"` | «Доступ завершён» → продление подписки |
| `403` | Иное `ChatDenied` | Paywall (`SCREEN_SPEC` §14) |
| `404` | `"нет такого собеседника"` (только если агент вне реестра) | Не достигается при `oracle` |
| `409` | `{"detail": {"code": "request_in_progress"}}` — тот же `X-Idempotency-Key` в полёте | Не ретраить; ждать |
| `422` | Pydantic-валидация `AskIn` | Инлайн-ошибка |
| `429` | Rate limit `llm` (12/60с) или лимит вопросов | «Вопросы исчерпаны» + `Retry-After` |

Формат access-denied: `status = 402 if reason == "sub_over" else 429`, текст локализован (`app/api/common/errors.py:25-36`).

### `POST /api/ask` — compat, не используется в v2
`app/api/routers/chat.py:51-61`. Response — **только** `{answer, questions_left, allowance}`. `allow_paid` из тела **игнорируется**. Оставлена для совместимости со старым фронтом; новый интерфейс её не зовёт.

### Idempotency
`X-Idempotency-Key` → таблица `chat_requests`. Повтор с тем же ключом: `completed` → возвращает сохранённый ответ; `processing` → 409; `conflict` (ключ другого пользователя) → 400.

---

## 5. Чат и сессии

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/chat` | Лента с главным Oracle (compat) — `{messages: []}` |
| `GET` | `/api/chat/{agent}` | `{messages, thread, agent}` — история |
| `DELETE` | `/api/chat/{agent}` | `{ok: true}` — архив; сообщения и память сохраняются |
| `GET` | `/api/chat/{agent}/sessions?offset=` | Список сессий, страницы по 100, новые впереди |
| `POST` | `/api/chat/{agent}/sessions` | `{thread_id, title}` |
| `DELETE` | `/api/chat/{agent}/sessions` | `{ok, archived, memory_preserved: true}` |
| `GET` | `/api/chat/{agent}/sessions/{thread_id}` | Сообщения сессии, лимит 60 |
| `POST` | `/api/chat/{agent}/sessions/{thread_id}` | Тот же полный payload, что `/api/chat/oracle` |
| `DELETE` | `/api/chat/{agent}/sessions/{thread_id}` | Архив сессии |

Для v2: **сессии остаются** — многочатовой режим полезен ( ChatGPT-паттерн), но выбора агента у них нет. Рекомендуемая модель: одна сессия = один сюжет/период жизни, а не один агент.

---

## 6. Натальная карта

### `GET /api/chart` — `app/api/routers/chart.py:79-132`
```json
{
  "natal_schema_version": 2,
  "mode": "full",                     // "full" | "lite"
  "precision": "exact",
  "engine": "Swiss Ephemeris via Kerykeion",
  "engine_provenance": {"product_engine": "OracleAI Engine", "adapter_version": "oracleai-kerykeion-engine-v2", "backend": "Kerykeion", "backend_version": "5.12.9", "ephemeris": "Swiss Ephemeris", "license_notice": "AGPL-3.0/commercial licensing obligations apply…"},
  "zodiac_type": "Tropical",
  "house_system": "P", "house_system_name": "Placidus",
  "perspective_type": "Apparent Geocentric",
  "sun": "Телец",
  "ascendant": {"sign": "Лев", "deg": 12.3, "deg_exact": 12.341, "abs_deg": 132.3, "abs_deg_exact": 132.341},
  "mc": {"sign": "...", "deg": 0, "deg_exact": 0, "abs_deg": 0, "abs_deg_exact": 0},
  "planets": [{"name": "Солнце", "sign": "Телец", "deg": 21.4, "deg_exact": 21.412, "abs_deg": 51.4, "abs_deg_exact": 51.412, "house": 8, "retro": false}],
  "houses": [{"n": 1, "sign": "Лев", "deg": 12.3, "deg_exact": 12.341, "abs_deg": 132.3, "abs_deg_exact": 132.341}],
  "aspects": [{"p1": "Солнце", "p2": "Луна", "aspect": "тригон", "glyph": "△", "orb": 2.1}],
  "nodes": [{"name": "Раху (Северный узел)", "sign": "...", "deg": 0, "deg_exact": 0, "abs_deg": 0, "abs_deg_exact": 0, "house": null, "retro": true}],
  "lunar_nodes": {"mode": "true", "mode_label": "True Node", "rahu": null, "ketu": null},
  "additional_points": [{"name": "Хирон", "point": "Chiron", "sign": "...", "deg": 0, "deg_exact": 0, "abs_deg": 0, "abs_deg_exact": 0, "house": null, "retro": false}],
  "note": "...",
  "calculation": {"input": {"birth_date": "1994-05-12", "birth_time": "14:30", "city": "Москва", "lat": 55.75, "lon": 37.62, "tz": "Europe/Moscow", "time_known": true, "precision_reason": "date_only", "adapter_version": "oracleai-kerykeion-engine-v2"}, "configuration_fingerprint": "sha256[:16]", "values": {"rounded_for_ui": true, "exact_fields_suffix": "_exact", "longitude_unit": "degrees", "orb_unit": "degrees"}},
  "sections": {"version": 1, "exact": true, "sections": {"identity": {"title": "Ядро личности и маска", "items": [{"key": "sun", "label": "Солнце", "value": "Телец · 21.4° · 8-й дом", "sign": "Телец", "house": 8, "meaning": "...", "available": true}]}}},
  "birth": {"date": "1994-05-12", "time": "14:30", "city": "Москва", "time_known": true, "time_precision": "exact"}
}
```

**`precision` — допустимые значения** (`app/core/astro.py:452`): `exact` (время + координаты + tz → видны дома, ASC, MC), `time_without_location`, `date_only`, `interval` (неоднозначное локальное время из-за смены пояса), `sun_only` (lite-режим, kerykeion недоступен).

**Обязательное правило UI:** при `precision != "exact"` дома и асцендент не показываются. Валидатор `validate_chart_text` (`app/core/interpretation.py:310`) отвергает ссылки на дома при неизвестном времени — интерфейс не должен создавать данных, которые отклонятся на проверке.

**Placements:** 10 планет (Солнце…Плутон), 12 домов, аспекты 5 типов (`conjunction 0°/opposition 180°/trine 120°/square 90°/sextile 60°`, орбы 8/8/8/7/6°), узлы (Раху/Кету/Лилит), 5 дополнительных точек (Хирон, Джуно, Церера, Веста, Паллада). `sections` — 4 группы: `identity`, `mind_career`, `relationships`, `nodes`.

### Прочие endpoint'ы карты
| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/chart` | Построить/обновить карту; пишет `users.chart_json` |
| `GET` | `/api/chart/image` | Растр PNG/WebP; `Cache-Control: private, max-age=3600` |
| `POST` | `/api/chart/interpret` | AI-разбор карты (rate_limit `llm`) |
| `GET` | `/api/matrix` | Матрица Судьбы: 7 позиций (`personal, spirit, family, destiny, center, love, money`), каждая `{n, arcana, title, meaning, keywords, plus, minus, advice}`. Требует `birth_date`, иначе 400 |
| `GET` | `/api/chart/pdf` | PDF через WeasyPrint; 503 если недоступен |
| `GET` | `/api/city/suggest` | Автодополнение городов с опечатками (`difflib`), ≤8 результатов |
| `GET` | `/api/placements` | Каталог 24 калькуляторов `[{code, label, scope}]` + `palm` |

---

## 7. Таро — каталог (проверено, 10 раскладов)

| code | emoji | title | cards | tier |
|---|---|---|---|---|
| `one` | 🂠 | Одна карта | 1 | included |
| `three` | 🂠🂠🂠 | Прошлое · Настоящее · Будущее | 3 | included |
| `love` | 💞 | На отношения | 4 | included |
| `path` | 🛤️ | Выбор пути | 5 | included |
| `choice` | 🔀 | Выбор из двух | 5 | premium |
| `money` | 🪙 | Деньги и дело | 4 | premium |
| `career` | 🧭 | Карьера и путь | 5 | premium |
| `work` | ⚖️ | Проблемы на работе | 6 | premium |
| `celtic` | ✝️ | Кельтский крест | 10 | premium |
| `year` | 🎡 | Колесо года | 12 | premium |

`DEFAULT_SPREAD = "three"`. Позиции — в `app/core/tarot.py:280-380` (`SPREADS[code]["positions"]`).

**Важно:** `included` ≠ бесплатный unconditionally. `included`-расклад тратит вопрос дня тарифа (`limits.spread_access` → `limits.check` → PLAN/FOLLOWUP). Premium — либо купленное право (`entitlements` `kind='spread'`), либо тот же тарифный путь.

### `GET /api/tarot/spreads` — витрина (`app/services/catalog.py:54-79`)
```json
[{"code": "three", "title": "Прошлое · Настоящее · Будущее",
  "positions": ["Прошлое", "Настоящее", "Будущее"], "cards": 3,
  "tier": "included", "emoji": "🂠🂠🂠", "hint": "...",
  "sku": "spread_three", "price_stars": 150, "price_crystals": 20, "owned": 0}]
```
`owned` считается **только для premium** и всегда 0 у `included`. Сортировка: `included` первыми, затем по числу карт.

### `GET /api/tarot/spreads/full` — `tarot.py:25-34`
```json
[{"code": "three", "title": "...", "positions": [...], "tier": "included", "emoji": "...", "hint": "...", "guide": "2–4 предложения, что покажет расклад"}]
```
Без цен и `owned` — для экрана выбора.

### `POST /api/tarot/draw?spread=<code>` — `tarot.py:36-62`
Request (тело или query — фронт шлёт в теле):
```json
{"question": "что ждёт меня в отношениях", "deck": "tarot"}
```
`deck` ∈ `{tarot, lenormand}`; неизвестное нормализуется в `tarot`.

Response — `app/services/chat.py:304-350`:
```json
{
  "reading_id": 123, "title": "Прошлое · Настоящее · Будущее",
  "positions": ["Прошлое", "Настоящее", "Будущее"],
  "cards": [{"img": "m03", "name": "Императрица", "emoji": "👑", "arcana": "major",
             "num": "III", "suit": null, "reversed": false,
             "meaning": "изобилие, забота, плодородие…",
             "short": "изобилие", "advice": "позволь себе получить"}],
  "spread": "three", "deck": "tarot", "thread_id": 42,
  "ledger": {
    "version": "tarot-ledger-v1", "deck_id": "rws-78-v1", "deck": "tarot",
    "tradition": "Rider-Waite-Smith", "spread": "three",
    "entries": [{"index": 0, "position": "Прошлое", "card_id": "m03", "name": "Императрица", "arcana": "major", "suit": null, "reversed": false, "orientation": "upright"}],
    "adjacent_combinations": [{"left": "Императрица", "right": "Император", "rule": "adjacent_cards_read_together", "type": "adjacent_pair"}],
    "checksum": "sha256[:16]",
    "interpretation_boundary": "Cards and positions are calculated evidence; …",
    "replay": {"version": "tarot-replay-v1", "mode": "immutable_cards", "source": "server_persisted_cards_json", "deterministic": true, "checksum": "..."}
  },
  "charge": "plan",
  "guide": "..."
}
```

**Ключевой инвариант:** карты сохраняются в БД **до** трактовки. `TAROT_REPLAY_CONTRACT.mode = "immutable_cards"`; `replay_ledger()` пересобирает ledger из тех же карт и сверяет `checksum` — при расхождении `ValueError("tarot ledger checksum mismatch")`. Фронт не должен пытаться изменить карты клиентски.

### `POST /api/tarot/interpret/{reading_id}` — `tarot.py:64-77`
Response — текст трактовки. Повторный вызов возвращает сохранённый ответ, не новую генерацию. Rate limit `llm`.

### Прочие
| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/tarot/history` | `{items: [{id, spread, question, cards, deck, outcome, created_at}]}` |
| `GET` | `/api/tarot/history/{id}` | Полный расклад + `ledger`, пересобранный из `cards_json` |
| `GET` | `/api/tarot/stats` | `{total, by_spread, outcome_stats}` |
| `POST` | `/api/tarot/outcome/{id}` | `{outcome: "came_true"\|"partly"\|"no"}` |

### Поля карты в колоде (78 карт, `app/core/tarot.py:197-215`)
| Поле | Старший | Младший |
|---|---|---|
| `img` | `"m00"`…`"m21"` | `"{wands|cups|swords|pents}{01..14}"` |
| `name` | `"Шут"` | `"Туз Кубков"` |
| `meaning` | архетип + тень | из `RWS_MINOR` |
| `short` | опц. | `null` |
| `advice` | опц. | `null` |
| `arcana` | `"major"` | `"minor"` |
| `num` | `"0"`…`"XXI"` | `"1".."10"`, затем ранг |
| `suit` | `null` | `"Кубков"` и т.д. |

Маппинг на файл: `/static/img/{tarot|lenormand}/{img}.jpg` (`miniapp/js/09-tarot.js:106`). **78 файлов в каждой папке — совпадение 1:1, проверено.**

Колода (`DECK_META`, `tarot.py:446`): `tarot` → `rws-78-v1` (Rider-Waite-Smith), `lenormand` → `mary-el-78-v1`.

---

## 8. Совместимость и партнёры

| Метод | Путь | Назначение / ответ |
|---|---|---|
| `GET` | `/api/partners` | Список партнёров |
| `POST` | `/api/partners` | `{id, name, relation, birth_date, birth_time, birth_city, chart_json}` |
| `DELETE` | `/api/partners/{id}` | `{ok: true}` — `DELETE ... WHERE id=:id AND tg_id=:tg_id` |
| `POST` | `/api/compat` | Без списания лимита. `{you:{sign,element}, partner:{sign,element}, total, score, relation, verdict, breakdown[], spheres[]}` |
| `POST` | `/api/compat/full` | AI-разбор пары; требует `active_user`; `{answer, scores}` |
| `POST` | `/api/synastry` | Точная синастрия по сохранённому партнёру; **требует `active_user`** |
| `POST` | `/api/composite` | Композит, круговые midpoint'ы; **требует `active_user`** |
| `POST` | `/api/transits` | `{as_of: "YYYY-MM-DD", time?}` детерминированный снапшот; **требует `active_user`** |
| `POST` | `/api/returns` | `{planet: "Sun", year}` солярная возвратность; **требует `active_user`** |

`spheres[]` — 5 сфер 0..100: `love`, `harmony`, `career`, `friendship`, `growth`. `total` = `clamp(35, 98)`. `verdict`: ≥80 союз-пламя/основа/ветер/глубина, ≥60 союз-рост, иначе союз-урок.

Ошибка `ChartProductError` → 422 `{code, message, missing}`. Чужой/несуществующий партнёр → единая 404 `partner_not_found` (не палит существование строки).

---

## 9. Память и shared context

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/memories` | `[{id, fact, kind, weight, last_used, created_at}]` — пусто при `memory_enabled=0` |
| `POST` | `/api/memories` | Создать факт вручную; **409 при `memory_enabled=0`** |
| `DELETE` | `/api/memories/{id}` | `DELETE WHERE id=:id AND tg_id=:tg_id`; единая 404 |

**Сверено с живым backend 2026-10-12** (см. §9.1 ниже).

### 9.1 Фактическое поведение (проверено, не предположено)

| Операция | Фактический результат |
|---|---|
| `GET /api/memories` без авторизации | `401 {"detail":"подпись Telegram не подтверждена"}` |
| `POST /api/memories` при `memory_enabled=false` | `409 {"detail":"память отключена в настройках приватности"}` |
| `POST /api/memories` `fact` короче 3 символов | `422`, массив Pydantic-ошибок (`detail[].msg`) |
| `POST /api/memories` валидный | `200 {"ok":true}` — **созданная запись НЕ возвращается** |
| `POST /api/memories` дубликат текста | `200 {"ok":true}` без новой строки (вес существующей +1) |
| `POST /api/memories` `kind:"bogus"` | `200`, сохраняется как есть — множество `kind` на уровне HTTP не проверяется |
| `GET /api/memories/{id}` | `405 Method Not Allowed` — **чтения одной записи нет** |
| `PATCH /api/memories/{id}` | `405 Method Not Allowed` — **редактирования нет** |
| `DELETE` чужого/несуществующего id | `404 {"detail":"нет такой памяти"}` |
| `DELETE` повторно того же id | `404` — идемпотентности в смысле «второй раз 200» нет |

Следствия для интерфейса:
- После создания список **перечитывается**, а не дополняется оптимистично: ответа с записью backend не даёт.
- `kind` интерфейс всегда отправляет как `"fact"`: категории на сервере не валидируются, а модель их не выбирает.
- Чтение и удаление при выключенной памяти **доступны** — флаг проверяется только в `POST`. Поэтому «память выключена» не равно «данные потеряны».
- Сортировка `weight DESC, id DESC`, серверный лимит **60**, пагинации нет.
- **Редактирование записи не реализуется**: контракта нет. Это ограничение, а не упущение интерфейса.
- Факты не пишутся в `localStorage`; локально живёт только черновик неотправленного текста.
| `GET` | `/api/memory/context?limit=&offset=` | `{items: [{id, event_type, agent, content, source_ref, created_at, expires_at}], owner_scoped: true}` |
| `GET` | `/api/memory/snapshots?limit=&offset=` | `{items: [{id, snapshot_type, snapshot_key, payload, created_at, expires_at}]}` |

**Параметра `tg_id` в контракте нет ни у одного эндпоинта** — owner-scope ставится в SQL из auth-зависимости. Подделка владельца невозможна по построению.

**Поля `memory_enabled`:**
- default **0** (выключено) — `test_new_users_default_to_memory_off`, `test_security_regressions.py:224`.
- Проверяется в трёх местах: в API (`profile.py:444,457`), в `_context` (`runtime.py:70-72`) и **в самих инструментах** (`tool_registry.py:937,950,960`): «Tool calls are model-generated and must never be able to override the user's setting».
- Изменяется через `PATCH /api/profile {memory_enabled}` или кнопку в боте.

---

## 10. История

### 10.1 Общий архив активностей
`GET /api/history?limit=1..100` — `app/api/routers/history.py:17-32`.
```json
{"items": [{
  "kind": "report|tarot|chat|diary",
  "entry_id": 12,
  "item_id": 12,
  "source_id": "tarot:12",
  "evidence_id": "tarot:12",            // null для diary
  "title": "three",
  "created_at": "2026-10-09T…",
  "status": "ready",
  "preview": "Звезда, Солнце, Луна",   // ≤160, пусто для chat/diary
  "action": {"type": "reading", "kind": "tarot", "id": 12},
  "deep_link": "/api/tarot/history/12",
  "deletion": "use the source surface to delete or archive this item"
}]}
```
`source_id` — всегда строка `f"{kind}:{entry_id}"` (не `"reading"`). `evidence_id` = `f"{kind}:{entry_id}"` только для `report` и `tarot`, иначе `null`. `deep_link` — путь внутри `/api`, вызывается как относительный GET. Архивные треды исключаются. Palm намеренно не включается. **Приватный контент не отдаётся** — только метаданные.

### 10.2 Серверная единая история диалога с Oracle (Stage 4.4 & 4.4.1)
`GET /api/chat/history/unified?limit=50&before_id=&before_created_at=` (алиас: `GET /api/chat/unified`) — `app/api/routers/chat.py`.
Объединяет сообщения всех 4 доменов (`oracle`, `astro`, `tarot`, `chiromant`) с детерминированной сортировкой по `(created_at ASC, id ASC)` и стабильной составной keyset-пагинацией:
```json
{
  "messages": [
    {
      "id": 14,
      "role": "assistant",
      "text": "Текст ответа",
      "agent": "tarot",
      "thread_id": 5,
      "created_at": "2026-10-11T17:10:30.333419+00:00"
    }
  ],
  "has_more": false,
  "oldest_id": 14,
  "oldest_created_at": "2026-10-11T17:10:30.333419+00:00",
  "newest_id": 50,
  "newest_created_at": "2026-10-11T21:51:18.773288+00:00",
  "missing": []
}
```
- **Составной keyset-курсор:** пагинация в прошлое передает `before_id` и `before_created_at`. Условие SQL `(m.created_at < :before_created_at OR (m.created_at = :before_created_at AND m.id < :before_id))` гарантирует монотонность даже при несовпадении порядка автоинкрементного ID и времени записи. Для обратной совместимости, если передан только `before_id`, сервер автоматически резолвит его `created_at`.
- **Семантика missing:** `missing: []` — список доменов, недоступных при выборке. На сервере выборка выполняется единым атомарным запросом к общей таблице `messages`, поэтому при успешном ответе массив всегда пустой `[]`. Фиктивные ошибки источников не имитируются. Поле сохранено для совместимости типов.
- **Исключение архива:** отсекаются сообщения из архивных тредов (`threads.archived = 1`).
- **Авторизация и изоляция:** `Depends(confirmed_age_user)`, строгий owner-scope `WHERE m.tg_id = :tg_id`. Анонимный вызов → 401.
- **Стабильность пагинации:** добавление новых входящих сообщений во время чтения ленты не сдвигает keyset-курсор в прошлое (в отличие от `OFFSET`, где новые строки вызывают дублирование элементов между страницами). Гарантия snapshot consistency не заявляется, так как транзакционный snapshot на уровне HTTP-запросов без сессионных блокировок не используется.
- **Обратная совместимость:** существующие эндпоинты `GET /api/chat/{agent}` и `GET /api/chat/{agent}/sessions` сохранены для legacy miniapp.

---

## 11. Люди и граф памяти (существующий контракт + v2-добавление)

### Существующее
`GET/POST/DELETE /api/partners` (см. §8). Поля: `id, tg_id, name, relation, birth_date, birth_time, birth_city, birth_lat, birth_lon, tz, chart_json, created_at`.

**Два именования одной сущности, не перепутать:** в API люди называются `partners` (старый контракт), а в UI — `people`. Один и тот же ресурс.

### v2-добавление: 13 новых эндпоинтов

Реализуются на Этапе 6 (`MIGRATION_PLAN.md`). Схема — `ARCHITECTURE.md` §4. Все с `Depends(current_user)`, owner-scope `WHERE ... AND tg_id=:tg_id` в SQL, rate-limit `read`/`write`. Параметра `tg_id` в контракте нет.

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/people` | Люди + агрегированная сводка (сколько чтений, фактов, событий) |
| `POST` | `/api/people` | Создать человека |
| `GET` | `/api/people/{id}` | Карточка человека с фактами, чтениями и событиями |
| `DELETE` | `/api/people/{id}` | Удалить человека |
| `GET` | `/api/events` | Личные события, хронологически |
| `POST` | `/api/events` | Создать событие |
| `GET` | `/api/events/{id}` | Одно событие + его связи |
| `DELETE` | `/api/events/{id}` | Удалить событие |
| `GET` | `/api/memories/{id}` | Факт + его связи (источник для «отвязать») |
| `PATCH` | `/api/memories/{id}` | Изменить текст/тип факта |
| `POST` | `/api/memory-links` | Связать сущности |
| `DELETE` | `/api/memory-links/{id}` | Удалить связь |
| `GET` | `/api/people/{id}/timeline` | Обратная хроника по линии отношений |

Все три контракта, которых не хватало (`GET /api/people/{id}`, `GET|PATCH /api/memories/{id}`, `GET /api/events/{id}`), описаны в §11.1 — они закрывают разрыв между экранами и API. Расширение `GET /api/memories` полями `source_kind` и `links` — §11.2.

**Все 13 — новые, в текущем backend их нет.** Реализуются на Этапе 6. Существующими остаются только `/api/partners*` (старое имя людей) и `GET /api/memories`.

#### `GET /api/people`
```json
{"items": [{
  "id": 7, "name": "Кирилл", "relation": "partner",
  "birth_date": "1990-03-04", "synastry_ready": true,
  "conversations": [
    {"id": 42, "title": "Что между нами", "created_at": "...",
     "messages_count": 12, "preview": ""}
  ],
  "counts": {"memories": 4, "readings": 2, "events": 3, "diary": 5, "threads": 1}
}]}
```

#### `POST /api/people`
Request: `{"name": "Кирилл", "relation": "partner", "birth_date": "04.03.1990", "birth_time": "14:00", "birth_city": "Москва"}` — совместим с существующим `PartnerIn`. Response: `{"id": 7, "ok": true}`.

#### `GET /api/events`
```json
{"items": [{
  "id": 3, "title": "Первое свидание", "happened_on": "2026-02-14",
  "note": "...", "source_kind": "user", "source_id": null, "created_at": "..."
}]}
```
`source_kind` ∈ `{user, diary, reading}` — **никогда не `derived`**: событие это то, что произошло или что пользователь сохранил. Система не создаёт событий сама.

#### `POST /api/events`
Request: `{"title": "1..120", "happened_on": "YYYY-MM-DD | null", "note": "≤1000", "source_kind": "user"}`. `source_kind` при создании из UI **всегда** `user`. Response: `{"id": 3, "ok": true}`.

#### `POST /api/memory-links`
Request:
```json
{"left": {"kind": "memory", "id": 11}, "right": {"kind": "partner", "id": 7}, "origin": "explicit"}
```
- `kind` ∈ `{memory, partner, reading, diary, event, thread}` — закрытый набор из 6 типов, иначе 422. Тип `thread` доступен **только** с `origin="derived"` (создаётся сервером по совпадению имени); вручную `thread` связать нельзя (422 `thread_requires_derived_origin`).
- `origin` ∈ `{explicit, derived}`. **UI может создавать только `explicit`.** Значение `derived` выставляется исключительно сервером (эвристика в `extract_memory_llm`), и такой факт помечается в UI как наблюдение, а не как факт пользователя.
- Связь `memory ↔ memory` запрещена (422 `same_kind_link_forbidden`).
- Повторная связь → идемпотентно `{"ok": true, "already": true}`.

Response: `{"id": 15, "ok": true}`.

#### `DELETE /api/memory-links/{id}`
`{"ok": true}`; 404 `"нет такой связи"` (чужой и несуществующий неразличимы).

#### `GET /api/people/{id}/timeline`
```json
{"items": [{
  "kind": "event|reading|memory|diary",
  "id": 12, "date": "2026-02-14",
  "title": "Первое свидание",
  "preview": "≤160 символов",         // пусто для diary
  "source_kind": "user|derived",      // только для kind=memory
  "deep_link": "/api/events/12"        // путь внутри /api, относительный GET
}], "person": {"id": 7, "name": "Кирилл"}}
```
Сортировка — по `date` desc. **Приватный контент не отдаётся** — только метаданные, как в `/api/history`.

#### Ошибки новых эндпоинтов
| Код | Когда |
|---|---|
| `404` | Чужой или несуществующий id — единый ответ |
| `409` | `memory_off` — попытка создать связь или событие при `memory_enabled=0` |
| `422` | Неизвестный `kind`, `origin != explicit` из UI, связь `memory↔memory` |

**Consent.** При `memory_enabled=0`: чтение (`GET`) работает — пользователь имеет право увидеть, что запомнено, иначе удаление невозможно; запись (`POST`) → 409.

#### Удаление каскадом
`DELETE /api/people/{id}` удаляет связи **приложением**, не `ON DELETE CASCADE` в БД: одна ошибка схемы не должна утаскивать факты. Связанные `memories` при этом **сохраняются**, но теряют связь (становятся «без привязки»). `DELETE /api/events/{id}` — аналогично. `POST /api/account/delete` чистит `memory_links` и `personal_events` через тот же allowlist-механизм, что и остальные таблицы (`app/repo/users.py:202`).

### 11.1 Три недостающих контракта (закрывают разрыв UI ↔ API)

Ранее в документе отсутствовали три endpoint'а, на которые ссылались `SCREEN_SPEC.md` и `UX_FLOWS.md`. Ниже — их контракты. **Все три новые, в текущем backend их нет** — они реализуются на Этапе 6 (`MIGRATION_PLAN.md`).

#### `GET /api/people/{id}` — карточка человека

Нужен `SCREEN_SPEC.md` §8 (Person Profile). Без него экран не может показать ни факты, ни чтения.

Request: путь `{id}`. Owner-scope: `SELECT ... FROM partners WHERE id=:id AND tg_id=:tg_id`.

Response 200:
```json
{
  "id": 7, "name": "Кирилл", "relation": "partner",
  "birth_date": "1990-03-04", "birth_city": "Москва",
  "synastry_ready": true,
  "memories": [
    {"id": 11, "fact": "работает в IT", "kind": "person",
     "source_kind": "user", "weight": 2, "created_at": "..."}
  ],
  "readings": [
    {"id": 55, "spread": "love", "question": "что между нами",
     "created_at": "...", "cards_preview": "Звезда, Солнце, Луна"}
  ],
  "events": [
    {"id": 3, "title": "Первое свидание", "happened_on": "2026-02-14", "source_kind": "user"}
  ],
  "counts": {"memories": 4, "readings": 2, "events": 3, "diary": 5}
}
```
- `birth_date`, `birth_city` — из существующей таблицы `partners`, отдаются как есть.
- `synastry_ready` — существующий признак (полная точная карта партнёра).
- `readings[].cards_preview` — только имена карт, без `answer` (приватный контент не отдаётся).
- `conversations[]` — **только метаданные**: `title`, `created_at`, `messages_count`, `preview` принудительно `""`. Текст переписки не отдаётся, как в `/api/history`.
- `memories[].source_kind` — **новое поле** (`user` | `derived`), см. §11.2.

Ошибки: `404` `"человек не найден"` (чужой и несуществующий неразличимы). Rate-limit `read`. Consent: при `memory_enabled=0` блоки `memories` и `events` возвращаются **пустыми**, но `id/name/relation/birth_*/counts` отдаются — профиль человека не является приватной памятью, и пользователь имеет право его видеть.

#### `GET /api/memories/{id}` + `PATCH /api/memories/{id}` — просмотр и правка факта

`PATCH` нужен `SCREEN_SPEC.md` §13 («каждый: редактировать / удалить / отвязать»). Раньше существовали только `POST` и `DELETE`, то есть UI обещал правку без API.

Request `PATCH`:
```json
{"fact": "новый текст факта 3..1000", "kind": "fact"}
```
Оба поля опциональны, но хотя бы одно обязательно. `kind` ∈ `{person, event, emotion, goal, fact}` — иначе 422. **`source_kind` через `PATCH` изменить нельзя**: 422 `source_kind_readonly`. Поле устанавливается только сервером (см. §11.2).

Response 200 — тот же объект факта, что в `GET /api/memories` (§9), с `source_kind`.

Request `GET`: путь `{id}`. Response — объект факта **плюс** блок связей:
```json
{
  "id": 11, "fact": "работает в IT", "kind": "person",
  "source_kind": "user", "weight": 2, "created_at": "...",
  "last_used": "...",
  "links": [
    {"link_id": 15, "kind": "partner", "id": 7, "label": "Кирилл", "origin": "explicit"},
    {"link_id": 16, "kind": "event", "id": 3, "label": "Первое свидание", "origin": "derived"}
  ]
}
```
Это источник данных для действия «отвязать факт от человека» (`SCREEN_SPEC.md` §13): UI читает `links`, показывает их с признаком `origin` и удаляет конкретный `link_id` через `DELETE /api/memory-links/{link_id}`. Связь с `origin="derived"` показывается с пометкой «я связала сама» и удаляется тем же вызовом — отзыв производной связи разрешён.

Ошибки: `404` `"нет такой памяти"`; `409` `"память отключена в настройках приватности"` для `PATCH` (как у `POST`). Rate-limit `read`/`write`.

#### `GET /api/events/{id}` — одно событие

Нужен, потому что `GET /api/people/{id}/timeline` возвращает `deep_link: "/api/events/{id}"`, а обработчика для этого пути не было. Без `GET` тап по записи таймлайна ведёт в 404.

Request: путь `{id}`. Owner-scope: `WHERE id=:id AND tg_id=:tg_id`.

Response 200:
```json
{
  "id": 3, "title": "Первое свидание", "happened_on": "2026-02-14",
  "note": "...", "source_kind": "user", "source_id": null,
  "created_at": "...",
  "links": [
    {"link_id": 20, "kind": "partner", "id": 7, "label": "Кирилл", "origin": "explicit"}
  ]
}
```
`source_kind` ∈ `{user, diary, reading}` — **`derived` невозможно**: система не создаёт событий. `source_id` заполнен, если событие возникло из записи дневника или расклада.

Ошибки: `404` `"нет такого события"`. Rate-limit `read`.

### 11.2 `source_kind` в контракте `/api/memories`

Согласование модели с UI (пункт 3 задания). Существующий `GET /api/memories` (`app/api/routers/profile.py:442`) отдаёт `{id, fact, kind, weight, last_used, created_at}` — в нём **нет** поля, которым можно отличить факт пользователя от производного наблюдения. После добавления колонки `memories.source_kind` ответ расширяется:

```json
{
  "items": [{
    "id": 11, "fact": "работает в IT", "kind": "person",
    "source_kind": "user",
    "weight": 2, "last_used": "...", "created_at": "...",
    "links": [
      {"link_id": 15, "kind": "partner", "id": 7, "label": "Кирилл", "origin": "explicit"}
    ]
  }]
}
```

| Поле | Значения | Кто устанавливает | Как отличается в UI |
|---|---|---|---|
| `source_kind` | `user` | Пользователь сказал/написал; `extract_memory_llm` из его слов | «Запомнила с твоих слов» — факт |
| `source_kind` | `derived` | Только сервер (эвристика/синтез) | «Моё наблюдение» — предположение |
| `links[].origin` | `explicit` | Пользователь связал вручную | Нейтральная связь |
| `links[].origin` | `derived` | Только сервер | «Связала сама» + можно отвязать |

**Инварианты:**
- `POST /api/memories` и `PATCH /api/memories/{id}` **не принимают** `source_kind` от клиента (422 `source_kind_readonly`). Клиент не может объявить предположение фактом.
- Существующие строки без колонки получают `'user'` через `DEFAULT` — они извлечены из слов пользователя.
- `POST /api/events` не принимает `derived` (см. §11).
- При `memory_enabled=0` ответ остаётся 200 с `items: []`, но **`source_kind` и `links` в нём не приходят** — выключенная память не отдаёт содержимое.

**Как UI отвязывает факт от человека:** `GET /api/memories/{id}` → блок `links` → тап «отвязать» → `DELETE /api/memory-links/{link_id}`. Обратного «привязать» из этого экрана нет: он делается из `POST /api/memory-links` с `origin="explicit"`.

---

## 12. Практики

| Метод | Путь | Ответ |
|---|---|---|
| `GET` | `/api/practices?category=` | `{categories: [{code,title,emoji,sort}], items: [{code,title,about,category,category_title,emoji,days,goal,fit,best_time,moon,text,steps[],program[],signs[],warning,started,finished,status,day_index,streak,streak_alive,last_done,started_at,finished_at,days_left,today_step,percent}]}` |
| `GET` | `/api/practices/{code}` | Одна практика |
| `POST` | `/api/practices/{code}/start` | `{...view}` |
| `POST` | `/api/practices/{code}/done` | `{...view, already, day_index, streak, finished, title, message}` |
| `POST` | `/api/practices/{code}/stop` | `{...view}` |

`status` ∈ `not_started | active | completed`. Повторная отметка за сутки — `already: true`, no-op. День считается по таймзоне клиентки. 8 практик, 3 категории (`money`, `love`, `energy`).

---

## 13. Дневник, прогнозы, уведомления

| Метод | Путь | Ключевое |
|---|---|---|
| `GET` | `/api/today` | `{forecast, card{name,emoji,meaning,num,img}, moon{name,emoji,advice,day}, sun_season{sign,symbol,element}, sphere, day, next_action{kind,emoji,title,text,cta,chat,fn}}`. Требует `active_user`. **Карта дня без `reversed`** — не отдаётся по контракту |
| `GET` | `/api/moon/week?days=7` | `[{date, weekday, day_num, phase, moon_sign, lunar_day{n,quality,path}, transit, engine}]` |
| `GET` | `/api/sky` | `{sun_season, moon}` |
| `GET` | `/api/horoscope?sign=` | Общий по знаку, `rate_limit("read")` |
| `GET` | `/api/diary` | Записи + streak |
| `POST` | `/api/diary` | `{text: 1..1000, mood?: ≤20}` → возвращает лунный ориентир и reflection |
| `GET` | `/api/diary/prompt` | Детерминированный вопрос дня |
| `GET` | `/api/diary/summary?month=YYYY-MM` | Факты + `data_for_prompt`, текст пишет LLM |
| `GET` | `/api/notifications` | Inbox, HTML стрипается |
| `GET`/`PATCH` | `/api/notifications/preferences` | Только `morning_forecast`; `PATCH` с `null` возвращает текущие |
| `POST` | `/api/notifications/read-all` | — |

`moon_day.transit`: первый по орбу аспект транзитной Луны к Солнцу/Луне/Асценденту натальной карты, `null` если карты нет.

---

## 14. Профиль, оплата, приватность

| Метод | Путь | Ключевое |
|---|---|---|
| `POST` | `/api/profile` | Создание/обновление + пересчёт онбординга |
| `PATCH` | `/api/profile` | Сверено с кодом `app/api/routers/profile.py:361` (`ProfileIn`) и живьём. Поля: `{name?≤60, birth_date?, birth_time?≤5, birth_time_precision?(exact\|approx\|unknown), city?≤60, intent?(oracle\|astro\|tarot\|chiromant), onboarding_complete?=false, oracle_name?≤30, persona?, morning_push?, memory_enabled?, lang?(ru\|en), gender?(f\|m), tz?≤64, goal?≤40}`. Ответ: `{ok, updated: string[], onboarded: bool}`. Частичное обновление: `undefined`/пустой объект ничего не пишет. **Неизвестные поля молча игнорируются** (Pydantic без `extra="forbid"` → 200), состав полей ограничивает клиент |
| `PATCH` | `/api/profile` (завершение онбординга) | При `onboarding_complete: true` сервер (`app/api/common/onboarding.py:26`) требует, чтобы `{name, birth_date, birth_time_precision, city, intent}` пришли **вместе** (`model_fields_set`), иначе 400. Валидирует имя 2–60, дату 1900..сегодня, время `HH:MM` (при `unknown` — не требуется), город — только ключ из `geo.FALLBACK` (иначе 400 «Выбери город из предложенных подсказок»). Считает карту и **атомарно** пишет 14 полей: `name, birth_date, birth_time, birth_time_known, birth_time_precision, birth_city, birth_lat, birth_lon, tz, chart_json, goal(=intent), onboarded=1, onboarding_step=NULL`. Идемпотентно. **До completion ни одно поле рождения не сохраняется** — пошаговая запись онбординга через этот endpoint невозможна |
| | | **Расхождение контракта (зафиксировано, не обходится):** `age_confirmed` в `ProfileIn` **отсутствует**, колонки `age_confirmed`/`age_proof_hash` удалены миграцией `0006_drop_age_columns` (GAUNTLET v2). `PATCH {"age_confirmed": true}` → **200 с `updated: []`**, поле не записывается. Подтверждение 16+ на сервере не проверяется — это клиентский шаг онбординга. Тарифный гейт — отдельно и только на сервере (`Depends(active_user)` → 402) |
| `GET` | `/api/personas` | `[{code, title, emoji}]` — 3 персоны, `style` наружу **не выдаётся** |
| `GET` | `/api/account/privacy` | `delete_mode: "anonymize"`, `no-store`. Что сохраняется, что удаляется |
| `GET` | `/api/account/export` | Профиль (`name`, `lang`, `tz`, `created_at`, `status`) + история платежей. **Приватный контент (чаты, память, дневник) не экспортируется** |
| `POST` | `/api/account/delete` | `{confirm: true}` обязательно, иначе 400; идемпотентно |
| `GET` | `/api/entitlements` | `{tier, subscription_status, period_end, grace_until, items[{qty_total,qty_used,qty_left,usable}]}` |
| `GET` | `/api/shop` | Каталог товаров |
| `POST` | `/api/shop/invoice` | Stars |
| `POST` | `/api/shop/web-checkout` | Paddle; 404 если флаг `web_payments` off |
| `POST` | `/api/shop/crystals` | Покупка кристаллов |
| `POST` | `/api/shop/promo` | **404 для неизвестного кода**, 409 иначе |
| `GET` | `/api/shop/orders`, `/api/shop/payment-history` | История |

**Правило fulfilment** (`shop.py:1-6`): Mini App **никогда** не выдаёт товар напрямую за Stars. Он создаёт заказ и ссылку; fulfilment приходит боту.

---

## 15. Хиромантия (пальмы) — домен с высоким риском

| Метод | Путь | Ключевое |
|---|---|---|
| `GET` | `/api/palm` | `{items: [...≤20], raw_image_stored: false}` |
| `POST` | `/api/palm` | **Raw-body upload**, `Content-Type` ∈ `{image/jpeg, image/png, image/webp}`, ≤8 МБ, ≤20 Мп, сторона ≤8000 и ≥480 (иначе issue `low_resolution`) |
| `GET` | `/api/palm/{id}` | **404 если `status != "complete"`** — чтения `needs_phone`/`failed`/`deleted` недоступны вовсе |
| `DELETE` | `/api/palm/{id}` | Soft delete; raw-изображения не хранятся (только sha256 + размер) |

Ошибки: `415` — MIME вне allowlist, `413` — >8 МБ, `400` — ValueError движка, `502` — прочее.

Ответ чтения (`palm-evidence-v1`): `status` ∈ `{complete, needs_photo}`, `image_quality{score,issues[]}`, `hand_detected`, `hand_side` ∈ `{left,right,unknown}`, `hand_shape_element`, `requires_view[]`, `photo_assessment{view_type, missing_views[], advice[]}`, `observations[]`, `lines{}` (13 скаляров + 3 массива), `mounts{}` (7), `fingers{}` (5), `markings[]`, `interpretive_prompts[]`, `narrative`, `limitations[]`, `safety_flags[]`, `semantic_summary`.

`confidence_semantics` — дословно: `"0=нет визуального подтверждения; 0.01–0.49=слабое/частичное; 0.50–0.79=умеренное; 0.80–1.00=чёткое наблюдение, подтверждённое кадром"`. При `evidence_state ∈ {unknown, not_supported}` confidence принудительно обнуляется.

**UI-следствие:** домен «хиромантия» в v2 получает `risk_level: high` и лимиты 20с / 4 хода / 6 вызовов (из `agent.yaml` Миры). Интерфейс обязан показывать `needs_phone`-состояние с приёмами съёмки, а не молча падать.

---

## 16. Служебное

| Метод | Путь | Ключевое |
|---|---|---|
| `GET` | `/api/health` | Liveness; без auth |
| `GET` | `/api/public/config` | `bot_username`, `webapp_url` до `/start`; без auth |
| `GET` | `/api/faq?lang=` | Публичный FAQ |
| `POST` | `/api/funnel/events` | Батч ≤20, allowlist `visit|signup|activation`, `extra="forbid"`, без auth |
| `POST` | `/api/feedback` | Day7-опрос: 422 `survey_version_unknown`/`no_valid_answers`, 409 `survey_already_completed` |
| `POST` | `/api/jobs/chat/{agent}` | 202 `{job_id, status:"queued", kind:"llm.chat"}` — async; требует `CELERY_ENABLED=1` |
| `GET` | `/api/jobs`, `/api/jobs/{task_id}` | `payload_json` наружу не отдаётся |
| `GET` | `/api/share/enabled` | Проверка доступности шаринга |
| `GET` | `/metrics` | `Authorization: Bearer $METRICS_TOKEN` (если задан); Caddy отдаёт 404 |

OpenAPI: в DEV_MODE `/api/docs` и `/api/openapi.json` публичны; в проде `/api/openapi.json` требует `current_user` (`main.py:148-168`). Генерация TS-типов возможна авторизованным запросом.

---

## 17. Что UI не должен делать

1. **Не отправлять `tg_id` в теле запроса.** Параметра владельца в контракте нет; owner-scope делает SQL.
2. **Не пытаться изменить карты после draw.** `immutable_cards` + `checksum` на сервере.
3. **Не показывать дома/ASC/MC при `precision != "exact"`.** Валидатор отклонит ответ.
4. **Не считать `included`-расклад бесплатным.** Он тратит вопрос дня.
5. **Не выдавать товар за Stars из Mini App.** Только заказ + ссылка.
6. **Не рисовать цены на клиенте.** Источник — `/api/tarot/spreads` (`price_stars`, `price_crystals`, `owned`).
7. **Не обходить `memory_enabled` через аргументы инструментов.** Согласие проверяется в инструментах.
8. **Не трактовать `next_action.chat` как выбор агента** — в v2 это домен-подсказка, а не персонаж.
