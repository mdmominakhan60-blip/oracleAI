#!/usr/bin/env node
/* BUS-509 e2e smoke: R-8 chat viewport (mock API, без бэкенда).
 * 1) nav-hidden: .app-nav и .app-header скрыты в чате, возвращаются после back → главная.
 * 2) heads-hidden: скролл вниз коллапсирует .chat-head (max-height:0), вверх — возвращает;
 *    reduced-motion — transition нет (статично), но переключение работает.
 * 3) intro collapse: при малой stable-высоте viewport intro-карточка — одна
 *    строка kicker (persona/next скрыты).
 * 4) --tg-viewport-stable-height: выставляется из viewportChanged(isStateStable),
 *    #app-root.height его использует; viewportChanged без isStateStable
 *    значение НЕ меняет. Композер остаётся в layout при малой высоте.
 * 5) Тело чата ≥60% высоты на 375x667 с 3+ сообщениями (в покое и при скрытых шапках).
 * Запуск: node scripts/qa_bus509_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18099';
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus509');
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
await new Promise((r) => server.listen(18099, '127.0.0.1', r));

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const ME = JSON.stringify({ id: 1, name: 'Тест Тестов', lang: 'ru', flags: {}, birth_date: '1990-05-05', chart_mode: 'manual' });
const AGENTS = JSON.stringify([
  { code: 'oracle', name: 'Лилит', title: 'Личный Оракул', role: 'Оракул', greeting: 'Привет! Я Лилит.', suggestions: ['a', 'b', 'c'], capabilities: [], avatar: '' },
  { code: 'astro', name: 'Урания', title: 'Астролог', role: 'Астролог', greeting: 'Привет! Я Урания.', suggestions: ['a', 'b', 'c'], capabilities: [], avatar: '' },
  { code: 'tarot', name: 'Мадам Ленорман', title: 'Таролог', role: 'Таролог', greeting: 'Привет!', suggestions: ['a', 'b', 'c'], capabilities: [], avatar: '' },
  { code: 'chiromant', name: 'Мира', title: 'Хиромант', role: 'Хиромант', greeting: 'Привет!', suggestions: ['a', 'b', 'c'], capabilities: [], avatar: '' },
]);

/* Длинная лента: в покое и при скрытых шапках контент переполняет скроллер,
 * чтобы программный скролл реально двигал scrollTop. */
const LONG = 'Длинное сообщение для проверки скролла, текст занимает несколько строк на мобильной ширине. '.repeat(6);
const CHAT_3PLUS = JSON.stringify({
  thread_id: 't1',
  agent: JSON.parse(AGENTS)[0],
  messages: [
    { role: 'assistant', text: 'Привет! Я Лилит. Расскажи, что у тебя на душе — вместе найдём опору.' },
    { role: 'user', text: 'Мне тревожно из-за работы, дедлайны давят, не могу сосредоточиться уже вторую неделю' },
    { role: 'assistant', text: 'Слышу тебя. Давай разберём, что именно вызывает тревогу: неопределённость, нагрузка или отношения с людьми.' },
    { role: 'user', text: LONG },
    { role: 'assistant', text: LONG },
    { role: 'user', text: LONG },
    { role: 'assistant', text: LONG },
  ],
});

/* Мок Telegram WebApp: expand() уже вызывается в boot; onEvent('viewportChanged')
 * копит подписчиков, что даёт начальное значение viewportStableHeight=667. */
const TG_MOCK = () => {
  const handlers = {};
  let stableH = 667;
  window.Telegram = {
    WebApp: {
      ready: () => {}, expand: () => {}, setHeaderColor: () => {},
      viewportStableHeight: stableH, viewportHeight: stableH,
      initDataUnsafe: {}, initData: '', colorScheme: 'dark',
      onEvent: (name, fn) => { (handlers[name] = handlers[name] || []).push(fn); },
      offEvent: () => {},
      emitViewport: (px, isStateStable) => {
        window.Telegram.WebApp.viewportHeight = px;
        if (isStateStable) { stableH = px; window.Telegram.WebApp.viewportStableHeight = px; }
        (handlers.viewportChanged || []).forEach((fn) => fn({ isStateStable }));
      },
    },
  };
};

