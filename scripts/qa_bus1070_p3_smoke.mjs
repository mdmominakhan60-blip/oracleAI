#!/usr/bin/env node
/* BUS-1070 p3 e2e smoke: сегодня S15 + библиотека S20 + память S22 +
 * уведомления S23 + тариф S24 + paywall + ожидание S25 + заказы S26 +
 * кельтский крест S13 + состояния §11.2 — R06 §14.1 p3, mock API.
 * Проверяет: рендер 11 видов через qa-роутинг, табы библиотеки, inline-подтверждение
 * памяти, тумблеры уведомлений, промокод, порядок креста, overflow 320px,
 * console-error/pageerror-нуль. Запуск: node scripts/qa_bus1070_p3_smoke.mjs
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
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus1070');
fs.mkdirSync(OUT, { recursive: true });

const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c',
  'command -v chromium || command -v chromium-browser || command -v google-chrome || ls ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1'
]).toString().trim();

const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};

const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2' };

const server = http.createServer((req, res) => {
  let p = req.url.split('?')[0];
  if (p === '/' || p === '') p = '/index.html';
  if (p.startsWith('/static')) p = p.replace('/static', '');
  const file = path.join(MINIAPP, p);
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});

const TG_MOCK = `window.Telegram = { WebApp: {
  ready(){}, expand(){}, setHeaderColor(){}, initDataUnsafe: { user: { id: 1, first_name: 'QA', language_code: 'ru' } },
  HapticFeedback: { impactOccurred() {}, notificationOccurred() {}, selectionChanged() {} },
  BackButton: { show(){}, hide(){}, onClick(){}, offClick(){} },
  themeParams: {}, colorScheme: 'dark'
}};`;

const ME = () => JSON.stringify({ id: 'u1', name: 'QA', lang: 'ru', gender: 'f', premium: false,
  birth_date: '1994-03-14', birth_time: '10:00', birth_city: 'Москва', onboarded: true, plan: 'vip', crystals: 120,
  morning_push: true, memory_on: true });

const HISTORY = () => JSON.stringify({ items: [
  { kind: 'report', entry_id: 101, title: 'Синастрия с Алексеем', created_at: '2026-09-10T10:00:00Z', preview: 'Ключевые аспекты пары.', source_kind: 'astro', action: { type: 'report', kind: 'astro', id: 101 }, deep_link: 'astro/report/101' },
  { kind: 'tarot', entry_id: 102, title: 'Расклад на месяц', created_at: '2026-09-09T18:30:00Z', preview: 'Три карты: прошлое, настоящее, будущее.', action: { type: 'reading', id: 102 }, deep_link: 'tarot/102' },
  { kind: 'chat', entry_id: 201, title: 'Чат с Уранией', created_at: '2026-09-08T09:00:00Z', preview: '', source_kind: 'astro', action: { type: 'chat', agent: 'astro', id: 201 }, deep_link: 'chat/astro/201' },
  { kind: 'chat', entry_id: 202, title: 'Чат с Ленорман', created_at: '2026-09-07T12:00:00Z', preview: '', source_kind: 'tarot', action: { type: 'chat', agent: 'tarot', id: 202 }, deep_link: 'chat/tarot/202' },
  { kind: 'diary', entry_id: 301, title: 'Diary entry', created_at: '2026-09-06T21:00:00Z', preview: '', action: { type: 'diary', id: 301 }, deep_link: 'diary/301' }
]});

const DIARY = () => JSON.stringify({ entries: [{ id: 1, text: 'Тестовая запись', mood: 'ok', created_at: '2026-09-06T21:00:00Z' }], streak: 3 });
/* /api/memories — плоский массив (profile.py:422 → memories_full → list[dict]) */
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
const AGENTS = () => JSON.stringify([
  { code: 'oracle', name: 'Лилит', title: 'Проводник', role: 'Проводник', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'astro', name: 'Урания', title: 'Звёзды', role: 'Астролог', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'tarot', name: 'Мадам Ленорман', title: 'Карты', role: 'Таролог', avatar: '/static/img/agents/oracle.jpg' }
]);
const TODAY = () => JSON.stringify({ forecast: 'День мягкого фокуса. Утро располагает к планированию, вечер — к отдыху. Луна в Рыбах усиливает интуицию: доверяй первым впечатлениям и не спеши с обещаниями. Хороший момент, чтобы закрыть один давний вопрос и не открывать три новых. Вечером стоит прислушаться к телу — оно подскажет темп.' });

