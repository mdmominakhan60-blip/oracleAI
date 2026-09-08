#!/usr/bin/env node
/* BUS-635 e2e smoke: единая витрина тарифов (mock API, без бэкенда).
 * 1) витрина рендерит только v2-планы (free/vip_core/vip_plus/pro/concierge_v2),
 *    legacy-коды (guide/vip/vip_year/concierge) не видны;
 * 2) features из API рендерятся на карточке с человеческими лейблами (RU и EN);
 * 3) badge «recommended» → featured + лейбл «Выбор большинства»;
 * 4) бесплатный тариф: цена «Бесплатно», CTA disabled;
 * 5) current tier (vip_core) → карточка pay-plan--current, CTA «Текущий тариф» disabled;
 * 6) annual toggle перестраивает цены;
 * 7) покупка с витрины: тап по CTA vip_plus → POST /api/shop/invoice {plan, billing_period};
 * 8) console чист.
 * Запуск: node scripts/qa_bus635_smoke.mjs
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
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus635');
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
await new Promise((r) => server.listen(18099, '127.0.0.1', r));

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

/* Канонический v2-каталог — срез реального catalog_payload (цены/каналы Stars). */
const V2_PLANS = [
  { code: 'free', title: '✦ Искра', tagline: 'Базовая ценность, Today и понятный preview премиум-возможностей', price_usd: 0, price_stars: 0, annual_price_usd: 0, annual_price_stars: 0, period_days: 36500, features: ['today.basic', 'astro.basic', 'report.natal.basic', 'tarot.basic', 'history.basic', 'premium.preview', 'crystals.purchase'], badge: null, is_active: true, is_public: true, sort: 10 },
  { code: 'vip_core', title: 'VIP', tagline: 'Личный AI-проводник, память и регулярная глубина', price_usd: 19.99, price_stars: 1040, annual_price_usd: 199.9, annual_price_stars: 10395, period_days: 30, features: ['today.basic', 'astro.basic', 'astro.advanced', 'tarot.basic', 'tarot.advanced', 'palm.basic', 'ai.chat', 'ai.memory', 'ai.deep_context', 'report.natal.basic', 'report.natal.deep.limited', 'voice', 'crystals.purchase'], badge: null, is_active: true, is_public: true, sort: 20 },
  { code: 'vip_plus', title: 'VIP Plus', tagline: 'Лучший выбор для регулярной работы и расширенных разборов', price_usd: 34.99, price_stars: 1820, annual_price_usd: 349.9, annual_price_stars: 18195, period_days: 30, features: ['today.basic', 'ai.chat', 'ai.memory', 'report.natal.deep', 'report.synastry.deep.limited', 'monthly_report', 'priority_queue', 'voice', 'advanced_reports'], badge: 'recommended', is_active: true, is_public: true, sort: 30 },
  { code: 'pro', title: 'Pro', tagline: 'Высокий allowance, advanced reports и приоритетная обработка', price_usd: 69.99, price_stars: 3640, annual_price_usd: 699.9, annual_price_stars: 36395, period_days: 30, features: ['today.basic', 'ai.chat', 'report.natal.deep', 'report.synastry.deep', 'monthly_report', 'priority_queue', 'voice', 'advanced_reports'], badge: null, is_active: true, is_public: true, sort: 40 },
  { code: 'concierge_v2', title: 'Concierge', tagline: 'Максимальное качество маршрутизации и высокий fair-use allowance', price_usd: 99.99, price_stars: 5200, annual_price_usd: 999.9, annual_price_stars: 51995, period_days: 30, features: ['today.basic', 'ai.chat', 'ai.memory', 'report.natal.deep', 'report.synastry.deep', 'monthly_report', 'priority_queue', 'voice', 'advanced_reports', 'concierge_tools'], badge: 'highest priority', is_active: true, is_public: true, sort: 50 },
];

const SHOP_BASE = (tier) => JSON.stringify({
  current_plan: tier === 'vip_core' ? 'vip' : 'free',
  sub_active: tier === 'vip_core',
  sub_days_left: tier === 'vip_core' ? 21 : 0,
  crystals: 320,
  // legacy-структура специально присутствует: витрина должна её игнорировать
  plans: [
    { code: 'guide', title: '✦✦ Guiding', price_stars: 550, is_active: 1 },
    { code: 'vip', title: '✦✦✦ VIP Oracle', price_stars: 1300, is_active: 1 },
  ],
  products: {},
  entitlements: [],
  catalog: {
    catalog_version: '2026-08-v2', price_book_version: 'pb-2026-08-v2',
    plans: V2_PLANS, annual_plans: [],
    crystal_packs: [], products: [],
    current_entitlements: {
      tier: tier, status: tier === 'vip_core' ? 'active' : 'free',
      ai_message_limit: tier === 'vip_core' ? 120 : 0,
      ai_messages_used: 0, crystals: 320,
    },
  },
  current_entitlements: {},
});

