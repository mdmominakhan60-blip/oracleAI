# OracleAI v2 — Test Plan

Что существует, что нужно перезапустить и что написать. **Ни один тест не был запущен при написании этого документа** — все численные утверждения взяты из чтения кода и конфигураций.

---

## 1. Существующая база (114 файлов, 1257 тестовых функций)

| Область | Файлы | Покрытие | Зависимости |
|---|---|---|---|
| API Mini App | `test_api.py` (96), `test_api_growth.py`, `test_api_entitlements.py` | Полный HTTP-контракт через `httpx.ASGITransport`, реальная PostgreSQL | Реальная БД |
| Auth / replay | `test_bus200_replay.py` (25), `test_security_regressions.py` (22), `test_env_guard.py` (10) | HMAC, dup-key, просрочка, replay, токены, fail-open/closed, DEV_KEY | **Живой Redis** |
| Ядро / лимиты | `test_core.py` (47), `test_limits.py` (25) | Колода, астрология, матрица, совместимость, лимиты | `LLM_PROVIDER=off` |
| Агенты | `test_agent_routing.py` (9), `test_agent_context.py`, `test_agent_context_integrity.py`, `test_agent_file_harness.py`, `test_agent_runtime_guard.py` | Домены, пороги, allow-list, offline, бюджеты | LLM off |
| Таро | `test_tarot_contract.py`, `test_bus1232_precision_canon.py` | Ledger, checksum, воспроизводимость | — |
| Карты / Vedic | `test_chart_contract.py`, `test_chart_integration.py`, `test_vedic.py`, `test_chart_products.py` | Precision-gates, composite/transits/returns | — |
| Palm | 7 файлов | MIME/размер/пиксели/EXIF, owner-isolation, ONNX-пути | Моки загрузок |
| Память | `test_bus810_memory_api.py`, `test_shared_context.py`, `test_memory_evaluation.py` | Consent-off блокирует инструменты, изоляция | — |
| Биллинг | 8 файлов (~180 тестов) | Идемпотентность webhook, возвраты, entitlements, кристаллы | — |
| Админ / CRM | ~10 файлов | Роли, аудит, сегменты | — |
| Ops | `test_release_gate.py`, `test_selfcheck_guard.py`, `test_log_stream.py`, `test_pdfgen.py` | Fail-closed TRUNCATE, log-редакция, PDF golden | Частично admin-БД |

**Фикстуры** (`tests/conftest.py`): НЕ SQLite — общая PostgreSQL + `pg_advisory_lock` на весь тест + `TRUNCATE CASCADE` + seed. `user` = tg_id 1001 (vip), `free_user` = 1002.

## 2. Предусловия (без них прогон упадёт на чистом чекауте)

| Предусловие | Почему | Подтверждение |
|---|---|---|
| `node scripts/build_frontend.mjs` | `miniapp/dist/` в `.gitignore` и отсутствует; `tests/test_api.py:965` читает `manifest.json` без skip-guard | `tests/test_api.py` |
| Живой PostgreSQL (или `docker compose up -d --wait postgres`) | Все тесты на реальной БД | `conftest.py:87` |
| Живой Redis | `tests/test_bus200_replay.py:271,285` создают `Redis.from_url` без skip-guard | `test_bus200_replay.py` |
| `APP_ENV=test/ci` + `ALLOW_DB_RESET=1` | Reset тестовой БД | `Makefile:_test` |
| Системные libcairo/libpango | PDF-генерация WeasyPrint | `ci.yml` |

**Команда полного прогона** (не выполнена):
```bash
make test
# или явно, как в CI:
APP_ENV=test DEV_MODE=1 DEV_KEY=test-dev-key LLM_PROVIDER=off \
DATABASE_URL=postgresql+asyncpg://oracle_test:oracle@127.0.0.1:5432/oracle_test \
POSTGRES_ADMIN_DATABASE_URL=[REDACTED:connection_string]127.0.0.1:5432/postgres \
ALLOW_DB_RESET=1 REDIS_URL=redis://127.0.0.1:6379/0 pytest -q
```

## 3. Что нужно перезапустить (нельзя считать зелёным)

| Проверка | Почему нельзя доверять прошлому |
|---|---|
| Полный pytest | Последний документально подтверждённый прогон — август 2026 |
| `pip-audit -r requirements.txt` | Последнее заявление «no known vulnerabilities» от 2026-08-27 |
| `python scripts/selfcheck.py` | Требует живой БД **и** живых LLM-провайдеров для `llm_smoke` |
| `python scripts/release_gate.py --production` | Требует production-окружения |
| `tests/test_data.py` | Отдельный CI-run; миграции |
| Frontend axe/Lighthouse | Требуют собранного бандла и поднятого API |
| Ссылка `CURRENT_STATUS.md` на CI-ран `33093428849` | Из репозитория не проверяема |