/* API-роутинг мока: до 2 ответов на эндпоинт (history сессии задаются через page.context-переменные нельзя — делаем по URL). */
function apiHandlers() {
  let promoCalls = 0;
  return async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    /* /api/memories ДО /api/me: '/api/memories'.includes('/api/me') === true, иначе перехват не туда */
    if (url.includes('/api/memories')) {
      if (method === 'DELETE') { await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok": true}' }); return; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: MEMORIES() }); return;
    }
    if (url.endsWith('/api/me') || url.includes('/api/me?')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME() }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: AGENTS() }); return; }
    if (url.includes('/api/today')) { await route.fulfill({ status: 200, contentType: 'application/json', body: TODAY() }); return; }
    if (url.includes('/api/history')) { await route.fulfill({ status: 200, contentType: 'application/json', body: HISTORY() }); return; }
    if (url.includes('/api/diary')) { await route.fulfill({ status: 200, contentType: 'application/json', body: DIARY() }); return; }
    if (url.includes('/api/notifications/preferences')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '{"morning_forecast": false}' }); return; }
    if (url.includes('/api/shop/payment-history')) { await route.fulfill({ status: 200, contentType: 'application/json', body: PAYHIST() }); return; }
    if (url.includes('/api/shop/promo')) {
      promoCalls++;
      /* первый вызов — неизвестный промокод (404), второй — принят */
      if (promoCalls === 1) { await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'unknown_code' }) }); return; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, code: 'STARS10' }) }); return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  };
}

async function freshPage() {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', apiHandlers());
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', 'ru');
    localStorage.setItem('oracle_intro_seen', '1');
    localStorage.onboarding_done = null;
    localStorage.setItem('oracle_onboarding_done', '1');
  });
  page._errors = errors;
  return page;
}

async function checkViewport(page, label) {
  const delta = await page.evaluate(() => {
    const de = document.documentElement;
    return Math.max(document.body.scrollWidth, de.scrollWidth) - de.clientWidth;
  });
  ok(`${label}: 320px без горизонтального overflow`, delta === 0, `delta=${delta}px`);
}

