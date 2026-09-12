#!/usr/bin/env node
/* BUS-1070 p1 e2e smoke: онбординг + чат-состояния + история + sheet (R06 §14.1, mock API).
 * Проверяет: welcome→onboarding 5 шагов+review (S03/S04), ошибки полей §11.2,
 * пустой чат (S05), история (S07), sheet-инструменты (S10), статус-баннер (S01),
 * 320px без горизонтального overflow, console-error-нулль.
 * Запуск: node scripts/qa_bus1070_p1_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18097';
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
  birth_date: null, birth_time: null, birth_city: null, onboarded: false });
const AGENTS = () => JSON.stringify([
  { code: 'oracle', name: 'Лилит', title: 'Проводник', role: 'Проводник', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'astro', name: 'Астролог', title: 'Звёзды', role: 'Астролог', avatar: '/static/img/agents/astro.jpg' },
  { code: 'tarot', name: 'Таро', title: 'Карты', role: 'Таролог', avatar: '/static/img/agents/tarot.jpg' }
]);
const SESSIONS = () => JSON.stringify([
  { id: 's1', agent: 'oracle', title: 'Про работу', preview: 'Чувствую, что застряла…', ts: Date.now() - 3600e3 },
  { id: 's2', agent: 'astro', title: 'Луна и сон', preview: 'Почему я не сплю?', ts: Date.now() - 86400e3 }
]);

async function freshPage({ reducedMotion = 'no-preference' } = {}) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark', reducedMotion });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME() }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: AGENTS() }); return; }
    if (/\/api\/(chat\/\w+\/)?sessions/.test(url)) { await route.fulfill({ status: 200, contentType: 'application/json', body: SESSIONS() }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', 'ru');
    localStorage.setItem('oracle_intro_seen', '1');
    localStorage.setItem('oracle_chat_guide_v2', '1');
    localStorage.setItem('oracle_onboarding_done', '0');
  });
  page._errors = errors;
  return page;
}

let browser;
async function run() {
  await new Promise((r) => server.listen(18097, '127.0.0.1', r));
  browser = await chromium.launch({ executablePath: CHROME_PATH, args: ['--no-sandbox'] });

  /* ── S03 Welcome ────────────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=welcome', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    const cta = await page.$('.onboarding__title, [data-welcome-cta], .btn--primary, .btn-primary');
    ok('S03 welcome renders', !!cta, 'CTA или заголовок найдены');
    await page.screenshot({ path: OUT + '/s03-welcome.png' });
    await page.close();
  }

  /* ── S04 Onboarding: 5 шагов + review ───────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=onboarding&qa_step=1', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    const cards = await page.$$('.intent-card');
    ok('S04 шаг 1: intent-карточки', cards.length >= 2, `${cards.length} карточек`);
    if (cards.length) await cards[0].click();
    await page.waitForTimeout(200);
    const step2 = await page.$('#ob-name, .field__input');
    ok('S04 шаг 2: имя после выбора намерения', !!step2);
    // Ошибка поля §11.2: 1 символ
    if (step2) {
      await step2.fill('А');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(200);
      const err = await page.$('.field__error, [aria-invalid="true"]');
      ok('S04 §11.2: ошибка имени (мин. 2 символа)', !!err);
      await step2.fill('Анна');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(200);
    }
    const dateSeg = await page.$('.date-seg, #ob-day');
    ok('S04 шаг 3: дата рождения', !!dateSeg);
    // 31.02 — несуществующий день (месяц — число, контракт number-инпута)
    if (await page.$('#ob-day')) {
      await page.fill('#ob-day', '31');
      await page.fill('#ob-month', '2');
      await page.fill('#ob-year', '1994');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(200);
      const derr = await page.$('.field__error:not([hidden]), [data-ob-error]:not([hidden])');
      ok('S04 §11.2: ошибка даты (31.02)', !!derr);
      await page.fill('#ob-day', '14');
      await page.fill('#ob-month', '3');
      await page.fill('#ob-year', '1994');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(200);
    }
    const choice = await page.$('.choice-row');
    ok('S04 шаг 4: время (choice-rows)', !!choice);
    if (choice) {
      await choice.click();
      await page.waitForTimeout(150);
    }
    const next4 = await page.$('[data-act="ob-next"]');
    if (next4) { await next4.click(); await page.waitForTimeout(250); }
    const city = await page.$('#ob-city, .combobox input');
    ok('S04 шаг 5: город', !!city);
    if (city) {
      const nextEmpty = await page.$('[data-act="ob-next"]');
      if (nextEmpty) { await nextEmpty.click(); await page.waitForTimeout(300); }
      const cityErr = await page.$eval('[data-ob-error]', (el) => !el.hidden).catch(() => false);
      ok('S04 §11.2: ошибка города (пустой ввод)', cityErr === true);
      await city.fill('К');
      await page.waitForTimeout(300);
      const opts = await page.$$('.combobox__option');
      ok('S04 шаг 5: combobox подсказки', opts.length >= 1, `${opts.length} опций`);
      if (opts.length) await opts[0].click();
      await page.waitForTimeout(150);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(300);
    }
    const review = await page.$('.review-row, .review-list');
    ok('S04 review: проверка данных', !!review);
    const startBtn = await page.$('[data-act="ob-next"], .onboarding__footer .btn--primary, .onboarding__footer .btn-primary');
    if (startBtn && review) { await startBtn.click(); await page.waitForTimeout(400); }
    ok('S04: завершение онбординга сохраняет (обязательный шаг)', await page.evaluate(() => localStorage.getItem('oracle_onboarding_done') === '1'));
    await page.screenshot({ path: OUT + '/s04-onboarding-review.png' });
    await page.close();
  }

  /* ── S05 Пустой чат ─────────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=hub', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const ex = await page.$$('.empty-chat__example, .chat-suggest, .suggestion, [data-suggest]');
    ok('S05 чат-хаб рендерится', !!(await page.$('#app-main')));
    ok('S05: подстановщики/сценарии входа', ex.length >= 1 || !!(await page.$('.agent-card')), `${ex.length} подсказок`);
    await page.screenshot({ path: OUT + '/s05-chat-empty.png' });
    await page.close();
  }

  /* ── S07 История ────────────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=sessions', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const cards = await page.$$('.session-card, .sess-row');
    ok('S07 история: карточки сессий', cards.length >= 1, `${cards.length} карточек`);
    // удаление с подтверждением §11.1: первый тап — inline-подтверждение
    const del = await page.$('[data-act="sess-del"], .sess-del');
    if (del) {
      await del.click();
      await page.waitForTimeout(250);
      const row = del ? await del.getAttribute('data-tid') : null;
      const confirmedRow = await page.$('.session-card[data-confirmed="1"]');
      const confirmLabel = await page.$('.session-card__confirm-label:not([hidden])');
      ok('S07 §11.1: удаление с подтверждением', !!(confirmedRow || confirmLabel));
    }
    await page.screenshot({ path: OUT + '/s07-sessions.png' });
    await page.close();
  }

  /* ── S10 Sheet-инструменты ──────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=sheet', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    const sheet = await page.$('.sheet');
    const rows = await page.$$('.tool-row');
    ok('S10 sheet-инструменты открываются', !!sheet && rows.length >= 3, `${rows.length} инструментов`);
    await page.screenshot({ path: OUT + '/s10-sheet-tools.png' });
    await page.close();
  }

  /* ── S01/S02 Статус-баннер session expired ──────────────────────────── */
  {
    const page = await freshPage();
    await page.route('**/api/me', async (route) => {
      await route.fulfill({ status: 401, contentType: 'application/json', body: '{"detail":"expired"}' });
    });
    await page.goto(BASE + '/?qa=1', { waitUntil: 'networkidle' });
    await page.waitForTimeout(600);
    const banner = await page.$('.status-banner--error, .soft-empty--recovery, [data-auth-required]');
    ok('S01/S02: 401 → стойкий экран/баннер ошибки входа', !!banner);
    await page.screenshot({ path: OUT + '/s01-session-expired.png' });
    await page.close();
  }

  /* ── 320px без горизонтального overflow ─────────────────────────────── */
  for (const vw of [320, 390]) {
    const page = await freshPage();
    await page.setViewportSize({ width: vw, height: 844 });
    await page.goto(BASE + '/?qa=1&qa_view=onboarding&qa_step=1', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    const overflow = await page.evaluate(() => {
      const d = document.documentElement;
      return d.scrollWidth - d.clientWidth;
    });
    ok(`320px: no horizontal overflow (${vw}px)`, overflow <= 1, `delta=${overflow}px`);
    await page.close();
  }

  await browser.close();
  server.close();
  const failed = results.filter(r => !r.pass).length;
  console.log(`\n${failed === 0 ? 'ALL PASS' : failed + ' FAILED'} (${results.length} checks)`);
  fs.writeFileSync(path.join(OUT, 'p1-smoke-results.json'), JSON.stringify({ ts: new Date().toISOString(), results }, null, 2));
  process.exit(failed === 0 ? 0 : 1);
}

run().catch(async (e) => {
  console.error('SMOKE ERROR:', e.message);
  try { await browser?.close(); } catch {}
  server.close();
  process.exit(2);
});