**Известный ожидаемо падающий тест:** `TestProdGrantCheck::test_flags_truncate_privilege_on_production` — падает, пока роль `oracle` остаётся владельцем таблиц (DevOps-грант не выполнен). Это не регрессия.

## 4. Статические гейты (дешёвые, без БД)

```bash
python -m ruff check app scripts tests
python -m compileall -q app scripts tests
find miniapp/js admin scripts -type f -name '*.js' | xargs -n1 node --check
python scripts/check_repository_hygiene.py
python scripts/check_architecture.py
python scripts/check_cache_busting.py
python scripts/check_design_contract.py
python scripts/check_p004_infrastructure.py
python scripts/sql_shim_inventory.py && git diff --exit-code docs/SQL_SHIM_INVENTORY.md
python scripts/check_route_inventory.py
```

Для нового фронта (Этап 1+):
```bash
cd frontend-v2 && npm ci && npm run build && npx tsc --noEmit && npx eslint .
```

## 5. Новые тесты, которые нужно написать

### 5.1 Единый Oracle (критично — Этап 5)

| ID | Тест | Что проверяет |
|---|---|---|
| N-1 | `test_unified_oracle_routes_mixed_domain` | «что скажут карты про мой Сатурн» → инструменты Таро **и** натальной карты |
| N-2 | `test_domain_allowlist_blocks_foreign_tools` | Домен `tarot` не может вызвать `get_chart` |
| N-3 | `test_no_agent_selection_surface` | Grep-тест: ни один маршрут/компонент фронта не предлагает выбор агента |
| N-4 | `test_routing_hides_persona_name` | В ответе нет подписи с именем персоны вроде «Урании» |
| N-5 | `test_chiromant_domain_limits` | Домен `chiromant`: timeout 20с, max_turns 4, max_tool_calls 6, risk_level high |
| N-6 | `test_shared_context_keyed_by_domain` | Записи shared-context помечены доменом, не персоной |

### 5.2 Память и граф (Этап 6)

| ID | Тест | Что проверяет |
|---|---|---|
| N-7 | `test_memory_link_create_and_query` | Связь факт↔человек создаётся и читается |
| N-8 | `test_memory_link_requires_consent` | При `memory_enabled=0` новая связь и событие → 409 `memory_off`, но чтение работает |
| N-9 | `test_personal_event_source_kind_defaults_user` | События по умолчанию `source_kind='user'` |
| N-10 | `test_derived_facts_distinguishable` | `source_kind='derived'` различим в API-ответе |
| N-11 | `test_cross_user_isolation_all_new_endpoints` | Кросс-юзер на всех 13 новых ручках (`/api/people*`, `/api/events*`, `/api/memory-links*`) |
| N-12 | `test_account_delete_clears_graph` | `account/delete` → 0 строк в `memory_links`, `personal_events`, `memories`, `partners`, `tarot_readings`, `diary` |
| N-13 | `test_timeline_survives_deleted_source` | Удалённая запись не ломает timeline |
| N-14 | `test_legacy_memories_migrate_to_user_source` | Существующие строки без `source_kind` → `'user'` |
| N-15 | `test_age_gate_on_active_user_routes` | Без `age_confirmed_at` → 402 на `/api/today`, `/api/compat/full`, `/api/synastry`, `/api/composite`, `/api/transits`, `/api/returns`, `/api/chart/pdf`; read-ручки отдают 200. `anonymize` обезличивает `age_confirmed_at` |
| N-16 | `test_age_confirmed_is_write_once` | `PATCH {age_confirmed: false}` → 422 `age_confirmed_readonly`; повторное `{age_confirmed: true}` идемпотентно |
| N-17 | `test_onboarding_resumes_from_step` | Прерванный на шаге 3 онбординг → повторный вход на шаге 3; при `onboarded=true` → Home без онбординга |
| N-18 | `test_combined_request_runs_chart_before_tarot` | Смешанный запрос: `get_chart` в `tools_used` раньше `draw_tarot`; `draw_tarot` **не** в первой итерации цикла (параллельность запрещена) |
| N-19 | `test_palm_excludes_other_domains_in_combined` | `palm_*` + другой домен → инструменты другого домена не вызываются |
| N-20 | `test_person_profile_returns_related_data` | `GET /api/people/{id}` → `memories`, `readings`, `events`, `conversations`, `counts`; при `memory_enabled=0` блоки `memories`/`events` пусты, профиль человека отдаётся |
| N-21 | `test_memory_get_returns_links_for_unlink_action` | `GET /api/memories/{id}` → `links[]` с `link_id`/`origin`; `DELETE /api/memory-links/{link_id}` отвязывает, сам факт сохраняется |
| N-22 | `test_patch_memory_rejects_source_kind` | `PATCH /api/memories/{id} {source_kind: "derived"}` → 422 `source_kind_readonly` |
| N-23 | `test_thread_link_requires_derived_origin` | `POST /api/memory-links` с `kind=thread` и `origin="explicit"` → 422 `thread_requires_derived_origin`; `conversations[]` в таймлайне содержит `preview=""` (текст переписки не утёк) |
| N-24 | `test_timeline_deep_links_resolve` | `GET /api/people/{id}/timeline` → `deep_link` вида `/api/events/{id}` резолвится через `GET /api/events/{id}` (200), не 404 |

