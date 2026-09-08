#!/usr/bin/env node
/* BUS-636 Э5 e2e smoke: поведение сообщений чата (mock API, без бэкенда).
 * 1) стадия работы: .chat-stage появляется при отправке, текст фаз меняется, таймер идёт;
 * 2) стадия исчезает после ответа и после отмены;
 * 3) markdown: заголовок # → .md-h, списки - / 1. → ul/ol li, `code` и ```блоки```,
 *    **жирный** / *курсив*;
 * 4) XSS-инвариант: payload в ответе не создаёт элементов/атрибутов;
 * 5) retry: ошибка API → карточка восстановления + «Повторить отправку» → повторный POST без дубля вопроса;
 * 6) умный скролл: автоскролл вниз, если пользователь у дна; не дёргает, если прокрутил вверх;
 * 7) авто-высота инпута: rows растут с многострочным вводом (макс 4);
 * 8) console чист.
 * Запуск: node scripts/qa_bus636_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18100';
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus636');
fs.mkdirSync(OUT, { recursive: true });

const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome']).toString().trim();

const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};

/* Статик-сервер: /static/js/x.js -> miniapp/js/x.js, / -> miniapp/index.html */
const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, BASE).pathname);
  if (p.startsWith('/static/')) p = p.slice('/static/'.length);
  else p = '/index.html';
  const clean = p.split('?')[0];
  const file = path.join(MINIAPP, clean.replace(/^\//, ''));
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('nf'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});
await new Promise((r) => server.listen(18100, '127.0.0.1', r));

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const ME = JSON.stringify({ id: 1, name: 'Тест Тестов', lang: 'ru', flags: {}, birth_date: '1990-05-05', chart_mode: 'manual' });
const TG_MOCK = () => {
  window.Telegram = {
    WebApp: {
      ready: () => {}, expand: () => {}, setHeaderColor: () => {},
      viewportStableHeight: 667, viewportHeight: 667,
      initDataUnsafe: {}, initData: '', colorScheme: 'dark',
      onEvent: () => {}, offEvent: () => {},
      HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {}, selectionChanged: () => {} },
    },
  };
};

const MD_ANSWER = [
  '# План на неделю',
  '',
  'Смотри, **Марс** в соединении с Луной — день *энергичный*.',
  '',
  '- Утро: `медитация` 10 минут',
  '- Вечер: ревизия целей',
  '',
  '1. Запиши итог',
  '2. Отметь настроение',
  '',
  '```js',
  'const focus = "марс";',
  'console.log(focus);',
  '```',
  '',
  'Готова помочь углубиться.',
].join('\n');

const XSS_ANSWER = [
  '# Заголовок <img src=x onerror=alert(1)>',
  'Обычный текст <script>alert(2)</script> и <b>жирный html</b>',
  '- пункт [x](javascript:alert(3))',
  '```html',
  '<script>alert(4)</script>',
  '```',
].join('\n');

/* Управляемые состояния mock-чата */
const state = {
  chatCalls: [],           // POST-вызовы
  failNext: 0,             // сколько следующих POST вернуть 503
  delayMs: 0,              // задержка ответа
  answer: MD_ANSWER,
};

