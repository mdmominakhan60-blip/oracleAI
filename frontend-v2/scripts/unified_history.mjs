/**
 * Регрессионный тест сценария истории единого Oracle (этап 2.5).
 *
 * Проверяемый сценарий (из задания):
 *   1. Пользователь отправляет обычный вопрос.
 *   2. Пользователь задаёт вопрос, маршрутизированный в Таро или астрологию.
 *   3. Получает ответ.
 *   4. Перезагружает страницу.
 *   5. Возвращается в Oracle и просматривает историю.
 *
 * Фактическое поведение backend (установлено разведкой и проверено здесь):
 *   каждый домен пишет в СВОЙ тред (`oracle` / `tarot` / `astro` / `chiromant`,
 *   app/services/chat.py ensure_thread по коду агента). Поэтому
 *   `GET /api/chat/oracle` отдаёт только тред `oracle`, и без сборки с
 *   нескольких доменов хронология теряет ответы Таро/астрологии.
 *
 * Тест доказывает, что единая хронология ВОССТАНАВЛИВАЕТСЯ без изменений
 * backend — через sessions каждого домена и слияние по created_at.
 * Никаких фиктивных сообщений: каждый тред реальный.
 *
 * Требует backend (API_TARGET) и dev-сервер не нужен.
 */
import { spawnSync } from 'node:child_process';

const TARGET = process.env.API_TARGET ?? 'http://172.29.0.2:8080';
const TG_ID = Number(process.env.TG_ID ?? 10002);

let failures = 0;
const check = (ok, label, extra = '') => {
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${extra ? ' — ' + extra : ''}`);
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function initData() {
  const out = spawnSync('python3', ['scripts/make_init_data.py', String(TG_ID)], { encoding: 'utf8' });
  if (out.status !== 0) throw new Error(`make_init_data failed: ${out.stderr}`);
  return out.stdout.trim();
}

async function mint() {
  for (let i = 1; i <= 6; i += 1) {
    const res = await fetch(`${TARGET}/api/auth/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: initData() }),
    });
    if (res.status === 200) {
      const body = await res.json();
      check(typeof body.session_token === 'string', 'сессия выдана');
      return body.session_token;
    }
    if (res.status === 429) {
      const wait = Number(res.headers.get('Retry-After') ?? 12);
      console.log(`     rate-limit минта, жду ${wait}с…`);
      await sleep((wait + 1) * 1000);
      continue;
    }
    check(false, 'сессия выдана', `status=${res.status}`);
    process.exit(1);
  }
  check(false, 'сессия выдана', 'rate-limit не отпустил');
  process.exit(1);
}

