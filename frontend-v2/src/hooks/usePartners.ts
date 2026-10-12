import { useCallback, useRef, useState } from 'react';
import { ApiDomainError, ApiTransportError } from '../api/transport';
import { withSessionRetry } from '../api/session';
import {
  createPartner,
  deletePartner,
  fetchPartners,
  type PartnerCreate,
  type PartnerItem,
} from '../api/client';
import { useResource, PROFILE_ERRORS } from './useResource';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   usePartners — реальный список партнеров/людей и операции над ним.

   Сущность в backend называется `partners` (app/api/routers/chart.py:463,
   app/repo/readings.py).
   Поддерживаются реальные методы:
   - GET /api/partners → список сохраненных людей;
   - POST /api/partners → добавление (и при memory_enabled создает факт);
   - DELETE /api/partners/{id} → удаление.

   Отдельного эндпоинта чтения по ID в API нет, поэтому getPartner(id)
   находит партнера в актуальном списке, загруженном с сервера.
   ============================================================================ */

export type PartnerMutationStatus = 'idle' | 'saving' | 'saved' | 'error';

export interface PartnerMutation {
  status: PartnerMutationStatus;
  errorKey: TranslationKey | null;
  detail: string | null;
}

const IDLE: PartnerMutation = { status: 'idle', errorKey: null, detail: null };

export interface UsePartnersResult {
  items: PartnerItem[];
  status: 'loading' | 'ready' | 'error';
  errorKey: TranslationKey | null;
  canRetry: boolean;
  reload: () => void;
  getPartner: (id: number | string | undefined) => PartnerItem | null;
  add: (data: PartnerCreate) => Promise<boolean>;
  remove: (id: number) => Promise<boolean>;
  mutation: PartnerMutation;
  resetMutation: () => void;
}

export function usePartners(enabled = true): UsePartnersResult {
  const list = useResource<PartnerItem[]>({
    load: (signal) => fetchPartners(signal),
    errorKeyFor: (error: ApiDomainError) => PROFILE_ERRORS[error.status] ?? 'state.error',
    enabled,
  });

  const [mutation, setMutation] = useState<PartnerMutation>(IDLE);
  const inFlight = useRef(false);

  const resetMutation = useCallback(() => setMutation(IDLE), []);

  const getPartner = useCallback(
    (id: number | string | undefined): PartnerItem | null => {
      if (!id || !list.data) return null;
      const numericId = typeof id === 'number' ? id : parseInt(id, 10);
      if (Number.isNaN(numericId)) return null;
      return list.data.find((p) => p.id === numericId) ?? null;
    },
    [list.data],
  );

  const add = useCallback(
    async (data: PartnerCreate): Promise<boolean> => {
      if (inFlight.current) return false;
      if (!data.name?.trim()) {
        setMutation({ status: 'error', errorKey: 'people.name_required', detail: null });
        return false;
      }
      if (!data.birth_date?.trim()) {
        setMutation({ status: 'error', errorKey: 'people.birth_required', detail: null });
        return false;
      }
      inFlight.current = true;
      setMutation({ status: 'saving', errorKey: null, detail: null });
      try {
        await withSessionRetry(() => createPartner(data), 'POST');
        await list.reload();
        setMutation({ status: 'saved', errorKey: null, detail: null });
        return true;
      } catch (error) {
        setMutation({
          status: 'error',
          errorKey:
            error instanceof ApiDomainError
              ? PROFILE_ERRORS[error.status] ?? 'state.error'
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

  const remove = useCallback(
    async (id: number): Promise<boolean> => {
      if (inFlight.current) return false;
      inFlight.current = true;
      setMutation({ status: 'saving', errorKey: null, detail: null });
      try {
        await withSessionRetry(() => deletePartner(id), 'DELETE');
        await list.reload();
        setMutation({ status: 'saved', errorKey: null, detail: null });
        return true;
      } catch (error) {
        setMutation({
          status: 'error',
          errorKey:
            error instanceof ApiDomainError
              ? PROFILE_ERRORS[error.status] ?? 'state.error'
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
    getPartner,
    add,
    remove,
    mutation,
    resetMutation,
  };
}