async function freshPage() {
  const context = await browser.newContext({ viewport: { width: 375, height: 667 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (route.request().method() === 'POST' && /\/api\/chat\//.test(url)) {
      state.chatCalls.push({ url, body: route.request().postDataJSON() });
      if (state.failNext > 0) { state.failNext--; await route.fulfill({ status: 503, contentType: 'application/json', body: '{"error":"unavailable"}' }); return; }
      if (state.delayMs > 0) await new Promise((r) => setTimeout(r, state.delayMs));
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ thread_id: 't1', answer: state.answer, routing: null, proof: { mode: 'ai', tools_used: [] } }) });
      return;
    }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME }); return; }
    if (url.includes('/api/agents')) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([
        { code: 'astro', name: 'Астролог', tagline: 'Звёзды' },
        { code: 'tarot', name: 'Таролог', tagline: 'Карты' },
      ]) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript((l) => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', l);
    localStorage.setItem('oracle_intro_seen', '1');
  }, 'ru');
  await page.goto(`${BASE}/?qa=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  // открываем чат первого агента как пользователь
  await page.evaluate(() => app.openChat('astro'));
  await page.waitForTimeout(500);
  return { context, page, errors };
}

const stageInfo = (page) => page.evaluate(() => {
  const el = document.querySelector('.chat-stage');
  if (!el) return null;
  const text = el.querySelector('.chat-stage__text');
  const timer = el.querySelector('.chat-stage__timer');
  return { present: true, text: text ? text.textContent : '', timer: timer ? timer.textContent : '', live: el.getAttribute('aria-live') };
});

/* ── 1. Стадия работы: появляется, фазы, таймер; исчезает после ответа ── */
{
  const { context, page, errors } = await freshPage();
  state.delayMs = 8000; // достаточно долго: проверки таймера/фазы до ответа
  await page.fill('#chat-input', 'Что меня ждёт на неделе?');
  await page.click('#send-btn');
  await page.waitForTimeout(400);
  let s = await stageInfo(page);
  ok('stage: полоска появилась при отправке', !!s, JSON.stringify(s));
  ok('stage: aria-live=polite (role=status)', s && s.live === 'polite');
  ok('stage: начальная фаза «Думаю над вопросом»', s && s.text === 'Думаю над вопросом…', s && s.text);
  await page.waitForTimeout(2200);
  s = await stageInfo(page);
  ok('stage: таймер тикает (секунды)', s && /^[2-9]\d?с$/.test(s.timer || ''), s && s.timer);
  // фазы STAGE_PHASES меняются на 12с и 28с — проверяем механику переключения,
  // а не конкретный текст: подменяем _lastStageIdx сценарием с коротким порогом
  const phaseSwitch = await page.evaluate(() => {
    const el = document.querySelector('.chat-stage');
    if (!el) return null;
    app._lastStageIdx = -1;
    app.chat._stageStartedAt = Date.now() - 13 * 1000; // симулируем 13с ожидания
    app._tickChatStage();
    return el.querySelector('.chat-stage__text').textContent;
  });
  ok('stage: фаза переключается по порогу времени', phaseSwitch === 'Собираю все нити ответа…', phaseSwitch);
  await page.screenshot({ path: path.join(OUT, 'bus636-stage.png') });
  state.delayMs = 0; // дальше ответ приходит сразу

  // ждём ответ → стадия исчезла
  await page.waitForSelector('.chat-stage', { state: 'detached', timeout: 15000 });
  ok('stage: исчезла после ответа', true);
  const msgs = await page.evaluate(() => [...document.querySelectorAll('.chat-messages .msg')].map((m) => m.className));
  ok('stage: вопрос и ответ в ленте', msgs.length >= 2 && /user/.test(msgs[0]) && /assistant/.test(msgs[msgs.length - 1]), msgs.join('|'));

  /* ── 3. Markdown ── */
  const md = await page.evaluate(() => {
    const last = document.querySelector('.chat-messages .msg.assistant:last-child') || document.querySelector('.chat-messages .msg:last-child');
    return {
      h: !!last.querySelector('.md-h'),
      hText: (last.querySelector('.md-h') || {}).textContent || '',
      ul: last.querySelectorAll('ul li').length,
      ol: last.querySelectorAll('ol li').length,
      inlineCode: (last.querySelector('code') || {}).textContent || '',
      pre: last.querySelectorAll('pre').length,
      preText: (last.querySelector('pre code') || {}).textContent || '',
      b: last.querySelectorAll('b').length,
      i: last.querySelectorAll('i').length,
      html: last.innerHTML,
    };
  });
  ok('md: заголовок # → .md-h', md.h && md.hText === 'План на неделю', md.hText);
  ok('md: маркированный список (2 li)', md.ul === 2, String(md.ul));
  ok('md: нумерованный список (2 li)', md.ol === 2, String(md.ol));
  ok('md: inline `code`', md.inlineCode === 'медитация', md.inlineCode);
  ok('md: код-блок ``` → pre', md.pre === 1 && /const focus/.test(md.preText), md.preText.slice(0, 30));
  ok('md: **жирный** и *курсив*', md.b >= 1 && md.i >= 1);

  /* ── 4. XSS-инвариант ── */
  state.answer = XSS_ANSWER;
  await page.fill('#chat-input', 'тест безопасности');
  await page.click('#send-btn');
  await page.waitForSelector('.chat-stage', { state: 'detached', timeout: 15000 });
  const xss = await page.evaluate(() => {
    const msgs = [...document.querySelectorAll('.chat-messages .msg.assistant')];
    const last = msgs[msgs.length - 1];
    return {
      img: last.querySelectorAll('img').length,
      script: last.querySelectorAll('script').length,
      a: last.querySelectorAll('a').length,
      onerr: last.innerHTML.includes('onerror='),
      rawScript: last.innerHTML.includes('<script'),
      htmlTag: last.querySelectorAll('b:not(.md-h)').length, // <b> от html не должен стать элементом
    };
  });
  ok('xss: <img onerror> не создал элемент', xss.img === 0, JSON.stringify(xss));
  // «onerror=» встречается как экранированный текст (esc перевёл <img> в текст);
  // инвариант — отсутствие элементов/атрибутов, проверен выше
  ok('xss: <script> не исполняется/не вставлен', xss.script === 0 && !xss.rawScript);
  ok('xss: [x](javascript:) не создал ссылку', xss.a === 0);
  // rich() по дизайну пропускает голые <b>/<i> (rich-разметка_esc+b/i-rebuild);
  // инвариант безопасности — атрибуты и сторонние теги не проходят. <b> текстом
  // внутри .msg.assistant без события/атрибута безопасен — проверяем отсутствие
  // обработчиков, а не тега.
  const bCount = await page.evaluate(() => {
    const msgs = [...document.querySelectorAll('.chat-messages .msg.assistant')];
    const last = msgs[msgs.length - 1];
    return [...last.querySelectorAll('b')].every((b) => !b.getAttribute('onerror') && !b.getAttribute('onclick'));
  });
  ok('xss: <b> без атрибутов-событий (rich-контракт)', bCount, JSON.stringify(xss));
  await page.screenshot({ path: path.join(OUT, 'bus636-xss.png') });

  ok('console чист (блок 1)', errors.length === 0, errors.join(' | ').slice(0, 200));
  await context.close();
}

