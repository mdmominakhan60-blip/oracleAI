#!/usr/bin/env node
/* BUS-399 verify: кристаллы и подписка в шапке Mini App.
 * Запуск: BASE=http://localhost:18090 DEV_KEY=bus240-qa-key node scripts/verify_bus399_header.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';

const BASE = process.env.BASE || 'http://localhost:18090';
const DEV_KEY = process.env.DEV_KEY || 'bus240-qa-key';
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome']).toString().trim();

const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond, extra });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const errors = [];
const newPage = async (ctx) => {
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  return page;
};

// feedback-модал (feedback_pending) перехватывает клики — закрыть, если открылся
const closeFeedbackModal = async (page) => {
  if (await page.locator('#app-modal .modal').count()) {
    await page.evaluate(() => window.app.closeModal());
    await page.waitForTimeout(300);
  }
};

try {
  // ── Кейс A: активная подписка (QA-42: plan «Путеводная», 250 кристаллов) ──
  let ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true, extraHTTPHeaders: { 'X-Dev-Key': DEV_KEY } });
  let page = await newPage(ctx);
  await page.goto(`${BASE}/?dev_user=900000042&qa=1&qa_view=home`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await closeFeedbackModal(page);

  const status = page.locator('[data-header-status]');
  ok('A1: статус-ряд видим', await status.isVisible());
  const cry = page.locator('.header-crystals');
  ok('A2: бейдж кристаллов виден', await cry.isVisible());
  ok('A3: баланс 250 в бейдже', (await cry.textContent()).includes('250'), (await cry.textContent()).trim());

  const sub = page.locator('.header-sub--active');
  ok('A4: статус активной подписки виден', await sub.isVisible());
  const subText = (await sub.textContent()).trim();
  ok('A5: имя плана «Путеводная»', subText.includes('Путеводная'), subText);
  ok('A6: дата окончания 2026-09-17', subText.includes('2026-09-17'), subText);
  ok('A7: нет CTA при активной подписке', (await page.locator('.header-sub--cta').count()) === 0);

  // Тап по кристаллам ведёт в payment
  await cry.click();
  await page.waitForTimeout(600);
  const view = await page.evaluate(() => window.app.view);
  ok('A8: тап по кристаллам → payment', view === 'payment', view);
  const payHead = await page.locator('.pay-plans, .pay-section').count();
  ok('A9: экран тарифов отрисован', payHead > 0, 'pay-sections=' + payHead);

  // Шапка не перегружена: user-pill и bell на месте
  ok('A10: user-pill сохранён', (await page.locator('.user-pill').count()) === 1);
  ok('A11: bell сохранён', (await page.locator('.app-header .bell').count()) === 1);
  await page.screenshot({ path: 'scripts/bus399-shot-mobile-active.png', fullPage: false });
  await ctx.close();

  // ── Кейс B: без подписки (QA-43: free, 12 кристаллов) → CTA «Тарифы» ──
  ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true, extraHTTPHeaders: { 'X-Dev-Key': DEV_KEY } });
  page = await newPage(ctx);
  await page.goto(`${BASE}/?dev_user=900000043&qa=1&qa_view=home`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await closeFeedbackModal(page);

  ok('B1: бейдж кристаллов 12', (await page.locator('.header-crystals').textContent()).includes('12'));
  const cta = page.locator('.header-sub--cta');
  ok('B2: CTA «Тарифы» виден', await cta.isVisible(), (await cta.textContent()).trim());
  ok('B3: нет активного статуса', (await page.locator('.header-sub--active').count()) === 0);
  await cta.click();
  await page.waitForTimeout(600);
  ok('B4: тап CTA → payment', (await page.evaluate(() => window.app.view)) === 'payment');
  await page.screenshot({ path: 'scripts/bus399-shot-mobile-cta.png', fullPage: false });
  await ctx.close();

  // ── Кейс C: desktop-шелл ──
  ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, locale: 'ru-RU', bypassCSP: true, extraHTTPHeaders: { 'X-Dev-Key': DEV_KEY } });
  page = await newPage(ctx);
  await page.goto(`${BASE}/?dev_user=900000042&qa=1&qa_view=home`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await closeFeedbackModal(page);
  ok('C1: desktop статус-ряд видим', await page.locator('[data-header-status]').isVisible());
  ok('C2: desktop бейдж 250', (await page.locator('.header-crystals').textContent()).includes('250'));
  await page.screenshot({ path: 'scripts/bus399-shot-desktop-active.png', fullPage: false });
  await ctx.close();

  // ── Кейс D: EN-локаль (меняем lang QA-юзера через API, возвращаем после) ──
  ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'en-US', bypassCSP: true, extraHTTPHeaders: { 'X-Dev-Key': DEV_KEY } });
  page = await newPage(ctx);
  await page.goto(`${BASE}/?dev_user=900000042&qa=1&qa_view=home`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await closeFeedbackModal(page);
  await ctx.request.post(`${BASE}/api/profile?dev_user=900000042`, { headers: { 'X-Dev-Key': DEV_KEY }, data: { lang: 'en' } });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await closeFeedbackModal(page);
  const enSub = (await page.locator('.header-sub--active').textContent()).trim();
  ok('D1: EN «until» в статусе', /until/i.test(enSub), enSub);
  const enCry = await page.locator('.header-crystals').getAttribute('aria-label');
  ok('D2: EN aria-label кристаллов', /^Crystals:/i.test(enCry || ''), enCry);
  await ctx.request.post(`${BASE}/api/profile?dev_user=900000042`, { headers: { 'X-Dev-Key': DEV_KEY }, data: { lang: 'ru' } });
  await ctx.close();

  // ── Кейс E: синк this.me из storefront (loadPayments) ──
  ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true, extraHTTPHeaders: { 'X-Dev-Key': DEV_KEY } });
  page = await newPage(ctx);
  await page.goto(`${BASE}/?dev_user=900000042&qa=1&qa_view=home`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await page.evaluate(() => window.app.go('payment'));
  await page.waitForTimeout(900);
  const meCrystals = await page.evaluate(() => window.app.me.crystals);
  ok('E1: me.crystals синхронизирован из storefront', meCrystals === 250, 'me.crystals=' + meCrystals);
  await ctx.close();
} finally {
  await browser.close();
}

console.log(`\nИтог: ${results.filter(r => r.pass).length}/${results.length} PASS`);
if (errors.length) {
  console.log('\nJS-ошибки:');
  errors.forEach(e => console.log('  ' + e));
}
process.exit(results.every(r => r.pass) && errors.length === 0 ? 0 : 1);
