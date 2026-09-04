-- OracleAI PostgreSQL native schema (canonical source).
--
-- Загружается ТОЛЬКО из Alembic baseline (0001_pg_native_baseline).
-- Никогда не применяется как runtime CREATE — schema.py и pg_schema.py удалены.
-- Изменения существующих таблиц описываются последующими Alembic-ревизиями.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(255) PRIMARY KEY);

CREATE TABLE IF NOT EXISTS users (
    tg_id            BIGINT PRIMARY KEY,
    name             TEXT,
    username         TEXT,
    lang             TEXT DEFAULT 'ru',
    gender           TEXT DEFAULT NULL,       -- f|m; NULL = нейтральные обращения
    persona          TEXT DEFAULT 'friend',
    oracle_name      TEXT DEFAULT 'Лилит',
    tz               TEXT DEFAULT 'Europe/Moscow',

    birth_date       TEXT,
    birth_time       TEXT,
    birth_time_known BIGINT DEFAULT 1,
    birth_time_precision TEXT DEFAULT 'exact', -- exact|approximate|unknown
    birth_city       TEXT,
    birth_lat        DOUBLE PRECISION,
    birth_lon        DOUBLE PRECISION,
    chart_json       TEXT,
    natal_technique  TEXT DEFAULT 'astrology', -- astrology|lenormand
    natal_technique_version TEXT DEFAULT 'v1',
    onboarding_step  TEXT DEFAULT NULL,

    sub_level        TEXT DEFAULT 'trial',   -- код тарифа из plans
    sub_until        TEXT,
    crystals         BIGINT DEFAULT 0,

    onboarded        BIGINT DEFAULT 0,
    morning_push     BIGINT DEFAULT 1,
    memory_enabled   BIGINT DEFAULT 0,   -- память включается только явным согласием
    -- age_confirmed / age_proof_hash dropped in 0006_drop_age_columns (GAUNTLET v2)
    ref_by           BIGINT,
    goal             TEXT,                   -- главный запрос: love|career|practice
    source           TEXT,                   -- канал привлечения (utm/ref/organic)
    status           TEXT DEFAULT 'active',  -- active|blocked
    ltv_stars        BIGINT DEFAULT 0,      -- денормализация для CRM
    expiry_notified  BIGINT DEFAULT 0,
    last_seen        TEXT,
    deleted_at       TEXT,                   -- «удали мои данные»: анонимизация
    created_at       TEXT
);