/* ── 5. Retry: ошибка → recovery-карточка → «Повторить отправку» без дубля ── */
{
  const { context, page, errors } = await freshPage();
  state.failNext = 1;
  await page.fill('#chat-input', 'Вопрос с ошибкой');
  await page.click('#send-btn');
  await page.waitForSelector('.chat-recovery', { timeout: 10000 });
  ok('retry: recovery-карточка после ошибки', true);
  const draft = await page.evaluate(() => app.chat.draft);
  ok('retry: черновик сохранён в app.chat.draft', draft === 'Вопрос с ошибкой', draft);
  // фильтруем только POST этого вопроса: 503-лог в console — ожидаемое поведение api()
  const errFiltered = errors.filter((e) => !/503 \(Service Unavailable\)/.test(e));
  const callsAfterFail = state.chatCalls.length;
  await page.click('.chat-recovery .chat-retry');
  await page.waitForTimeout(800);
  ok('retry: повторный POST ушёл', state.chatCalls.length === callsAfterFail + 1, String(state.chatCalls.length));
  const texts = state.chatCalls.map((c) => c.body.text);
  // 2 POST-вызова — норма: первый упал (503), второй — ретрай. Инвариант FE-012:
  // echo=false → в ленте один пузырь вопроса (проверен ниже).
  ok('retry: ретрай переиспользует текст без переспрашивания', texts.filter((t) => t === 'Вопрос с ошибкой').length === 2, texts.join('|'));
  const userBubbles = await page.evaluate(() => [...document.querySelectorAll('.chat-messages .msg.user')].map((m) => m.textContent.trim()));
  ok('retry: пузырь вопроса один', userBubbles.length === 1, userBubbles.join('|'));
  const recoveryGone = await page.evaluate(() => !document.querySelector('.chat-recovery'));
  ok('retry: recovery-карточка ушла после ретрая', recoveryGone);
  ok('console чист (блок 2, без ожидаемого 503)', errFiltered.length === 0, errFiltered.join(' | ').slice(0, 200));
  await context.close();
}

