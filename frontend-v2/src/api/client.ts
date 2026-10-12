/* ============================================================================
   OracleAI V2 — API-клиент.

   Все сетевые вызовы собраны здесь и в transport.ts; экраны импортируют
   функции, но fetch не вызывают.

   Контракты сверены с живым backend, не только по документам:
   - POST /api/auth/session              → session.ts
   - GET  /api/me                        → fetchMe (BUS-807, 42 поля)
   - POST /api/chat/oracle               → askOracle (agent/routing/proof)
   - GET|POST /api/chat/oracle/sessions  → fetchChatSessions (по агенту)
   - GET  /api/chat/oracle/sessions/{id} → fetchSessionMessages (по агенту)
   - POST /api/chat/oracle               → askOracle (обёртка — askOracleUnified)
   - GET  /api/tarot/spreads/full        → fetchSpreadCatalog
   - GET  /api/tarot/history/{id}        → fetchReading
   - POST /api/tarot/draw                → drawTarot
   - POST /api/tarot/interpret/{id}      → interpretReading
   - GET  /api/chart                     → fetchChart
   - GET  /api/chat/history/unified      → fetchServerUnifiedHistory
   - PATCH /api/profile                  → patchProfile (onboarding и профиль)
   - GET  /api/personas                  → fetchPersonas
   - GET  /api/city/suggest              → fetchCitySuggestions
   - GET  /api/memories                  → fetchMemories
   - POST /api/memories                  → createMemory
   - DELETE /api/memories/{id}           → deleteMemory
   - GET  /api/partners                  → fetchPartners
   - POST /api/partners                  → createPartner
   - DELETE /api/partners/{id}           → deletePartner
   - POST /api/compat                    → calculateCompat

   Люди (People / Partners):
   В существующем backend сущность называется `partners` (app/api/routers/chart.py:463).
   Поддерживаются реальные GET /api/partners, POST /api/partners,
   DELETE /api/partners/{id} и POST /api/compat.
   Отдельного эндпоинта чтения карточки (GET /api/partners/{id}) и редактирования
   (PATCH) в backend нет — поэтому они не имитируются.
   Связи людей с событиями (personal_events) и графом памяти (memory_links)
   в БД отсутствуют, поэтому фиктивные данные исключены.

   Память подключена к реальному backend, но контракт узкий: чтения и
   редактирования одной записи нет (`GET|PATCH /api/memories/{id}` → 405),
   поэтому экран не имитирует эти операции на клиенте.
   ============================================================================ */


/* ── Домен: профиль и bootstrap ───────────────────────────────────────────── */

export type BirthPrecision = 'exact' | 'approx' | 'unknown';

/** Тариф из /api/me: объект с фичами, а не код-строка (сверено с живым ответом). */
export interface PlanInfo {
  code: string;
  title: string;
  tagline: string;
  price_stars: number;
  price_usd: number;
  period_days: number;
  daily_questions: number;
  memory_depth: number;
  crystals_grant: number;
  features: string[];
  badge: string;
}

/** Фактический ответ allowance (сверено с GET /api/me на живом backend). */
export interface Allowance {
  plan: string;
  plan_title: string;
  limit: number;
  used: number;
  left: number;
  period: string;
  extra_questions: number;
  crystals: number;
  emergency_cost: number;
  can_ask: boolean;
}

export interface MemoryFact {
  id: number;
  fact: string;
  kind: 'person' | 'event' | 'emotion' | 'goal' | 'fact';
  source_kind: 'user' | 'derived';
  weight: number;
  created_at: string;
}

export interface AgentQuality {
  risk_level: 'low' | 'medium' | 'high';
  memory: string;
  output_contract: string;
  skills_max_active: number;
}

/** Ответ GET /api/me — контракт заморожен (BUS-807), менять нельзя. */
export interface Me {
  tg_id: number;
  name: string;
  username: string;
  oracle_name: string;
  persona: 'friend' | 'witch' | 'mentor';
  tz: string;
  birth_date: string | null;
  birth_city: string | null;
  birth_time_known: boolean;
  birth_time: string | null;
  birth_time_precision: BirthPrecision;
  onboarding_step: string | null;
  onboarded: boolean;
  sun: { sign: string; symbol: string; element: string } | null;
  chart_mode: 'full' | 'lite' | null;
  chart_precision: BirthPrecision | 'sun_only' | null;
  crystals: number;
  sub_active: boolean;
  plan: PlanInfo | null;
  allowance: Allowance;
  questions_left: number;
  memories: string[];
  memory_enabled: boolean;
  diary_streak: number;
  global_streak: number;
  lang: 'ru' | 'en';
  flags: Record<string, boolean>;
}