CREATE TABLE IF NOT EXISTS threads (
    id           BIGSERIAL PRIMARY KEY,
    tg_id        BIGINT NOT NULL,
    agent        TEXT NOT NULL DEFAULT 'oracle',   -- код агента из core/agents
    title        TEXT,
    msg_count    BIGINT DEFAULT 0,
    last_text    TEXT,                             -- превью для списка чатов
    last_at      TEXT,
    archived     BIGINT DEFAULT 0,
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id          BIGSERIAL PRIMARY KEY,
    tg_id       BIGINT NOT NULL,
    thread_id   BIGINT,                     -- NULL — исторические сообщения бота
    agent       TEXT DEFAULT 'oracle',
    role        TEXT,
    text        TEXT,
    is_question BIGINT DEFAULT 0,
    surface     TEXT DEFAULT 'bot',          -- bot|miniapp
    tokens      BIGINT,
    created_at  TEXT
);
CREATE TABLE IF NOT EXISTS chat_requests (
    idempotency_key TEXT PRIMARY KEY,
    tg_id           BIGINT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'processing', -- processing|completed|failed
    response_json   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memories (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    fact       TEXT,
    kind       TEXT DEFAULT 'fact',
    weight     BIGINT DEFAULT 1,
    embedding  vector,                        -- float32-вектор для поиска по смыслу
    embed_model TEXT,                       -- какой моделью посчитан (миграция векторов)
    last_used  TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS profile_summaries (
    tg_id       BIGINT PRIMARY KEY,
    summary     TEXT,                       -- «кто она» одним абзацем для промпта
    facts_count BIGINT DEFAULT 0,          -- на скольких фактах собрана
    built_at    TEXT
);
CREATE TABLE IF NOT EXISTS shared_context_events (
    id          BIGSERIAL PRIMARY KEY,
    tg_id       BIGINT NOT NULL,
    event_type  TEXT NOT NULL,              -- recommendation|palm_observation|decision
    agent       TEXT NOT NULL,
    content     TEXT NOT NULL,              -- bounded assistant guidance; rendered as untrusted data
    source_ref  TEXT,
    created_at  TEXT NOT NULL,
    expires_at  TEXT
);
CREATE TABLE IF NOT EXISTS shared_context_snapshots (
    id            BIGSERIAL PRIMARY KEY,
    tg_id         BIGINT NOT NULL,
    snapshot_type TEXT NOT NULL,            -- transits
    snapshot_key  TEXT NOT NULL,            -- user-local date or explicit version key
    payload_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    expires_at    TEXT,
    UNIQUE (tg_id, snapshot_type, snapshot_key)
);
CREATE TABLE IF NOT EXISTS diary (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    text       TEXT,
    mood       TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS forecasts (
    tg_id         BIGINT,
    day           TEXT,
    text          TEXT,
    lang          TEXT DEFAULT 'ru',     -- язык текста прогноза (ru|en)
    audio_file_id TEXT,                   -- озвучка прогноза: file_id Telegram
    created_at    TEXT,
    PRIMARY KEY (tg_id, day, lang)
);
CREATE TABLE IF NOT EXISTS reports (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    kind       TEXT NOT NULL,                -- natal|matrix|synastry|solar|monthly
    period     TEXT,                         -- YYYY-MM для месячных, год для соляра
    title      TEXT,
    body       TEXT,
    meta_json  TEXT,
    created_at TEXT
    -- Reports are immutable history entries. The latest row for a kind/period
    -- remains the cache; regeneration appends a new version.
);
CREATE TABLE IF NOT EXISTS deliveries (
    tg_id      BIGINT NOT NULL,
    kind       TEXT NOT NULL,                -- forecast|weekly|expiry|winback|broadcast
    key        TEXT NOT NULL,                -- день/идентификатор повода
    created_at TEXT,
    PRIMARY KEY (tg_id, kind, key)
);


CREATE TABLE IF NOT EXISTS user_notifications (
    id          BIGSERIAL PRIMARY KEY,
    tg_id       BIGINT NOT NULL,
    kind        TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    dedupe_key  TEXT NOT NULL,
    read_at     TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (tg_id, dedupe_key)
);


CREATE TABLE IF NOT EXISTS tarot_readings (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    spread     TEXT,
    question   TEXT,
    cards_json TEXT,
    answer     TEXT,
    surface    TEXT DEFAULT 'bot',
    paid_with  TEXT,                          -- daily|crystals|stars|entitlement
    outcome    TEXT,                           -- came_true|partly|no (отметка клиентки)
    outcome_at TEXT,
    deck       TEXT DEFAULT 'tarot',            -- tarot|lenormand (migration 0007)
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS palm_readings (
    id            BIGSERIAL PRIMARY KEY,
    tg_id         BIGINT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'complete', -- complete|needs_photo|failed|deleted
    hand_side     TEXT,                              -- left|right|unknown
    image_sha256  TEXT,
    image_size    BIGINT,
    analysis_json TEXT,
    error_code    TEXT,
    surface       TEXT DEFAULT 'miniapp',
    created_at    TEXT,
    updated_at    TEXT,
    deleted_at    TEXT
);
CREATE TABLE IF NOT EXISTS partners (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    name       TEXT,
    relation   TEXT DEFAULT 'partner',        -- partner|crush|colleague|friend
    birth_date TEXT,
    birth_time TEXT,
    birth_city TEXT,
    birth_lat  DOUBLE PRECISION,
    birth_lon  DOUBLE PRECISION,
    tz         TEXT,
    chart_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS synastry_cache (
    id            BIGSERIAL PRIMARY KEY,
    tg_id         BIGINT NOT NULL,
    partner_key   TEXT NOT NULL,              -- дата/идентификатор партнёра
    score         BIGINT,
    breakdown_json TEXT,
    answer        TEXT,
    created_at    TEXT
);
CREATE TABLE IF NOT EXISTS practices (
    id          BIGSERIAL PRIMARY KEY,
    tg_id       BIGINT NOT NULL,
    code        TEXT NOT NULL,                -- код практики из content_items
    day_index   BIGINT DEFAULT 0,
    streak      BIGINT DEFAULT 0,
    last_done   TEXT,
    started_at  TEXT,
    finished_at TEXT
);


CREATE TABLE IF NOT EXISTS plans (
    code             TEXT PRIMARY KEY,
    title            TEXT NOT NULL,
    tagline          TEXT,
    price_stars      BIGINT DEFAULT 0,
    price_usd        DOUBLE PRECISION DEFAULT 0,          -- витрина web-оплаты (Paddle)
    period_days      BIGINT DEFAULT 30,
    daily_questions  BIGINT DEFAULT 3,
    weekly_questions BIGINT DEFAULT 0,       -- для free-уровня «1 вопрос в неделю»
    memory_depth     BIGINT DEFAULT 20,      -- сколько фактов памяти в промпте
    crystals_grant   BIGINT DEFAULT 0,       -- бонус ✦ при покупке
    features_json    TEXT,                    -- список фич для витрины
    badge            TEXT,                    -- «выбор большинства» и т.п.
    sort             BIGINT DEFAULT 100,
    is_active        BIGINT DEFAULT 1,
    is_public        BIGINT DEFAULT 1,
    created_at       TEXT,
    updated_at       TEXT
);
CREATE TABLE IF NOT EXISTS products (
    sku            TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,             -- spread|report|crystals|plan
    title          TEXT NOT NULL,
    description    TEXT,
    price_stars    BIGINT DEFAULT 0,
    price_crystals BIGINT DEFAULT 0,
    grant_kind     TEXT,                      -- что выдаём: spread|report|crystals|plan
    grant_code     TEXT,                      -- код расклада/отчёта/тарифа
    grant_qty      BIGINT DEFAULT 1,
    valid_days     BIGINT,                   -- срок жизни права (NULL — бессрочно)
    sort           BIGINT DEFAULT 100,
    is_active      BIGINT DEFAULT 1,
    created_at     TEXT,
    updated_at     TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    id             BIGSERIAL PRIMARY KEY,
    tg_id          BIGINT NOT NULL,
    kind           TEXT NOT NULL,             -- plan|product|crystals
    sku            TEXT,
    title          TEXT,
    amount_stars   BIGINT DEFAULT 0,
    amount_crystals BIGINT DEFAULT 0,
    status         TEXT DEFAULT 'pending',    -- pending|paid|failed|refunded
    payload        TEXT UNIQUE,               -- invoice payload (идемпотентность)
    surface        TEXT DEFAULT 'bot',
    meta_json      TEXT,
    created_at     TEXT,
    paid_at        TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    id            BIGSERIAL PRIMARY KEY,
    order_id      BIGINT,
    tg_id         BIGINT NOT NULL,
    amount_stars  BIGINT DEFAULT 0,
    currency      TEXT DEFAULT 'XTR',
    charge_id     TEXT,
    provider      TEXT DEFAULT 'telegram_stars',
    status        TEXT DEFAULT 'succeeded',   -- succeeded|refunded
    created_at    TEXT
);
CREATE TABLE IF NOT EXISTS entitlements (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    kind       TEXT NOT NULL,                 -- spread|report|question
    code       TEXT,                          -- конкретный расклад/отчёт ('*' — любой)
    qty_total  BIGINT DEFAULT 1,
    qty_used   BIGINT DEFAULT 0,
    expires_at TEXT,
    source     TEXT DEFAULT 'purchase',       -- purchase|promo|gift|referral|admin
    order_id   BIGINT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS crystal_ledger (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    delta      BIGINT,
    reason     TEXT,
    balance    BIGINT,                       -- баланс после операции (аудит)
    ref        TEXT,
    created_at TEXT
);


CREATE TABLE IF NOT EXISTS promo_codes (
    code       TEXT PRIMARY KEY,
    kind       TEXT DEFAULT 'plan_days',      -- plan_days|crystals|product
    days       BIGINT DEFAULT 30,
    plan_code  TEXT DEFAULT 'vip',
    crystals   BIGINT DEFAULT 0,
    sku        TEXT,
    batch      TEXT,
    max_uses   BIGINT DEFAULT 1,
    used_count BIGINT DEFAULT 0,
    expires_at TEXT,
    created_by BIGINT,
    created_at TEXT,
    used_by    BIGINT,                       -- legacy: первый активировавший
    used_at    TEXT
);
CREATE TABLE IF NOT EXISTS promo_redemptions (
    id         BIGSERIAL PRIMARY KEY,
    code       TEXT NOT NULL,
    tg_id      BIGINT NOT NULL,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS referrals (
    id          BIGSERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL,
    invitee_id  BIGINT NOT NULL,
    level       BIGINT DEFAULT 1,            -- 1 — подруга, 2 — подруга подруги
    bonus       BIGINT DEFAULT 0,
    created_at  TEXT,
    UNIQUE (referrer_id, invitee_id, level)
);


CREATE TABLE IF NOT EXISTS geocache (
    city_key   TEXT PRIMARY KEY,            -- нормализованное название города
    lat        DOUBLE PRECISION,
    lon        DOUBLE PRECISION,
    tz         TEXT,
    source     TEXT,                        -- builtin|nominatim
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS horoscopes (
    day        TEXT NOT NULL,               -- YYYY-MM-DD
    sign       TEXT NOT NULL,               -- знак зодиака (рус.)
    text       TEXT,
    posted_at  TEXT,                        -- когда ушло в канал-спутник
    created_at TEXT,
    PRIMARY KEY (day, sign)
);
CREATE TABLE IF NOT EXISTS llm_usage (
    id                BIGSERIAL PRIMARY KEY,
    tg_id             BIGINT,
    provider          TEXT,
    model             TEXT,
    purpose           TEXT,                 -- answer|forecast|report|memory|horoscope
    prompt_tokens     BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    cost_usd          DOUBLE PRECISION DEFAULT 0,
    latency_ms        BIGINT DEFAULT 0,
    ok                BIGINT DEFAULT 1,
    day               TEXT,
    created_at        TEXT,
    sku               TEXT,
    catalog_version   TEXT DEFAULT 'legacy',
    subscription_code TEXT,
    included_usage    BIGINT DEFAULT 0,
    crystal_spend     BIGINT DEFAULT 0,
    overage           BIGINT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS safety_events (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT,
    category   TEXT,                        -- crisis|violence|medical|stop_topic
    excerpt    TEXT,
    action     TEXT,                        -- support|soften|blocked
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS scheduler_leases (
    name             TEXT PRIMARY KEY,
    owner            TEXT,
    acquired_at      TEXT,
    lease_until      TEXT,
    last_started_at  TEXT,
    last_finished_at TEXT,
    last_status      TEXT DEFAULT 'never', -- never|running|ok|error
    last_error       TEXT,
    run_count        BIGINT DEFAULT 0,
    failure_count    BIGINT DEFAULT 0
);
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id   TEXT PRIMARY KEY,            -- id от провайдера: ключ идемпотентности
    provider   TEXT,
    kind       TEXT,
    payload    TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS payment_webhook_failures (
    id          BIGSERIAL PRIMARY KEY,
    provider    TEXT NOT NULL,
    code        TEXT NOT NULL,
    status_code BIGINT,
    created_at  TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS catalog_versions (
    version           TEXT PRIMARY KEY,
    price_book_version TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active', -- draft|active|retired
    effective_from    TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_book_items (
    id                BIGSERIAL PRIMARY KEY,
    catalog_version   TEXT NOT NULL,
    price_book_version TEXT NOT NULL,
    item_type         TEXT NOT NULL,           -- plan|annual_plan|crystal_pack|deep_operation
    code              TEXT NOT NULL,
    title             TEXT NOT NULL,
    description       TEXT,
    tier_code         TEXT,
    channel           TEXT NOT NULL,           -- stars|web|crypto|internal
    currency          TEXT NOT NULL,           -- XTR|USD|CRYSTAL
    amount_minor      BIGINT DEFAULT 0,
    amount_stars      BIGINT DEFAULT 0,
    period_days      BIGINT,
    crystal_qty      BIGINT DEFAULT 0,
    bonus_qty        BIGINT DEFAULT 0,
    grant_kind       TEXT,
    grant_code       TEXT,
    grant_qty        BIGINT DEFAULT 0,
    valid_days       BIGINT,
    expected_cost_usd DOUBLE PRECISION,
    target_margin    DOUBLE PRECISION,
    features_json    TEXT,
    metadata_json    TEXT,
    is_active        BIGINT DEFAULT 1,
    is_public        BIGINT DEFAULT 1,
    sort             BIGINT DEFAULT 100,
    effective_from   TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    UNIQUE (price_book_version, item_type, code, channel)
);
CREATE TABLE IF NOT EXISTS subscription_state (
    tg_id                  BIGINT PRIMARY KEY,
    tier_code              TEXT NOT NULL DEFAULT 'free',
    catalog_version        TEXT NOT NULL DEFAULT 'legacy',
    price_book_version     TEXT NOT NULL DEFAULT 'legacy',
    status                 TEXT NOT NULL DEFAULT 'free', -- free|active|cancelled|grace|expired|refunded
    period_start           TEXT,
    period_end             TEXT,
    cancel_at_period_end   BIGINT DEFAULT 0,
    grace_until            TEXT,
    ai_message_limit       BIGINT DEFAULT 0,
    ai_messages_used       BIGINT DEFAULT 0,
    compute_budget_usd     DOUBLE PRECISION DEFAULT 0,
    compute_used_usd       DOUBLE PRECISION DEFAULT 0,
    monthly_crystals_granted BIGINT DEFAULT 0,
    updated_at             TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS monetization_usage (
    id                BIGSERIAL PRIMARY KEY,
    tg_id             BIGINT NOT NULL,
    operation_key     TEXT NOT NULL,
    capability        TEXT NOT NULL,
    sku               TEXT,
    catalog_version   TEXT DEFAULT 'legacy',
    tier_code         TEXT DEFAULT 'free',
    period_start      TEXT,
    units             BIGINT DEFAULT 1,
    compute_cost_usd  DOUBLE PRECISION DEFAULT 0,
    crystal_cost      BIGINT DEFAULT 0,
    charged_source    TEXT NOT NULL,           -- included|crystals|entitlement|free|none
    status            TEXT NOT NULL DEFAULT 'reserved', -- reserved|succeeded|failed|restored
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    UNIQUE (tg_id, operation_key)
);
CREATE TABLE IF NOT EXISTS crystal_lots (
    id                BIGSERIAL PRIMARY KEY,
    tg_id             BIGINT NOT NULL,
    source            TEXT NOT NULL,           -- purchased|subscription_bonus|legacy|promo|refund
    order_id          BIGINT,
    original_qty      BIGINT NOT NULL,
    remaining_qty     BIGINT NOT NULL,
    expires_at        TEXT,
    created_at        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS monetization_assignments (
    tg_id             BIGINT NOT NULL,
    experiment        TEXT NOT NULL,
    variant           TEXT NOT NULL,
    assigned_at       TEXT NOT NULL,
    PRIMARY KEY (tg_id, experiment)
);


CREATE TABLE IF NOT EXISTS events (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT,
    name       TEXT NOT NULL,
    props_json TEXT,
    surface    TEXT DEFAULT 'bot',            -- bot|miniapp|admin|system
    day        TEXT,                          -- YYYY-MM-DD (UTC) для быстрых группировок
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS product_cost_events (
    id               BIGSERIAL PRIMARY KEY,
    tg_id            BIGINT,
    event_kind       TEXT NOT NULL,           -- llm|pdf|voice|tool|delivery|refund|support
    sku              TEXT NOT NULL,
    catalog_version  TEXT DEFAULT 'legacy',
    channel          TEXT DEFAULT 'system',   -- bot|miniapp|web|system
    purpose          TEXT,
    provider         TEXT,
    model            TEXT,
    result_category  TEXT,
    status           TEXT DEFAULT 'succeeded',
    units            BIGINT DEFAULT 1,
    input_tokens     BIGINT DEFAULT 0,
    output_tokens    BIGINT DEFAULT 0,
    retry_count      BIGINT DEFAULT 0,
    latency_ms       BIGINT DEFAULT 0,
    duration_ms      BIGINT DEFAULT 0,
    artifact_bytes   BIGINT DEFAULT 0,
    cost_usd         DOUBLE PRECISION,
    reference_id     TEXT,
    order_id         BIGINT,
    reason           TEXT,
    price_variant    TEXT,
    day              TEXT,
    created_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_stats (
    day        TEXT PRIMARY KEY,
    stats_json TEXT,
    updated_at TEXT
);


CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value_json TEXT,
    updated_at TEXT,
    updated_by BIGINT
);
CREATE TABLE IF NOT EXISTS content_items (
    id         BIGSERIAL PRIMARY KEY,
    kind       TEXT NOT NULL,                 -- persona|spread|practice|copy|faq
    code       TEXT NOT NULL,
    title      TEXT,
    body       TEXT,
    meta_json  TEXT,
    is_active  BIGINT DEFAULT 1,
    sort       BIGINT DEFAULT 100,
    updated_by BIGINT,
    updated_at TEXT,
    created_at TEXT,
    UNIQUE (kind, code)
);
CREATE TABLE IF NOT EXISTS feature_flags (
    code        TEXT PRIMARY KEY,
    is_on       BIGINT DEFAULT 0,
    rollout_pct BIGINT DEFAULT 100,
    description TEXT,
    updated_by  BIGINT,
    updated_at  TEXT
);
CREATE TABLE IF NOT EXISTS admins (
    tg_id      BIGINT PRIMARY KEY,
    role       TEXT DEFAULT 'admin',          -- owner|admin|support|analyst
    title      TEXT,
    added_by   BIGINT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS admin_audit (
    id           BIGSERIAL PRIMARY KEY,
    admin_id     BIGINT,
    action       TEXT NOT NULL,
    target       TEXT,
    payload_json TEXT,
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS user_notes (
    id         BIGSERIAL PRIMARY KEY,
    tg_id      BIGINT NOT NULL,
    author_id  BIGINT,
    text       TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS user_tags (
    tg_id      BIGINT NOT NULL,
    tag        TEXT NOT NULL,
    author_id  BIGINT,
    created_at TEXT,
    PRIMARY KEY (tg_id, tag)
);
CREATE TABLE IF NOT EXISTS broadcasts (
    id           BIGSERIAL PRIMARY KEY,
    title        TEXT,
    body         TEXT,
    button_text  TEXT,
    button_url   TEXT,
    segment_json TEXT,
    status       TEXT DEFAULT 'draft',        -- draft|scheduled|running|done|cancelled
    total        BIGINT DEFAULT 0,
    sent         BIGINT DEFAULT 0,
    failed       BIGINT DEFAULT 0,
    scheduled_at TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    created_by   BIGINT,
    created_at   TEXT
);
CREATE TABLE IF NOT EXISTS broadcast_targets (
    broadcast_id BIGINT NOT NULL,
    tg_id        BIGINT NOT NULL,
    status       TEXT DEFAULT 'pending',      -- pending|claiming|sent|failed|skipped
    error        TEXT,
    sent_at      TEXT,
    claimed_at   TEXT,                        -- момент захвата (G9: атомарный claim)
    PRIMARY KEY (broadcast_id, tg_id)
);
CREATE TABLE IF NOT EXISTS task_jobs (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'queued', -- queued|running|succeeded|failed|retry|rejected
    tg_id        BIGINT,
    payload_json TEXT,
    result_json  TEXT,
    error        TEXT,
    attempts     BIGINT NOT NULL DEFAULT 0,
    available_at TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
    

CREATE INDEX IF NOT EXISTS idx_msg_user            ON messages(tg_id, is_question, created_at);
CREATE INDEX IF NOT EXISTS idx_msg_created         ON messages(created_at);
CREATE INDEX IF NOT EXISTS idx_msg_thread          ON messages(thread_id, id);
CREATE INDEX IF NOT EXISTS idx_msg_user_id          ON messages(tg_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_msg_user_thread_id   ON messages(tg_id, thread_id, id);
CREATE INDEX IF NOT EXISTS idx_msg_user_question_id ON messages(tg_id, is_question, id DESC);
CREATE INDEX IF NOT EXISTS idx_thread_user         ON threads(tg_id, archived, last_at);
CREATE INDEX IF NOT EXISTS idx_thread_user_agent   ON threads(tg_id, agent, archived, id DESC);
CREATE INDEX IF NOT EXISTS idx_thread_user_recent  ON threads(
    tg_id, archived, COALESCE(last_at, created_at) DESC, id DESC
);
CREATE INDEX IF NOT EXISTS idx_reports_user  ON reports(tg_id, kind);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON user_notifications(tg_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON user_notifications(tg_id, read_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mem_user        ON memories(tg_id);
CREATE INDEX IF NOT EXISTS idx_mem_user_rank   ON memories(tg_id, weight DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_shared_event_user_time ON shared_context_events(tg_id, event_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shared_snapshot_user_key ON shared_context_snapshots(tg_id, snapshot_type, snapshot_key);
CREATE INDEX IF NOT EXISTS idx_diary_user      ON diary(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_read_user     ON tarot_readings(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_read_created  ON tarot_readings(created_at);
CREATE INDEX IF NOT EXISTS idx_palm_user     ON palm_readings(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_name   ON events(name, day);
CREATE INDEX IF NOT EXISTS idx_events_user       ON events(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_events_user_name  ON events(tg_id, name);
CREATE INDEX IF NOT EXISTS idx_events_day        ON events(day);
CREATE INDEX IF NOT EXISTS idx_task_jobs_status_available ON task_jobs(status, available_at);
CREATE INDEX IF NOT EXISTS idx_task_jobs_user_created ON task_jobs(tg_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_created_name
    ON events(created_at, name, tg_id);
CREATE INDEX IF NOT EXISTS idx_orders_user        ON orders(tg_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status      ON orders(status, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status_paid ON orders(status, paid_at);
CREATE INDEX IF NOT EXISTS idx_pay_created        ON payments(created_at);
CREATE INDEX IF NOT EXISTS idx_pay_status_created ON payments(status, created_at);
CREATE INDEX IF NOT EXISTS idx_ent_user      ON entitlements(tg_id, kind, code);
CREATE INDEX IF NOT EXISTS idx_ledger_user   ON crystal_ledger(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_users_seen         ON users(last_seen);
CREATE INDEX IF NOT EXISTS idx_users_created      ON users(created_at);
CREATE INDEX IF NOT EXISTS idx_users_created_source ON users(created_at, source);
CREATE INDEX IF NOT EXISTS idx_users_sub     ON users(sub_until);
CREATE INDEX IF NOT EXISTS idx_partners_user ON partners(tg_id);
CREATE INDEX IF NOT EXISTS idx_syn_user      ON synastry_cache(tg_id, partner_key);
CREATE INDEX IF NOT EXISTS idx_notes_user    ON user_notes(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_ref_referrer  ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_ref_invitee   ON referrals(invitee_id, level);
CREATE INDEX IF NOT EXISTS idx_promo_batch   ON promo_codes(batch);
CREATE INDEX IF NOT EXISTS idx_promo_red     ON promo_redemptions(code, tg_id);
CREATE INDEX IF NOT EXISTS idx_promo_created  ON promo_redemptions(created_at);
CREATE INDEX IF NOT EXISTS idx_pay_order     ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payment_webhook_failures_created
    ON payment_webhook_failures(created_at, provider);
CREATE INDEX IF NOT EXISTS idx_bt_status     ON broadcast_targets(broadcast_id, status);
CREATE INDEX IF NOT EXISTS idx_usage_day     ON llm_usage(day, purpose);
CREATE INDEX IF NOT EXISTS idx_usage_user    ON llm_usage(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_created ON llm_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_subscription_state_status ON subscription_state(status, period_end);
CREATE INDEX IF NOT EXISTS idx_monetization_usage_user_period ON monetization_usage(tg_id, period_start, status);
CREATE INDEX IF NOT EXISTS idx_monetization_usage_sku ON monetization_usage(sku, created_at);
CREATE INDEX IF NOT EXISTS idx_crystal_lots_user_expiry ON crystal_lots(tg_id, expires_at, id);
CREATE INDEX IF NOT EXISTS idx_price_book_public ON price_book_items(price_book_version, is_active, is_public, sort);
CREATE INDEX IF NOT EXISTS idx_assignments_experiment ON monetization_assignments(experiment, variant);
CREATE INDEX IF NOT EXISTS idx_product_cost_day_sku ON product_cost_events(day, sku, event_kind);
CREATE INDEX IF NOT EXISTS idx_product_cost_created ON product_cost_events(created_at);
CREATE INDEX IF NOT EXISTS idx_product_cost_order ON product_cost_events(order_id);
CREATE INDEX IF NOT EXISTS idx_safety_user   ON safety_events(tg_id, created_at);
CREATE INDEX IF NOT EXISTS idx_horo_day      ON horoscopes(day);
CREATE INDEX IF NOT EXISTS idx_practice_user ON practices(tg_id, code);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

