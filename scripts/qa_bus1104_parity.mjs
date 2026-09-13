#!/usr/bin/env node
/* BUS-1104 QA-гейт волны B: постраничная сверка miniapp против прототипа R06.
 * Для каждого вида: кадр прототипа (design/r06/pX/index.html#view-Y) и живой
 * qa-рендер миниаппы (?qa=1&qa_view=...) при 390x844, скриншот-пара + DOM-дамп
 * структурных селекторов. Артефакт: parity/…png + parity-report.json.
 * Запуск: node scripts/qa_bus1104_parity.mjs [p1|p2|p3|all]
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
/* Прототипы R06 влиты только в dev (BUS-734); QA-worktree стоит на master.
 * Миниаппа — из master-worktree (канон реализации), прототип — из dev-дерева. */
const PROTO = process.env.R06_PROTO_ROOT || path.join(ROOT, '..', 'design/r06');
const MINIAPP = path.join(ROOT, 'miniapp');
const OUT = path.join(process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus1104'), 'parity');
fs.mkdirSync(OUT, { recursive: true });

const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c',
  'command -v chromium || command -v chromium-browser || command -v google-chrome || ls ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1'
]).toString().trim();

/* Матрица покрытия: S-вид → кадр прототипа (pkg, view-id) ↔ qa_view миниаппы.
 * Источник: HANDOFF.md S01–S30 (25 слитых видов, без S14/S30). */
const MAP = [
  // p1
  { s: 'S03', title: 'Welcome/намерение', pkg: 'p1', proto: null, qa: 'welcome', spec: 'С §2.1' },
  { s: 'S04', title: 'Знакомство (онбординг)', pkg: 'p1', proto: 'view-onboarding', qa: 'onboarding' },
  { s: 'S05', title: 'Новый разговор', pkg: 'p1', proto: 'view-chat-empty', qa: 'home', spec: 'hub/чат-хаб' },
  { s: 'S06', title: 'Разговор (чат)', pkg: 'p1', proto: 'view-chat-dialog', qa: 'chat', spec: 'openChat' },
  { s: 'S06-st', title: 'Чат-состояния', pkg: 'p1', proto: 'view-chat-states', qa: 'chat-states', spec: 'скелетоны/ошибка/streaming' },
  { s: 'S07', title: 'История', pkg: 'p1', proto: 'view-sessions', qa: 'sessions' },
  { s: 'S10', title: 'Каталог инструментов', pkg: 'p1', proto: 'view-sheet-tools', qa: 'sheet' },
  // p2
  { s: 'S11a', title: 'Инструмент Быстрый', pkg: 'p2', proto: 'view-tool-quick', qa: 'tool-quick' },
  { s: 'S11b', title: 'Инструмент Форма', pkg: 'p2', proto: 'view-tool-form', qa: 'tool-form' },
  { s: 'S11c', title: 'Выполнение', pkg: 'p2', proto: 'view-tool-run', qa: 'tool-run' },
  { s: 'S12', title: 'Результат', pkg: 'p2', proto: 'view-result', qa: 'result' },
  { s: 'S13a', title: 'Таро: вопрос', pkg: 'p2', proto: 'view-tarot-question', qa: 'tarot-question' },
  { s: 'S13b', title: 'Таро: draw/reveal', pkg: 'p2', proto: 'view-tarot-reveal', qa: 'tarot-reveal' },
  { s: 'S13c', title: 'Таро: zoom', pkg: 'p2', proto: 'view-tarot-zoom', qa: 'tarot-zoom' },
  { s: 'S13d', title: 'Таро: разбор', pkg: 'p2', proto: 'view-tarot-reading', qa: 'tarot-reading' },
  // p3
  { s: 'S13x', title: 'Кельтский крест', pkg: 'p3', proto: 'view-tarot-grid', qa: 'tarot-cross' },
  { s: 'S15', title: 'Сегодня', pkg: 'p3', proto: 'view-today', qa: 'today' },
  { s: 'S20', title: 'Библиотека', pkg: 'p3', proto: 'view-library', qa: 'library' },
  { s: 'S21', title: 'Профиль', pkg: 'p3', proto: 'view-profile', qa: 'profile' },
  { s: 'S22', title: 'Память', pkg: 'p3', proto: 'view-memory', qa: 'memory-r06' },
  { s: 'S23', title: 'Уведомления/язык', pkg: 'p3', proto: 'view-notifications', qa: 'notifications-r06' },
  { s: 'S24', title: 'Тариф/paywall', pkg: 'p3', proto: 'view-plan', qa: 'plan-r06' },
  { s: 'S24b', title: 'Paywall', pkg: 'p3', proto: 'view-paywall', qa: 'paywall', extra: 'qa_paywall_src=library' },
  { s: 'S25', title: 'Оплата/ожидание', pkg: 'p3', proto: 'view-pay-pending', qa: 'pay-pending' },
  { s: 'S26', title: 'Заказы', pkg: 'p3', proto: 'view-orders', qa: 'orders-r06' },
  { s: 'S-states', title: 'Матрица состояний §11.2', pkg: 'p3', proto: 'view-states', qa: 'states' },
];