const ME = (lang) => JSON.stringify({ id: 1, name: 'Тест Тестов', lang, flags: {}, birth_date: '1990-05-05', chart_mode: 'manual' });
const TG_MOCK = () => {
  window.Telegram = {
    WebApp: {
      ready: () => {}, expand: () => {}, setHeaderColor: () => {},
      viewportStableHeight: 667, viewportHeight: 667,
      initDataUnsafe: {}, initData: '', colorScheme: 'dark',
      onEvent: () => {}, offEvent: () => {},
      openInvoice: () => {},
    },
  };
};

let invoiceCalls = [];

async function freshPage({ lang = 'ru', tier = 'free' } = {}) {
  const context = await browser.newContext({ viewport: { width: 375, height: 667 }, locale: lang === 'en' ? 'en-US' : 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/shop/invoice')) {
      invoiceCalls.push(route.request().postDataJSON());
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ link: 'https://t.me/invoice-test' }) });
      return;
    }
    if (url.includes('/api/shop')) { await route.fulfill({ status: 200, contentType: 'application/json', body: SHOP_BASE(tier) }); return; }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME(lang) }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript((l) => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', l);
    localStorage.setItem('oracle_intro_seen', '1');
  }, lang);
  await page.goto(`${BASE}/?qa=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  // qa_view=payment boot не поддерживает — открываем витрину как пользователь
  await page.evaluate(() => app.goPayment());
  await page.waitForTimeout(500);
  return { context, page, errors };
}

const plansOf = (page) => page.evaluate(() => ({
  codes: [...document.querySelectorAll('.pay-plan .pay-kicker')].map((k) => k.textContent.trim()),
  titles: [...document.querySelectorAll('.pay-plan h3')].map((t) => t.textContent.trim()),
  features: [...document.querySelectorAll('.pay-plan')].map((c) => [...c.querySelectorAll('.pay-plan__features li')].map((li) => li.textContent.trim())),
  badges: [...document.querySelectorAll('.pay-plan__badge')].map((b) => b.textContent.trim()),
  currentTags: [...document.querySelectorAll('.pay-plan__current-tag')].map((t) => t.textContent.trim()),
  featured: [...document.querySelectorAll('.pay-plan--featured .pay-kicker')].map((k) => k.textContent.trim()),
  current: [...document.querySelectorAll('.pay-plan--current .pay-kicker')].map((k) => k.textContent.trim()),
  prices: [...document.querySelectorAll('.pay-plan .pay-price strong')].map((s) => s.textContent.trim()),
  ctas: [...document.querySelectorAll('.pay-cta')].map((b) => ({ text: b.textContent.trim(), disabled: b.disabled, plan: b.getAttribute('data-plan') })),
  count: (document.querySelector('.pay-section-count') || {}).textContent || '',
}));

/* ── RU, free-пользователь ── */
{
  const { context, page, errors } = await freshPage({ lang: 'ru', tier: 'free' });
  const p = await plansOf(page);
  ok('ru: ровно 5 v2-планов', p.codes.length === 5, p.codes.join(','));
  ok('ru: коды v2 на витрине', ['free', 'vip_core', 'vip_plus', 'pro', 'concierge_v2'].every((c) => p.codes.includes(c)), p.codes.join(','));
  ok('ru: legacy-коды не видны', !p.codes.some((c) => ['guide', 'vip', 'vip_year', 'concierge'].includes(c)));
  ok('ru: цены без $9.99/$24.99', !p.prices.some((s) => s.includes('9.99') || s.includes('24.99')), p.prices.join(','));
  ok('ru: free — Бесплатно, CTA «Текущий тариф» disabled (free — текущий tier)', p.prices[0] === 'Бесплатно' && p.ctas[0].disabled && p.ctas[0].text === 'Текущий тариф', `price=${p.prices[0]} cta=${p.ctas[0].text}`);
  ok('ru: free показывает features', p.features[0].length === 7, `${p.features[0].length} шт.`);
  ok('ru: лейбл ai.chat по-русски', p.features[1].includes('Диалоги с Оракулом'), p.features[1].join('|'));
  ok('ru: счётчик 5 тарифов', /5 тариф/.test(p.count), p.count);
  ok('ru: badge recommended → vip_plus featured + лейбл', p.featured.includes('vip_plus') && p.badges.includes('Выбор большинства'), p.badges.join(','));
  ok('ru: free — текущий tier, тег на месте', p.currentTags.includes('Твой тариф'), p.currentTags.join(','));
  ok('ru: console чист', errors.length === 0, errors.join(' | ').slice(0, 200));

  // Покупка с витрины: тап по CTA vip_plus → invoice {plan, billing_period}
  invoiceCalls = [];
  await page.click('.pay-cta[data-plan="vip_plus"]');
  await page.waitForTimeout(400);
  ok('ru: покупка vip_plus → /api/shop/invoice', invoiceCalls.length === 1 && invoiceCalls[0].plan === 'vip_plus' && invoiceCalls[0].billing_period === 'monthly', JSON.stringify(invoiceCalls[0] || {}));

  // annual toggle
  await page.click('[data-act="payment-period"][data-period="annual"]');
  await page.waitForTimeout(200);
  const annual = await plansOf(page);
  ok('ru: annual цена vip_plus 18195', annual.prices[2] === '✦ 18 195' || annual.prices[2] === '✦ 18 195', annual.prices.join(','));

  await page.screenshot({ path: path.join(OUT, 'bus635-storefront-ru-free.png'), fullPage: true });
  await context.close();
}

/* ── RU, действующий подписчик vip_core (legacy-алиас current_plan=vip) ── */
{
  const { context, page, errors } = await freshPage({ lang: 'ru', tier: 'vip_core' });
  const p = await plansOf(page);
  ok('ru-vip: карточка vip_core подсвечена', p.current.includes('vip_core'), p.current.join(','));
  ok('ru-vip: тег «Твой тариф»', p.currentTags.includes('Твой тариф'), p.currentTags.join(','));
  const cta = p.ctas.find((c) => c.plan === 'vip_core');
  ok('ru-vip: CTA текущего тарифа disabled «Текущий тариф»', cta && cta.disabled && cta.text === 'Текущий тариф', JSON.stringify(cta || {}));
  const plus = p.ctas.find((c) => c.plan === 'vip_plus');
  ok('ru-vip: CTA апгрейда активен', plus && !plus.disabled);
  ok('ru-vip: console чист', errors.length === 0, errors.join(' | ').slice(0, 200));

  // BUS-399: шапка берёт тайтл текущего плана из canonical-каталога
  const headerTitle = await page.evaluate(() => {
    const el = document.querySelector('.header-sub--active b');
    return el ? el.textContent.trim() : null;
  });
  ok('ru-vip: шапка показывает «VIP» из v2-каталога', headerTitle === 'VIP', String(headerTitle));
  await page.screenshot({ path: path.join(OUT, 'bus635-storefront-ru-vip.png'), fullPage: true });
  await context.close();
}

/* ── EN, free ── */
{
  const { context, page, errors } = await freshPage({ lang: 'en', tier: 'free' });
  const p = await plansOf(page);
  ok('en: 5 планов', p.codes.length === 5);
  ok('en: заголовки v2 по-английски', p.titles.includes('VIP Plus') && p.titles.includes('Concierge'), p.titles.join(','));
  ok('en: ai.chat лейбл по-английски', p.features[1].includes('Chats with the Oracle'), p.features[1].join('|'));
  ok('en: free — Free + disabled', p.prices[0] === 'Free' && p.ctas[0].disabled, `price=${p.prices[0]}`);
  ok('en: badge «Most popular»', p.badges.includes('Most popular'), p.badges.join(','));
  ok('en: CTA активного плана «Open Stars checkout»', p.ctas.find((c) => c.plan === 'vip_plus')?.text === 'Open Stars checkout');
  ok('en: console чист', errors.length === 0, errors.join(' | ').slice(0, 200));
  await page.screenshot({ path: path.join(OUT, 'bus635-storefront-en-free.png'), fullPage: true });
  await context.close();
}

await browser.close();
server.close();

const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} PASS${failed.length ? `, ${failed.length} FAIL` : ''}`);
process.exit(failed.length ? 1 : 0);
