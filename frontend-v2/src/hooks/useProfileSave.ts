import { useCallback, useRef, useState } from 'react';
import { ApiDomainError, ApiTransportError } from '../api/transport';
import { withSessionRetry } from '../api/session';
import { patchProfile, type ProfilePatch, type ProfilePatchResult } from '../api/client';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   useProfileSave — запись профиля через PATCH /api/profile.

   Общий слой для онбординга и настроек. Отдельная от useResource сущность,
   потому что загрузка и мутация отличаются принципиально:

   - Загрузку при отказе можно повторить безопасно. Мутацию — нет: сервер
     мог применить часть операции, и автоматический повтор при неопределённом
     исходе (таймаут, обрыв после отправки) создаёт неконтролируемый дубль.
     Поэтому поворот к состоянию ошибки — всегда ручной, по действию
     пользователя.
   - Источник истины о результате — ответ сервера и последующий GET /api/me,
     а не локальный флаг. Хук возвращает `updated` и `onboarded` из ответа,
     экран решает, что перечитывать.

   Сохранность ввода — задача экрана: хук не хранит поля и не восстанавливает
   их, он лишь честно сообщает, чем закончилась попытка.
   ============================================================================ */

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface SaveState {
  status: SaveStatus;
  /** Поля, которые сервер реально записал (из ответа, не из запроса). */
  updated: string[] | null;
  onboarded: boolean;
  /** Ключ сообщения об отказе; null для успеха. */
  errorKey: TranslationKey | null;
  /** Текст сервера для точечных отказов (400 по конкретному полю). */
  detail: string | null;
}

const INITIAL: SaveState = {
  status: 'idle',
  updated: null,
  onboarded: false,
  errorKey: null,
  detail: null,
};

/** Отказ домена → ключ интерфейса. Общий для онбординга и настроек. */
export function profileSaveErrorKey(error: ApiDomainError): TranslationKey {
  if (error.status === 401) return 'auth.required';
  if (error.status === 429) return 'state.rate_limited';
  // 400 — отказ бизнес-валидатора (onboarding_fields): текст сервера точечный.
  // 422 — отказ Pydantic (значение вне Literal, слишком длинная строка):
  // detail приходит массивом без message, поэтому показываем общий текст.
  if (error.status === 400) return 'profile.save_rejected';
  if (error.status === 422) return 'profile.save_rejected';
  return 'state.error';
}

export interface UseProfileSave {
  state: SaveState;
  /** Отправляет запрос. Возвращает ответ сервера или null при отказе. */
  save: (patch: ProfilePatch) => Promise<ProfilePatchResult | null>;
}

export function useProfileSave(): UseProfileSave {
  const [state, setState] = useState<SaveState>(INITIAL);
  // Защита от двойной отправки: онбординг вызывает save из обработчика
  // кнопки, которую можно нажать повторно до ответа сервера.
  const inFlight = useRef(false);

  const save = useCallback(async (patch: ProfilePatch) => {
    if (inFlight.current) return null;
    inFlight.current = true;
    setState((s) => ({ ...s, status: 'saving', errorKey: null, detail: null }));
    try {
      const result = await withSessionRetry(() => patchProfile(patch), 'PATCH');
      setState({
        status: 'saved',
        updated: result?.updated ?? [],
        onboarded: result?.onboarded ?? false,
        errorKey: null,
        detail: null,
      });
      return result;
    } catch (error) {
      const domain = error instanceof ApiDomainError;
      const transport = error instanceof ApiTransportError;
      setState({
        status: 'error',
        updated: null,
        // Ответа нет — о завершении ничего неизвестно, не утверждаем ложного.
        onboarded: false,
        errorKey: domain
          ? profileSaveErrorKey(error as ApiDomainError)
          : transport
            ? 'network.error'
            : 'state.error',
        detail: domain && (error as ApiDomainError).status === 400
          ? (error as ApiDomainError).message
          : null,
      });
      return null;
    } finally {
      inFlight.current = false;
    }
  }, []);

  return { state, save };
}
