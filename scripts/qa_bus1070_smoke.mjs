#!/usr/bin/env node
/* BUS-1070 e2e smoke: имплементация R06 в miniapp (mock API, без бэкенда).
 * §2 контракта: 25 видов S01–S30 (без S14/S30) рендерятся без ошибок консоли,
 * data-goto-навигация резолвится, live-маппинг (chart/tarot/widget-*) вызывает
 * реальные app-методы, токен-мост резолвит r06-переменные.
 * Запуск: node scripts/qa_bus1070_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18107';
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus741');
fs.mkdirSync(OUT, { recursive: true });
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome || ls ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1']).toString().trim();
const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};
const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json', '.woff2': 'font/woff2' };
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
await new Promise((r) => server.listen(18107, '127.0.0.1', r));
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const SHOP_BASE = () => JSON.stringify({
  current_plan: 'free', sub_active: false, sub_days_left: 0, crystals: 0,
  plans: [], products: {}, entitlements: [], catalog: { catalog_version: 'qa', plans: [], annual_plans: [], crystal_packs: [], products: [] }, current_entitlements: {},
});
const ME = () => JSON.stringify({ id: 1, name: 'Тест Тестов', lang: 'ru', flags: {}, birth_date: '1990-05-05', chart_mode: 'manual' });
const TG_MOCK = () => {
  window.Telegram = {
    WebApp: {
      ready: () => {}, expand: () => {}, setHeaderColor: () => {}, enableClosingConfirmation: () => {},
      viewportStableHeight: 667, viewportHeight: 667,
      initDataUnsafe: {}, initData: '', colorScheme: 'dark',
      onEvent: () => {}, offEvent: () => {}, HapticFeedback: { impactOccurred: () => {}, notificationOccurred: () => {}, selectionChanged: () => {} },
      openInvoice: () => {}, MainButton: { hide: () => {}, show: () => {}, onClick: () => {} },
    },
  };
};

async function freshPage() {
  const context = await browser.newContext({ viewport: { width: 375, height: 667 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org|Failed to load resource/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/shop')) { await route.fulfill({ status: 200, contentType: 'application/json', body: SHOP_BASE() }); return; }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME() }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '[{"id":"oracle","name":"Оракул","role":"Хранитель"},{"id":"astro","name":"Астролог","role":"Звёзды"},{"id":"tarot","name":"Мадам Ленорман","role":"Таролог"}]' }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', 'ru');
    localStorage.setItem('oracle_intro_seen', '1');
  });
  await page.goto(`${BASE}/?qa=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  return { context, page, errors };
}

/* ── 1. Реестр views: все 25 заявленных существуют и рендерятся без JS-ошибок ── */
{
  const { context, page, errors } = await freshPage();
  const views = await page.evaluate(() => {
    const out = {};
    const names = ['session-expired', 'auth-error', 'welcome', 'onboarding', 'chat-empty', 'chat-dialog',
      'sessions', 'agent-select', 'tool-catalog', 'tool-quick', 'tool-form', 'tool-run', 'result',
      'tarot-question', 'tarot-reveal', 'tarot-zoom', 'tarot-reading', 'synastry', 'vedic', 'widgets',
      'today', 'library', 'profile', 'memory', 'notifications', 'plan', 'paywall', 'pay-pending', 'orders',
      'tarot-grid', 'states'];
    const main = document.getElementById('app-main');
    for (const n of names) {
      try {
        const fn = app._r06 && app._r06.views[n];
        if (typeof fn !== 'function') { out[n] = 'missing'; continue; }
        main.innerHTML = '';
        fn(main);
        out[n] = main.innerHTML.length > 40 ? 'ok' : 'empty';
      } catch (e) { out[n] = 'throws: ' + e.message; }
    }
    return out;
  });
  const bad = Object.entries(views).filter(([, v]) => v !== 'ok');
  ok(`§2: все ${Object.keys(views).length} r06-views рендерятся`, bad.length === 0, bad.length ? JSON.stringify(Object.fromEntries(bad)) : `${Object.keys(views).length}/${Object.keys(views).length} ok`);
  ok('§2: рендер views без pageerror', errors.length === 0, errors.slice(0, 3).join(' | '));
  await context.close();
}

/* ── 2. data-goto-навигация: клики по реальной разметке резолвятся ── */
{
  const { context, page, errors } = await freshPage();
  const nav = await page.evaluate(() => {
    const main = document.getElementById('app-main');
    const visited = [];
    const probe = (view) => {
      const fn = app._r06.views[view];
      if (fn) fn(main);
      const btns = [...main.querySelectorAll('[data-goto]')];
      const targets = btns.map((b) => b.getAttribute('data-goto')).filter((t, i, a) => a.indexOf(t) === i);
      for (const t of targets) {
        visited.push(view + ' → ' + t);
        if (t.startsWith('ob-step-')) {
          if (!app._r06.views['onboarding']) return 'no onboarding view';
          continue;
        }
        const live = ['home', 'hub', 'profile', 'payment', 'chat', 'chart', 'tarot', 'widget-moon', 'widget-palm', 'widget-matrix', 'widget-career'];
        const resolved = live.includes(t) || (app._r06 && app._r06.views[t]) || typeof app[t] === 'function';
        if (!resolved) return 'UNRESOLVED: ' + t;
      }
      return null;
    };
    for (const v of ['welcome', 'tool-catalog', 'today', 'library', 'profile', 'plan', 'widgets', 'tarot-reveal', 'tarot-question', 'result', 'states', 'paywall', 'orders', 'memory', 'notifications']) {
      const err = probe(v);
      if (err) return err;
    }
    return null;
  });
  ok('§4: все data-goto-таргеты резолвятся', nav === null, nav || 'все резолвятся');
  ok('§4: навигационные пробы без pageerror', errors.length === 0, errors.slice(0, 3).join(' | '));
  await context.close();
}