/* ── Домен: чат с Oracle ──────────────────────────────────────────────────── */

export interface RoutingInfo {
  agent: string;
  confidence: number;
  score: number;
  runner_up_score: number;
  reason: string;
  candidates: string[];
  auto_route: boolean;
}

export interface ProofInfo {
  mode: 'deterministic' | 'offline' | 'safety';
  tools_used: string[];
  tools_available: string[];
  quality: AgentQuality;
  provider: string | null;
  model: string | null;
}

export interface AskResponse {
  answer: string;
  agent: string;
  routing: RoutingInfo;
  proof: ProofInfo;
  thread_id: number;
  charge: string;
  allowance: Allowance;
}

export interface AskRequest {
  text: string;
  allow_paid?: boolean;
}

/* ── Домен: память и связи ────────────────────────────────────────────────── */

/* ============================================================================
   Типы людей/событий/памяти.

   Контракты спроектированы (docs/product-v2/API_CONTRACTS.md §11), но
   в backend ещё НЕ реализованы — поэтому здесь только типы, без функций
   запроса. Функции появятся вместе с endpoint'ами, чтобы спецификация
   не выдавалась за работающую функцию.
   ============================================================================ */

export type LinkKind = 'memory' | 'partner' | 'reading' | 'diary' | 'event' | 'thread';
export type LinkOrigin = 'explicit' | 'derived';

export interface MemoryLink {
  link_id: number;
  kind: LinkKind;
  id: number;
  label: string;
  origin: LinkOrigin;
}

export interface MemoryDetail extends MemoryFact {
  last_used: string | null;
  links: MemoryLink[];
}

export interface PersonalEvent {
  id: number;
  title: string;
  happened_on: string | null;
  note: string | null;
  source_kind: 'user' | 'diary' | 'reading';
  source_id: number | null;
  created_at: string;
}

/* ── Домен: люди ──────────────────────────────────────────────────────────── */

/**
 * Реальная модель человека из `GET /api/partners` (app/repo/readings.py:159).
 * Полей связей и агрегатов `counts` в существующем backend нет (в БД нет
 * таблиц personal_events и memory_links), поэтому они не выдумываются.
 */
export interface PartnerItem {
  id: number;
  name: string;
  relation: string;
  birth_date: string;
  birth_city: string | null;
  synastry_ready: boolean;
}

/** Запрос на создание человека `POST /api/partners` (PartnerIn: wave_a.py:34). */
export interface PartnerCreate {
  name: string;
  birth_date: string;
  relation?: string | undefined;
  birth_time?: string | undefined;
  birth_city?: string | undefined;
}

/** Запрос совместимости `POST /api/compat` (CompatIn: compatibility.py:9). */
export interface CompatRequest {
  partner_date: string;
  partner_name?: string;
  relation?: 'love' | 'friend' | 'work' | 'family';
  save?: boolean;
}

export interface CompatBreakdownItem {
  title: string;
  value: number;
  note: string;
}

export interface CompatResult {
  you: { sign: string; element: string };
  partner: { sign: string; element: string };
  total: number;
  score: number;
  relation: string;
  verdict: string;
  breakdown: CompatBreakdownItem[];
}

export function fetchPartners(signal?: AbortSignal) {
  return requestJson<PartnerItem[]>('/api/partners', { signal });
}

export function createPartner(data: PartnerCreate, signal?: AbortSignal) {
  return requestJson<{ id: number; ok: boolean }>('/api/partners', {
    method: 'POST',
    body: data,
    signal,
  });
}

export function deletePartner(id: number, signal?: AbortSignal) {
  return requestJson<{ ok: boolean }>(`/api/partners/${id}`, {
    method: 'DELETE',
    signal,
  });
}

export function calculateCompat(data: CompatRequest, signal?: AbortSignal) {
  return requestJson<CompatResult>('/api/compat', {
    method: 'POST',
    body: {
      partner_date: data.partner_date,
      partner_name: data.partner_name ?? '',
      relation: data.relation ?? 'love',
      save: data.save ?? false,
    },
    signal,
  });
}

export interface PersonCounts {
  memories: number;
  readings: number;
  events: number;
  threads: number;
}

export interface PersonSummary {
  id: number;
  name: string;
  relation: string;
  birth_date: string | null;
  synastry_ready: boolean;
  counts: PersonCounts;
}

