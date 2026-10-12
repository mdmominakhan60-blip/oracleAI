import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchToday, type TodayPayload } from '../api/client';
import { ApiDomainError, ApiTransportError } from '../api/transport';
import { withSessionRetry } from '../api/session';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   useToday — прогноз дня (карта дня, луна, сезон Солнца, следующий шаг).

   GET /api/today требует АКТИВНУЮ подписку (app/api/routers/today.py:24 —
   Depends(active_user)). Без подписки backend отвечает 402 «подписка
   завершена» — это честное тарифное ограничение, а не ошибка UI:
   экран показывает предложение продлить, не имитируя прогноз.

   Бюджет: endpoint делает llm-вызов (forecast кэшируется на сутки), поэтому
   загружаем один раз на монтирование и не перезапрашиваем без нужды.
   ============================================================================ */

export type TodayStatus = 'loading' | 'ready' | 'locked' | 'error';

export interface TodayState {
  status: TodayStatus;
  today: TodayPayload | null;
  errorKey: TranslationKey | null;
  canRetry: boolean;
}

export function useToday(options: { enabled?: boolean } = {}) {
  const { enabled = true } = options;
  const [state, setState] = useState<TodayState>({
    status: 'loading',
    today: null,
    errorKey: null,
    canRetry: false,
  });

  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    if (!enabled) {
      setState({ status: 'loading', today: null, errorKey: null, canRetry: false });
      return;
    }
    const controller = new AbortController();
    setState((s) => ({ ...s, status: 'loading', errorKey: null }));
    try {
      const today = await withSessionRetry(() => fetchToday(controller.signal), 'GET');
      if (!alive.current) return;
      setState({ status: 'ready', today, errorKey: null, canRetry: false });
    } catch (error) {
      if (!alive.current) return;
      // 402 = тарифное ограничение (нет активной подписки), а не сбой.
      if (error instanceof ApiDomainError && error.status === 402) {
        setState({ status: 'locked', today: null, errorKey: 'today.locked_title', canRetry: false });
        return;
      }
      setState({
        status: 'error',
        today: null,
        errorKey: keyFor(error),
        canRetry: error instanceof ApiTransportError,
      });
    }
  }, [enabled]);

  useEffect(() => {
    void load();
  }, [load]);

  return { ...state, reload: load };
}

function keyFor(error: unknown): TranslationKey {
  if (error instanceof ApiDomainError) {
    if (error.status === 429) return 'oracle.limit_title';
    if (error.status === 404) return 'today.missing';
    return 'state.error';
  }
  return 'network.error';
}
