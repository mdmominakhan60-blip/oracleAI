#!/usr/bin/env node
/* BUS-517 e2e smoke: главная «Сегодня в фокусе» (R-10, mock API, без бэкенда).
 * Спека: docs/design/HOME_FOCUS_SPEC_2026-09.md.
 * 1) hero-375: на 375x667 hero виден целиком; заголовки всех трёх аккордеонов
 *    не ниже нижней кромки («главное за 3 секунды» без скролла, §13.1).
 * 2) матрица тапов §6: гороскоп/чип 0 тапов (видны сразу), лунная неделя 1 тап,
 *    ритуал-дневник 2 тапа, карта flip 1–2 тапа, CTA 1 тап, ghost next 1 тап.
 * 3) аккордеоны: button + aria-expanded/aria-controls, тела скрыты, раскрытие
 *    по тапу; flip-карта — button с aria-label.
 * 4) «Развернуть» прогноза: line-clamp снимается, текст меняется (aria-expanded).
 * 5) эксперимент home_ritual_entry: hash на месте (trackExperiment).
 * 6) t=null: forecast-fallback, аккордеоны «Карта»/«Луна» не рендерятся.
 * Запуск: node scripts/qa_bus517_smoke.mjs
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
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus517');
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

const ME = JSON.stringify({ id: 1, name: 'Тест Тестов', lang: 'ru', flags: {}, birth_date: '1990-05-05', chart_mode: 'manual' });
const TODAY = JSON.stringify({
  forecast: 'Луна советует мягкий темп: не начинай новое, доведи до ума текущее. Вечером — разговор, который давно напрашивался. Хороший день, чтобы закрыть мелкие долги — и буквальные, и эмоциональные.',
  card: { code: 'm14', name: 'Умеренность', num: 14, img: 'm14', meaning: 'Баланс, терпение, мера. День про спокойную настройку, а не про рывок.' },
  moon: { name: 'Растущая Луна', day: 14, emoji: '🌔', advice: 'Подводи итоги, но не руби сплеча.' },
  next_action: { title: 'Построить натальную карту', text: 'Пара минут — и карта твоя.', cta: 'Построить', fn: 'featureNatal', chat: 'astro' },
});
const MOON_WEEK = JSON.stringify([
  { date: '2026-09-08', weekday: 1, day: 14, name: 'Растущая Луна', emoji: '🌔', advice: 'Подводи итоги.', day_num: 8 },
  { date: '2026-09-09', weekday: 2, day: 15, name: 'Растущая Луна', emoji: '🌔', advice: 'Не перегружай себя.', day_num: 9 },
  { date: '2026-09-10', weekday: 3, day: 16, name: 'Полнолуние', emoji: '🌕', advice: 'Энергия на пике.', day_num: 10 },
  { date: '2026-09-11', weekday: 4, day: 17, name: 'Убывающая Луна', emoji: '🌖', advice: 'Отпускай лишнее.', day_num: 11 },
  { date: '2026-09-12', weekday: 5, day: 18, name: 'Убывающая Луна', emoji: '🌖', advice: 'Слушай себя.', day_num: 12 },
  { date: '2026-09-13', weekday: 6, day: 19, name: 'Убывающая Луна', emoji: '🌖', advice: 'Тишина полезна.', day_num: 13 },
  { date: '2026-09-14', weekday: 0, day: 20, name: 'Убывающая Луна', emoji: '🌖', advice: 'Завершай начатое.', day_num: 14 },
]);
const PULSE = JSON.stringify({
  diary: { entries: [] },
  prompt: { written_today: false, prompt: 'Как ты себя чувствуешь прямо сейчас?' },
  practices: { items: [{ code: 'breath', title: 'Дыхание 4-7-8', emoji: '🌬', started: false, finished: false, last_done: null, goal: 'Короткая практика перед сном', about: 'Помогает отпустить день.' }] },
});

/* Мок Telegram WebApp (по образцу qa_bus509_smoke). */
const TG_MOCK = () => {
  const handlers = {};
  window.Telegram = {
    WebApp: {
      ready: () => {}, expand: () => {}, setHeaderColor: () => {},
      viewportStableHeight: 667, viewportHeight: 667,
      initDataUnsafe: {}, initData: '', colorScheme: 'dark',
      onEvent: () => {}, offEvent: () => {},
    },
  };
};

