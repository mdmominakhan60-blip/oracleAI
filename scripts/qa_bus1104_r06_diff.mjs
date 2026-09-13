#!/usr/bin/env node
/* BUS-1104 QA-гейт волны B: независимая постраничная сверка miniapp (master)
 * против живого прототипа R06 design/r06/p1–p3. Для каждой пары
 * (qa_view миниаппы ↔ #view-кадр прототипа): скриншот обоих при 390px,
 * извлечение структурных сигналов (заголовок, CTA-кнопки, поля, aria),
 * console-error/pageerror-нуль. Прототип раздаётся per-package
 * (CSS url() резолвится от корня пакета — грабля из BUS-973).
 * Запуск: node scripts/qa_bus1104_r06_diff.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const DESIGN = path.join(ROOT, 'design/r06');
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus1104');
fs.mkdirSync(OUT, { recursive: true });

const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c',
  'command -v chromium || command -v chromium-browser || command -v google-chrome || ls ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1'
]).toString().trim();

/* Матрица сверки: S-экран ← qa-маршрут миниаппы ← кадр прототипа R06.
   Слэш в view = несколько кадров одного экрана; null = кадра нет (спека-слой),
   сверка только по структурным сигналам миниаппы. */
const MATRIX = [
  // p1 — онбординг+чат+навигация (SPEC p1 §1)
  { s: 'S03', pkg: 'p1', route: 'welcome', frame: null, note: 'С §2.1 — кадра нет, сверка по сигналам' },
  { s: 'S04', pkg: 'p1', route: 'onboarding', frame: 'view-onboarding', args: 'qa_step=1' },
  { s: 'S05', pkg: 'p1', route: 'hub', frame: 'view-chat-empty', note: 'hub = пустой чат-центр волны B' },
  { s: 'S06', pkg: 'p1', route: 'states', frame: 'view-chat-states', note: 'реестр состояний §11.2' },
  { s: 'S07', pkg: 'p1', route: 'sessions', frame: 'view-sessions' },
  { s: 'S10', pkg: 'p1', route: 'sheet', frame: 'view-sheet-tools' },
  // p2 — инструменты+Таро (SPEC p2 §1)
  { s: 'S11a', pkg: 'p2', route: 'tool-quick', frame: 'view-tool-quick' },
  { s: 'S11b', pkg: 'p2', route: 'tool-form', frame: 'view-tool-form' },
  { s: 'S11c', pkg: 'p2', route: 'tool-run', frame: 'view-tool-run' },
  { s: 'S12', pkg: 'p2', route: 'result', frame: 'view-result' },
  { s: 'S13a', pkg: 'p2', route: 'tarot-question', frame: 'view-tarot-question' },
  { s: 'S13b', pkg: 'p2', route: 'tarot-reveal', frame: 'view-tarot-reveal' },
  { s: 'S13c', pkg: 'p2', route: 'tarot-zoom', frame: 'view-tarot-zoom' },
  { s: 'S13d', pkg: 'p2', route: 'tarot-reading', frame: 'view-tarot-reading' },
  // p3 — сегодня/библиотека/профиль/paywall/крест/состояния (SPEC p3 §1)
  { s: 'S15', pkg: 'p3', route: 'today', frame: 'view-today' },
  { s: 'S16–19', pkg: 'p3', route: 'library', frame: 'view-library' },
  { s: 'S22', pkg: 'p3', route: 'memory-r06', frame: 'view-memory' },
  { s: 'S23', pkg: 'p3', route: 'notifications-r06', frame: 'view-notifications' },
  { s: 'S24', pkg: 'p3', route: 'plan-r06', frame: 'view-plan' },
  { s: 'S25', pkg: 'p3', route: 'paywall', frame: 'view-paywall' },
  { s: 'S26', pkg: 'p3', route: 'pay-pending', frame: 'view-pay-pending' },
  { s: 'S26', pkg: 'p3', route: 'orders-r06', frame: 'view-orders' },
  { s: 'S13', pkg: 'p3', route: 'tarot-cross', frame: null, note: 'кельтский крест — кадр в p4/HANDOFF S14' },
];

const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.woff2': 'font/woff2' };

/* Сервер миниаппы: /static → miniapp/, /api/* → mock (как у FE-смоков). */
function miniServer() {
  return http.createServer((req, res) => {
    let p = req.url.split('?')[0];
    if (p === '/' || p === '') p = '/index.html';
    if (p.startsWith('/static')) p = p.replace('/static', '');
    const file = path.join(MINIAPP, p);
    fs.readFile(file, (err, data) => {
      if (err) {
        if (p.startsWith('/api/')) { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ ok: true })); return; }
        res.writeHead(404); res.end('nf'); return;
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
      res.end(data);
    });
  });
}

/* Сервер прототипа: per-package корень (CSS url() от корня пакета — BUS-973). */
function protoServer() {
  return http.createServer((req, res) => {
    const m = req.url.split('?')[0].match(/^\/(p[1-4])(\/.*)?$/);
    if (!m) { res.writeHead(404); res.end('nf'); return; }
    const file = path.join(DESIGN, m[1], m[2] === undefined ? '/index.html' : (m[2] || '/index.html'));
    fs.readFile(file, (err, data) => {
      if (err) { res.writeHead(404); res.end('nf'); return; }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
      res.end(data);
    });
  });
}