export interface PersonDetail extends PersonSummary {
  birth_city: string | null;
  memories: MemoryFact[];
  readings: Array<{
    id: number;
    spread: string;
    question: string | null;
    created_at: string;
    cards_preview: string;
  }>;
  events: PersonalEvent[];
  conversations: Array<{
    id: number;
    title: string;
    created_at: string;
    messages_count: number;
    preview: '';
  }>;
}

export type TimelineKind = 'event' | 'reading' | 'memory' | 'diary';

export interface TimelineItem {
  kind: TimelineKind;
  id: number;
  date: string;
  title: string;
  preview: string;
  source_kind?: 'user' | 'derived';
  deep_link: string;
}

/* ── Домен: Таро ──────────────────────────────────────────────────────────── */

export type Deck = 'tarot' | 'lenormand';
export type SpreadTier = 'included' | 'premium';

export interface TarotCard {
  img: string;
  name: string;
  emoji: string;
  arcana: 'major' | 'minor';
  num: string;
  suit: string | null;
  reversed: boolean;
  meaning: string;
  short: string | null;
  advice: string | null;
}

export interface SpreadInfo {
  code: string;
  title: string;
  positions: string[];
  cards: number;
  tier: SpreadTier;
  emoji: string;
  hint: string;
  sku: string | null;
  price_stars: number | null;
  price_crystals: number | null;
  owned: number;
}

export interface ReadingLedgerEntry {
  index: number;
  position: string;
  card_id: string;
  name: string;
  arcana: 'major' | 'minor';
  suit: string | null;
  reversed: boolean;
  orientation: 'upright' | 'reversed';
}

export interface ReadingResult {
  reading_id: number;
  title: string;
  positions: string[];
  cards: TarotCard[];
  spread: string;
  deck: Deck;
  thread_id: number;
  charge: string;
  ledger: {
    version: string;
    deck_id: string;
    deck: Deck;
    tradition: string;
    spread: string;
    entries: ReadingLedgerEntry[];
    checksum: string;
  };
}

/* ── Домен: натальная карта ───────────────────────────────────────────────── */

export type ChartPrecision = 'exact' | 'time_without_location' | 'date_only' | 'interval' | 'sun_only';

export interface ChartPayload {
  natal_schema_version: number;
  mode: 'full' | 'lite';
  precision: ChartPrecision;
  engine: string;
  zodiac_type: string;
  house_system: string;
  house_system_name: string;
  sun: { sign: string; symbol: string; element: string } | null;
  ascendant: { sign: string; deg: number } | null;
  mc: { sign: string; deg: number } | null;
  planets: Array<{
    name: string;
    sign: string;
    deg: number;
    house: number | null;
    retro: boolean;
  }>;
  houses: Array<{ n: number; sign: string; deg: number }>;
  aspects: Array<{ p1: string; p2: string; aspect: string; orb: number }>;
  note: string | null;
  /** Секции трактовки. Ключи: identity, mind_career, relationships, nodes. */
  sections?: {
    version: number;
    exact: boolean;
    sections: Record<
      string,
      { title: string; items: Array<{ key: string; label: string; value: string }> }
    >;
  } | undefined;
}

/* ── Транспорт: загготовка без сетевых вызовов ────────────────────────────── */

export interface ChatMessage {
  id: number;
  role: string;
  text: string;
  created_at: string;
}

export interface AgentProfile {
  code: string;
  name: string;
  emoji: string;
  title: string;
  tagline: string;
  accent: string;
  avatar: string;
  greeting: string;
  suggestions: string[];
  capabilities: string[];
}

/* ── Профиль ─────────────────────────────────────────────────────────────── */

export function fetchMe(signal?: AbortSignal) {
  return requestJson<Me>('/api/me', { signal });
}

/**
 * PATCH /api/profile — запись профиля и завершение онбординга.
 *
 * Состав полей ограничен клиентом по контракту `ProfileIn`
 * (app/api/routers/profile.py:361): backend игнорирует незнакомые свойства
 * (Pydantic без `extra="forbid"` отвечает 200), поэтому молчаливая опечатка
 * не видна на сервере — ограничение состава держим на этой стороне.
 *
 * Частичное обновление: `undefined` не сериализуется, поле сервер не трогает.
 */
export interface ProfilePatch {
  name?: string | undefined;
  birth_date?: string | undefined;
  birth_time?: string | undefined;
  birth_time_precision?: BirthPrecision | undefined;
  city?: string | undefined;
  intent?: Intent | undefined;
  onboarding_complete?: boolean | undefined;
  oracle_name?: string | undefined;
  persona?: Persona | undefined;
  morning_push?: boolean | undefined;
  memory_enabled?: boolean | undefined;
  lang?: 'ru' | 'en' | undefined;
  gender?: 'f' | 'm' | undefined;
  tz?: string | undefined;
  goal?: string | undefined;
}