### 5.3 Фронтенд-контракты (Этапы 1–5)

| ID | Тест | Что проверяет |
|---|---|---|
| N-15 | `test_api_client_401_re_mints_once` | Порт `withSessionResilient`: 401 → реминт → один повтор |
| N-16 | `test_api_client_retries_5xx_only_on_get` | POST с 5xx не ретраится |
| N-17 | `test_idempotency_key_sent_on_chat` | `X-Idempotency-Key` присутствует в каждом вопросе |
| N-18 | `test_draft_survives_error_and_abort` | Текст не теряется при ошибке и отмене |
| N-19 | `test_no_hardcoded_api_responses` | REVIEW-гейт: нет моков в компонентах |
| N-20 | `test_tarot_card_image_fallback` | `onError` → `card-face.jpg` |
| N-21 | `test_chart_hides_houses_when_imprecise` | `precision != exact` → дома/ASC/MC не рендерятся |
| N-22 | `test_reduced_motion_disables_flip` | `prefers-reduced-motion` → мгновенное открытие |

### 5.4 Существующие тесты, требующие пересмотра

| Тест | Почему |
|---|---|
| `test_miniapp_actions`, `test_architecture_boundaries` | Читают исходники `miniapp/js/*` через ro-монтирование; при переезде в `frontend-v2/` — пересмотреть |
| `test_api.py:965` | Проверяет hashed-бандл; завязан на `manifest.json` |
| `test_route_inventory.py` | Новые endpoint'ы графа должны попасть в инвентарь `docs/EVIDENCE/ROUTE_INVENTORY_P1009.txt` или иметь `PUBLIC_ROUTE_REASONS` |

## 6. Гейты CI

| Гейт | Где | Статус |
|---|---|---|
| Полный pytest + ruff + аудит + release_gate | `.github/workflows/ci.yml` | Описан верно; **исполнение не подтверждаемо из репозитория** |
| axe + Lighthouse | `ci.yml` job `frontend-quality` | Требует собранного бандла |
| Линт-стадия (без pytest) | `.gitlab-ci.yml` | Должен исполняться на GitLab-раннере |

**Важно:** `deploy.yml` срабатывает по `workflow_run conclusion == 'success'`. Если GitHub CI не запускается, автодеплой мёртв — только ручной `workflow_dispatch`. GitLab CI гоняет только lint (осознанно: Free-квота 400 мин/мес).

## 7. Порядок прогона на каждом этапе

```bash
# 1. Статика (быстро, ловит опечатки и границы)
python -m ruff check app scripts tests && python -m compileall -q app scripts tests
python scripts/check_architecture.py && python scripts/check_repository_hygiene.py
python scripts/check_design_contract.py && python scripts/check_cache_busting.py

# 2. Сборка фронта и её гейты
node scripts/build_frontend.mjs   # или cd frontend-v2 && npm run build (Этап 1+)
python scripts/check_frontend_build.py
python scripts/check_frontend_provenance.py
python scripts/check_static_asset_references.py

# 3. Полные тесты (нужны PostgreSQL, Redis, построенный бандл)
make test

# 4. Гейты релиза
python -m pip_audit -r requirements.txt
python scripts/selfcheck.py          # требует живой БД и LLM
python scripts/release_gate.py

# 5. Доступность и производительность (Этап 1+)
cd frontend-v2 && npm run test:axe && npm run test:lighthouse
```

## 8. Чего в плане тестов нет и почему

- **Нет e2e на реальных Telegram-клиентах** (iOS/Android/Desktop) — это внешний гейт P0-001, для которого нужны реальные устройства и аккаунты. Автоматизируется через `scripts/telegram_webview_qa.py`, но не заменяет ручную проверку.
- **Нет нагрузочного тестирования нового фронта** — `load/` существует, но новый UX-профиль нужно описывать отдельно после реализации.
- **Нет тестов лицензионного соответствия** — `docs/CHART_ENGINE_LICENSING.md` требует юридического решения, которое не автоматизируется.
