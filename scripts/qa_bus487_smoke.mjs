#!/usr/bin/env node
/* BUS-487 e2e smoke: два фикса из ревью BUS-397 (non-blocking).
 * A. savedLocal-ветка: язык сохранён, oracle_intro_seen нет → интро должно показаться.
 * B. Двойной тап по кнопке языка во время await POST → ровно один POST /api/profile.
 * Страница открывается локально, API-роуты мокаются через page.route — DEV_KEY не нужен.
 * Запуск: node scripts/qa_bus487_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '../miniapp');
const PORT = 18097;
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome']).toString().trim();

const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond, extra });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};

// Статик-сервер miniapp (без Telegram env: tg() undefined → mintSession не идёт).
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.webp': 'image/webp' };
const server = createServer(async (req, res) => {
  try {
    let p = decodeURIComponent(req.url.split('?')[0]);
    if (p === '/') p = '/index.html';
    // Прод-маппинг: /static/* → miniapp/* (index.html грузит /static/js/…, /static/dist/…).
    if (p.startsWith('/static/')) p = p.slice('/static'.length);
    const file = await readFile(path.join(ROOT, p));
    res.writeHead(200, { 'Content-Type': mime[path.extname(p)] || 'application/octet-stream' });
    res.end(file);
  } catch (e) { res.writeHead(404); res.end('not found'); }
});
await new Promise((r) => server.listen(PORT, '127.0.0.1', r));
const BASE = `http://127.0.0.1:${PORT}`;

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
let failed = 0;
try {
  // ─── Сценарий A: savedLocal-ветка показывает интро ───
  {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', colorScheme: 'dark' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()); });

    // Мокаем API: /api/me и прочие GET — иначе renderAuthRequired заменит экран.
    let postProfileCount = 0;
    await page.route('**/api/**', async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() === 'POST' && url.pathname === '/api/profile') postProfileCount++;
      if (url.pathname === '/api/me') return route.fulfill({ json: { id: 1, name: 'QA User', lang: 'ru', flags: {} } });
      if (url.pathname === '/api/agents' || url.pathname.startsWith('/api/today') || url.pathname.startsWith('/api/spread')) return route.fulfill({ json: {} });
      return route.fulfill({ status: 200, json: {} });
    });

    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      // Язык выбран, но Mini App закрыли на интро: oracle_intro_seen не проставился.
      localStorage.setItem('oracle_lang', 'ru');
      localStorage.removeItem('oracle_intro_seen');
    });
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(600);

    // maybeIntro рендерит #intro (без класса .intro — класс только у language-оверлея).
    const introVisible = await page.locator('#intro .intro-slide').count();
    ok('A1: интро показывается при сохранённом языке без oracle_intro_seen', introVisible >= 3, `slides=${introVisible}`);
    const overlayButtons = await page.locator('.lang-pick-btns button').count();
    ok('A2: оверлей выбора языка НЕ показывается (язык сохранён)', overlayButtons === 0, `langBtns=${overlayButtons}`);

    // A3: с oracle_intro_seen интро НЕ показывается (нет регресса гейта).
    await page.evaluate(() => localStorage.setItem('oracle_intro_seen', '1'));
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    const introGone = await page.locator('#intro').count();
    ok('A3: oracle_intro_seen=1 → интро скрыто (гейт цел)', introGone === 0, `count=${introGone}`);
    ok('A: console чист (A-сценарий)', errors.length === 0, errors.slice(0, 3).join(' | '));
    await context.close();
  }

  // ─── Сценарий B: двойной тап → ровно один POST /api/profile ───
  {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', colorScheme: 'dark' });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
    page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()); });

    let postProfileCount = 0;
    let postDelay = 0;
    await page.route('**/api/**', async (route) => {
      const url = new URL(route.request().url());
      const method = route.request().method();
      if (method === 'POST' && url.pathname === '/api/profile') {
        postProfileCount++;
        if (postDelay) await new Promise((r) => setTimeout(r, postDelay));
        return route.fulfill({ json: { ok: true } });
      }
      if (url.pathname === '/api/me') return route.fulfill({ json: { id: 2, name: 'QA User', lang: 'ru', flags: {} } });
      return route.fulfill({ status: 200, json: {} });
    });

    await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' });
    await page.evaluate(() => {
      localStorage.removeItem('oracle_lang');
      localStorage.removeItem('oracle_intro_seen');
    });
    await page.reload({ waitUntil: 'networkidle' });

    // Оверлей выбора языка показан, POST задержан на 400ms — окно для двойного тапа.
    const btnRu = page.locator('.lang-pick-btns button[data-lang="ru"]');
    await btnRu.waitFor({ state: 'visible', timeout: 4000 });
    postDelay = 400;
    // Первый тап — реальный клик.
    await btnRu.click();
    const isDisabledAfterFirst = await btnRu.evaluate((b) => b.disabled);
    ok('B0: кнопки disabled сразу после первого тапа (гвардия активна)', isDisabledAfterFirst === true, `disabled=${isDisabledAfterFirst}`);
    const enDisabled = await page.locator('.lang-pick-btns button[data-lang="en"]').evaluate((b) => b.disabled);
    ok('B0b: соседняя кнопка тоже disabled', enDisabled === true, `disabled=${enDisabled}`);
    // Реальный повторный тап: браузер не диспатчит click на disabled-кнопке,
    // playwright-клик зависает на enabled-гейте (или элемент уже detached) —
    // ровно это и происходит с настоящим двойным тапом пользователя.
    const secondTapBlocked = await btnRu.click({ timeout: 1200 }).then(() => false, () => true);
    ok('B1a: повторный тап во время POST не срабатывает (disabled)', secondTapBlocked === true);
    await page.waitForTimeout(900);

    ok('B1: двойной тап во время POST → ровно один POST /api/profile', postProfileCount === 1, `posts=${postProfileCount}`);
    const langSaved = await page.evaluate(() => localStorage.getItem('oracle_lang'));
    ok('B2: язык сохранён после выбора', langSaved === 'ru', `oracle_lang=${langSaved}`);
    const disabledDuringFlight = await page.evaluate(() => {
      // воспроизводим состояние повторно: после ответа кнопки не обязаны быть живы
      // (оверлей удалён), поэтому проверяем инвариант через сам факт единственного POST.
      return true;
    });
    ok('B3: оверлей закрылся после выбора (boot продолжился)', (await page.locator('.lang-pick-btns').count()) === 0);
    ok('B: console чист (B-сценарий)', errors.length === 0, errors.slice(0, 3).join(' | '));
    await context.close();
  }
} finally {
  server.close();
  await browser.close();
}

failed = results.filter((r) => !r.pass).length;
console.log(`\n${results.filter((r) => r.pass).length}/${results.length} passed`);
process.exit(failed ? 1 : 0);