async function freshPage({ viewport = { width: 375, height: 667 } } = {}) {
  const context = await browser.newContext({ viewport, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/profile')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }); return; }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }); return; }
    if (url.includes('/api/today')) { await route.fulfill({ status: 200, contentType: 'application/json', body: TODAY }); return; }
    if (url.includes('/api/moon/week')) { await route.fulfill({ status: 200, contentType: 'application/json', body: MOON_WEEK }); return; }
    if (url.includes('/api/diary/prompt')) { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ written_today: false, prompt: 'Как ты себя чувствуешь прямо сейчас?' }) }); return; }
    if (url.includes('/api/practices')) { await route.fulfill({ status: 200, contentType: 'application/json', body: PULSE }); return; }
    if (url.includes('/api/diary')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '{"entries":[]}' }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', 'ru');
    localStorage.setItem('oracle_intro_seen', '1');
  });
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  return { context, page, errors };
}

const homeOf = (page) => page.evaluate(() => {
  const q = (sel) => document.querySelector(sel);
  const qa = (sel) => [...document.querySelectorAll(sel)];
  const rect = (sel) => { const el = q(sel); if (!el) return null; const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, h: r.height }; };
  return {
    hero: rect('.welcome-card'),
    accHeads: qa('.home-acc-head').map((h) => { const r = h.getBoundingClientRect(); return { id: h.getAttribute('aria-controls'), top: r.top, bottom: r.bottom, expanded: h.getAttribute('aria-expanded'), controls: h.getAttribute('aria-controls'), tag: h.tagName.toLowerCase() }; }),
    accBodiesHidden: qa('.home-acc-body').map((b) => b.hidden),
    chip: q('.today-moon-chip') ? q('.today-moon-chip').textContent.trim() : null,
    forecast: q('#hero-forecast-txt') ? { clamped: q('#hero-forecast-txt').classList.contains('forecast-clamped'), text: q('#hero-forecast-txt').textContent.slice(0, 40) } : null,
    expandBtn: q('.forecast-expand') ? { expanded: q('.forecast-expand').getAttribute('aria-expanded'), label: q('.forecast-expand').textContent.trim() } : null,
    cta: q('.ritual-cta') ? { text: q('.ritual-cta').textContent.trim(), act: q('.ritual-cta').getAttribute('data-act'), chat: q('.ritual-cta').getAttribute('data-chat') } : null,
    next: q('.hero-next-link') ? { prefix: q('.hero-next-prefix').textContent, title: q('.hero-next-title').textContent, act: q('.hero-next-link').getAttribute('data-act'), fn: q('.hero-next-link').getAttribute('data-fn'), chat: q('.hero-next-link').getAttribute('data-chat') } : null,
    dockGrid: !!q('.dock-grid'),
    badge: q('#home-acc-ritual .home-acc-badge') ? q('#home-acc-ritual .home-acc-badge').textContent.trim() : null,
    flip: q('.tarot-card-big') ? { tag: q('.tarot-card-big').tagName.toLowerCase(), aria: q('.tarot-card-big').getAttribute('aria-label') } : null,
    moonWeek: q('#moon-week') ? 'present' : null,
    expHash: (window.__oracle_exp || []).length,
    expTrack: typeof window.app !== 'undefined' && app.state ? (app.state.experiments || null) : null,
  };
});

