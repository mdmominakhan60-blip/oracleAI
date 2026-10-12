import { fetchMe, type Me } from '../api/client';
import { useResource, errorKeyFrom, PROFILE_ERRORS } from './useResource';

/* ============================================================================
   useMe — профиль пользователя.

   Общая механика загрузки (статусы, отмена, защита от устаревших ответов)
   вынесена в useResource: Home, Settings и Chart читают один и тот же профиль
   без дублирования useEffect.
   ============================================================================ */

export function useMe() {
  return useResource<Me>({
    load: (signal) => fetchMe(signal),
    errorKeyFor: errorKeyFrom(PROFILE_ERRORS),
  });
}
