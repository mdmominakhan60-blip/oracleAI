#!/usr/bin/env node
/* BUS-1103 S14 e2e smoke: натальная карта в miniapp — 7 видов через
 * qa-роутинг (?qa=1&qa_view=chart-*), ?fail=1 → chart-error, interpret
 * human v2 (render_order+blocks) с fallback structured v1, empty-ветка без
 * карты, 320px overflow, console-error/pageerror-нуль.
 * Контракты сверены: GET /api/chart (chart.py:104-122), POST
 * /api/chart/interpret (chart.py:381-383, chart_human.py:493-516).
 * Запуск: node scripts/qa_bus1103_s14_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18099';
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus1103');
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

const ME = (over = {}) => JSON.stringify({ id: 'u1', name: 'QA', lang: 'ru', gender: 'f', premium: false,
  birth_date: '1994-03-14', birth_time: '10:00', birth_city: 'Москва', birth_time_known: true, onboarded: true, plan: 'vip', crystals: 120,
  morning_push: true, memory_on: true, ...over });

const AGENTS = () => JSON.stringify([
  { code: 'oracle', name: 'Лилит', title: 'Проводник', role: 'Проводник', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'astro', name: 'Урания', title: 'Звёзды', role: 'Астролог', avatar: '/static/img/agents/oracle.jpg' },
  { code: 'tarot', name: 'Мадам Ленорман', title: 'Карты', role: 'Таролог', avatar: '/static/img/agents/oracle.jpg' }
]);

/* Полная карта: 10 планет + 2 узла (wheelItems = 12), 12 домов, 5 аспектов.
 * abs_deg — эклиптическая долгота (wheelPos: SVG-угол 180°−deg). */
const CHART = () => JSON.stringify({
  natal_schema_version: 2, mode: 'lite', precision: 'full', engine: 'kerykeion',
  sun: { name: 'Солнце', sign: 'Рыбы', deg: 23.4, house: 10, abs_deg: 353.4 },
  ascendant: { sign: 'Близнецы', deg: 14, abs_deg: 74 },
  mc: { sign: 'Водолей', deg: 28 },
  birth: { date: '1994-03-14', time: '10:00', city: 'Москва', time_known: true },
  planets: [
    { name: 'Солнце', sign: 'Рыбы', deg: 23, house: 10, abs_deg: 353 },
    { name: 'Луна', sign: 'Рак', deg: 7, house: 2, abs_deg: 97 },
    { name: 'Меркурий', sign: 'Овен', deg: 12, house: 11, abs_deg: 12, retro: true },
    { name: 'Венера', sign: 'Водолей', deg: 5, house: 9, abs_deg: 305 },
    { name: 'Марс', sign: 'Козерог', deg: 18, house: 8, abs_deg: 288 },
    { name: 'Юпитер', sign: 'Скорпион', deg: 9, house: 6, abs_deg: 219 },
    { name: 'Сатурн', sign: 'Рыбы', deg: 30, house: 10, abs_deg: 360 },
    { name: 'Уран', sign: 'Козерог', deg: 25, house: 8, abs_deg: 295 },
    { name: 'Нептун', sign: 'Козерог', deg: 23, house: 8, abs_deg: 293 },
    { name: 'Плутон', sign: 'Скорпион', deg: 28, house: 6, abs_deg: 238 }
  ],
  houses: Array.from({ length: 12 }, (_, i) => ({ n: i + 1, sign: 'Близнецы', deg: i * 5 })),
  aspects: [
    { p1: 'Солнце', p2: 'Луна', aspect: 'секстиль', angle: 62, glyph: '⚹' },
    { p1: 'Луна', p2: 'Марс', aspect: 'трин', angle: 119, glyph: '△' },
    { p1: 'Меркурий', p2: 'Венера', aspect: 'соединение', angle: 8, glyph: '☌' },
    { p1: 'Сатурн', p2: 'Нептун', aspect: 'соединение', angle: 6, glyph: '☌' },
    { p1: 'Юпитер', p2: 'Плутон', aspect: 'соединение', angle: 9, glyph: '☌' }
  ],
  nodes: [
    { name: 'Раху (Сев. узел)', sign: 'Скорпион', deg: 27, house: 6, abs_deg: 237 },
    { name: 'Кету (Юж. узел)', sign: 'Телец', deg: 27, house: 12, abs_deg: 57 }
  ],
  lunar_nodes: { rahu: { name: 'Раху (Сев. узел)' }, ketu: { name: 'Кету (Юж. узел)' } }
});

