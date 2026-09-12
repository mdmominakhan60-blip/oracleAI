// BUS-973 фаза 4 — независимая QA-проверка R06 (p1/p2/p3)
// Проверки: загрузка 0 ошибок консоли, хеш-навигация, DOM-пробы, 320px overflow, bg-состояния
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v google-chrome-stable || command -v chromium']).toString().trim();

const results = [];
function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ' — ' + detail : ''}`);
}

// static file server: корень = каталог пакета (probe-http.html: base=http://127.0.0.1:8741/index.html)
const server = http.createServer((req, res) => {
  const pkgMatch = req.url.match(/^\/(p[123])(\/.*)$/);
  const pkg = pkgMatch ? pkgMatch[1] : 'p1';
  const urlPath = decodeURIComponent((pkgMatch ? pkgMatch[2] : req.url).split('?')[0]);
  let fsPath = path.join(ROOT, 'design/r06', pkg, urlPath);
  if (urlPath.endsWith('/')) fsPath = path.join(fsPath, 'index.html');
  try {
    const data = fs.readFileSync(fsPath);
    const ext = path.extname(fsPath);
    const mime = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.jpg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp' }[ext] || 'application/octet-stream';
    res.writeHead(200, { 'Content-Type': mime });
    res.end(data);
  } catch {
    res.writeHead(404); res.end('not found');
  }
});
await new Promise(r => server.listen(0, '127.0.0.1', r));
const port = server.address().port;
const base = `http://127.0.0.1:${port}`;

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const PKGS = ['p1', 'p2', 'p3'];

for (const pkg of PKGS) {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  const consoleErrors = [];
  const failedRequests = [];
  page.on('console', m => {
    if (m.type() !== 'error') return;
    const t = m.text();
    if (t.includes('favicon') || t.includes('the server responded with a status of 404')) return;
    consoleErrors.push(t);
  });
  page.on('response', r => { if (r.status() >= 400 && !r.url().includes('favicon')) failedRequests.push(`${r.status()} ${r.url()}`); });

  // 1. Загрузка без ошибок
  await page.goto(`${base}/${pkg}/index.html`, { waitUntil: 'networkidle' });
  check(`${pkg}: загрузка без 4xx/5xx`, failedRequests.length === 0, failedRequests.join('; ') || 'все запросы ok');
  check(`${pkg}: консоль без ошибок`, consoleErrors.length === 0, consoleErrors.slice(0, 3).join('; ') || 'чисто');

  // 2. Все view существуют и только один активен по умолчанию
  const viewInfo = await page.evaluate(() => {
    const views = [...document.querySelectorAll('.screen-view')];
    return { total: views.length, ids: views.map(v => v.id), active: views.filter(v => v.classList.contains('is-active')).map(v => v.id) };
  });
  check(`${pkg}: view инвентарь`, viewInfo.total > 0, `${viewInfo.total} view: ${viewInfo.ids.join(', ')}`);
  check(`${pkg}: ровно 1 активный view по умолчанию`, viewInfo.active.length === 1, viewInfo.active.join(','));

  // 3. Хеш-навигация: прямой переход на каждый view
  let hashOk = 0; let hashFail = [];
  for (const id of viewInfo.ids) {
    const short = id.replace('view-', '');
    await page.goto(`${base}/${pkg}/index.html#${id}`, { waitUntil: 'load' });
    const active = await page.evaluate(() => document.querySelector('.screen-view.is-active')?.id || '(none)');
    if (active === id) hashOk++; else hashFail.push(`${short}→${active}`);
  }
  check(`${pkg}: хеш-навигация ${hashOk}/${viewInfo.ids.length}`, hashFail.length === 0, hashFail.join('; ') || 'все view доступны по прямой ссылке');

  // 4. data-bg состояния на sky
  const bgProbe = await page.evaluate(() => {
    const sky = document.getElementById('sky');
    return sky ? (sky.dataset.bg || '(no data-bg)') : '(no #sky)';
  });
  check(`${pkg}: #sky data-bg задан`, /^(welcome|chat|tarot|work)$/.test(bgProbe), `data-bg=${bgProbe}`);

  // 5. 320px probe — отсутствие горизонтального переполнения на всех view
  const ctx320 = await browser.newContext({ viewport: { width: 320, height: 568 } });
  const page320 = await ctx320.newPage();
  await page320.goto(`${base}/${pkg}/index.html`, { waitUntil: 'networkidle' });
  let overflowViews = [];
  for (const id of viewInfo.ids) {
    await page320.evaluate(v => { location.hash = v; }, id);
    await page320.waitForTimeout(150);
    const ov = await page320.evaluate(() => {
      const d = document.documentElement;
      return { scrollW: d.scrollWidth, clientW: d.clientWidth };
    });
    if (ov.scrollW > ov.clientW + 1) overflowViews.push(`${id} (${ov.scrollW}>${ov.clientW})`);
  }
  check(`${pkg}: 320px без горизонтального overflow`, overflowViews.length === 0, overflowViews.join('; ') || `${viewInfo.ids.length} view чисто`);

  await ctx.close(); await ctx320.close();
}

// 6. Проверка доступности ключевых DOM-узлов (data-act / скрытие [hidden])
await (async () => {
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await ctx.newPage();
  await page.goto(`${base}/p1/index.html`, { waitUntil: 'networkidle' });
  const probe = await page.evaluate(() => {
    const q = s => !!document.querySelector(s);
    return {
      sky: q('#sky'),
      navBtns: document.querySelectorAll('.proto-nav button').length,
      sheets: document.querySelectorAll('.sheet, [class*="sheet"]').length,
    };
  });
  check('p1: DOM-узлы прототипа', probe.sky && probe.navBtns > 0 && probe.sheets > 0, JSON.stringify(probe));
  await ctx.close();
})();

await browser.close();
server.close();

const fails = results.filter(r => !r.ok).length;
console.log(`\nИТОГО: ${results.length - fails}/${results.length} PASS, ${fails} FAIL`);
process.exit(fails ? 1 : 0);
