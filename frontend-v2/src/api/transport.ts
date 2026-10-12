/* ============================================================================
   Transport — единственный слой, который знает про fetch.

   ПРАВИЛА (нарушение = дефект):
   - Никаких запросов в экранных компонентах. Всё через requestJson/requestText.
   - Токен никогда не попадает в текст ошибки и в консоль.
   - Сырой ответ сервера не показывается пользователю: сообщения строятся
     из типизированной ошибки и переводятся через i18n на уровне экрана.
   - Не-JSON тело (HTML от прокси, пустой ответ) — это ошибка транспорта,
     а не «успех с undefined».

   Схема ошибок сервера: {"detail": "..."} или {"detail": {"code","message"}}.
   ============================================================================ */

/** Ошибка транспорта: сеть, таймаут, разбор тела. Пользователю не показывается как есть. */
export class ApiTransportError extends Error {
  constructor(message: string, options: { cause?: unknown } = {}) {
    super(message);
    this.name = 'ApiTransportError';
    if (options.cause !== undefined) this.cause = options.cause;
  }
}

/**
 * Ошибка предметной области: сервер ответил, но отказал.
 * status + code позволяют экрану выбрать правильное сообщение и действие.
 */
export class ApiDomainError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiDomainError';
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE' | undefined;
  body?: unknown;
  signal?: AbortSignal | undefined;
  /** Заголовки поверх стандартных (X-Idempotency-Key и т.п.). */
  headers?: Record<string, string> | undefined;
  timeoutMs?: number | undefined;
}

/** Заголовки, добавляемые к каждому запросу. Токен — из session-модуля. */
export type HeaderProvider = () => Record<string, string>;

const DEFAULT_TIMEOUT_MS = 20_000;
/** LLM-запросы отвечают дольше: server-side workflow timeout — 90с (app/config.py). */
export const LLM_TIMEOUT_MS = 95_000;

let headerProvider: HeaderProvider = () => ({});

/** Регистрируется один раз при инициализации API-слоя (см. configureApi). */
export function setHeaderProvider(provider: HeaderProvider): void {
  headerProvider = provider;
}

function buildHeaders(options: RequestOptions): Record<string, string> {
  const headers: Record<string, string> = { ...headerProvider() };
  for (const [key, value] of Object.entries(options.headers ?? {})) {
    headers[key] = value;
  }
  if (options.body !== undefined && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  return headers;
}

/** Достаёт человекочитаемое сообщение и код из тела ошибки сервера. */
function parseErrorBody(status: number, raw: string): ApiDomainError {
  let code = `http_${status}`;
  let message = '';
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed === 'object' && parsed !== null && 'detail' in parsed) {
      const detail = (parsed as { detail: unknown }).detail;
      if (typeof detail === 'string') {
        message = detail;
      } else if (typeof detail === 'object' && detail !== null) {
        const obj = detail as { code?: unknown; message?: unknown };
        if (typeof obj.code === 'string') code = obj.code;
        if (typeof obj.message === 'string') message = obj.message;
      }
    } else {
      message = raw.slice(0, 300);
    }
  } catch {
    message = raw.slice(0, 300);
  }
  return new ApiDomainError(status, code, message);
}

/** Объединяет внешний AbortSignal с внутренним таймаутом. */
function withTimeout(signal: AbortSignal | undefined, timeoutMs: number): {
  signal: AbortSignal;
  cleanup: () => void;
} {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new ApiTransportError('timeout')), timeoutMs);
  const onAbort = () => controller.abort(signal?.reason);
  if (signal) {
    if (signal.aborted) controller.abort(signal.reason);
    else signal.addEventListener('abort', onAbort, { once: true });
  }
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    },
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

/** Базовый запрос. Возвращает распарсенный JSON или бросает типизированную ошибку. */
export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const body = options.body === undefined ? null : JSON.stringify(options.body);
  const { signal, cleanup } = withTimeout(options.signal, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      method,
      headers: buildHeaders(options),
      body,
      signal,
    });
    const raw = await response.text();
    if (!response.ok) {
      throw parseErrorBody(response.status, raw);
    }
    if (!raw) {
      return undefined as T;
    }
    try {
      return JSON.parse(raw) as T;
    } catch (cause) {
      // HTML вместо JSON — обычно прокси или SPA-fallback вместо endpoint'а.
      throw new ApiTransportError('response is not JSON', { cause });
    }
  } catch (error) {
    if (error instanceof ApiDomainError || error instanceof ApiTransportError) throw error;
    if (isAbortError(error)) throw error;
    // Сеть недоступна, DNS, CORS — всё это транспорт.
    throw new ApiTransportError('network error', { cause: error });
  } finally {
    cleanup();
  }
}

/** Запрос бинарного содержимого (картинки-шеринги). */
export async function requestBlob(path: string, options: RequestOptions = {}): Promise<Blob> {
  const { signal, cleanup } = withTimeout(options.signal, options.timeoutMs ?? DEFAULT_TIMEOUT_MS);
  try {
    const response = await fetch(path, {
      method: options.method ?? 'GET',
      headers: buildHeaders(options),
      signal,
    });
    if (!response.ok) {
      const raw = await response.text().catch(() => '');
      throw parseErrorBody(response.status, raw);
    }
    return await response.blob();
  } catch (error) {
    if (error instanceof ApiDomainError || error instanceof ApiTransportError) throw error;
    if (isAbortError(error)) throw error;
    throw new ApiTransportError('network error', { cause: error });
  } finally {
    cleanup();
  }
}

export { isAbortError };