/* interpret human v2 — форма chart_human.py:493-516 (render_order + blocks). */
const INTERPRET = () => JSON.stringify({
  text: '**1. Кто ты** Полномочный разбор.',
  structured: {
    luminaries: { sun: 'Солнце в Рыбах: глубокая эмпатия.', moon: 'Луна в Раке: забота о своих.', ascendant: 'Асцендент в Близнецах: лёгкость контакта.' },
    personality_portrait: 'Чуткий стратег с живым умом.',
    rahu_ketu: { rahu: 'Рост через глубину доверия.', ketu: 'Отпустить контроль.', growth_step: 'Один честный разговор в неделю.' },
    strengths: ['эмпатия', 'интуиция', 'системность'],
    weaknesses: ['самопожертвование до усталости'],
    purpose: 'Собирать людей вокруг смыслов.',
    relationships: 'В паре нужна тишина и безопасность.',
    career_money: 'Процветает в проектах на стыке людей и смысла.',
    aspect_synthesis: 'Водные трены дают мягкий поток.',
    peak_periods: { status: 'Ключевые окна обозначены.', periods: ['2026 Q4: пересборка целей', '2027 Q2: рост дохода'], note: 'Окна — тенденции, не приговор.' },
    synthesis: 'Мягкая сила через глубину.',
    disclaimer: 'Разбор — инструмент рефлексии, не медицинская или финансовая рекомендация.'
  },
  human: {
    contract_version: 2,
    render_order: ['who_you_are', 'strengths', 'obstacles', 'love', 'career', 'purpose', 'profile'],
    blocks: {
      who_you_are: { title: 'Кто ты', text: 'Тихая сила: чувствуешь глубже, чем показываешь.' },
      strengths: { title: 'Твои сильные стороны', items: ['эмпатия без растворения', 'чутьё на людей'] },
      obstacles: { title: 'Что может мешать тебе', items: ['спасать всех подряд'] },
      love: { title: '❤️ Любовь', fields: { style: { label: 'Стиль', text: 'Мягкий, но с границами.' }, need: { label: 'Потребность', text: 'Безопасность и честность.' } } },
      career: { title: '💼 Карьера', fields: { strength: { label: 'Сила', text: 'Связывать людей и смыслы.' }, risk: { label: 'Риск', text: 'Выгорание от чужих задач.' } } },
      purpose: { title: '✨ Твоя цель', text: 'Быть глубиной, в которой другие слышат себя.', details: { rahu: 'Углубление в доверие.', ketu: 'Освобождение от гипер-контроля.' } },
      profile: { title: 'Твой профиль', summary: 'Водный стратег с воздушным входом.', scales: [{ name: 'Стихии', value: 'вода/воздух' }] }
    },
    question_hooks: [{ question: 'Почему я веду себя именно так?' }, { question: 'Что даёт мне силы?' }],
    disclaimer: 'Разбор — инструмент рефлексии, не медицинская или финансовая рекомендация.'
  }
});