/** Ответ `PATCH /api/profile`: реально записанные поля и флаг завершения. */
export interface ProfilePatchResult {
  ok: boolean;
  updated: string[];
  onboarded: boolean;
}

export function patchProfile(patch: ProfilePatch, signal?: AbortSignal) {
  return requestJson<ProfilePatchResult>('/api/profile', {
    method: 'PATCH',
    body: patch,
    signal,
  });
}

/* ── Память (memories) ───────────────────────────────────────────────────── */

/**
 * Факт из `GET /api/memories`. Набор полей — ровно то, что отдаёт
 * `dialog.memories_full` (app/repo/dialog.py:420): `id, fact, kind, weight,
 * last_used, created_at`. Полей `source_kind`, `links[]`, категорий-справочника
 * в ответе нет — интерфейс их не выдумывает.
 */
export interface MemoryItem {
  id: number;
  fact: string;
  kind: string;
  weight: number;
  last_used: string | null;
  created_at: string;
}

/** Тело `POST /api/memories`: `fact` 3..300, `kind` по умолчанию `fact`. */
export interface MemoryCreate {
  fact: string;
  kind?: string;
}

export function fetchMemories(signal?: AbortSignal) {
  return requestJson<MemoryItem[]>('/api/memories', { signal });
}

/**
 * Создание факта. Backend отвечает `{"ok": true}` и НЕ возвращает созданную
 * запись, поэтому после успеха список перечитывается, а не дополняется
 * локально: иначе на экране появилась бы строка, которой сервер мог не создать
 * (дедупликация по нормализованному тексту отдаёт тот же 200).
 */
export function createMemory(item: MemoryCreate, signal?: AbortSignal) {
  return requestJson<{ ok: true }>('/api/memories', {
    method: 'POST',
    body: { fact: item.fact, kind: item.kind ?? 'fact' },
    signal,
  });
}

/**
 * «Забудь это». Чужой и несуществующий id дают одну и ту же 404, поэтому
 * интерфейс не различает их и не сообщает лишнего.
 */
export function deleteMemory(id: number, signal?: AbortSignal) {
  return requestJson<{ ok: true }>(`/api/memories/${id}`, {
    method: 'DELETE',
    signal,
  });
}

/** Направление знакомства: единственное поле, от которого зависит `goal`. */
export type Intent = 'oracle' | 'astro' | 'tarot' | 'chiromant';

/** Тон Oracle. Коды совпадают с `PERSONAS` в app/core/personas.py. */
export type Persona = 'friend' | 'witch' | 'mentor';

/** Образ из `GET /api/personas` (app/core/personas.py). */
export interface PersonaInfo {
  code: Persona;
  title: string;
  emoji: string;
}

export function fetchPersonas(signal?: AbortSignal) {
  return requestJson<PersonaInfo[]>('/api/personas', { signal });
}

/** Подсказка города из `GET /api/city/suggest`. */
export interface CitySuggestion {
  key: string;
  label: string;
  country: string;
  timezone: string;
  detail: string;
}

export function fetchCitySuggestions(query: string, signal?: AbortSignal) {
  return requestJson<{ items: CitySuggestion[] }>(
    `/api/city/suggest?q=${encodeURIComponent(query)}`,
    { signal },
  );
}

/* ── Чат с Oracle ─────────────────────────────────────────────────────────── */

/* ── Прогноз дня ─────────────────────────────────────────────────────────── */

/**
 * GET /api/today. Требует активной подписки (Depends(active_user)) —
 * без неё backend отвечает 402, и фронт показывает тарифное ограничение.
 */
export interface TodayPayload {
  forecast: string;
  card: {
    name: string;
    emoji: string;
    meaning: string;
    num: string;
    img: string;
  };
  moon: { name: string; emoji: string; advice: string; day: number };
  sun_season: { sign: string; symbol: string; element: string };
  sphere: string;
  day: string;
  next_action: {
    kind: string;
    emoji: string;
    title: string;
    text: string;
    cta: string;
    chat: string;
    fn: string;
  };
}

export function fetchToday(signal?: AbortSignal) {
  return requestJson<TodayPayload>('/api/today', { signal, timeoutMs: 60_000 });
}

export interface ChatHistoryResponse {
  agent: AgentProfile;
  thread_id: number;
  messages: ChatMessage[];
}

