/* ============================================================================
   Сессии — порт контракта miniapp/js/01-utils.js:43-100.

   Фактический серверный контракт (проверено по коду, не по документам):
   - POST /api/auth/session  {init_data} → {session_token, expires_in}
     (app/api/routers/auth_router.py:117-150, проверка подписи — security.py).
   - X-Session-Token приоритетнее x-init-data (app/api/deps.py:107-140).
   - initData одноразовая: повторный минт той же строки → 401 «initData уже
     использована (replay)». Ретрай минта бессмыслен и вреден.
   - 401 на read-ручках → токен протух: чистим, минтим, один повтор.
   - 404 «открой бота /start», 403 «заблокирован», 410 «удалён».

   Отличия от старой реализации и почему:
   1. Токен в sessionStorage, не localStorage: креды не переживают вкладку.
      Ключ версионированный (oracleai.session.v2) — старому формату не доверяем.
   2. in-flight-дедуп минта сохранён: параллельные минты дают 401 replay.
   3. Провал минта больше не проглатывается молча: вызывающий код получает
      причину и решает, что показать.
   ============================================================================ */

import type { ApiDomainError } from './transport';

const TOKEN_KEY = 'oracleai.session.v2';

/** Причины, по которым сессию не получить. Для UI, не для пользователя. */
export type SessionMintFailure =
  | 'no_init_data'
  | 'rejected'
  | 'replay'
  | 'network'
  | 'bad_response';

export type SessionMintResult =
  | { ok: true; failure?: undefined }
  | { ok: false; failure: SessionMintFailure };

// Fallback на память процесса, когда sessionStorage недоступен (приватный режим).
let memoryToken: string | null = null;

function readToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return memoryToken;
  }
}

function writeToken(token: string): void {
  memoryToken = token;
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* ignore */
  }
}

export function clearSession(): void {
  memoryToken = null;
  try {
    window.sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

export function sessionToken(): string | null {
  return readToken();
}

/** Источник initData — только Telegram SDK. Никаких заменителей. */
export function readInitData(): string | null {
  const telegram = (window as unknown as {
    Telegram?: { WebApp?: { initData?: string } };
  }).Telegram;
  const initData = telegram?.WebApp?.initData;
  return initData && initData.length > 0 ? initData : null;
}

/** Заголовки авторизации: токен приоритетнее initData (как на сервере). */
export function authHeaders(): Record<string, string> {
  const token = readToken();
  if (token) return { 'X-Session-Token': token };
  const initData = readInitData();
  if (initData) return { 'X-Init-Data': initData };
  return {};
}

/** Настоящий минт, отделён от дедупа, чтобы in-flight не затирался раньше времени. */
async function mintSessionOnce(): Promise<SessionMintResult> {
  try {
    const initData = readInitData();
    if (!initData) return { ok: false, failure: 'no_init_data' };

    const response = await fetch('/api/auth/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: initData }),
    });

    if (response.status === 401) {
      const body = await response.text().catch(() => '');
      const failure: SessionMintFailure = body.includes('использована') ? 'replay' : 'rejected';
      return { ok: false, failure };
    }
    if (!response.ok) return { ok: false, failure: 'rejected' };

    const body: unknown = await response.json().catch(() => null);
    const token =
      typeof body === 'object' && body !== null && 'session_token' in body
        ? (body as { session_token?: unknown }).session_token
        : undefined;
    if (typeof token !== 'string' || !token) return { ok: false, failure: 'bad_response' };

    writeToken(token);
    return { ok: true };
  } catch {
    return { ok: false, failure: 'network' };
  }
}

let mintInFlight: Promise<SessionMintResult> | null = null;

/**
 * Обмен initData на сессионный токен.
 * Одна попытка: повтор даёт 401 replay, потому что nonce одноразовый.
 * Параллельные вызовы делят один промис.
 */
export function mintSession(): Promise<SessionMintResult> {
  if (mintInFlight) return mintInFlight;
  mintInFlight = mintSessionOnce();
  void mintInFlight.finally(() => {
    mintInFlight = null;
  });
  return mintInFlight;
}

function isAuthError(error: unknown): error is ApiDomainError {
  return (
    typeof error === 'object' &&
    error !== null &&
    'status' in error &&
    (error as { status?: unknown }).status === 401
  );
}

/**
 * Выполнить запрос, при 401 один раз переминтив сессию.
 * Мутации (не-GET) не повторяем автоматически: сервер мог применить часть
 * операции до отказа, и дубль опаснее исходной ошибки.
 */
export async function withSessionRetry<T>(
  run: (retried: boolean) => Promise<T>,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
): Promise<T> {
  try {
    return await run(false);
  } catch (error) {
    if (!isAuthError(error) || method !== 'GET') throw error;
    clearSession();
    const minted = await mintSession();
    if (!minted.ok) throw error;
    return await run(true);
  }
}
