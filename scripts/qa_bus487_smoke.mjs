#!/usr/bin/env node
/* BUS-487 e2e smoke: два фикса maybeLanguage (mock API, без бэкенда).
 * 1) savedLocal-ветка: интро показывается при повторном запуске (oracle_lang
 *    есть, oracle_intro_seen нет).
 * 2) двойной тап по кнопке языка за время await POST /api/profile — ровно один POST.
 * Запуск: node scripts/qa_bus487_smoke.mjs
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
await new Promise((r) => server.listen(18097, '127.0.0.1', r));

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

async function freshPage(pageSetup) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true,
    colorScheme: 'dark',
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()); });
  if (pageSetup) await pageSetup(page, context);
  return { context, page, errors };
}

/* ——— Сценарий 1: повторный запуск, язык сохранён, интро не пройдено ——— */
{
  let profilePosts = 0;
  const { context, page, errors } = await freshPage(async (p) => {
    await p.route('**/api/**', async (route) => {
      const url = route.request().url();
      const method = route.request().method();
      if (url.includes('/api/profile') && method === 'POST') { profilePosts++; await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }); return; }
      if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, name: 'Тест', lang: 'ru', flags: {} }) }); return; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
    await p.addInitScript(() => { localStorage.setItem('oracle_lang', 'ru'); /* oracle_intro_seen НЕ ставим — эмуляция закрытия на интро */ });
  });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  const introVisible = await page.locator('#intro .intro-track').count();
  const isLanguageOverlay = await page.locator('#intro [data-lang-sub]').count();
  ok('S1 повторный запуск (язык сохранён): интро показано', introVisible === 1, `#intro track count=${introVisible}`);
  ok('S1 это гайд-интро, а не повторный выбор языка', isLanguageOverlay === 0, `lang-sub count=${isLanguageOverlay}`);
  // Пройти интро до конца: кнопки Next/Start
  try {
    const btn = page.locator('[data-intro-start]');
    for (let i = 0; i < 6 && await btn.count(); i++) {
      await btn.first().click();
      await page.waitForTimeout(150);
    }
    const introGone = (await page.locator('#intro').count()) === 0;
    ok('S1 интро проходимо (Start снимает оверлей)', introGone);
  } catch (e) { ok('S1 интро проходимо (Start снимает оверлей)', false, e.message); }
  ok('S1 консоль чиста (сценарий 1)', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий 2: двойной тап по кнопке языка во время POST ——— */
{
  let profilePosts = 0;
  const { context, page, errors } = await freshPage(async (p) => {
    // ВАЖНО: один route на всё (последний зарегистрированный перехватывает
    // первым — раздельные обработчики на '**/api/profile' и '**/api/**'
    // пропускали POST мимо счётчика).
    await p.route('**/api/**', async (route) => {
      const url = route.request().url();
      const method = route.request().method();
      if (url.includes('/api/profile') && method === 'POST') {
        profilePosts++;
        await new Promise((r) => setTimeout(r, 350)); // держим POST висящим
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
        return;
      }
      if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, name: 'Тест', lang: 'ru', flags: {} }) }); return; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
  });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  const langOverlay = await page.locator('#intro [data-lang-sub]').count();
  ok('S2 первый запуск: показан оверлей выбора языка', langOverlay === 1, `count=${langOverlay}`);
  // Двойной тап + спам: всё синхронно в одном evaluate, пока POST висит.
  // click #1 — реальный путь (POST уходит, кнопки дизейблятся);
  // click #2 — нативный повторный тап (гасится disabled);
  // dispatchEvent x2 — сырой клик мимо disabled (гасится once-guard picked).
  await page.evaluate(() => {
    const b = document.querySelector('[data-lang="ru"]');
    b.click();
    b.click();
    b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    b.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
  await page.waitForTimeout(900);
  ok('S2 двойной тап: ровно один POST /api/profile', profilePosts === 1, `POSTs=${profilePosts}`);
  const introGuide = await page.locator('#intro .intro-dots').count();
  ok('S2 после выбора показан гайд-интро', introGuide === 1, `dots count=${introGuide}`);
  ok('S2 консоль чиста (сценарий 2)', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий 3: регресс первого запуска без POST-исказителей ——— */
{
  let profilePosts = 0;
  const { context, page, errors } = await freshPage(async (p) => {
    await p.route('**/api/**', async (route) => {
      const url = route.request().url();
      if (url.includes('/api/profile') && route.request().method() === 'POST') { profilePosts++; }
      if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ id: 1, name: 'Тест', lang: 'ru', flags: {} }) }); return; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
    });
  });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  const langOverlay = await page.locator('#intro [data-lang-sub]').count();
  ok('S3 чистый первый запуск: оверлей языка виден', langOverlay === 1, `count=${langOverlay}`);
  await page.locator('[data-lang="en"]').click();
  await page.waitForTimeout(500);
  ok('S3 одиночный тап EN: один POST /api/profile', profilePosts === 1, `POSTs=${profilePosts}`);
  ok('S3 консоль чиста (сценарий 3)', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

await browser.close();
server.close();
const failed = results.filter((r) => !r.pass).length;
console.log(`\nИтого: ${results.length - failed}/${results.length} PASS`);
process.exit(failed ? 1 : 0);