/* ── 3. Токен-мост: r06-переменные резолвятся в computed styles ── */
{
  const { context, page } = await freshPage();
  const tokens = await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'btn-primary';
    probe.style.display = 'none';
    document.body.appendChild(probe);
    const cs = getComputedStyle(probe);
    const out = { bg: cs.backgroundImage, color: cs.color };
    const vars = ['--color-bg', '--color-surface', '--color-surface-raised', '--color-surface-overlay', '--color-accent-hover', '--color-border-control', '--color-text-error', '--shadow-overlay'];
    out.vars = Object.fromEntries(vars.map((v) => [v, getComputedStyle(document.documentElement).getPropertyValue(v).trim()]));
    probe.remove();
    return out;
  });
  ok('§5: btn-primary рендерит live-градиент', /rgb\(/.test(tokens.bg) && tokens.bg !== 'none', tokens.bg);
  ok('§5: все 8 алиас-переменных резолвятся', Object.values(tokens.vars).every((v) => v.length > 0), JSON.stringify(tokens.vars));
  await context.close();
}

/* ── 4. Live-маппинг: data-goto="chart" открывает чат астролога (мок) ── */
{
  const { context, page, errors } = await freshPage();
  app: {
    await page.evaluate(() => {
      app._r06.views['welcome'](document.getElementById('app-main'));
    });
    const chartBtn = await page.$('[data-goto="chart"]');
    ok('§4: welcome рендерит data-goto="chart"', !!chartBtn);
    if (chartBtn) {
      await page.evaluate(() => { app.openChat = new Proxy(app.openChat, { apply: (t, self2, args) => { window.__openChatCalled = args[0]; return Reflect.apply(t, self2, args); } }); });
      await chartBtn.click();
      await page.waitForTimeout(300);
      const called = await page.evaluate(() => window.__openChatCalled);
      ok('§4: клик data-goto="chart" вызывает openChat("astro")', called === 'astro', 'called=' + called);
    }
    ok('§4: live-маппинг без pageerror', errors.length === 0, errors.slice(0, 3).join(' | '));
  }
  await context.close();
}

/* ── 5. Onboarding wizard: ob-step-N меняет dataset и перерисовывает ── */
{
  const { context, page, errors } = await freshPage();
  await page.evaluate(() => {
    app._r06.views['onboarding'](document.getElementById('app-main'));
  });
  const step2 = await page.evaluate(() => {
    const main = document.getElementById('app-main');
    main.dataset.obStep = '2';
    app._r06.views['onboarding'](main);
    return { step: main.dataset.obStep, hasSeg: !!main.querySelector('.seg-progress'), text: main.textContent.includes('дата рождения') };
  });
  ok('§3: onboarding шаг 2 рендерится (seg-progress, контент)', step2.hasSeg && step2.step === '2', JSON.stringify(step2));
  await page.screenshot({ path: path.join(OUT, 'bus1070-onboarding-step2.png'), fullPage: false });
  ok('§3: onboarding wizard без pageerror', errors.length === 0, errors.slice(0, 3).join(' | '));
  await context.close();
}

/* ── 6. Экранные скриншоты ключевых видов (мобильный 375px, тёмная тема) ── */
{
  const { context, page } = await freshPage();
  const shots = [['welcome', 'S01'], ['today', 'S15'], ['library', 'S20'], ['profile', 'S21'], ['plan', 'S24'], ['tarot-grid', 'S13'], ['states', 'matrix'], ['tool-quick', 'S11a'], ['result', 'S12'], ['tarot-reveal', 'S13b']];
  for (const [view, tag] of shots) {
    await page.evaluate((v) => { app._r06.views[v](document.getElementById('app-main')); }, view);
    await page.waitForTimeout(150);
    await page.screenshot({ path: path.join(OUT, `bus1070-${view}.png`), fullPage: false });
  }
  ok('§6: скриншоты 10 ключевых видов сохранены', fs.readdirSync(OUT).filter((f) => f.startsWith('bus1070-') && f.endsWith('.png')).length >= 11);
  await context.close();
}

await browser.close();
server.close();
const fails = results.filter((r) => !r.pass).length;
console.log(`\n${results.length - fails}/${results.length} passed`);
process.exitCode = fails ? 1 : 0;