const filter = process.argv[2] || 'all';
const items = MAP.filter(m => filter === 'all' || m.pkg === filter);

/* --- два статик-сервера: прототип (по pkg) и миниаппа --- */
function serve(root, isProto) {
  const srv = http.createServer((req, res) => {
    let p = req.url.split('?')[0];
    if (p === '/' || p === '') p = '/index.html';
    if (isProto) {
      /* прототип: /p1/index.html → design/r06/p1/index.html */
      const m = p.match(/^\/(p[1234])(\/.*)$/);
      if (!m) { res.writeHead(404); res.end(); return; }
      p = m[1] + m[2];
    } else {
      if (p.startsWith('/static')) p = p.replace('/static', '');
    }
    const file = path.join(root, p);
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404); res.end(); return; }
      const ext = path.extname(file);
      const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff2': 'font/woff2' }[ext] || 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': mime });
      res.end(data);
    });
  });
  return srv;
}

const protoSrv = serve(PROTO, true);
const miniSrv = serve(MINIAPP, false);
let protoBase = '', miniBase = '';

/* mock API миниаппы: копия контракта из qa_bus1070_p3/p2 */
const TG_MOCK = `window.Telegram = { WebApp: {
  ready(){}, expand(){}, setHeaderColor(){}, initDataUnsafe: { user: { id: 1, first_name: 'QA', language_code: 'ru' } },
  HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
  BackButton: { show(){}, hide(){}, onClick(){}, offClick(){} },
  themeParams: {}, colorScheme: 'dark'
}};`;
const ME = () => JSON.stringify({ id: 'u1', name: 'QA', lang: 'ru', gender: 'f', premium: false,
  birth_date: '1994-03-14', birth_time: '10:00', birth_city: 'Москва', onboarded: true, balance: 120,
  flags: {}, morning_push: true, memory_on: true });
const AGENTS = () => JSON.stringify([
  { code: 'oracle', name: 'Лилит', title: 'Проводник', role: 'Проводник', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'astro', name: 'Урания', title: 'Звёзды', role: 'Астролог', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'tarot', name: 'Мадам Ленорман', title: 'Карты', role: 'Таролог', avatar: '/static/img/agents/oracle.jpg' }
]);
const HISTORY = () => JSON.stringify({ items: [
  { kind: 'report', entry_id: 101, title: 'Синастрия с Алексеем', created_at: '2026-09-10T10:00:00Z', preview: 'Ключевые аспекты пары.', source_kind: 'astro', action: { type: 'report', kind: 'astro', id: 101 }, deep_link: 'astro/report/101' },
  { kind: 'tarot', entry_id: 102, title: 'Расклад на месяц', created_at: '2026-09-09T18:30:00Z', preview: 'Три карты: прошлое, настоящее, будущее.', action: { type: 'reading', id: 102 }, deep_link: 'tarot/102' },
  { kind: 'chat', entry_id: 201, title: 'Чат с Уранией', created_at: '2026-09-08T09:00:00Z', preview: '', source_kind: 'astro', action: { type: 'chat', agent: 'astro', id: 201 }, deep_link: 'chat/astro/201' },
  { kind: 'chat', entry_id: 202, title: 'Чат с Ленорман', created_at: '2026-09-07T12:00:00Z', preview: '', source_kind: 'tarot', action: { type: 'chat', agent: 'tarot', id: 202 }, deep_link: 'chat/tarot/202' },
  { kind: 'diary', entry_id: 301, title: 'Diary entry', created_at: '2026-09-06T21:00:00Z', preview: '', action: { type: 'diary', id: 301 }, deep_link: 'diary/301' }
]});
const DIARY = () => JSON.stringify({ entries: [{ id: 1, text: 'Тестовая запись', mood: 'ok', created_at: '2026-09-06T21:00:00Z' }], streak: 3 });
const MEMORIES = () => JSON.stringify([
  { id: 11, fact: 'Работает в офисе на севере города', kind: 'user', weight: 1, last_used: null, created_at: '2026-09-01T10:00:00Z' },
  { id: 12, fact: 'Любит утренние прогулки', kind: 'user', weight: 1, last_used: null, created_at: '2026-09-02T10:00:00Z' }
]);
const PAYHIST = () => JSON.stringify([
  { id: 'o1', kind: 'subscription', sku: 'vip_month', title: 'VIP на месяц', amount_stars: 250, status: 'paid', provider: 'stars', created_at: '2026-09-05T10:00:00Z' },
  { id: 'o2', kind: 'crystals', sku: 'cr_500', title: '500 кристаллов', amount_stars: 100, status: 'pending', provider: 'crypto', created_at: '2026-09-11T10:00:00Z' },
  { id: 'o3', kind: 'subscription', sku: 'vip_plus_month', title: 'VIP+ на месяц', amount_stars: 400, status: 'refunded', provider: 'stars', created_at: '2026-09-04T10:00:00Z' },
  { id: 'o4', kind: 'crystals', sku: 'cr_100', title: '100 кристаллов', amount_stars: 25, status: 'failed', provider: 'crypto', created_at: '2026-09-03T10:00:00Z' }
]);
const TODAY = () => JSON.stringify({ forecast: 'День мягкого фокуса. Утро располагает к планированию, вечер — к отдыху. Луна в Рыбах усиливает интуицию: доверяй первым впечатлениям и не спеши с обещаниями.' });