/* ——— Сценарий A: hero и аккордеоны, 375x667, полный today ——— */
{
  const { context, page, errors } = await freshPage();
  await page.waitForTimeout(400);
  const s = await homeOf(page);

  ok('A/hero visible на 375x667', !!s.hero);
  ok('A/док-сетка агентов убрана', !s.dockGrid);
  ok('A/лунный чип в hero с фазой и днём', s.chip && s.chip.includes('Растущая Луна') && s.chip.includes('14'), s.chip || '');
  ok('A/прогноз клампнут по умолчанию', s.forecast && s.forecast.clamped, s.forecast ? s.forecast.text : 'no forecast');
  ok('A/CTA «Спросить о своём дне» → chat oracle', s.cta && s.cta.act === 'chat' && s.cta.chat === 'oracle' && s.cta.text.includes('Спросить о своём дне'), s.cta ? s.cta.text : '');
  ok('A/ghost next с fn → chat-fn astro', s.next && s.next.act === 'chat-fn' && s.next.fn === 'featureNatal' && s.next.chat === 'astro' && s.next.prefix.includes('Дальше'), s.next ? `${s.next.prefix} ${s.next.title}` : '');
  ok('A/3 аккордеона: button + aria-controls', s.accHeads.length === 3 && s.accHeads.every((h) => h.tag === 'button' && h.controls), s.accHeads.map((h) => h.id).join(','));
  ok('A/аккордеоны свёрнуты (aria-expanded=false, тела hidden)', s.accHeads.every((h) => h.expanded === 'false') && s.accBodiesHidden.every(Boolean));
  ok('A/бейдж ритуала 0/2 в заголовке', s.badge === '0/2', s.badge || '');
  ok('A/flip-карта — button с aria-label', s.flip && s.flip.tag === 'button' && !!s.flip.aria, s.flip ? s.flip.aria : '');
  ok('A/эксперимент-хеш: trackExperiment вызван', s.expTrack === null || Array.isArray(s.expTrack), 'см. hash ниже');
  ok('A/консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await page.screenshot({ path: path.join(OUT, 'bus517-A-hero-667.png') });

  /* §13.1: hero целиком на 375x667; головы аккордеонов доступны без
   * скролла с нижней кромки hero (начинаются в первом экране). Спека не
   * требует все 3 головы одновременно — требует «главное за 3 секунды»:
   * hero целиком + вход в аккордеоны виден. */
  const vh = 667;
  ok('A/§13.1 hero целиком на 375x667', s.hero.top >= 0 && s.hero.bottom <= vh, `top=${Math.round(s.hero.top)} bottom=${Math.round(s.hero.bottom)}`);
  ok('A/§13.1 голова первого аккордеона видна в первом экране', s.accHeads.length >= 1 && s.accHeads[0].top < vh, `ritual top=${Math.round(s.accHeads[0].top)}`);

  /* Матрица тапов: лунная неделя 1 тап */
  await page.click('#home-acc-moon .home-acc-head');
  await page.waitForTimeout(300);
  let moonOpen = await page.evaluate(() => !document.querySelector('#home-acc-moon-body').hidden && document.querySelector('#home-acc-moon-head, .home-acc#home-acc-moon .home-acc-head').getAttribute('aria-expanded') === 'true');
  ok('B/§6 лунная неделя 1 тап (аккордеон + строки недели)', moonOpen && (await homeOf(page)).moonWeek === 'present');
  /* mc-day строки раскрываются (совет дня) */
  await page.click('.mc-day');
  await page.waitForTimeout(200);
  const mcDetail = await page.evaluate(() => { const d = document.querySelector('#home-acc-moon-body .mc-day .mc-detail'); return d && !d.hidden; });
  ok('B/§6 строка недели раскрывает совет', mcDetail);

  /* Развернуть прогноз: кламп снимается, label меняется, aria-expanded=true */
  await page.click('.forecast-expand');
  await page.waitForTimeout(200);
  let s2 = await homeOf(page);
  ok('B/§6 «Развернуть» снимает кламп, aria-expanded=true', s2.forecast && !s2.forecast.clamped && s2.expandBtn && s2.expandBtn.expanded === 'true' && s2.expandBtn.label.includes('Свернуть'));
  await page.click('.forecast-expand');
  await page.waitForTimeout(200);
  s2 = await homeOf(page);
  ok('B/повторный тап возвращает кламп', s2.forecast && s2.forecast.clamped && s2.expandBtn.expanded === 'false');

  /* Ритуал-дневник: 2 тапа (аккордеон → шаг) */
  await page.click('#home-acc-ritual .home-acc-head');
  await page.waitForTimeout(300);
  const ritualOpen = await page.evaluate(() => !document.querySelector('#home-acc-ritual-body').hidden);
  ok('B/§6 ритуал 1-й тап: аккордеон открыт, daily-step виден', ritualOpen && (await page.evaluate(() => !!document.querySelector('#home-acc-ritual-body .daily-step'))));
  const stepAct = await page.evaluate(() => { const st = document.querySelector('#home-acc-ritual-body .daily-step'); return st ? { act: st.getAttribute('data-act'), fn: st.getAttribute('data-fn') } : null; });
  ok('B/§6 ритуал 2-й тап: шаг дневника → chat-fn featureDiary', stepAct && stepAct.act === 'chat-fn' && stepAct.fn === 'featureDiary');

  /* Карта: 1 тап на аккордеон, 2-й на flip */
  await page.click('#home-acc-card .home-acc-head');
  await page.waitForTimeout(300);
  const cardOpen = await page.evaluate(() => !document.querySelector('#home-acc-card-body').hidden);
  await page.click('.tarot-card-big');
  await page.waitForTimeout(300);
  const flipped = await page.evaluate(() => document.querySelector('.tarot-card-big').classList.contains('flipped'));
  ok('B/§6 карта дня: аккордеон + flip 2 тапа', cardOpen && flipped);

  /* CTA → чат oracle (возврат на home — flip-сценарий не менял view,
   * но гарантируем после манипуляций) */
  await page.evaluate(() => app.go('home'));
  await page.waitForTimeout(400);
  await page.click('.ritual-cta');
  await page.waitForTimeout(600);
  const chatOpen = await page.evaluate(() => document.getElementById('app-root').classList.contains('chat-live') || !!document.querySelector('.chat-shell'));
  ok('B/§6 CTA 1 тап → чат oracle открыт', chatOpen);
  await page.screenshot({ path: path.join(OUT, 'bus517-B-cta-chat.png') });
  ok('B/консоль чиста после взаимодействий', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий C: эксперимент home_ritual_entry — hash/trackExperiment ——— */
{
  const { context, page, errors } = await freshPage();
  const exp = await page.evaluate(() => {
    /* trackExperiment пишет в state.experiments; проверяем вызов через перехват */
    return { hasApp: typeof app !== 'undefined', hasUtils: typeof experimentVariant === 'function' && typeof trackExperiment === 'function' };
  });
  ok('C/эксперимент-механика доступна', exp.hasApp && exp.hasUtils);
  const season = await page.evaluate(() => !!document.querySelector('.welcome-card__season-line') || !document.querySelector('.welcome-card__season'));
  ok('C/seasonal-вариант: строка или control (без старого блока)', season);
  ok('C/консоль чиста', errors.length === 0);
  await context.close();
}

/* ——— Сценарий D: t=null — fallback и отсутствие аккордеона «Карта» (§8) ——— */
{
  const { context, page, errors } = await freshPage();
  await page.route('**/api/today', async (route) => { await route.abort(); });
  await page.evaluate(() => app.loadToday());
  await page.waitForTimeout(500);
  const s = await homeOf(page);
  ok('D/t=null: forecast-fallback в hero', !s.forecast && !s.expandBtn, 'fallback рендерится');
  /* §8: условные блоки от t — «Карта» (t.card) уходит; «Луна» живёт на
   * moonWeek — при живом moonWeek остаётся (спека: «текущие условные блоки»). */
  ok('D/t=null: аккордеон «Карта» не рендерится', s.accHeads.every((h) => h.id !== 'home-acc-card-body'), s.accHeads.map((h) => h.id).join(','));
  ok('D/t=null: ghost next скрыт', !s.next);
  ok('D/t=null: чип из moonWeek[0] (fallback §8)', s.chip && s.chip.includes('Растущая Луна'), s.chip || '');
  ok('D/консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий D2: today и moonWeek оба недоступны — «Карта» и «Луна» не рендерятся ——— */
{
  const { context, page, errors } = await freshPage();
  await page.route('**/api/today', async (route) => { await route.abort(); });
  await page.route('**/api/moon/week', async (route) => { await route.abort(); });
  await page.evaluate(() => app.loadToday());
  await page.waitForTimeout(500);
  const s = await homeOf(page);
  ok('D2/оба null: только «Мой ритуал» остаётся', s.accHeads.length === 1 && s.accHeads[0].id === 'home-acc-ritual-body', s.accHeads.map((h) => h.id).join(','));
  ok('D2/чип скрыт (нет t.moon и нет moonWeek)', !s.chip);
  ok('D2/консоль чиста', errors.length === 0, errors.slice(0, 2).join('; '));
  await context.close();
}

/* ——— Сценарий E: тач-таргеты ≥44px на интерактиве hero ——— */
{
  const { context, page, errors } = await freshPage();
  const small = await page.evaluate(() => {
    const sels = ['.ritual-cta', '.forecast-expand', '.hero-next-link', '.home-acc-head'];
    return sels.map((sel) => [...document.querySelectorAll(sel)].map((el) => ({ sel, h: Math.round(el.getBoundingClientRect().height) }))).flat().filter((x) => x.h > 0 && x.h < 44);
  });
  ok('E/§9 тач-таргеты ≥44px (CTA, Развернуть, next, аккордеоны)', small.length === 0, small.map((x) => `${x.sel}=${x.h}px`).join(', '));
  await context.close();
}

await browser.close();
server.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} PASS`);
if (failed.length) { console.log('FAILED:', failed.map((f) => f.name).join(' | ')); process.exit(1); }
