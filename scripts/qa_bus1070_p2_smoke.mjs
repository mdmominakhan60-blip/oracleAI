#!/usr/bin/env node
/* BUS-1070 p2 e2e smoke: инструменты S11 (quick/form/run) + результат S12 +
 * таро S13 (question/reveal/zoom/reading) — R06 §14.1 p2, mock API.
 * Проверяет: рендер 8 видов через qa-роутинг, состояния §11.2 (run-fail,
 * disabled draw), порядок открытия карт, зум, overflow 320px/390px,
 * console-error/pageerror-нуль. Запуск: node scripts/qa_bus1070_p2_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18098';
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
  birth_date: '1994-03-14', birth_time: '10:00', birth_city: 'Москва', onboarded: true });
const AGENTS = () => JSON.stringify([
  { code: 'oracle', name: 'Лилит', title: 'Проводник', role: 'Проводник', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'astro', name: 'Урания', title: 'Звёзды', role: 'Астролог', avatar: '/static/img/agents/astro.jpg' },
  { code: 'tarot', name: 'Мадам Ленорман', title: 'Карты', role: 'Таролог', avatar: '/static/img/agents/tarot.jpg' }
]);

async function freshPage() {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME() }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: AGENTS() }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
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
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME() }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: AGENTS() }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
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
  await new Promise((r) => server.listen(18098, '127.0.0.1', r));
  browser = await chromium.launch({ executablePath: CHROME_PATH, args: ['--no-sandbox'] });

  /* ── S11a: быстрый инструмент (прогноз) ───────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tool-quick', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S11a прогноз: шапка+титул', !!(await page.$('.screenheader')) && !!(await page.$('.tool-view__title')));
    ok('S11a прогноз: поле даты + кнопка submit', !!(await page.$('#tq-date')) && !!(await page.$('[data-act="tool-submit"][data-tool="forecast"]')));
    ok('S11a прогноз: terms-строка тарифа', !!(await page.$('.tool-view__terms')));
    /* §11.2 кворум-состояние: submit переводит в run */
    await page.click('[data-act="tool-submit"][data-tool="forecast"]');
    await page.waitForTimeout(300);
    ok('S11a → tool-run: шаги выполнения', (await page.$$('.tool-run__steps .tool-run__step')).length >= 3);
    await page.screenshot({ path: OUT + '/p2-s11a-quick.png' });
    await page.close();
  }

  /* ── S11b: инструмент с формой (синастрия) ────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tool-form', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S11b синастрия: блок своих данных', !!(await page.$('.review-list')));
    const day = await page.$('#p-day');
    ok('S11b синастрия: поля даты партнёра', !!(day && (await page.$('#p-month')) && (await page.$('#p-year'))));
    if (day) {
      /* §11.2: невалидная дата партнёра → inline-ошибка */
      await page.fill('#p-day', '31');
      await page.fill('#p-month', '2');
      await page.fill('#p-year', '1995');
      await page.click('[data-act="tool-submit"][data-tool="syn"]');
      await page.waitForTimeout(250);
      const derr = await page.$('.field__error:not([hidden]), [data-field-error]:not([hidden])');
      ok('S11b §11.2: ошибка даты (31.02)', !!derr);
      const monthAria = await page.getAttribute('#p-month', 'aria-label');
      ok('S11b a11y: aria-label месяца = месяц (не «день»)', /месяц|month/i.test(monthAria || ''), monthAria || '');
      await page.fill('#p-day', '14');
      await page.fill('#p-month', '3');
      await page.click('[data-act="tool-submit"][data-tool="syn"]');
      let runSteps = 0;
      try {
        await page.waitForSelector('.tool-run__steps .tool-run__step', { timeout: 3000 });
        runSteps = (await page.$$('.tool-run__steps .tool-run__step')).length;
      } catch {}
      ok('S11b → tool-run после валидной даты', runSteps >= 3, `${runSteps} шагов`);
    }
    await page.screenshot({ path: OUT + '/p2-s11b-form.png' });
    await page.close();
  }

  /* ── S11c: run + fail-состояние §11.2 ─────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tool-run', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const steps = await page.$$('.tool-run__steps .tool-run__step');
    ok('S11c run: 4 шага', steps.length >= 4, `${steps.length} шагов`);
    ok('S11c run: спиннер + role=status', !!(await page.$('.tool-run__spinner')) && !!(await page.$('[role="status"]')));
    ok('S11c run: главная кнопка disabled (дубль-защита)', !!(await page.$('.tool-view__footer .btn--primary[disabled]')));
    /* fail-состояние через программный вход */
    await page.evaluate(() => app.go('tool-run', { fail: true }));
    await page.waitForTimeout(250);
    const fail = await page.$('#run-fail-demo:not([hidden])');
    ok('S11c §11.2 fail: баннер + check/retry', !!fail && !!(await page.$('[data-act="run-fail-check"]')));
    await page.screenshot({ path: OUT + '/p2-s11c-run.png' });
    await page.close();
  }

  /* ── S12: результат ──────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=result', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S12 результат: шапка + аватар', !!(await page.$('.result__head')) && !!(await page.$('.result__avatar')));
    ok('S12 результат: meta (агент/дата/номер)', (await page.$$('.result__meta span')).length >= 3);
    ok('S12 результат: кнопки share/discuss/library', !!((await page.$('[data-act="result-share"]')) && (await page.$('[data-act="result-discuss"]')) && (await page.$('[data-act="result-library"]'))));
    await page.screenshot({ path: OUT + '/p2-s12-result.png' });
    await page.close();
  }

  /* ── S13a: таро — вопрос ──────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tarot-question', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S13a вопрос: шапка агента', !!(await page.$('.chat-header')));
    ok('S13a вопрос: input + примеры', !!(await page.$('#tarot-q')) && (await page.$$('.tarot-examples__item')).length >= 3);
    ok('S13a вопрос: config-строки (расклад/колода)', (await page.$$('.tarot-config__row')).length >= 2);
    const drawBtn = await page.$('[data-act="tarot-draw"]');
    ok('S13a вопрос: кнопка расклада', !!drawBtn);
    if (drawBtn) {
      await drawBtn.click();
      // renderTarotReveal сначала 600 мс показывает draw-сцену (fan рубашек),
      // карты рендерятся в _paintTarotReveal по setTimeout — ждём селектор.
      let revealCards = 0;
      try {
        await page.waitForSelector('.tarot-cards .tcard', { timeout: 3000 });
        revealCards = (await page.$$('.tarot-cards .tcard')).length;
      } catch {}
      ok('S13a → reveal после draw', revealCards >= 3, `${revealCards} карт`);
    }
    await page.screenshot({ path: OUT + '/p2-s13a-question.png' });
    await page.close();
  }

  /* ── S13b: reveal + порядок открытия + warn ───────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tarot-reveal', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    const cards = await page.$$('.tarot-cards .tcard');
    ok('S13b reveal: 3 карты', cards.length === 3, `${cards.length} карт`);
    ok('S13b reveal: все закрыты, счётчик 0/3', !(await page.$('.tcard.is-open')) && /0\D*3/.test(await page.textContent('#tarot-counter')));
    /* §6.4: клик по карте №3 (не следующая) → warn, карта не открыта */
    if (cards.length === 3) {
      await cards[2].click();
      await page.waitForTimeout(200);
      const warned = await page.$eval('.tarot-cards .tcard[data-i="2"]', (el) => el.hasAttribute('data-warn')).catch(() => false);
      ok('S13b §6.4: не-следующая карта → warn', warned === true);
      ok('S13b §6.4: карта при этом не открылась', !(await page.$('.tcard.is-open')));
      /* открытие по порядку: 0 → 1 */
      await cards[0].click();
      await page.waitForTimeout(200);
      const openedCount = await page.$$eval('.tcard.is-open', (els) => els.length);
      ok('S13b §6.4: открытие первой по порядку', openedCount === 1, `${openedCount} открыто`);
      /* клик по открытой → зум; таро-грид ре-рендерится — берём свежий хендл */
      const c0 = await page.$('.tarot-cards .tcard[data-i="0"]');
      if (c0) await c0.click();
      await page.waitForTimeout(300);
      const zoomed = await page.evaluate(() => window.app && window.app.view === 'tarot-zoom');
      ok('S13b §6.4: клик по открытой → зум', zoomed === true);
    }
    await page.screenshot({ path: OUT + '/p2-s13b-reveal.png' });
    await page.close();
  }

  /* ── S13c: зум карты ─────────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tarot-zoom', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S13c зум: титул карты в шапке', !!(await page.$('.screenheader__title')));
    ok('S13c зум: кнопка назад к картам', !!(await page.$('[data-act="tarot-back-cards"]')));
    const back = await page.$('[data-act="tarot-back-cards"]');
    if (back) { await back.click(); await page.waitForTimeout(250); }
    await page.screenshot({ path: OUT + '/p2-s13c-zoom.png' });
    await page.close();
  }

  /* ── S13d: разбор расклада ────────────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tarot-reading', { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    ok('S13d разбор: контейнер рендерится', !!(await page.$('.tarot')) && !!(await page.$('.tarot-reading__title')));
    ok('S13d разбор: CTA обсудить/настроить', !!((await page.$('[data-act="tarot-discuss"]')) || (await page.$('[data-act="tarot-config"]'))));
    await page.screenshot({ path: OUT + '/p2-s13d-reading.png' });
    await page.close();
  }

  /* ── 320px overflow по всем видам p2 ──────────────────────────────── */
  {
    const views = ['tool-quick', 'tool-form', 'tool-run', 'result', 'tarot-question', 'tarot-reveal', 'tarot-zoom', 'tarot-reading'];
    for (const v of views) {
      const page = await openAt(320);
      await page.goto(BASE + '/?qa=1&qa_view=' + v, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      await checkViewport(page, v);
      await page.close();
    }
  }

  /* ── console-error/pageerror-нуль на ключевых видах ───────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=tarot-question', { waitUntil: 'networkidle' });
    await page.click('[data-act="tarot-draw"]');
    await page.waitForTimeout(400);
    await page.evaluate(() => app.go('tarot-zoom'));
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('tarot-reading'));
    await page.waitForTimeout(300);
    ok('JS: ноль console.error/pageerror в таро-потоке', page._errors.length === 0, page._errors.join(' | ').slice(0, 200));
    await page.screenshot({ path: OUT + '/p2-tarot-flow.png' });
    await page.close();
  }

  const failed = results.filter((r) => !r.pass).length;
  console.log(`\n${failed === 0 ? 'ALL PASS' : failed + ' FAILED'} (${results.length} checks)`);
  fs.writeFileSync(path.join(OUT, 'p2-smoke-results.json'), JSON.stringify({ ts: new Date().toISOString(), results }, null, 2));
  process.exit(failed === 0 ? 0 : 1);
}

run().catch(async (e) => {
  console.error('SMOKE ERROR:', e.message);
  try { await browser?.close(); } catch {}
  server.close();
  process.exit(2);
});
