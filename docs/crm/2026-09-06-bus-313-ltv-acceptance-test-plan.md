# BUS-313 — QA тест-план приёмки LTV-волны

Продукт: oracleAI. Зона QA (tests/, ROUTING.md). Приёмка стартует только после done BUS-308…312.

## 1. Статусы доставки (BUS-308, миграция 0012 `deliveries(status, error)`)

| # | Сценарий | Ожидание | Результат 2026-09-08 |
|---|----------|----------|----------|
| 1.1 | fresh БД → alembic upgrade head | 0012 применяется, колонки status/error у deliveries | PASS (0012+0013 до head) |
| 1.2 | восстановление с 0008-старта | 0008→0012 проезжает без ручных правок | PASS (повторный down→up тоже) |
| 1.3 | baseline.sql parity | DDL deliveries в baseline ≡ итогу миграции (урок BUS-231) | PASS (status default 'sent', error nullable) |
| 1.4 | forbidden-отправка | строка не sent; дедуп держится (`already_sent` = True) | PASS с уточнением: 1-2 дня — мягкий failed, терминальный forbidden только с 3-го дня подряд (BUS-369, порог FORBIDDEN_THRESHOLD=3, окно 7д) |
| 1.5 | временный сбой доставки | status='failed'; следующий тик пере-claim и ретрай | PASS (test_send_once_retries_after_temporary_failure) |
| 1.6 | claim-token | 16 hex в error во время отправки, затирается при sent | PASS (2^64-пространство, secrets.token_hex(8)) |
| 1.7 | reclaim зависшей sending | пере-claim по CLAIM_TIMEOUT_S=600 | **FINDING (Q3-несоотв. плану):** reclaim есть только у broadcast_targets; deliveries, зависшая в 'sending' (крэш между claim и mark), не пере-claimается — claim() берёт только из 'failed'. Не регресс (старая схема вела к тому же), но безаварийность не Recoverability-complete. Рекомендация Backend: забирать sending старше CLAIM_TIMEOUT_S в claim() |

## 2. Очередь внимания (BUS-309, ltv_tier + GET /api/admin/attention-queue)

Грани окон на синтетических юзерах (tg_id 10001+, вне аналитики сценария):

| # | Правило | Вход | Невход | Результат |
|---|---------|------|--------|----------|
| 2.1 | Q1 refund 48ч | внутри окна (47ч55м) | за окном (48ч5м) | PASS (грань `>=` верифицирована код-ревью: created_at>=since) |
| 2.2 | Q2 VIP sleeping/sub-expired 5д | sleeping_14d ∩ tier A; sub_expired ≥5д | — | PASS (test_q2_vip_sleeping, q2_vip_sub_expired_5d) |
| 2.3 | Q3 WB2 без redemption ≥7д | WB2 10д назад, tier A/B, expired | — | PASS |
| 2.4 | Q4 ≥3 limit_reached за 7д | 4 хита | — | PASS (HAVING COUNT>=3) |
| 2.5 | Q5 failed/forbidden 24ч; Q6 новые ≥3 полных дней + O1; Q7 гэп ≥30д + возврат 48ч | — | — | PASS (грани в test_bus313_acceptance_boundaries.py: 23ч55м/24ч5м; 2д23ч/3д2ч — окно в полных днях _days_since; 29д23ч/30д5м) |
| 2.6 | forbidden-исключение из Q2-Q4/Q6/Q7 | Q1 сохраняется | — | PASS (test_attention_queue_forbidden_excludes…, test_q1_survives_forbidden_exclusion) |
| 2.7 | «открытие канала» | первая успешная доставка после forbidden → обычные правила | — | PASS (test_channel_reopen…: closed→Q5-исключён из Q2 → sent → вернулся в Q2) |
| 2.8 | сортировка | P1→P2→P3→тир→давность | — | PASS |
| 2.9 | лимит | ровно 50 максимум; counts/overdue по всей очереди | — | PASS (counts_full_not_limited: limit=2, counts≥3, truncated=true) |
| 2.10 | права | dashboard — 200; без права — 403 | — | PASS (dev_user без admins → 403) |
| 2.11 | синтетика 10001/10002 | исключена из очереди и LTV | — | PASS (test_attention_queue_synthetic_excluded, test_ltv_tier_synthetic_excluded, test_user_card_ltv_synthetic) |

## 3. Матрица компенсаций (BUS-310, fc870f7)

Пороги (по коммиту): support 3д; admin 3/7/10; owner 3/7/10/14 (усиление PB-3). Каппинг grant: admin ≤7 / owner ≤30; кристаллы admin ≤30✦; support на grant — 403.

| # | Сценарий | Ожидание | Результат |
|---|----------|----------|----------|
| 3.1 | POST /users/{tg_id}/gift каждый порог×роль | разрешено по матрице; сверх — 403 gift_days_not_allowed | PASS 19/19 (test_bus310_compensation_matrix.py) |
| 3.2 | причина пуста | 422 (pydantic min_length=1), аудит не пишется | PASS (test_gift_requires_reason; уточнение: 422, не 400) |
| 3.3 | анти-абьюз | 60д для 3/7-дневных, **90д для 10/14** (PB-3; OP_GIFT_COOLDOWN_DAYS = {3:60, 7:60, 10:90, 14:90}); прямые redemptions op_* тоже держат окно | PASS (cooldown 409 + next_available_at ±120с; test_gift_redemption_outside_endpoint_blocks_too) |
| 3.4 | аудит user.gift | причина обязательна, code/days/reason записаны | PASS |
| 3.5 | GET /promo/op-report | redemption rate + конверсия; право dashboard (support видит) | PASS |
| 3.6 | eligibility endpoint | allowed_days по роли, eligible/cooldown/next_available_at | PASS |

