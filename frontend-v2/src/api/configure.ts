/* Инициализация API-слоя: связывает транспорт с сессией.
   Вызывается один раз из main.tsx. */
import { setHeaderProvider, LLM_TIMEOUT_MS } from './transport';
import { authHeaders, mintSession, withSessionRetry } from './session';

export { LLM_TIMEOUT_MS };

setHeaderProvider(authHeaders);

export async function initializeApi(): Promise<void> {
  // Токен уже мог быть выдан ранее (reload вебвью) — тогда минтить не нужно.
  // Без токена и без initData (не Telegram) приложение честно работает в
  // неавторизованном режиме: сервер сам ответит 401 на защищённых ручках.
  await mintSession();
}

export { withSessionRetry, mintSession, authHeaders };