async function main() {
  const token = await mint();
  const headers = { 'X-Session-Token': token, 'Content-Type': 'application/json' };
  const post = async (text) => {
    const res = await fetch(`${TARGET}/api/chat/oracle`, {
      method: 'POST',
      headers: { ...headers, 'X-Idempotency-Key': `hist-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` },
      body: JSON.stringify({ text }),
    });
    return { status: res.status, body: res.status === 200 ? await res.json() : await res.json().catch(() => ({})) };
  };
  const get = async (path) => {
    const res = await fetch(`${TARGET}${path}`, { headers });
    return { status: res.status, body: res.status === 200 ? await res.json() : null };
  };

  // ── Шаг 1: обычный вопрос ────────────────────────────────────────────────
  const plain = await post('мне тревожно, помоги разобраться');
  const quota = plain.status === 429;
  if (quota) {
    console.log('     дневная квота исчерпана — проверяем историю на уже сохранённых тредах');
  } else {
    check(plain.status === 200, 'обычный вопрос → 200', `agent=${plain.body?.agent}`);
  }

  // ── Шаг 2: вопрос в другой домен ─────────────────────────────────────────
  if (!quota) {
    const tarot = await post('вытяни карты про мою работу');
    if (tarot.status === 200) {
      check(tarot.body?.routing?.agent === 'tarot', 'вопрос про карты маршрутизирован в tarot', tarot.body?.routing?.agent);
    } else {
      console.log(`     таро-вопрос: status=${tarot.status} (квота?) — продолжаем`);
    }
  }

  // ── Шаг 4 (эмуляция перезагрузки страницы) ─────────────────────────────
  // Токен stateless (HMAC), поэтому перезагрузка страницы читает историю тем же
  // заголовком. Повторное чтение «с нуля» доказывает, что enrichment
  // происходит из серверного состояния, а НЕ из памяти вкладки: если бы лента
  // жила в React-state, после reload она была бы пустой.
  const h2 = { 'X-Session-Token': token, 'Content-Type': 'application/json' };
  const get2 = async (path) => {
    const res = await fetch(`${TARGET}${path}`, { headers: h2 });
    return res.status === 200 ? await res.json() : null;
  };

  // ── Шаг 5: единая история после «перезагрузки» ───────────────────────────
  const AGENTS = ['oracle', 'astro', 'tarot', 'chiromant'];
  const messages = [];
  const missing = [];
  const oracleOnly = [];

  for (const agent of AGENTS) {
    try {
      const sessions = await get2(`/api/chat/${agent}/sessions`);
      for (const session of sessions ?? []) {
        if (session.archived) continue;
        const thread = await get2(`/api/chat/${agent}/sessions/${session.id}`);
        for (const m of thread?.messages ?? []) {
          messages.push({ ...m, agent, thread_id: session.id });
          if (agent === 'oracle') oracleOnly.push(m);
        }
      }
    } catch {
      missing.push(agent);
    }
  }

  check(messages.length > oracleOnly.length,
    'единая история содержит ответы других доменов (не только oracle)',
    `объединённая=${messages.length}, oracle-only=${oracleOnly.length}`);

  messages.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id);
  const sorted = messages.every((m, i) => i === 0 || messages[i - 1].created_at <= m.created_at);
  check(sorted, 'хронология монотонна по created_at');

  const domains = [...new Set(messages.map((m) => m.agent))];
  check(domains.length >= 1, 'домены в истории', domains.join(', '));

  // Все сообщения должны иметь непустой текст и роль — доказывает, что это
  // реальные ответы сервера, а не заглушки.
  const complete = messages.every((m) => typeof m.text === 'string' && m.text.length > 0 && (m.role === 'user' || m.role === 'assistant'));
  check(complete, 'каждое сообщение — реальная роль + непустой текст', `${messages.length} шт.`);

  // ── Шаг 6 (Stage 4.4): серверный эндпоинт GET /api/chat/history/unified ──
  // Проверяем, что сервер объединяет все домены за 1 запрос
  const serverUnified = await get2('/api/chat/history/unified?limit=100');
  check(
    serverUnified !== null && Array.isArray(serverUnified.messages),
    'серверный эндпоинт GET /api/chat/history/unified отвечает 200 с массивом сообщений',
  );
  if (serverUnified?.messages) {
    check(
      serverUnified.messages.length === messages.length,
      'серверная история содержит то же число сообщений, что и клиентская сборка',
      `сервер=${serverUnified.messages.length}, клиент=${messages.length}`,
    );
    const sDomains = [...new Set(serverUnified.messages.map((m) => m.agent))];
    check(
      sDomains.length >= 2,
      'серверная история объединяет несколько доменов',
      sDomains.join(', '),
    );
    const sSorted = serverUnified.messages.every((m, i) => i === 0 || serverUnified.messages[i - 1].created_at <= m.created_at);
    check(sSorted, 'хронология серверной истории детерминирована и монотонна');
    check(serverUnified.has_more === false, 'has_more корректен при полной выборке');

    // Проверка пагинации
    const paged = await get2('/api/chat/history/unified?limit=5');
    check(
      paged?.messages?.length === 5 && paged?.has_more === true,
      'keyset-пагинация: limit=5 возвращает 5 сообщений и has_more=true',
    );
    check(
      paged?.oldest_id !== null && paged?.oldest_created_at !== null,
      'курсор содержит и oldest_id, и oldest_created_at',
      `id=${paged?.oldest_id}, time=${paged?.oldest_created_at}`,
    );

    // Вторая страница по составному курсору (before_id + before_created_at)
    if (paged?.oldest_id && paged?.oldest_created_at) {
      const paged2 = await get2(
        `/api/chat/history/unified?limit=5&before_id=${paged.oldest_id}&before_created_at=${encodeURIComponent(paged.oldest_created_at)}`,
      );
      check(
        paged2?.messages?.length === 5,
        'keyset-пагинация: вторая страница по составному курсору возвращает 5 сообщений',
      );
      const overlap = paged.messages.some((m) => paged2?.messages?.some((m2) => m2.id === m.id));
      check(!overlap, 'keyset-пагинация: страницы 1 и 2 не имеют пересечений (без дублей)');
    }

    // Проверка контракта missing (аудит 4.4.1: единый SQL запрос, нет фиктивных ошибок)
    check(
      Array.isArray(serverUnified.missing) && serverUnified.missing.length === 0,
      'контракт missing: пустой массив при успешном атомарном запросе',
    );
  }

  // ── Документированный разрыв: GET /chat/oracle игнорирует ?thread_id ─────
  // Роут отвечает всегда тредом `oracle` (thread_history → thread_messages
  // без user-override параметра). Значит «получить тред по id» через этот
  // эндпоинт невозможно — и это причина, по которой лента собирается с
  // нескольких доменов. Проверяем и фиксируем как известное поведение.
  const direct = await get2('/api/chat/oracle');
  const astroThread = messages.find((m) => m.agent === 'astro')?.thread_id;
  if (direct && astroThread) {
    const withParam = await get2(`/api/chat/oracle?thread_id=${astroThread}`);
    const paramIgnored = JSON.stringify(withParam?.messages?.map((m) => m.id)) ===
                         JSON.stringify(direct.messages?.map((m) => m.id));
    check(paramIgnored,
      'GET /chat/oracle?thread_id игнорируется → известный разрыв контракта',
      'тред тот же; для чужого домена нужен /chat/{agent}/sessions/{id}');
  }

  console.log(failures ? `\n${failures} FAIL` : '\nистория Oracle восстанавливается');
  process.exit(failures ? 1 : 0);
}

main().catch((e) => {
  console.error('исключение:', e);
  process.exit(1);
});