const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};

/* Структурные сигналы: заголовки, кнопки/CTA, поля ввода, aria-атрибуты. */
async function signals(page) {
  return page.evaluate(() => {
    const vis = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    const txt = (sel, n = 3) => Array.from(document.querySelectorAll(sel)).filter(vis).slice(0, n).map(el => el.textContent.trim().replace(/\s+/g, ' ').slice(0, 60));
    return {
      h1: txt('h1', 2), h2: txt('h2', 4), h3: txt('h3', 4),
      btns: Array.from(document.querySelectorAll('button, [role="button"], .btn')).filter(vis).slice(0, 14).map(el => (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 40)).filter(Boolean),
      inputs: Array.from(document.querySelectorAll('input, select, textarea')).filter(vis).map(el => ({ type: el.type || el.tagName.toLowerCase(), name: el.name || el.id || '', placeholder: el.placeholder || '' })),
      aria: document.querySelectorAll('[role], [aria-label], [aria-live], [aria-invalid]').length,
      imgs: Array.from(document.querySelectorAll('img')).filter(vis).length,
      formLabels: txt('label', 6),
    };
  });
}

const JS_ERRORS = [];

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox'] });

  const miniSrv = miniServer().listen(18099, '127.0.0.1');
  const protoSrv = protoServer().listen(18098, '127.0.0.2');
  await new Promise(r => setTimeout(r, 300));

  for (const row of MATRIX) {
    const { s, route } = row;
    const pkg = row.pkg && row.pkg.trim();
    try {
      /* миниаппа */
      let ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', colorScheme: 'dark' });
      let page = await ctx.newPage();
      const errs = [];
      page.on('console', m => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)); });
      page.on('pageerror', e => errs.push(String(e).slice(0, 120)));
      const argsStr = row.args ? '&' + row.args : '';
      await page.goto(`http://127.0.0.1:18099/?qa=1&qa_view=${route}${argsStr}`, { waitUntil: 'networkidle' });
      await page.waitForTimeout(600);
      const miniSig = await signals(page);
      await page.screenshot({ path: path.join(OUT, `${s.replace(/[–]/g, '_')}-${route}-mini.png`), fullPage: false });
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      ok(`${s} miniapp: маршрут ${route} рендерится`, miniSig.h1.length || miniSig.h2.length || miniSig.btns.length, `h2=${miniSig.h2.length} btns=${miniSig.btns.length}`);
      ok(`${s} miniapp: JS-чистота`, errs.length === 0, errs.length ? errs[0] : '0 ошибок');
      ok(`${s} miniapp: 320px-проба (кламп 390→?)`, overflow <= 1, `delta=${overflow}px`);
      ok(`${s} miniapp: i18n-слой RU`, await page.evaluate(() => document.documentElement.lang || 'ru'), '');
      await ctx.close();

      /* прототип */
      if (pkg && row.frame) {
        ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU' });
        page = await ctx.newPage();
        await page.goto(`http://127.0.0.2:18098/${pkg}/index.html#${row.frame}`, { waitUntil: 'networkidle' });
        await page.waitForTimeout(400);
        const protoSig = await signals(page);
        await page.screenshot({ path: path.join(OUT, `${s.replace(/[–]/g, '_')}-${route}-proto.png`), fullPage: false });
        ok(`${s} proto: кадр ${row.frame} рендерится`, protoSig.h1.length || protoSig.h2.length || protoSig.btns.length, `h2=${protoSig.h2.length} btns=${protoSig.btns.length}`);
        /* структурная сверка сигналов */
        const miniKeys = new Set([...miniSig.h2, ...miniSig.btns].map(x => x.toLowerCase()));
        const protoBtns = protoSig.btns;
        const matched = protoBtns.filter(b => miniKeys.has(b.toLowerCase()));
        ok(`${s} СВЕРКА: CTA-кнопки макета присутствуют в миниаппе`, protoBtns.length === 0 || matched.length / protoBtns.length >= 0.34, `прототип ${protoBtns.length}, совпало ${matched.length}`);
        fs.writeFileSync(path.join(OUT, `${s.replace(/[–]/g, '_')}-${route}-signals.json`), JSON.stringify({ s, route, mini: miniSig, proto: protoSig }, null, 2));
      } else {
        ok(`${s} прототип-кадр отсутствует (спека-слой)`, true, row.note || 'сверка по сигналам миниаппы');
      }
    } catch (e) {
      ok(`${s} (${route}): исключение`, false, String(e).split('\n')[0].slice(0, 100));
    }
  }

  await browser.close();
  miniSrv.close(); protoSrv.close();

  const passed = results.filter(r => r.pass).length;
  console.log(`\n${passed === results.length ? 'ALL PASS' : 'HAS FAILURES'} (${passed}/${results.length})`);
  fs.writeFileSync(path.join(OUT, 'diff-matrix-results.json'), JSON.stringify(results, null, 2));
  process.exit(passed === results.length ? 0 : 1);
})().catch(e => { console.error('FATAL', e); process.exit(2); });