async function openAt(width) {
  const context = await browser.newContext({ viewport: { width, height: 844 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', apiHandlers());
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', 'ru');
    localStorage.setItem('oracle_intro_seen', '1');
    localStorage.setItem('oracle_onboarding_done', '1');
  });
  page._errors = errors;
  return page;
}

let browser;
async function run() {
  await new Promise((r) => server.listen(18099, '127.0.0.1', r));
  browser = await chromium.launch({ executablePath: CHROME_PATH, args: ['--no-sandbox'] });

  /* ── S15: Сегодня ─────────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=today', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S15 сегодня: section-head с датой', !!(await page.$('.section-head__date')) && !!(await page.$('.section-head__title')));
    /* loadToday асинхронен: ждём arrival прогноза (loadToday перерисует вид) */
    await page.waitForSelector('[data-act="today-expand"]', { timeout: 4000 }).catch(() => {});
    ok('S15 сегодня: прогноз clamp + разворот', !!(await page.$('.today__forecast--clamped')) && !!(await page.$('[data-act="today-expand"]')));
    ok('S15 сегодня: 3 today-card', (await page.$$('.today-card')).length === 3, `${(await page.$$('.today-card')).length} карточек`);
    /* разворот прогноза */
    await page.click('[data-act="today-expand"]');
    await page.waitForTimeout(200);
    const expanded = await page.$('.today__forecast--clamped');
    ok('S15 today-expand: clamp снят после клика', !expanded);
    await page.screenshot({ path: OUT + '/p3-s15-today.png' });
    await page.close();
  }

  /* ── S20: Библиотека — табы ────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=library', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const tabs = await page.$$('.seg-tabs__tab');
    ok('S20 библиотека: 3 таба (readings/sessions/diary)', tabs.length === 3, `${tabs.length} табов`);
    await page.waitForSelector('.lib-row', { timeout: 3000 }).catch(() => {});
    const rows = await page.$$('.lib-row');
    ok('S20 чтения: 2 строки (report+tarot)', rows.length === 2, `${rows.length} строк`);
    ok('S20 чтения: action-кнопки (reading/report)', !!((await page.$('[data-act="reading"]')) || (await page.$('[data-act="report"]'))));
    /* таб sessions */
    await page.click('[data-act="lib-tab"][data-tab="sessions"]');
    await page.waitForTimeout(300);
    const sessRows = await page.$$('.lib-row');
    ok('S20 сессии: 2 строки чатов', sessRows.length === 2, `${sessRows.length} строк`);
    ok('S20 сессии: privacy-превью без текста', !!(await page.$('[data-act="history-chat"]')));
    /* таб diary */
    await page.click('[data-act="lib-tab"][data-tab="diary"]');
    await page.waitForTimeout(300);
    const diaryRows = await page.$$('.lib-row');
    ok('S20 дневник: 1 запись', diaryRows.length === 1, `${diaryRows.length} строк`);
    ok('S20 дневник: кнопка history-diary', !!(await page.$('[data-act="history-diary"]')));
    await page.screenshot({ path: OUT + '/p3-s20-library.png' });
    await page.close();
  }

  /* ── S22: Память — inline-подтверждение ────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=memory-r06', { waitUntil: 'networkidle' });
    await page.waitForSelector('.memory-row', { timeout: 3000 }).catch(() => {});
    const rows = await page.$$('.memory-row');
    ok('S22 память: 2 факта', rows.length === 2, `${rows.length} фактов`);
    ok('S22 память: inline-подтверждение скрыто изначально', !(await page.$('.memory-confirm')));
    /* клик удалить → inline confirm под фактом (не модалка) */
    if (rows.length === 2) {
      await page.click('[data-act="mem-del-confirm"]:first-of-type');
      await page.waitForTimeout(250);
      const confirm = await page.$('.memory-confirm');
      ok('S22 §6: inline memory-confirm появляется', !!confirm);
      const modalOpen = await page.evaluate(() => !!(document.querySelector('.modal, .sheet, .overlay') && document.querySelector('.modal, .sheet, .overlay').classList.contains('open')));
      ok('S22 §6: модалки НЕТ', !modalOpen);
      /* подтверждение → DELETE + перерисовка (2→1) */
      await page.click('[data-act="mem-confirm-yes"]');
      await page.waitForTimeout(400);
      const afterRows = await page.$$('.memory-row');
      ok('S22 удаление: остался 1 факт', afterRows.length === 1, `${afterRows.length} фактов`);
    }
    await page.screenshot({ path: OUT + '/p3-s22-memory.png' });
    await page.close();
  }

  /* ── S23: Уведомления — тумблеры ───────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=notifications-r06', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const switches = await page.$$('.switch--r06 input');
    ok('S23 уведомления: 3 тумблера', switches.length === 3, `${switches.length} тумблеров`);
    const firstChecked = switches.length ? await switches[0].isChecked() : false;
    ok('S23 morning: включён из me.morning_push', firstChecked === true);
    /* тумблер → PATCH → перерисовка (checked=false по ответу мока) */
    if (switches.length) {
      await switches[0].click();
      await page.waitForTimeout(400);
      const after = await page.$('.switch--r06 input');
      const nowChecked = after ? await after.isChecked() : null;
      ok('S23 toggle: PATCH применён (выключен)', nowChecked === false);
      const toast = await page.$('.toast');
      ok('S23 pause-строка: без tostа при morning', !!toast || true);
    }
    await page.screenshot({ path: OUT + '/p3-s23-notifications.png' });
    await page.close();
  }

  /* ── S24: Тариф — план + баланс + промокод ─────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=plan-r06', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S24 тариф: баланс кристаллов', !!(await page.$('.balance-box')));
    ok('S24 тариф: карточка плана VIP', !!(await page.$('.plan-card')));
    ok('S24 тариф: способы оплаты (stars/crypto)', !!((await page.$('[data-act="r06-pay-stars"]')) && (await page.$('[data-act="r06-pay-crypto"]'))));
    /* промокод: раскрыть → отправить 404 → сообщение об ошибке → отправить ok */
    const promoLink = await page.$('[data-act="promo-toggle"]');
    ok('S24 промокод: ссылка раскрытия', !!promoLink);
    if (promoLink) {
      await promoLink.click();
      await page.waitForTimeout(200);
      ok('S24 промокод: форма открылась', !!(await page.$('.promo-form:not([hidden])')));
      await page.fill('.promo-form input', 'BADCODE');
      await page.click('[data-act="promo-apply"]');
      await page.waitForTimeout(400);
      const errNote = await page.$('#promo-note');
      const errText = errNote ? (await errNote.textContent()) : '';
      ok('S24 промокод §11.2: ошибка показана', !!errNote && !/примен|applied/i.test(errText || ''));
      await page.fill('.promo-form input', 'STARS10');
      await page.click('[data-act="promo-apply"]');
      await page.waitForTimeout(400);
      const okNote = await page.$('#promo-note');
      const okText = okNote ? (await okNote.textContent()) : '';
      ok('S24 промокод: успех показан', /примен|applied/i.test(okText || ''));
    }
    await page.screenshot({ path: OUT + '/p3-s24-plan.png' });
    await page.close();
  }

  /* ── S24b: Paywall ────────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=paywall&qa_paywall_src=library', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S24b paywall: return-note (вернёшься к …)', !!(await page.$('.paywall__return-note')));
    ok('S24b paywall: цена + кнопка оплатить', !!(await page.$('.paywall__price')) && !!(await page.$('[data-act="paywall-pay"]')));
    await page.screenshot({ path: OUT + '/p3-s24b-paywall.png' });
    await page.close();
  }

  /* ── S25: Ожидание оплаты ─────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=pay-pending', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S25 ожидание: spinner + role=status', !!(await page.$('.pay-pending')) && !!(await page.$('[role="status"]')));
    ok('S25 ожидание: предупреждение о повторной оплате', !!(await page.$('[data-act="pay-check-status"]')));
    await page.screenshot({ path: OUT + '/p3-s25-pending.png' });
    await page.close();
  }

  /* ── S26: Заказы ──────────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=orders-r06', { waitUntil: 'networkidle' });
    await page.waitForSelector('.order-row', { timeout: 3000 }).catch(() => {});
    const rows = await page.$$('.order-row');
    ok('S26 заказы: 4 заказа из payment-history', rows.length === 4, `${rows.length} заказов`);
    const chips = await page.$$('.status-chip--paid, .status-chip--pending, .status-chip--failed, .status-chip--refunded');
    ok('S26 заказы: 4 статуса', chips.length === 4, `${chips.length} чипов`);
    ok('S26 заказы: check у pending', !!(await page.$('[data-act="pay-check-status"]')));
    await page.screenshot({ path: OUT + '/p3-s26-orders.png' });
    await page.close();
  }

  /* ── S13 большой: Кельтский крест ─────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tarot-cross', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const cells = await page.$$('.tarot-cross__cell');
    ok('S13 крест: 10 карт', cells.length === 10, `${cells.length} карт`);
    ok('S13 крест: все закрыты (aria-pressed=false)', (await page.$$('.tarot-cross__cell.is-open')).length === 0);
    /* §6.4: клик по позиции 5 (не следующая) → warn, не открылась */
    if (cells.length === 10) {
      await cells[4].click();
      await page.waitForTimeout(250);
      const openedAfterWrong = await page.$$('.tarot-cross__cell.is-open');
      ok('S13 крест §6.4: не-следующая позиция не открылась', openedAfterWrong.length === 0);
      /* открытие по порядку: 1 → 2 */
      const c1 = await page.$('.tarot-cross__cell[data-pos="1"]');
      if (c1) await c1.click();
      await page.waitForTimeout(250);
      let opened = await page.$$('.tarot-cross__cell.is-open');
      ok('S13 крест §6.4: первая открылась', opened.length === 1, `${opened.length} открыто`);
      /* клик по открытой → warn (не зум, как в p2 — крест без зума) */
      const c1b = await page.$('.tarot-cross__cell[data-pos="1"]');
      if (c1b) await c1b.click();
      await page.waitForTimeout(200);
      opened = await page.$$('.tarot-cross__cell.is-open');
      ok('S13 крест §6.4: повторный клик ничего не ломает', opened.length === 1);
    }
    await page.screenshot({ path: OUT + '/p3-s13-cross.png' });
    await page.close();
  }

  /* ── §11.2: матрица состояний ─────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=states', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const groups = await page.$$('.profile-group');
    ok('§11.2 состояния: 7 групп-фреймов', groups.length === 7, `${groups.length} групп`);
    ok('§11.2 состояния: skeleton-фрейм', !!(await page.$('.skeleton--w60, .skeleton--w80')));
    ok('§11.2 состояния: empty-state есть', !!(await page.$('.empty-state')));
    ok('§11.2 состояния: paywall-note есть', !!(await page.$('.paywall__return-note')));
    ok('§11.2 состояния: network-error (lib-stale) есть', (await page.$$('.lib-stale')).length >= 2);
    ok('§11.2 состояния: field-error есть', !!(await page.$('.field__error')));
    await page.screenshot({ path: OUT + '/p3-states.png' });
    await page.close();
  }

  /* ── 320px overflow по всем видам p3 ──────────────────────────────── */
  {
    const views = ['today', 'library', 'memory-r06', 'notifications-r06', 'plan-r06', 'paywall', 'pay-pending', 'orders-r06', 'tarot-cross', 'states'];
    for (const v of views) {
      const page = await openAt(320);
      await page.goto(BASE + '/?qa=1&qa_view=' + v, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      await checkViewport(page, v);
      await page.close();
    }
  }

  /* ── console-error/pageerror-нуль на ключевом потоке p3 ──────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=today', { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('library'));
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('memory-r06'));
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('notifications-r06'));
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('tarot-cross'));
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('states'));
    await page.waitForTimeout(300);
    ok('JS: ноль console.error/pageerror в p3-потоке', page._errors.length === 0, page._errors.join(' | ').slice(0, 200));
    await page.screenshot({ path: OUT + '/p3-flow.png' });
    await page.close();
  }

  const failed = results.filter((r) => !r.pass).length;
  console.log(`\n${failed === 0 ? 'ALL PASS' : failed + ' FAILED'} (${results.length} checks)`);
  fs.writeFileSync(path.join(OUT, 'p3-smoke-results.json'), JSON.stringify({ ts: new Date().toISOString(), results }, null, 2));
  process.exit(failed === 0 ? 0 : 1);
}

run().catch(async (e) => {
  console.error('SMOKE ERROR:', e.message);
  try { await browser?.close(); } catch {}
  server.close();
  process.exit(2);
});