/* Переключатели сессии: noChart → 400 (карта не построена); chartFail → 500. */
async function freshPage(opts = {}) {
  const context = await browser.newContext({ viewport: { width: opts.width || 390, height: 844 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  const me = opts.me || ME();
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/chart/interpret')) { await route.fulfill({ status: 200, contentType: 'application/json', body: INTERPRET() }); return; }
    if (url.includes('/api/chart')) {
      /* '/api/chart/...' уже отфильтрованы выше; здесь GET /api/chart и перерасчёт */
      if (opts.noChart) { await route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ detail: 'карта ещё не построена' }) }); return; }
      if (opts.chartFail) { await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'engine_error' }) }); return; }
      await route.fulfill({ status: 200, contentType: 'application/json', body: CHART() });
      return;
    }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: AGENTS() }); return; }
    if (url.endsWith('/api/me') || url.includes('/api/me?')) { await route.fulfill({ status: 200, contentType: 'application/json', body: me }); return; }
    if (url.includes('/api/today')) { await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ forecast: 'День мягкого фокуса.' }) }); return; }
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

let browser;
async function run() {
  await new Promise((r) => server.listen(18099, '127.0.0.1', r));
  browser = await chromium.launch({ executablePath: CHROME_PATH, args: ['--no-sandbox'] });

  /* ── ВИД 1 · chart-card: карточка-превью в ленте ──────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=chart-card', { waitUntil: 'networkidle' });
    await page.waitForSelector('.chart-card', { timeout: 4000 }).catch(() => {});
    ok('S14 card: .chart-card отрисована', !!(await page.$('.chart-card')));
    ok('S14 card: запрос-пузырь в ленте', !!(await page.$('.chart-card-feed .msg.user')));
    ok('S14 card: мини-колесо (svg)', !!(await page.$('.chart-card__wheel svg')));
    ok('S14 card: строка рождения из birth', (await (await page.$('.chart-card__meta'))?.textContent() || '').includes('14'));
    ok('S14 card: кнопка chart-open', !!(await page.$('[data-act="chart-open"]')));
    /* клик chart-open → chart-main */
    await page.click('[data-act="chart-open"]');
    await page.waitForTimeout(300);
    ok('S14 card: chart-open ведёт на chart-main', !!(await page.$('.chart-scene')));
    await page.screenshot({ path: OUT + '/s14-1-card.png' });
    await page.close();
  }

  /* ── ВИД 2 · chart-loading: 3 шага ────────────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=chart-loading', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    ok('S14 loading: role=status + spinner', !!(await page.$('.tool-run__status[role="status"]')) && !!(await page.$('.tool-run__spinner')));
    const steps = await page.$$('.tool-run__step');
    ok('S14 loading: 3 шага', steps.length === 3, `${steps.length} шагов`);
    ok('S14 loading: шаг 1 done, шаг 2 active', !!(await page.$('.tool-run__step.is-done')) && !!(await page.$('.tool-run__step.is-active')));
    ok('S14 loading: кнопка disabled + aria-busy', !!(await page.$('button[disabled][aria-busy="true"]')));
    await page.screenshot({ path: OUT + '/s14-2-loading.png' });
    await page.close();
  }

  /* ── ВИД 3 · chart-empty: карта не построена (400) ────────────────── */
  {
    const page = await freshPage({ noChart: true });
    await page.goto(BASE + '/?qa=1&qa_view=chart-main', { waitUntil: 'networkidle' });
    await page.waitForSelector('.chart-empty', { timeout: 4000 }).catch(() => {});
    ok('S14 empty: 400 → честный empty-вид', !!(await page.$('.chart-empty')));
    ok('S14 empty: заголовок + текст', !!(await page.$('.chart-empty__title')) && !!(await page.$('.chart-empty__text')));
    ok('S14 empty: CTA добавить данные рождения', !!(await page.$('[data-act="chart-add-birth"]')));
    await page.screenshot({ path: OUT + '/s14-3-empty.png' });
    await page.close();
  }

  /* ── ВИД 3b · chart-empty + noTime: partial-блок ───────────────────── */
  {
    const page = await freshPage({ noChart: true, me: ME({ birth_time: null, birth_time_known: false }) });
    await page.goto(BASE + '/?qa=1&qa_view=chart-main', { waitUntil: 'networkidle' });
    await page.waitForSelector('.chart-empty', { timeout: 4000 }).catch(() => {});
    ok('S14 empty noTime: partial-блок «время неизвестно»', !!(await page.$('.chart-partial')));
    ok('S14 empty noTime: два действия', (await page.$$('.chart-partial__actions .btn')).length === 2);
    await page.screenshot({ path: OUT + '/s14-3b-empty-notime.png' });
    await page.close();
  }

  /* ── ВИД 4 · chart-main: колесо + списки ──────────────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=chart-main', { waitUntil: 'networkidle' });
    await page.waitForSelector('.chart-scene', { timeout: 4000 }).catch(() => {});
    ok('S14 main: provenance-строка', !!(await page.$('.chart-provenance')));
    ok('S14 main: колесо svg + глифы', !!(await page.$('.chart-scene__wheel svg.chart-wheel')) && (await page.$$('.chart-wheel__p')).length > 0);
    const rows = await page.$$('.chart-row');
    ok('S14 main: 12 рядов планет (10+2 узла)', rows.length === 12, `${rows.length} рядов`);
    const aspects = await page.$$('.chart-aspect');
    ok('S14 main: 5 аспектов в details', aspects.length === 5, `${aspects.length} аспектов`);
    const houses = await page.$$('.chart-house');
    ok('S14 main: 12 домов', houses.length === 12, `${houses.length} домов`);
    ok('S14 main: светила (☉/☽) + Asc', (await page.$$('.chart-lum__row')).length === 3);
    ok('S14 main: ретро-глиф у Меркурия', !!(await page.$('.chart-row__retro')));
    ok('S14 main: CTA разбора + спросить', !!(await page.$('[data-act="chart-interpret"]')) && !!(await page.$('[data-act="chart-ask-agent"]')));
    ok('S14 main: share-кнопка в шапке', !!(await page.$('[data-act="chart-share"]')));
    await page.screenshot({ path: OUT + '/s14-4-main.png' });
    await page.close();
  }

  /* ── ВИД 5 · chart-zoom: планета крупно (клик по ряду) ────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=chart-main', { waitUntil: 'networkidle' });
    await page.waitForSelector('.chart-row', { timeout: 4000 }).catch(() => {});
    /* Меркурий — ряд 3 (индекс 2): ретро-планета, отражается в zoom */
    const rows = await page.$$('.chart-row');
    if (rows.length >= 3) await rows[2].click();
    await page.waitForTimeout(300);
    ok('S14 zoom: открылся (badge+title)', !!(await page.$('.chart-zoom__badge')) && !!(await page.$('.chart-zoom__title')));
    const titleTxt = await (await page.$('.chart-zoom__title')).textContent();
    ok('S14 zoom: выбрана кликнутая планета (Меркурий)', /Меркур/.test(titleTxt || ''), titleTxt);
    ok('S14 zoom: ретро-метка в meta', /Ретро|retro/i.test((await (await page.$('.chart-zoom__meta')).textContent()) || ''));
    ok('S14 zoom: CTA спросить о планете', !!(await page.$('[data-act="chart-ask-about-planet"]')));
    await page.screenshot({ path: OUT + '/s14-5-zoom.png' });
    await page.close();
  }

  /* ── ВИД 6 · chart-interpret: human v2 → 7 секций + verdict ────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=chart-interpret', { waitUntil: 'networkidle' });
    await page.waitForSelector('.interpret__sec-title, .interpret__deep summary', { timeout: 5000 }).catch(() => {});
    ok('S14 interpret: заголовок H1', !!(await page.$('.interpret__title')));
    ok('S14 interpret: verdict из who_you_are', !!(await page.$('.interpret__verdict')));
    const secs = await page.$$('.interpret__sec');
    const deeps = await page.$$('.interpret__deep summary');
    ok('S14 interpret: 7 блоков human v2 (sec+deep)', secs.length + deeps.length === 7, `${secs.length} sec + ${deeps.length} deep`);
    ok('S14 interpret: список strengths (items)', (await page.$$('.interpret__list li')).length >= 3);
    ok('S14 interpret: disclaimer', !!(await page.$('.interpret__disclaimer')));
    ok('S14 interpret: footer (обсудить + к карте)', !!(await page.$('[data-act="chart-ask-agent"]')) && !!(await page.$('[data-act="chart-back-main"]')));
    await page.screenshot({ path: OUT + '/s14-6-interpret.png', fullPage: true });
    await page.close();
  }

  /* ── ВИД 7 · chart-error: ?fail=1 → ошибка расчёта ─────────────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=chart-main&fail=1', { waitUntil: 'networkidle' });
    await page.waitForTimeout(400);
    ok('S14 error: fail-кадр role=alert', !!(await page.$('.tool-run__fail[role="alert"]')));
    ok('S14 error: chart-reload (проверить/заново)', (await page.$$('[data-act="chart-reload"]')).length === 2);
    /* reload → сброс failMode, карта грузится заново → main */
    await page.click('[data-act="chart-reload"]');
    await page.waitForSelector('.chart-scene', { timeout: 4000 }).catch(() => {});
    ok('S14 error: reload восстанавливает main', !!(await page.$('.chart-scene')));
    await page.screenshot({ path: OUT + '/s14-7-error.png' });
    await page.close();
  }

  /* ── Сбой GET /api/chart 5xx → пустой вид (не выдумываем данные) ──── */
  {
    const page = await freshPage({ chartFail: true });
    await page.goto(BASE + '/?qa=1&qa_view=chart-main', { waitUntil: 'networkidle' });
    await page.waitForSelector('.chart-empty', { timeout: 4000 }).catch(() => {});
    ok('S14 5xx: без карты — empty, не error-кадр', !!(await page.$('.chart-empty')) && !(await page.$('.tool-run__fail')));
    await page.close();
  }

  /* ── 320px overflow по всем видам S14 ─────────────────────────────── */
  {
    const views = ['chart-card', 'chart-loading', 'chart-empty', 'chart-main', 'chart-zoom', 'chart-interpret', 'chart-error'];
    for (const v of views) {
      const fail = v === 'chart-error' ? '&fail=1' : '';
      const page = await freshPage({ width: 320, noChart: v === 'chart-empty' });
      await page.goto(BASE + '/?qa=1&qa_view=' + v + fail, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      await checkViewport(page, v);
      await page.close();
    }
  }

  /* ── console-error/pageerror-нуль на сквозном потоке S14 ─────────── */
  {
    const page = await freshPage();
    await page.goto(BASE + '/?qa=1&qa_view=chart-card', { waitUntil: 'networkidle' });
    await page.waitForTimeout(300);
    await page.click('[data-act="chart-open"]');
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('chart-zoom'));
    await page.waitForTimeout(300);
    await page.evaluate(() => app.go('chart-interpret'));
    await page.waitForTimeout(600);
    await page.evaluate(() => app.go('chart-main'));
    await page.waitForTimeout(300);
    ok('JS: ноль console.error/pageerror в S14-потоке', page._errors.length === 0, page._errors.join(' | ').slice(0, 200));
    await page.screenshot({ path: OUT + '/s14-flow.png' });
    await page.close();
  }

  const failed = results.filter((r) => !r.pass).length;
  console.log(`\n${failed === 0 ? 'ALL PASS' : failed + ' FAILED'} (${results.length} checks)`);
  fs.writeFileSync(path.join(OUT, 's14-smoke-results.json'), JSON.stringify({ ts: new Date().toISOString(), results }, null, 2));
  process.exit(failed === 0 ? 0 : 1);
}

run().catch(async (e) => {
  console.error('SMOKE ERROR:', e.message);
  try { await browser?.close(); } catch {}
  server.close();
  process.exit(2);
});
