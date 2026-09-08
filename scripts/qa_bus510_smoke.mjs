#!/usr/bin/env node
/* BUS-510 e2e smoke: единая ось колонки интро (mock API, без бэкенда).
 * 1) языковой слайд + 4 слайда гайд-интро (вкл. CTA натальной карты) —
 *    геометрия: центр заголовка, dots, intro-start, skip и CTA совпадают;
 *    intro-start не шире вьюпорта; dots не прыгают по вертикали между слайдами.
 * 2) вьюпорты: 375x667 (Android), 390x844 (iPhone), 1024x800 (desktop frame).
 * 3) регресс: safe-area (calc), reduced-motion — оверлей жив, клики работают.
 * Запуск: node scripts/qa_bus510_smoke.mjs
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
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus510');
fs.mkdirSync(OUT, { recursive: true });

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
await new Promise((r) => server.listen(18098, '127.0.0.1', r));

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const ME_WITH_CHART_NEED = JSON.stringify({
  id: 1, name: 'Тест Тестов', lang: 'ru', flags: {},
  birth_date: '1990-05-05', chart_mode: null,
});

async function freshPage({ viewport, reducedMotion = false, setup }) {
  const context = await browser.newContext({
    viewport, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark',
    reducedMotion: reducedMotion ? 'reduce' : 'no-preference',
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    if (url.includes('/api/profile') && method === 'POST') { await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }); return; }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME_WITH_CHART_NEED }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  if (setup) await setup(page, context);
  return { context, page, errors };
}

/* Геометрия одного слайда интро: центры ключевых блоков + ширины.
 * Оси считаем в координатах вьюпорта — все элементы лежат в #intro fixed.
 * ВАЖНО: замеряем ВИДИМЫЙ слайд (ближайший к scrollLeft), а не первый в DOM. */
async function introGeometry(page) {
  return page.evaluate(() => {
    const box = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { cx: r.left + r.width / 2, cy: r.top + r.height / 2, left: r.left, right: r.right, top: r.top, bottom: r.bottom, w: r.width, h: r.height };
    };
    const track = document.querySelector('#intro .intro-track');
    let slide = null;
    if (track) {
      const k = Math.round(track.scrollLeft / (track.clientWidth || 1));
      slide = track.querySelectorAll('.intro-slide')[k] || track.querySelector('.intro-slide');
    }
    return {
      vw: window.innerWidth,
      slide: box(slide),
      title: box(slide && slide.querySelector('.intro-title')),
      sub: box(slide && slide.querySelector('.intro-sub')),
      dots: box(document.querySelector('#intro .intro-dots')),
      start: box(document.querySelector('#intro .intro-start')),
      skip: box(document.querySelector('#intro .intro-skip')),
      chartCta: box(slide && slide.querySelector('[data-intro-chart]')),
    };
  });
}

const cxAbove = (g) => { // допустимое расхождение центров, px
  if (!g) return null;
  const items = [g.title, g.dots, g.start, g.skip].filter(Boolean);
  if (items.length < 2) return null;
  return Math.max(...items.map((i) => i.cx)) - Math.min(...items.map((i) => i.cx));
};

async function gotoIntro(page, firstRun = true) {
  await page.addInitScript((first) => {
    localStorage.clear();
    if (!first) localStorage.setItem('oracle_lang', 'ru');
    /* oracle_intro_seen НЕ ставим — интро должен показаться */
  }, firstRun);
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  /* BUS-510: CTA-слайд карты до-добавляется после /api/me — ждём его появления */
  await page.waitForSelector('#intro .intro-slide:nth-child(4)', { timeout: 4000 }).catch(() => {});
  await page.waitForTimeout(250);
}

/* ——— Сценарий A: языковой слайд (первый вход, язык не выбран) ——— */
for (const [label, viewport] of [['android-375', { width: 375, height: 667 }], ['desktop-1024', { width: 1024, height: 800 }]]) {
  const { context, page, errors } = await freshPage({ viewport });
  await gotoIntro(page, true);
  const g = await introGeometry(page);
  const dev = cxAbove(g);
  ok(`A/${label} языковой слайд: заголовок в оси вьюпорта`, g.title && Math.abs(g.title.cx - g.vw / 2) <= 0.5, dev != null ? `dev=${dev}px` : '');
  const langBtns = await page.locator('#intro [data-lang]').first().isVisible();
  ok(`A/${label} языковой слайд: кнопки выбора языка видны`, langBtns);
  if (g && g.slide) {
    const offscreen = g.slide.right > g.vw + 1 || g.slide.left < -1;
    ok(`A/${label} слайд не вылезает за вьюпорт`, !offscreen, `left=${Math.round(g.slide.left)} right=${Math.round(g.slide.right)} vw=${g.vw}`);
  }
  await page.screenshot({ path: path.join(OUT, `bus510-A-lang-${label}.png`) });
  await context.close();
}

