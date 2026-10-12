import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiDomainError, ApiTransportError } from '../api/transport';
import { withSessionRetry } from '../api/session';
import type { RequestOptions } from '../api/transport';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   useResource — общая загрузка данных экрана.

   Закрывает четыре повтора одного паттерна (Home, Settings, Chart, Reading):
   статус loading/ready/error, защита от устаревших ответов, отмена
   AbortController при уходе с экрана и при повторном запросе.

   Повтор имеет смысл только при транспортной ошибке (сеть/таймаут): отказ
   домена (401/404/410) повторять бессмысленно — изменится лишь после смены
   сессии или данных.
   ============================================================================ */

export type ResourceStatus = 'loading' | 'ready' | 'error';

export interface ResourceState<T> {
  status: ResourceStatus;
  data: T | null;
  /**
   * КЛЮЧ сообщения об отказе из словаря i18n (не переведённый текст) —
   * экран сам вызывает t(errorKey), чтобы язык менялся без перезагрузки.
   */
  errorKey: TranslationKey | null;
  canRetry: boolean;
}

export interface ResourceOptions<T> {
  /** Загрузчик. Получает актуальный AbortSignal. */
  load: (signal: AbortSignal | undefined) => Promise<T>;
  /** Отказ сервера → ключ сообщения. По умолчанию — сетевая ошибка. */
  errorKeyFor?: (error: ApiDomainError) => TranslationKey | null;
  /** Запускать загрузку только при условии (например, валидный id). */
  enabled?: boolean;
}

export function useResource<T>({ load, errorKeyFor, enabled = true }: ResourceOptions<T>) {
  const [state, setState] = useState<ResourceState<T>>({
    status: 'loading',
    data: null,
    errorKey: null,
    canRetry: false,
  });

  const alive = useRef(true);
  const controller = useRef<AbortController | null>(null);
  // Актуальный загрузчик: useEffect не перезапускается из-за новой ссылки.
  const loadRef = useRef(load);
  loadRef.current = load;
  const errorKeyForRef = useRef(errorKeyFor);
  errorKeyForRef.current = errorKeyFor;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      controller.current?.abort();
    };
  }, []);

  const run = useCallback(async () => {
    if (!enabled) {
      setState({ status: 'error', data: null, errorKey: null, canRetry: false });
      return;
    }
    controller.current?.abort();
    const next = new AbortController();
    controller.current = next;

    setState((s) => ({ ...s, status: 'loading', errorKey: null }));
    try {
      const data = await withSessionRetry(
        () => loadRef.current(next.signal),
        // Мутаций здесь нет: хук используется только для чтения.
        'GET',
      );
      if (!alive.current) return;
      setState({ status: 'ready', data, errorKey: null, canRetry: false });
    } catch (error) {
      if (!alive.current) return;
      const transport = error instanceof ApiTransportError;
      const domainKey =
        error instanceof ApiDomainError ? (errorKeyForRef.current?.(error) ?? null) : null;
      setState({
        status: 'error',
        data: null,
        errorKey: domainKey ?? (transport ? 'network.error' : 'state.error'),
        canRetry: transport,
      });
    }
  }, [enabled]);

  useEffect(() => {
    void run();
  }, [run]);

  return { ...state, reload: run };
}

/** Часто используемый маппинг отказов домена в ключи интерфейса. */
export const PROFILE_ERRORS: Record<number, TranslationKey> = {
  401: 'auth.required',
  404: 'auth.need_start',
  403: 'auth.blocked',
  410: 'auth.deleted',
};

export const READ_ERRORS: Record<number, TranslationKey> = {
  404: 'reading.not_found',
  429: 'oracle.limit_title',
  402: 'oracle.access_ended',
};

export const ACCESS_ERRORS: Record<number, TranslationKey> = {
  429: 'oracle.limit_title',
  402: 'oracle.access_ended',
  400: 'oracle.bad_request',
};

export function errorKeyFrom(map: Record<number, TranslationKey>, fallback: TranslationKey = 'state.error') {
  return (error: ApiDomainError): TranslationKey => map[error.status] ?? fallback;
}

export type { RequestOptions };
