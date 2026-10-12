import { useCallback, useRef, useState } from 'react';
import { ApiDomainError, ApiTransportError } from '../api/transport';
import { withSessionRetry } from '../api/session';
import {
  createMemory,
  deleteMemory,
  fetchMemories,
  type MemoryItem,
} from '../api/client';
import { useResource, PROFILE_ERRORS } from './useResource';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   useMemories — список фактов и две мутации над ним.

   Модель данных серверная и односторонняя: backend даёт только
   `GET /api/memories`, `POST` (ответ `{ok:true}`) и `DELETE`. Чтения и
   редактирования отдельной записи нет (`GET|PATCH /api/memories/{id}` → 405),
   поэтому правка текста здесь не имитируется: факт удаляется и создаётся
   заново только по явному действию пользователя, если он захочет.

   Почему после создания список перечитывается, а не дополняется: ответа с
   созданной записью сервер не возвращает, а дедупликация по нормализованному
   тексту отвечает тем же `200` и не создаёт строку. Оптимистичная вставка
   показала бы запись, которой может не быть.
   ============================================================================ */

/** Отказ домена памяти → ключ интерфейса. */
export function memoryErrorKey(error: ApiDomainError): TranslationKey {
  if (error.status === 409) return 'memory.off_blocked';
  if (error.status === 404) return 'memory.not_found';
  if (error.status === 422) return 'memory.rejected';
  return PROFILE_ERRORS[error.status] ?? 'state.error';
}

export type MutationStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface MemoryMutation {
  status: MutationStatus;
  errorKey: TranslationKey | null;
  /** Текст сервера для 422/409 — он точнее общего сообщения. */
  detail: string | null;
}

const IDLE: MemoryMutation = { status: 'idle', errorKey: null, detail: null };

export interface UseMemoriesResult {
  items: MemoryItem[];
  status: 'loading' | 'ready' | 'error';
  errorKey: TranslationKey | null;
  canRetry: boolean;
  reload: () => void;
  /** Создать факт; true — сервер ответил 200 (список уже перечитан). */
  add: (fact: string) => Promise<boolean>;
  /** Удалить факт; true — сервер ответил 200. */
  remove: (id: number) => Promise<boolean>;
  mutation: MemoryMutation;
  /** id записи, удаление которой подтверждается прямо сейчас. */
  pendingDeleteId: number | null;
  askDelete: (id: number | null) => void;
  resetMutation: () => void;
}

/** Длина факта по контракту `MemoryIn`: min_length=3, max_length=300. */
export const FACT_MIN = 3;
export const FACT_MAX = 300;

export function factLengthError(fact: string): TranslationKey | null {
  const trimmed = fact.trim();
  if (trimmed.length === 0) return 'memory.form_empty';
  if (trimmed.length < FACT_MIN) return 'memory.form_too_short';
  if (trimmed.length > FACT_MAX) return 'memory.form_too_long';
  return null;
}

export function useMemories(enabled = true): UseMemoriesResult {
  const list = useResource<MemoryItem[]>({
    load: (signal) => fetchMemories(signal),
    errorKeyFor: memoryErrorKey,
    enabled,
  });

  const [mutation, setMutation] = useState<MemoryMutation>(IDLE);
  const [pendingDeleteId, setPendingDeleteId] = useState<number | null>(null);
  // Мутацию нельзя повторить автоматически: сервер мог применить операцию,
  // и повтор при неопределённом исходе создаёт дубль (или 404, выдаваемый
  // за «не удалилось»). Блокировка по ref'у держит и повторный клик.
  const inFlight = useRef(false);

  const resetMutation = useCallback(() => setMutation(IDLE), []);

  const add = useCallback(
    async (fact: string): Promise<boolean> => {
      if (inFlight.current) return false;
      const invalid = factLengthError(fact);
      if (invalid) {
        setMutation({ status: 'error', errorKey: invalid, detail: null });
        return false;
      }
      inFlight.current = true;
      setMutation({ status: 'saving', errorKey: null, detail: null });
      try {
        // Повтор мутации при 401 запрещён: сессия обновляется, а повтор PATCH
        // мог бы применить операцию дважды.
        await withSessionRetry(() => createMemory({ fact: fact.trim() }), 'POST');
        // «Сохранили» показываем только после того, как сервер ответил 200 —
        // и только после перечтения, чтобы экран не расходился с backend.
        await list.reload();
        setMutation({ status: 'saved', errorKey: null, detail: null });
        return true;
      } catch (error) {
        setMutation({
          status: 'error',
          errorKey: error instanceof ApiDomainError
            ? memoryErrorKey(error)
            : error instanceof ApiTransportError
              ? 'network.error'
              : 'state.error',
          detail: error instanceof ApiDomainError
            && (error.status === 409 || error.status === 422)
            ? error.message
            : null,
        });
        return false;
      } finally {
        inFlight.current = false;
      }
    },
    [list],
  );

  const remove = useCallback(
    async (id: number): Promise<boolean> => {
      if (inFlight.current) return false;
      inFlight.current = true;
      setMutation({ status: 'saving', errorKey: null, detail: null });
      try {
        await withSessionRetry(() => deleteMemory(id), 'DELETE');
        setPendingDeleteId(null);
        await list.reload();
        setMutation({ status: 'saved', errorKey: null, detail: null });
        return true;
      } catch (error) {
        setMutation({
          status: 'error',
          errorKey: error instanceof ApiDomainError
            ? memoryErrorKey(error)
            : error instanceof ApiTransportError
              ? 'network.error'
              : 'state.error',
          detail: error instanceof ApiDomainError ? error.message : null,
        });
        return false;
      } finally {
        inFlight.current = false;
      }
    },
    [list],
  );

  return {
    items: list.data ?? [],
    status: list.status,
    errorKey: list.errorKey,
    canRetry: list.canRetry,
    reload: list.reload,
    add,
    remove,
    mutation,
    pendingDeleteId,
    askDelete: setPendingDeleteId,
    resetMutation,
  };
}