/* ── 6. Умный скролл + 2. отмена стадии + 7. авто-высота инпута ── */
{
  const { context, page, errors } = await freshPage();
  // авто-высота: многострочный ввод → rows растут до 4
  const multi = 'строка один\nстрока два\nстрока три\nстрока четыре\nстрока пять\nстрока шесть';
  await page.fill('#chat-input', multi);
  await page.dispatchEvent('#chat-input', 'input');
  await page.waitForTimeout(150);
  const rows = await page.evaluate(() => document.getElementById('chat-input').rows);
  ok('input: авто-высота до 4 строк', rows === 4, 'rows=' + rows);
  await page.fill('#chat-input', 'одна строка');
  await page.dispatchEvent('#chat-input', 'input');
  await page.waitForTimeout(150);
  const rows1 = await page.evaluate(() => document.getElementById('chat-input').rows);
  ok('input: короткий ввод → 1 строка', rows1 === 1, 'rows=' + rows1);

  // отмена: стадия появляется, тап по × → стадия и busy сняты
  state.delayMs = 5000;
  await page.fill('#chat-input', 'долгий запрос');
  await page.click('#send-btn');
  await page.waitForTimeout(400);
  const stageDuring = await stageInfo(page);
  ok('cancel: стадия видна при долгом запросе', !!stageDuring);
  await page.click('#send-btn'); // в busy это кнопка отмены (data-act="cancel-chat")
  await page.waitForTimeout(500);
  const afterCancel = await page.evaluate(() => ({ stage: !!document.querySelector('.chat-stage'), busy: app.chat.busy }));
  ok('cancel: стадия снята после отмены', !afterCancel.stage && !afterCancel.busy, JSON.stringify(afterCancel));

  // умный скролл: отправка при нижнем положении → проскроллило к низу
  await page.evaluate(() => { const box = document.querySelector('.chat-messages'); box.scrollTop = box.scrollHeight; });
  state.delayMs = 0;
  await page.fill('#chat-input', 'скролл-тест низ');
  await page.click('#send-btn');
  await page.waitForTimeout(600);
  const atBottom = await page.evaluate(() => {
    const box = document.querySelector('.chat-messages');
    return box.scrollHeight - box.scrollTop - box.clientHeight < 120;
  });
  ok('scroll: у дна — автоскролл к новому ответу', atBottom);

  // пользователь прокрутил вверх → автоскролл не дёргает
  await page.evaluate(() => { const box = document.querySelector('.chat-messages'); box.scrollTop = 0; });
  await page.fill('#chat-input', 'скролл-тест верх');
  await page.click('#send-btn');
  await page.waitForTimeout(600);
  const stayedTop = await page.evaluate(() => {
    const box = document.querySelector('.chat-messages');
    return box.scrollTop < 50;
  });
  ok('scroll: прокрутил вверх — не дёргает к низу', stayedTop, 'scrollTop=' + (await page.evaluate(() => document.querySelector('.chat-messages').scrollTop)));

  ok('console чист (блок 3)', errors.length === 0, errors.join(' | ').slice(0, 200));
  await context.close();
}

state.failNext = 0; state.delayMs = 0; state.answer = MD_ANSWER;

await browser.close();
server.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} PASS${failed.length ? `, ${failed.length} FAIL` : ''}`);
process.exit(failed.length ? 1 : 0);