export function askOracle(
  request: AskRequest,
  options: { idempotencyKey: string; signal?: AbortSignal | undefined },
) {
  return requestJson<AskResponse>('/api/chat/oracle', {
    method: 'POST',
    body: request,
    signal: options.signal,
    headers: { 'X-Idempotency-Key': options.idempotencyKey },
    timeoutMs: LLM_TIMEOUT_MS,
  });
}

export interface ChatSession {
  id: number;
  agent: string;
  title: string;
  msg_count: number;
  last_text: string | null;
  last_at: string | null;
  archived: number;
  created_at: string;
}

/** Сессии конкретного домена: основа для сборки единой истории. */
export function fetchChatSessions(agent: string, signal?: AbortSignal) {
  return requestJson<ChatSession[]>(`/api/chat/${agent}/sessions`, { signal });
}

/** Сообщения одной сессии с owner-scope (чужой тред — 404). */
export function fetchSessionMessages(agent: string, threadId: number, signal?: AbortSignal) {
  return requestJson<ChatHistoryResponse>(
    `/api/chat/${agent}/sessions/${threadId}`,
    { signal },
  );
}

export interface ServerUnifiedHistoryMessage {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  agent: string;
  thread_id: number;
  created_at: string;
  charge?: string | undefined;
}

export interface ServerUnifiedHistory {
  messages: ServerUnifiedHistoryMessage[];
  has_more: boolean;
  oldest_id: number | null;
  oldest_created_at?: string | null | undefined;
  newest_id: number | null;
  newest_created_at?: string | null | undefined;
  missing: string[];
}

/**
 * Единая история диалога с Оракулом (серверный эндпоинт).
 * GET /api/chat/history/unified возвращает сообщения из всех 4 доменов
 * (oracle, astro, tarot, chiromant) с детерминированной сортировкой и
 * составной keyset-пагинацией (before_id, before_created_at, limit).
 */
export function fetchServerUnifiedHistory(options?: {
  limit?: number | undefined;
  before_id?: number | undefined;
  before_created_at?: string | undefined;
  signal?: AbortSignal | undefined;
}) {
  const params = new URLSearchParams();
  if (options?.limit !== undefined) params.set('limit', String(options.limit));
  if (options?.before_id !== undefined) params.set('before_id', String(options.before_id));
  if (options?.before_created_at !== undefined) params.set('before_created_at', options.before_created_at);
  const query = params.toString() ? `?${params.toString()}` : '';
  return requestJson<ServerUnifiedHistory>(`/api/chat/history/unified${query}`, {
    signal: options?.signal,
  });
}





/* ── Таро ─────────────────────────────────────────────────────────────────── */

export interface SpreadCatalogItem {
  code: string;
  title: string;
  positions: string[];
  tier: SpreadTier;
  emoji: string;
  hint: string;
  guide: string;
}

export function fetchSpreadCatalog(signal?: AbortSignal) {
  return requestJson<SpreadCatalogItem[]>('/api/tarot/spreads/full', { signal });
}

export interface DrawRequest {
  question: string;
  deck: Deck;
}

export function drawTarot(spread: string, request: DrawRequest) {
  return requestJson<ReadingResult>(`/api/tarot/draw?spread=${encodeURIComponent(spread)}`, {
    method: 'POST',
    body: request,
    timeoutMs: LLM_TIMEOUT_MS,
  });
}

export interface StoredReading {
  id: number;
  spread: string;
  question: string | null;
  answer: string | null;
  outcome: string | null;
  created_at: string;
  deck: Deck;
  cards: TarotCard[];
  /**
   * Позиции приходят не отдельным полем, а внутри ledger.entries[].position
   * (сверено с GET /api/tarot/history/{id}).
   */
  ledger: {
    spread: string;
    deck: Deck;
    tradition: string;
    entries: Array<{ index: number; position: string; card_id: string; name: string }>;
  };
}

export function fetchReading(readingId: number, signal?: AbortSignal) {
  return requestJson<StoredReading>(`/api/tarot/history/${readingId}`, { signal });
}

export function interpretReading(readingId: number) {
  return requestJson<{ answer: string }>(`/api/tarot/interpret/${readingId}`, {
    method: 'POST',
    timeoutMs: LLM_TIMEOUT_MS,
  });
}

/* ── Натальная карта и Матрица ────────────────────────────────────────────── */



export function fetchChart(signal?: AbortSignal) {
  return requestJson<ChartPayload>('/api/chart', { signal, timeoutMs: 60_000 });
}


import { requestJson, LLM_TIMEOUT_MS } from './transport';