async function mockRoute(route) {
  const url = route.request().url();
  const method = route.request().method();
  const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: typeof body === 'string' ? body : JSON.stringify(body) });
  if (url.includes('/api/memories')) { if (method === 'DELETE') return json({ ok: true }); return json(MEMORIES()); }
  if (url.endsWith('/api/me') || url.includes('/api/me?')) return json(ME());
  if (url.includes('/api/agents')) return json(AGENTS());
  if (url.includes('/api/today')) return json(TODAY());
  if (url.includes('/api/history')) return json(HISTORY());
  if (url.includes('/api/diary')) return json(DIARY());
  if (url.includes('/api/notifications/preferences')) return json({ morning_forecast: false });
  if (url.includes('/api/shop/payment-history')) return json(PAYHIST());
  if (url.includes('/api/shop/promo')) return json({ ok: true, code: 'STARS10' });
  return json({});
}

/* Структурный дамп активного view: классы-скелет DOM + текст заголовков/CTA. */
const DUMP_FN = () => {
  const active = document.querySelector('.screen-view.is-active') || document.querySelector('.view.is-active') || document.body;
  const pick = (sel, n = 4) => [...active.querySelectorAll(sel)].slice(0, n).map(el => el.className.toString().split(' ').filter(Boolean).slice(0, 3).join('.') || el.tagName.toLowerCase());
  const texts = [...active.querySelectorAll('h1,h2,h3,.screenheader__title,.section-head__title,.empty-state,button,.btn,summary')]
    .filter(el => el.offsetParent !== null || el.closest('[hidden]') === null)
    .slice(0, 12).map(el => (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 60)).filter(Boolean);
  return {
    viewId: active.id || '',
    hasSheet: !!active.querySelector('.sheet'),
    header: pick('.screenheader, .chat-header, .section-head'),
    cards: pick('.today-card, .agent-card, .history-card, .lib-row, .memory-row, .plan-card, .result__head, .tcard, .tarot-cross__cell'),
    forms: pick('input, select'),
    buttons: pick('button, .btn', 8),
    texts,
  };
};

async function run() {
  await new Promise(r => protoSrv.listen(18101, '127.0.0.1', r));
  await new Promise(r => miniSrv.listen(18102, '127.0.0.1', r));
  protoBase = `http://127.0.0.1:18101`;
  miniBase = `http://127.0.0.1:18102`;
  const browser = await chromium.launch({ executablePath: CHROME_PATH, args: ['--no-sandbox'] });

  const report = [];
  for (const m of items) {
    const entry = { ...m, protoDump: null, miniDump: null, notes: [] };
    /* --- прототип --- */
    if (m.proto) {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'dark' });
      const page = await ctx.newPage();
      await page.goto(`${protoBase}/${m.pkg}/index.html#${m.proto}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(250);
      entry.protoDump = await page.evaluate(DUMP_FN);
      await page.screenshot({ path: path.join(OUT, `${m.s}-proto.png`) });
      await ctx.close();
    } else {
      entry.notes.push('прототип-кадр отсутствует (С-вид): сверка по SPEC-требованиям');
    }
    /* --- миниаппа --- */
    {
      const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', colorScheme: 'dark', bypassCSP: true });
      const page = await ctx.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push('pageerror: ' + e.message));
      await page.route('**/telegram.org/**', r => r.abort());
      await page.route('**/api/**', mockRoute);
      await page.addInitScript(TG_MOCK);
      await page.addInitScript(() => {
        localStorage.clear();
        localStorage.setItem('oracle_lang', 'ru');
        localStorage.setItem('oracle_intro_seen', '1');
        localStorage.setItem('oracle_onboarding_done', '1');
      });
      const extra = m.extra ? '&' + m.extra : '';
      await page.goto(`${miniBase}/?qa=1&qa_view=${m.qa}${extra}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(350);
      entry.miniDump = await page.evaluate(DUMP_FN);
      entry.jsErrors = errors;
      await page.screenshot({ path: path.join(OUT, `${m.s}-mini.png`) });
      await ctx.close();
    }
    report.push(entry);
    console.log(`done ${m.s} ${m.title}`);
  }
  await browser.close();
  protoSrv.close(); miniSrv.close();
  fs.writeFileSync(path.join(OUT, `parity-report-${filter}.json`), JSON.stringify(report, null, 2));
  console.log(`OK ${items.length} видов → ${OUT}`);
}
run().catch(e => { console.error(e); process.exit(1); });
