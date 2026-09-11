#!/usr/bin/env node
/* BUS-993 perf-замеры §4.1 спеки R05 (mock API, без бэкенда).
 * Метрики:
 *  - число одновременно анимирующихся слоёв фона на состояние (бюджет ≤2)
 *  - keyframes новых правил — только opacity/transform (код-ревью, отдельный греп)
 *  - FPS за 8 с на desktop-viewport и mobile-viewport (DevTools Performance вручную
 *    не доступен в headless, поэтому rAF-проба; порог ≥55 desktop / ≥50 mobile)
 *  - длительность фреймов при скролле чата (jank: >3 подряд фреймов >33 мс)
 *  - CPU sky-системы: дельта SystemInfo.getCPUUsage на welcome (живой космос)
 *    и chat (статичный фон), % одного ядра (CDP; при отсутствии метода — available:false)
 * Запуск: node scripts/qa_bus993_perf.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18096';
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus993');
fs.mkdirSync(OUT, { recursive: true });
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || ls ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1']).toString().trim();
const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json', '.woff2': 'font/woff2' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, BASE).pathname);
  if (p.startsWith('/static/')) p = p.slice('/static/'.length); else p = '/index.html';
  const file = path.join(MINIAPP, p.split('?')[0].replace(/^\//, ''));
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('nf'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});
await new Promise((r) => server.listen(18096, '127.0.0.1', r));
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const SHOP_BASE = () => JSON.stringify({ current_plan: 'free', sub_active: false, sub_days_left: 0, crystals: 0, plans: [], products: {}, entitlements: [], catalog: { catalog_version: 'x', price_book_version: 'x', plans: [], annual_plans: [], crystal_packs: [], products: [], current_entitlements: { tier: 'free', status: 'free', ai_message_limit: 0, ai_messages_used: 0, crystals: 0 } }, current_entitlements: {} });
const ME = () => JSON.stringify({ id: 1, name: 'Тест Тестов', lang: 'ru', flags: {}, birth_date: '1990-05-05', chart_mode: 'manual' });
const AGENTS = () => JSON.stringify([{ code: 'oracle', name: 'Лилит', title: 'Личный оракул', emoji: '🌙', tagline: 'т' }, { code: 'tarot', name: 'Мадам Ленорман', title: 'Таролог', emoji: '🃏', tagline: 'т' }]);
const TG_MOCK = () => { window.Telegram = { WebApp: { ready: () => {}, expand: () => {}, setHeaderColor: () => {}, viewportStableHeight: 667, viewportHeight: 667, initDataUnsafe: {}, initData: '', colorScheme: 'dark', onEvent: () => {}, offEvent: () => {}, openInvoice: () => {} } }; };

async function freshPage({ width, height }) {
  const context = await browser.newContext({ viewport: { width, height }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  await page.route('**/telegram.org/**', (r) => r.abort());
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/shop')) { await route.fulfill({ status: 200, contentType: 'application/json', body: SHOP_BASE() }); return; }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME() }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: AGENTS() }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => { localStorage.clear(); localStorage.setItem('oracle_lang', 'ru'); localStorage.setItem('oracle_intro_seen', '1'); });
  await page.goto(`${BASE}/?qa=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  return { context, page };
}

// Число элементов фона с активной (running) CSS-анимацией
const animCount = (page) => page.evaluate(() => {
  const sels = ['.starfield', '.starfield::before', '.starfield .nebula', '.starfield .galaxy', '.starfield .lilith-sil', '.meteor', '.twinkle', '.constellations .cst'];
  let running = 0; const details = [];
  for (const sel of sels) {
    document.querySelectorAll(sel).forEach((el) => {
      const cs = getComputedStyle(el);
      const name = cs.animationName;
      const dur = parseFloat(cs.animationDuration) || 0;
      const iter = cs.animationIterationCount;
      if (name && name !== 'none' && dur > 0 && (iter === 'infinite' || parseFloat(iter) > 0)) {
        const state = el.getAnimations ? el.getAnimations().some((a) => a.playState === 'running') : true;
        if (state) { running++; details.push(sel); }
      }
    });
  }
  // псевдоэлементы ::before/::after звёздного слоя не попадают в querySelectorAll — считаем по getAnimations документа
  let pseudo = 0;
  document.querySelectorAll('.starfield').forEach((el) => {
    (el.getAnimations ? el.getAnimations({ subtree: true }) : []).forEach((a) => {
      if (a instanceof CSSAnimation && a.playState === 'running' && /starDrift|twinkle|cstBlink/.test(a.animationName)) pseudo++;
    });
  });
  return { running, pseudo, details };
});

async function measureFps(page, ms) {
  return page.evaluate((ms) => new Promise((resolve) => {
    let frames = 0; const start = performance.now();
    const tick = () => {
      frames++;
      if (performance.now() - start < ms) requestAnimationFrame(tick);
      else resolve({ frames, elapsed: performance.now() - start, fps: Math.round((frames / (performance.now() - start)) * 1000) });
    };
    requestAnimationFrame(tick);
  }), ms);
}

async function measureScrollJank(page) {
  // скроллим чат 3 с, собираем длительности фреймов через rAF-дельты
  const before = await page.evaluate(() => { const b = document.querySelector('.chat-messages') || document.querySelector('.screen'); if (b) b.scrollTop = 0; return true; });
  const deltas = await page.evaluate(() => new Promise((resolve) => {
    const ds = []; let last = performance.now(); const start = last;
    const box = document.querySelector('.chat-messages') || document.querySelector('.screen');
    const tick = () => {
      const now = performance.now();
      ds.push(now - last); last = now;
      if (box) box.scrollTop = ((now - start) / 8) % Math.max(200, box.scrollHeight - box.clientHeight);
      if (now - start < 3000) requestAnimationFrame(tick); else resolve(ds);
    };
    requestAnimationFrame(tick);
  }));
  let worstRun = 0, run = 0;
  for (const d of deltas) { if (d > 33) { run++; worstRun = Math.max(worstRun, run); } else run = 0; }
  return { jankRuns: worstRun, maxFrame: Math.round(Math.max(...deltas) * 10) / 10, avgFrame: Math.round((deltas.reduce((a, b) => a + b, 0) / deltas.length) * 10) / 10 };
}

// CPU sky-системы: CDP Performance.getMetrics — дельта TaskDuration (main-thread
// задачи рендерера) на интервале, % одного ядра. Без синтетического скролла —
// чистая нагрузка фоном. CSS-анимации opacity/transform идут на композиторе,
// поэтому ожидание: близко к 0.
async function measureCpu(page, ms) {
  const session = await page.context().newCDPSession(page);
  await session.send('Performance.enable').catch(() => {});
  const probe = async () => {
    try {
      const { metrics } = await session.send('Performance.getMetrics');
      const get = (n) => metrics.find((m) => m.name === n)?.value ?? null;
      return { TaskDuration: get('TaskDuration'), ScriptDuration: get('ScriptDuration') };
    } catch { return null; }
  };
  const m0 = await probe();
  await page.waitForTimeout(ms);
  const m1 = await probe();
  await session.detach().catch(() => {});
  const wall = ms / 1000;
  if (!m0 || !m1 || m0.TaskDuration === null || m1.TaskDuration === null) return { available: false };
  const d = m1.TaskDuration - m0.TaskDuration;
  return {
    available: true,
    metric: 'renderer-main TaskDuration (CDP Performance.getMetrics)',
    taskDurationDeltaSec: Math.round(d * 1000) / 1000,
    wallSec: wall,
    mainTaskCpuPercent: Math.max(0, Math.round((d / wall) * 1000) / 10),
    scriptDurationDeltaSec: Math.round(((m1.ScriptDuration ?? 0) - (m0.ScriptDuration ?? 0)) * 1000) / 1000,
  };
}

const report = {};
for (const vp of [{ label: 'mobile', width: 390, height: 844 }, { label: 'desktop', width: 1440, height: 900 }]) {
  const { context, page } = await freshPage(vp);
  // welcome
  await page.evaluate(() => app.closeChat && app.closeChat());
  await page.evaluate(() => app.go('home'));
  await page.waitForTimeout(300);
  const wAnim = await animCount(page);
  const wFps = await measureFps(page, 8000);
  const wCpu = await measureCpu(page, 4000);
  // chat
  await page.evaluate(() => app.openChat('oracle'));
  await page.waitForTimeout(400);
  const cAnim = await animCount(page);
  const cFps = await measureFps(page, 8000);
  const jank = await measureScrollJank(page);
  const cCpu = await measureCpu(page, 4000);
  // work
  await page.evaluate(() => { app.closeChat(); app.go('profile'); });
  await page.waitForTimeout(400);
  const kAnim = await animCount(page);
  // tarot
  await page.evaluate(() => app.openChat('tarot'));
  await page.waitForTimeout(400);
  const tAnim = await animCount(page);
  report[vp.label] = {
    welcome: { running: wAnim.running + wAnim.pseudo, details: wAnim.details, fps: wFps.fps, cpu: wCpu },
    chat: { running: cAnim.running + cAnim.pseudo, details: cAnim.details, fps: cFps.fps, scrollJank: jank, cpu: cCpu },
    work: { running: kAnim.running + kAnim.pseudo },
    tarot: { running: tAnim.running + tAnim.pseudo },
  };
  await context.close();
}
console.log(JSON.stringify(report, null, 1));
fs.writeFileSync(path.join(OUT, 'perf-bus993.json'), JSON.stringify(report, null, 1));
await browser.close();
server.close();