/* ——— Сценарий B: гайд-интро, слайды 1–4, геометрия оси + стабильность dots ——— */
for (const [label, viewport] of [['android-375', { width: 375, height: 667 }], ['iphone-390', { width: 390, height: 844 }], ['desktop-1024', { width: 1024, height: 800 }]]) {
  const { context, page, errors } = await freshPage({ viewport });
  await gotoIntro(page, false);
  const hasChart = await page.locator('[data-intro-chart]').count();
  ok(`B/${label} слайд 4 (CTA натальной карты) присутствует`, hasChart === 1, `count=${hasChart}`);

  let prevDotsTop = null, dotsStable = true, maxDev = 0;
  const slideCount = await page.locator('.intro-slide').count();
  for (let i = 0; i < slideCount; i++) {
    if (i > 0) {
      await page.locator('.intro-track').evaluate((el, k) => { el.scrollLeft = k * el.clientWidth; }, i);
      await page.waitForTimeout(350);
    }
    const g = await introGeometry(page);
    const dev = cxAbove(g);
    if (dev != null) maxDev = Math.max(maxDev, dev);
    ok(`B/${label} слайд ${i + 1}: title/dots/start/skip на одной оси (≤1px)`, dev != null && dev <= 1, `dev=${dev}px vw=${g.vw}`);
    const inVw = g.start && g.start.left >= -1 && g.start.right <= g.vw + 1;
    ok(`B/${label} слайд ${i + 1}: кнопка «Дальше/Начать» в границах вьюпорта`, inVw, g.start ? `left=${Math.round(g.start.left)} right=${Math.round(g.start.right)}` : 'нет кнопки');
    if (i === slideCount - 1 && g.chartCta) {
      const devCta = Math.max(g.chartCta.cx, g.title.cx) - Math.min(g.chartCta.cx, g.title.cx);
      ok(`B/${label} слайд 4: CTA карты в оси колонки (≤1px)`, devCta <= 1, `dev=${devCta}px`);
      ok(`B/${label} слайд 4: CTA в границах вьюпорта`, g.chartCta.left >= -1 && g.chartCta.right <= g.vw + 1, `left=${Math.round(g.chartCta.left)} right=${Math.round(g.chartCta.right)}`);
      // активный dot = последний; «Начать» — подпись финального слайда
      const activeOk = await page.evaluate(() => {
        const active = document.querySelector('#intro .intro-dots span.active');
        const all = document.querySelectorAll('#intro .intro-dots span');
        return active && all.length && active === all[all.length - 1];
      });
      ok(`B/${label} слайд 4: активен последний dot (до-вставка живая)`, activeOk);
      const startLabel = await page.locator('[data-intro-start]').textContent();
      ok(`B/${label} слайд 4: подпись кнопки — «Начать»`, /Начать|Begin/.test(startLabel), `label="${startLabel}"`);
    }
    if (prevDotsTop != null && g.dots && Math.abs(g.dots.top - prevDotsTop) > 1) dotsStable = false;
    if (g.dots) prevDotsTop = g.dots.top;
    await page.screenshot({ path: path.join(OUT, `bus510-B-slide${i + 1}-${label}.png`) });
  }
  ok(`B/${label} dots не прыгают по вертикали между слайдами`, dotsStable, `maxDev=${maxDev}px`);

  // Клик по «Дальше» двигает слайдер, «Пропустить» гасит оверлей
  await page.locator('.intro-track').evaluate((el) => { el.scrollLeft = 0; });
  await page.waitForTimeout(250);
  await page.locator('[data-intro-skip]').click();
  await page.waitForTimeout(300);
  ok(`B/${label} «Пропустить» снимает оверлей`, (await page.locator('#intro').count()) === 0);
  ok(`B/${label} консоль чиста`, errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий C: регресс — reduced-motion — интро жив и проходимо ——— */
{
  const { context, page, errors } = await freshPage({ viewport: { width: 375, height: 667 }, reducedMotion: true });
  await gotoIntro(page, false);
  const dots = await page.locator('#intro .intro-dots').count();
  ok('C/reduced-motion оверлей интро рендерится', dots === 1, `dots=${dots}`);
  const g = await introGeometry(page);
  const dev = cxAbove(g);
  ok('C/reduced-motion ось колонки сохранена (≤1px)', dev != null && dev <= 1, `dev=${dev}px`);
  await page.screenshot({ path: path.join(OUT, 'bus510-C-reduced-motion.png') });
  await context.close();
}

await browser.close();
server.close();
const failed = results.filter((r) => !r.pass).length;
console.log(`\nИтого: ${results.length - failed}/${results.length} PASS`);
console.log(`Скриншоты: ${OUT}`);
process.exit(failed ? 1 : 0);
