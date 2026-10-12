/* ============================================================================
   Единая история Oracle — получение объединенной хронологии от сервера.

   СЕРВЕРНЫЙ ЭНДПОИНТ: GET /api/chat/history/unified (app/api/routers/chat.py).
   Сервер объединяет сообщения всех 4 доменов (oracle, astro, tarot, chiromant)
   с детерминированной сортировкой по (created_at, id) и стабильной
   keyset-пагинацией (before_id, limit), исключая архивные треды (archived=1).

   Клиент больше НЕ выполняет 4..8 последовательных HTTP-запросов к сессиям
   и не сортирует массивы в памяти: один запрос к серверному API возвращает
   готовую отсортированную ленту.
   ============================================================================ */
import { askOracle, fetchServerUnifiedHistory, type ServerUnifiedHistoryMessage } from './client';
import { withSessionRetry } from './session';
import { LLM_TIMEOUT_MS } from './transport';

export interface UnifiedMessage {
  id: number;
  role: 'user' | 'assistant';
  text: string;
  created_at: string;
  /** Домен-обработчик вопроса (oracle / astro / tarot / chiromant). */
  agent: string;
  thread_id: number;
  /** Чем оплачен ответ (plan/followup/...). Followup не тратит лимит дня. */
  charge?: string | undefined;
}

export interface UnifiedHistory {
  messages: UnifiedMessage[];
  has_more?: boolean | undefined;
  oldest_id?: number | null | undefined;
  oldest_created_at?: string | null | undefined;
  newest_id?: number | null | undefined;
  newest_created_at?: string | null | undefined;
  /** Домены, которые не удалось загрузить (если применимо). */
  missing: string[];
}

export interface FetchUnifiedHistoryOptions {
  limit?: number | undefined;
  before_id?: number | undefined;
  before_created_at?: string | undefined;
  signal?: AbortSignal | undefined;
}

/**
 * Загрузка единой истории. Поддерживает как вызов с AbortSignal (обратная совместимость),
 * так и вызов с объектом опций составной keyset-пагинации.
 */
export async function fetchUnifiedHistory(
  signalOrOptions?: AbortSignal | FetchUnifiedHistoryOptions,
): Promise<UnifiedHistory> {
  const options: FetchUnifiedHistoryOptions =
    signalOrOptions instanceof AbortSignal
      ? { signal: signalOrOptions }
      : (signalOrOptions ?? {});

  const result = await withSessionRetry(
    () =>
      fetchServerUnifiedHistory({
        limit: options.limit ?? 50,
        before_id: options.before_id,
        before_created_at: options.before_created_at,
        signal: options.signal,
      }),
    'GET',
  );

  return {
    messages: (result.messages ?? []).map((m: ServerUnifiedHistoryMessage) => {
      const msg: UnifiedMessage = {
        id: m.id,
        role: m.role === 'assistant' ? 'assistant' : 'user',
        text: m.text,
        created_at: m.created_at,
        agent: m.agent,
        thread_id: m.thread_id,
      };
      if (m.charge !== undefined) {
        msg.charge = m.charge;
      }
      return msg;
    }),
    has_more: result.has_more,
    oldest_id: result.oldest_id,
    oldest_created_at: result.oldest_created_at,
    newest_id: result.newest_id,
    newest_created_at: result.newest_created_at,
    missing: result.missing ?? [],
  };
}

/** Отправка вопроса. Тред выбирает сервер по домену — клиент не маршрутизирует. */
export function askOracleUnified(text: string, idempotencyKey: string, signal?: AbortSignal) {
  return withSessionRetry(
    () =>
      askOracle({ text }, {
        idempotencyKey,
        signal,
      }),
    'POST',
  );
}

export { LLM_TIMEOUT_MS };