## 4. Тексты плейбуков (BUS-311, pb_* RU/EN)

| # | Сценарий | Ожидание | Результат |
|---|----------|----------|----------|
| 4.1 | ключи pb_* подставляются в карточки | плейсхолдеры валидны, нет сырых {token} | PASS с оговоркой: RU-каркасы — JS-fallback в attention-queue.js (PB_COPY_FALLBACKS), fillTemplate подставляет display/oracle_name/limit_hits_count/offer_expires_at/diff; невычислимое остаётся {token} по дизайну (оператор редактирует каркас) |
| 4.2 | RU/EN симметрия | каждому ru-ключу есть en-тёзка | **FINDING (P2):** pb-ключи НЕ seed-ятся в content_items (seed.py их не содержит; БД пуста по pb*); EN-версий нет ни в fallback, ни в seed — «EN — зона Backend seed'а» (комментарий BUS-312). На mock-стенде /api/admin/content?kind=copy отдаёт items: [] — работает fallback. Требуется: Backend seed'ит pb1..pb7 RU+EN в content_items (kind=copy), иначе EN-операторы видят RU-каркас |

## 5. Админка (BUS-312)

| # | Сценарий | Ожидание | Результат |
|---|----------|----------|----------|
| 5.1 | role-gating | недоступное — серое/с подсказкой, не скрытое | PASS (verify_crm_ltv_ui: crm:write гейтит textarea/кнопки, без права — текст-подсказка) |
| 5.2 | счётчики шапки | совпадают с API-ответом | PASS (сводка «Всего в очереди: 7» из data.counts, overdue-бейджи) |
| 5.3 | LTV-блок карточки + next best action | из attention-queue | PASS (тир, 6 метрик, risk-флаги, next_best_action, таймлайн 6 касаний; gift-форма по eligibility; axe a11y чист desktop+mobile) |

## 6. e2e no-channel

Сценарий full-path на живой очереди (tests/test_bus313_e2e_no_channel.py): VIP sleeping → forbidden → только Q5, Q2 закрыта → тег no-channel (кейс закрывается, данные не трогаются) → первая успешная доставка → channel_closed=False → **после выхода forbidden из окна 24ч** → возврат в Q2. Результат: PASS.

Примечание: карточка Q5 держится на факте failed/forbidden за 24ч-окно (не на channel_closed) — сразу после разблокировки Q5 остаётся до истечения окна; поведение задокументировано в pb5Hint.

## 7. Регресс

Базовая линия 869/886 (17 known, 12 palm) от 2026-09-05. Полный suite на 16c2734 собран 1241 тест, прогон 2026-09-08: 1234 passed, 1 skip (env), 6 failed → **все 6 после восстановления окружения — 0**:

- 4× test_bus200_replay — падение из-за недоступного redis (localhost:6379), тесты ждут живой redis (qa-redis-bus313); после `docker start` — PASS;
- test_api::test_miniapp_index_uses_hashed_bundles_in_production + test_security_regressions::test_production_config_accepts_safe_runtime_configuration — требовали `miniapp/dist/manifest.json`; после `node scripts/build_frontend.mjs` — PASS;
- 1 skip: test_api::test_miniapp_index_bundles_by_default_in_dev — тот же manifest (на момент прогона dist не собран); это env-skip, не продуктовый.

Вывод: продуктовых регрессий нет; новый тест-код волны (dedup/three-state, очередь, матрица, границы, e2e) регресс существующих цепочек scheduler (forecast/winback дедуп) не сломал.

## Прогресс прогона

| Пункт | Статус | Дата | Примечание |
|-------|--------|------|------------|
| план | готов | 2026-09-06 | восстановлен в основном repo (первичный коммит 0822e63 потерян со scratch-worktree) |
| блокеры BUS-308…312 | done | 2026-09-08 | проверено через API борда |
| §1–§6 приёмка | выполнено | 2026-09-08 | worktree .wt-bus313-qa от 16c2734; dedup 8/8, bus309 31/31, bus310 19/19, границы 6/6 (новый файл), e2e 1/1 (новый файл), verify_crm_ltv_ui ALL CHECKS PASSED |
| §7 полный регресс | готов | 2026-09-08 | 1241 собран, 1234 passed, 1 env-skip, 6→0 failed после env-восстановления (redis + dist-build); вердикт: PASS |
| FINDINGS | зафиксировано | 2026-09-08 | 1.7 reclaim 'sending'-доставок (Q3-несоответствие плану); 4.2 pb_* не seed-ятся, EN-версий нет (P2, seed — зона Backend) |

## Вердикт QA: PASS

Волна LTV (BUS-308…312) принята с двумя findinge'ами, не блокирующими релиз:
- **F1 (1.7, Q3):** deliveries, зависшая в 'sending' после крэша между claim и mark, не пере-claimается (claim() берёт только 'failed'); reclaim по CLAIM_TIMEOUT_S есть только у broadcast_targets. Не регресс (старая схема вела к тому же), но Recoverability-incomplete. Рекомендация Backend: забирать 'sending' старше CLAIM_TIMEOUT_S.
- **F2 (4.2, P2):** pb1–pb7 RU/EN не seed-ятся в content_items (seed.py их не содержит, fallback — только RU в attention-queue.js). EN-оператор видит RU-каркас. Рекомендация Backend: seed pb1..pb7 RU+EN (kind=copy).