async function freshPage({ viewport, reducedMotion = false }) {
  const context = await browser.newContext({
    viewport, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark',
    reducedMotion: reducedMotion ? 'reduce' : 'no-preference',
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  /* Настоящий telegram-web-app.js перезаписал бы TG_MOCK из addInitScript —
   * блокируем его, в смоуке работает мок. */
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/profile')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }); return; }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: AGENTS }); return; }
    if (url.includes('/api/chat/oracle')) { await route.fulfill({ status: 200, contentType: 'application/json', body: CHAT_3PLUS }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', 'ru');
    localStorage.setItem('oracle_intro_seen', '1');
    localStorage.setItem('oracle_chat_guide_v2', '1');
  });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);
  return { context, page, errors };
}

const stateOf = (page) => page.evaluate(() => {
  const q = (sel) => document.querySelector(sel);
  return {
    navHidden: document.getElementById('app-root').classList.contains('nav-hidden'),
    headsHidden: document.getElementById('app-root').classList.contains('heads-hidden'),
    chatLive: document.getElementById('app-root').classList.contains('chat-live'),
    navDisplay: q('.app-nav') ? getComputedStyle(q('.app-nav')).display : 'absent',
    headerDisplay: q('.app-header') ? getComputedStyle(q('.app-header')).display : 'absent',
    chatHeadH: q('.chat-head') ? Math.round(q('.chat-head').getBoundingClientRect().height) : -1,
    stableVar: document.getElementById('app-root').style.getPropertyValue('--tg-viewport-stable-height'),
    rootHeight: getComputedStyle(document.getElementById('app-root')).height,
    bodyShare: q('.chat-messages') ? q('.chat-messages').getBoundingClientRect().height / window.innerHeight : 0,
  };
});

/* ——— Сценарий 1+5: чат на 375x667, nav+header скрыты, тело чата ≥60% ——— */
{
  const { context, page, errors } = await freshPage({ viewport: { width: 375, height: 667 } });
  await page.evaluate(() => app.openChat('oracle'));
  await page.waitForTimeout(600);
  let s = await stateOf(page);
  ok('1/667 nav-hidden в чате: класс стоит', s.navHidden, `navDisplay=${s.navDisplay}`);
  ok('1/667 .app-nav скрыт (display:none)', s.navDisplay === 'none');
  ok('1/667 .app-header скрыт в чате (display:none)', s.headerDisplay === 'none');
  ok('5/667 тело чата ≥60% высоты экрана в покое', s.bodyShare >= 0.60, `share=${(s.bodyShare * 100).toFixed(1)}%`);
  await page.screenshot({ path: path.join(OUT, 'bus509-1-chat-open-667.png') });

  /* Скролл вниз по ленте — шапка чата коллапсирует.
   * ВАЖНО: openChat самоскроллит ленту к последнему сообщению — стартуем
   * от текущей позиции и идём только вниз, иначе тест мерит «вверх».
   * Первичный сдвиг вверх «будит» детектор: без него lastY уже у нижнего
   * края и скролл вниз не даёт дельты. */
  const scroller = page.locator('.chat-messages');
  await scroller.evaluate((el) => { el.scrollTop = Math.max(0, el.scrollTop - 40); el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(600);
  await scroller.evaluate((el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(700);
  s = await stateOf(page);
  ok('2/667 скролл вниз прячет шапку чата (heads-hidden)', s.headsHidden, `chatHeadH=${s.chatHeadH}px`);
  ok('5/667 со скрытой шапкой тело чата ≥70%', s.bodyShare >= 0.70, `share=${(s.bodyShare * 100).toFixed(1)}%`);
  await page.screenshot({ path: path.join(OUT, 'bus509-2-heads-hidden-scroll.png') });

  /* Скролл вверх — шапка возвращается */
  await scroller.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(500);
  s = await stateOf(page);
  ok('2/667 скролл вверх возвращает шапку', !s.headsHidden, `chatHeadH=${s.chatHeadH}px`);

  /* Back → главная: nav и header возвращаются, классы сняты */
  await page.evaluate(() => app.closeChat());
  await page.waitForTimeout(300);
  s = await stateOf(page);
  ok('1/667 после back nav-hidden снят', !s.navHidden, `navDisplay=${s.navDisplay}`);
  ok('1/667 .app-nav виден на главной', s.navDisplay !== 'none' && s.navDisplay !== 'absent');
  ok('1/667 .app-header виден на главной', s.headerDisplay !== 'none' && s.headerDisplay !== 'absent');
  ok('3/667 heads-hidden снят при выходе из чата', !s.headsHidden);
  ok('3/667 chat-live снят при выходе из чата', !s.chatLive);
  ok('1/667 консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий 2-RM: reduced-motion — переключение статичное, но живое ——— */
{
  const { context, page, errors } = await freshPage({ viewport: { width: 375, height: 667 }, reducedMotion: true });
  await page.evaluate(() => app.openChat('oracle'));
  await page.waitForTimeout(500);
  const transition = await page.evaluate(() => getComputedStyle(document.querySelector('.chat-head')).transitionDuration);
  ok('2/RM reduced-motion: transition отключён (0s)', transition === '0s' || parseFloat(transition) <= 0.001, `transition=${transition}`);
  const scroller = page.locator('.chat-messages');
  await scroller.evaluate((el) => { el.scrollTop = Math.max(0, el.scrollTop - 40); el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(600);
  await scroller.evaluate((el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(500);
  const s = await stateOf(page);
  ok('2/RM скролл вниз прячет шапку и в reduced-motion', s.headsHidden);
  /* Ждём выхода из окна подавления эха (400ms) — «вверх» после него */
  await scroller.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(400);
  const s2 = await stateOf(page);
  ok('2/RM скролл вверх возвращает шапку', !s2.headsHidden);
  ok('2/RM консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий 3+4: клавиатура — stable-высота, композер, intro-коллапс ——— */
{
  const { context, page, errors } = await freshPage({ viewport: { width: 375, height: 667 } });
  await page.evaluate(() => app.openChat('oracle'));
  await page.waitForTimeout(500);
  let s = await stateOf(page);
  ok('4/клавиатура стартовая --tg-viewport-stable-height=667px', s.stableVar === '667px', `var=${s.stableVar}`);

  /* Не-stable событие (анимация клавиатуры) — переменную менять нельзя */
  await page.evaluate(() => window.Telegram.WebApp.emitViewport(300, false));
  await page.waitForTimeout(200);
  s = await stateOf(page);
  ok('4/клавиатура viewportChanged без isStateStable НЕ меняет высоту', s.stableVar === '667px', `var=${s.stableVar}`);

  /* Клавиатура раскрылась и устоялась: 320px */
  await page.evaluate(() => window.Telegram.WebApp.emitViewport(320, true));
  await page.waitForTimeout(200);
  s = await stateOf(page);
  ok('4/клавиатура stable-событие ставит 320px', s.stableVar === '320px', `var=${s.stableVar}`);
  const composerVisible = await page.evaluate(() => {
    const c = document.querySelector('.composer');
    if (!c) return false;
    const r = c.getBoundingClientRect();
    return r.height > 10 && r.bottom <= window.innerHeight + 1;
  });
  ok('4/клавиатура композер виден при малой высоте (не вылезает за экран)', composerVisible);
  await page.screenshot({ path: path.join(OUT, 'bus509-4-keyboard-stable.png') });

  /* Клавиатура закрылась: 667 снова */
  await page.evaluate(() => window.Telegram.WebApp.emitViewport(667, true));
  await page.waitForTimeout(200);
  s = await stateOf(page);
  ok('4/клавиатура закрытие возвращает 667px', s.stableVar === '667px', `var=${s.stableVar}`);
  ok('4/клавиатура консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий 3: intro-коллапс на свежем чате (0 сообщений) при 320px ——— */
{
  const { context, page, errors } = await freshPage({ viewport: { width: 375, height: 667 } });
  /* Чат без истории — intro рендерится */
  await page.route('**/api/chat/oracle', async (route) => {
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ thread_id: null, agent: JSON.parse(AGENTS)[0], messages: [] }),
    });
  });
  await page.evaluate(() => {
    window.Telegram.WebApp.emitViewport(320, true);
  });
  await page.evaluate(() => { app.openChat('oracle'); });
  await page.waitForTimeout(700);
  const collapsed = await page.evaluate(() => {
    const intro = document.querySelector('.agent-intro');
    if (!intro) return null;
    return {
      cls: intro.classList.contains('agent-intro--collapsed'),
      persona: getComputedStyle(intro.querySelector('.ai-persona')).display,
      next: getComputedStyle(intro.querySelector('.ai-next')).display,
      kicker: getComputedStyle(intro.querySelector('.ai-kicker')).display,
      h: intro.getBoundingClientRect().height,
    };
  });
  ok('3/intro при 320px collapsed-класс стоит', collapsed && collapsed.cls, `h=${collapsed ? Math.round(collapsed.h) : '?'}px`);
  ok('3/intro persona скрыт', collapsed && collapsed.persona === 'none', `persona=${collapsed && collapsed.persona}`);
  ok('3/intro ai-next скрыт', collapsed && collapsed.next === 'none', `next=${collapsed && collapsed.next}`);
  ok('3/intro kicker виден (одна строка)', collapsed && collapsed.kicker !== 'none');
  ok('3/intro высота ≤ 40px', collapsed && collapsed.h <= 40, `h=${collapsed ? Math.round(collapsed.h) : '?'}px`);
  await page.screenshot({ path: path.join(OUT, 'bus509-3-intro-collapsed.png') });

  /* Клавиатура закрылась (667) — intro возвращается к полному виду */
  await page.evaluate(() => window.Telegram.WebApp.emitViewport(667, true));
  await page.waitForTimeout(300);
  const expanded = await page.evaluate(() => {
    const intro = document.querySelector('.agent-intro');
    return intro ? { cls: intro.classList.contains('agent-intro--collapsed'), persona: getComputedStyle(intro.querySelector('.ai-persona')).display } : null;
  });
  ok('3/intro при 667px возвращается полный вид', expanded && !expanded.cls && expanded.persona !== 'none', `persona=${expanded && expanded.persona}`);
  ok('3/intro консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Регресс: touch-таргеты back и шапка доступны после скрытия/возврата ——— */
{
  const { context, page, errors } = await freshPage({ viewport: { width: 375, height: 667 } });
  await page.evaluate(() => app.openChat('oracle'));
  await page.waitForTimeout(500);
  const scroller = page.locator('.chat-messages');
  await scroller.evaluate((el) => { el.scrollTop = Math.max(0, el.scrollTop - 40); el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(600);
  await scroller.evaluate((el) => { el.scrollTop = el.scrollHeight; el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(700);
  await scroller.evaluate((el) => { el.scrollTop = 0; el.dispatchEvent(new Event('scroll', { bubbles: false })); });
  await page.waitForTimeout(600);
  const backOk = await page.evaluate(() => {
    const b = document.querySelector('.chat-head .back');
    return !!b && b.getBoundingClientRect().height > 0;
  });
  ok('6/регресс back-кнопка видима после возврата шапки', backOk);
  /* Клик по back ведёт на главную (эмиттер data-act через открытую кнопку) */
  await page.click('.chat-head .back');
  await page.waitForTimeout(400);
  const onHome = await page.evaluate(() => !document.getElementById('app-root').classList.contains('nav-hidden'));
  ok('6/регресс back ведёт на главную (nav возвращён)', onHome);
  ok('6/регресс консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

await browser.close();
server.close();
const failed = results.filter((r) => !r.pass).length;
console.log(`\nИтого: ${results.length - failed}/${results.length} PASS`);
console.log(`Скриншоты: ${OUT}`);
process.exit(failed ? 1 : 0);
