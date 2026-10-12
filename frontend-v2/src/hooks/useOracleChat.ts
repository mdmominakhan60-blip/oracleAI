import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiDomainError } from '../api/transport';
import {
  fetchUnifiedHistory,
  askOracleUnified,
  type UnifiedMessage,
} from '../api/unifiedHistory';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   useOracleChat — единый диалог с Oracle.

   ОДНА лента: backend пишет разговор `oracle`, Таро и астрологию в РАЗНЫЕ
   треды (services/chat.py ensure_thread по коду агента), поэтому лента
   собирается из всех доменов через fetchUnifiedHistory и сортируется по
   created_at. Сообщения реальные — клиент ничего не додумывает и не создаёт
   новую беседу при рендере.

   Инварианты:
   - историю грузим один раз на монтирование (StrictMode-safe);
   - отправку блокируем флагом-рефом, чтобы двойной клик не создал второй вопрос;
   - ключ идемпотентности живёт до успешного ответа; после ошибки сбрасываем,
     иначе следующий вопрос вернул бы закешированный отказ.
   ============================================================================ */

export type ChatStatus = 'loading' | 'ready' | 'error';

export interface ChatState {
  status: ChatStatus;
  messages: UnifiedMessage[];
  /** Идёт отправка: второй запрос не начинается. */
  sending: boolean;
  errorKey: TranslationKey | null;
  /** Домены, историю которых не удалось загрузить (сеть/лимит). */
  missing: string[];
}

export function useOracleChat() {
  const [state, setState] = useState<ChatState>({
    status: 'loading',
    messages: [],
    sending: false,
    errorKey: null,
    missing: [],
  });

  const alive = useRef(true);
  const requestController = useRef<AbortController | null>(null);
  const idempotencyKey = useRef<string | null>(null);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      requestController.current?.abort();
    };
  }, []);

  const load = useCallback(async () => {
    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;

    setState((s) => ({ ...s, status: 'loading', errorKey: null }));
    try {
      const history = await fetchUnifiedHistory(controller.signal);
      if (!alive.current) return;
      setState({
        status: 'ready',
        messages: history.messages,
        sending: false,
        errorKey: null,
        missing: history.missing,
      });
    } catch (error) {
      if (!alive.current) return;
      setState((s) => ({ ...s, status: 'error', errorKey: keyFor(error), missing: [] }));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const send = useCallback(async (rawText: string): Promise<boolean> => {
    const question = rawText.trim();
    if (!question) return false;
    // Блокировка через ref: закрытие не устаревает между рендерами.
    if (idempotencyKey.current) return false;

    requestController.current?.abort();
    const controller = new AbortController();
    requestController.current = controller;
    const key = `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
    idempotencyKey.current = key;

    setState((s) => ({
      ...s,
      sending: true,
      errorKey: null,
      messages: [...s.messages, { id: Date.now(), role: 'user', text: question, created_at: new Date().toISOString(), agent: 'oracle', thread_id: 0 }],
    }));

    try {
      const response = await askOracleUnified(question, key, controller.signal);
      if (!alive.current) return false;
      idempotencyKey.current = null;
      setState((s) => ({
        ...s,
        sending: false,
        messages: [
          ...s.messages,
          {
            id: Date.now(),
            role: 'assistant',
            text: response.answer,
            created_at: new Date().toISOString(),
            agent: response.agent,
            thread_id: response.thread_id,
          },
        ],
      }));
      return true;
    } catch (error) {
      idempotencyKey.current = null;
      if (!alive.current) return false;
      setState((s) => ({
        ...s,
        sending: false,
        errorKey: keyFor(error),
        // Убираем неотвеченный вопрос — вызывающий код вернёт текст в композатор.
        messages: s.messages.filter((m) => m.text !== question),
      }));
      return false;
    }
  }, []);

  return { ...state, send, reload: load };
}

/** Ошибка → ключ сообщения. Сырые тексты сервера не показываются. */
function keyFor(error: unknown): TranslationKey {
  if (error instanceof ApiDomainError) {
    if (error.status === 429) return 'oracle.limit_title';
    if (error.status === 402) return 'oracle.access_ended';
    if (error.status === 400) return 'oracle.bad_request';
    return 'state.error';
  }
  return 'network.error';
}
