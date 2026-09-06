#!/usr/bin/env node
// BUS-178: UI-верификация экранов Аналитика / Аудитория / Когорты на mock-стенде.
import fs from 'node:fs/promises';
import { chromium } from '/home/softis/apps/oraclAI/oracleAI/node_modules/playwright-core/index.mjs';
import axe from 'axe-core';

const OUT = process.argv[2] || '/tmp/paperclip-run-bus-178-34fa7081-2a6-UwW69f/ui-evidence';
const CHROME_PATH = process.env.CHROME_PATH || '/usr/bin/google-chrome-stable';
const BASE = 'http://127.0.0.1:8791';
const results = [];
const errors = [];

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

async function checkViewport(name) {
  const context = await browser.newContext({
    viewport: { width: name === 'mobile' ? 390 : 1440, height: name === 'mobile' ? 844 : 900 },
    locale: 'ru-RU', reducedMotion: 'reduce',
    isMobile: name === 'mobile', hasTouch: name === 'mobile', bypassCSP: true,
  });
  const page = await context.newPage();
  page.on('pageerror', (err) => errors.push(`[${name}] pageerror: ${err.message}`));
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(`[${name}] console.error: ${msg.text()}`); });
  try {
    await page.goto(`${BASE}/admin/`, { waitUntil: 'networkidle' });
    await page.waitForSelector('#shell:not(.hidden)', { timeout: 5000 });
    await page.addScriptTag({ content: axe.source });
    const runAxe = async (label) => {
      const axeResult = await page.evaluate(async () => window.axe.run('body', { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'best-practice'] } }));
      await fs.writeFile(`${OUT}/axe-${label}.json`, JSON.stringify(axeResult, null, 2) + '\n');
      results.push({
        name: `axe-${label}`,
        violations: axeResult.violations.map((v) => `${v.id}(${v.nodes.length})`),
        incomplete: axeResult.incomplete.map((v) => `${v.id}(${v.nodes.length})`),
      });
    };

    // ── Аналитика (существующий экран, не ломаем) ──
    await page.click('.nav-item[data-view="analytics"]');
    await page.waitForTimeout(600);
    const analyticsChecks = {
      activationSteps: await page.locator('#anx-activation .funnel-step').count(),
      crmFunnelSteps: await page.locator('#anx-funnel .funnel-step').count(),
      segmentCards: await page.locator('#anx-segments .segment-card').count(),
      retentionRows: await page.locator('#anx-retention tbody tr').count(),
      revKpis: await page.locator('#anx-rev-kpi .kpi').count(),
      skuRows: await page.locator('#anx-rev-sku tbody tr').count(),
      tierRows: await page.locator('#anx-tiers tbody tr').count(),
      moneyFunnelRows: await page.locator('#anx-money-funnel tbody tr').count(),
      crystalRows: await page.locator('#anx-crystals tbody tr').count(),
      userRows: await page.locator('#anx-users-table tbody tr').count(),
      pageTitle: await page.locator('#view-title').textContent(),
    };
    results.push({ name, ...analyticsChecks });
    await page.screenshot({ path: `${OUT}/analytics-${name}.png`, fullPage: true });

    // сегмент-фильтр на Analytics: клик по «Платящие» → список
    await page.click('#anx-segments .segment-card[data-segment="paying"]');
    await page.waitForTimeout(400);
    results.push({
      name: `${name}-analytics-filter`,
      selectValue: await page.locator('#anx-segment').inputValue(),
      total: await page.locator('#anx-total').textContent(),
    });
    await page.screenshot({ path: `${OUT}/analytics-${name}-filtered.png`, fullPage: false });

    // drawer из списка analytics
    await page.click('#anx-users-table tbody tr');
    await page.waitForSelector('#drawer:not(.hidden)', { timeout: 5000 });
    results.push({ name: `${name}-analytics-drawer`, visible: await page.locator('#drawer-content .u-head .u-name').first().isVisible() });
    await page.screenshot({ path: `${OUT}/analytics-${name}-drawer.png` });
    await page.click('.drawer-close', { force: true });
    if (name === 'desktop') await runAxe(`analytics-${name}`);

    // ── Аудитория (BUS-178 экран A) ──
    await page.click('.nav-item[data-view="audience"]');
    await page.waitForTimeout(700);
    const audVisible = await page.locator('#view-audience').isVisible();
    results.push({ name: `${name}-audience-visible`, visible: audVisible });
    results.push({
      name: `${name}-audience`,
      segments: await page.locator('#aud-segments tbody tr').count(),
      churnCards: await page.locator('#aud-churn .churn-card').count(),
      goals: await page.locator('#aud-goals .funnel-step').count(),
    });
    await page.screenshot({ path: `${OUT}/audience-${name}.png`, fullPage: true });

    // клик по строке сегмента → детализация
    await page.click('#aud-segments tbody tr');
    await page.waitForTimeout(400);
    const detailVisible = await page.locator('#aud-detail-card:not(.hidden)').count();
    results.push({ name: `${name}-audience-detail`, visible: detailVisible > 0 });
    await page.screenshot({ path: `${OUT}/audience-${name}-detail.png`, fullPage: false });
    await page.click('#aud-detail-back');
    if (name === 'desktop') await runAxe(`audience-${name}`);

    // ── Когорты (BUS-178 экран B) ──
    await page.click('.nav-item[data-view="cohorts"]');
    await page.waitForTimeout(700);
    const cohVisible = await page.locator('#view-cohorts').isVisible();
    results.push({ name: `${name}-cohorts-visible`, visible: cohVisible });
    results.push({
      name: `${name}-cohorts`,
      retentionRows: await page.locator('#coh-retention tbody tr').count(),
      curves: await page.locator('#coh-curves svg').count(),
      churnCards: await page.locator('#coh-churn .churn-card').count(),
    });
    await page.screenshot({ path: `${OUT}/cohorts-${name}.png`, fullPage: true });
    if (name === 'desktop') await runAxe(`cohorts-${name}`);

    // тёмная тема — родная, проверим светлую на деградацию
    if (name === 'mobile') {
      await page.emulateMedia({ colorScheme: 'light' });
      await page.screenshot({ path: `${OUT}/analytics-mobile-lightscheme.png`, fullPage: false });
      results.push({ name: 'mobile-light-scheme', note: 'снимок при colorScheme:light — тема фиксированная тёмная' });
    }
  } finally {
    await context.close();
  }
}

await fs.mkdir(OUT, { recursive: true });
await checkViewport('desktop');
await checkViewport('mobile');
await browser.close();

await fs.writeFile(`${OUT}/summary.json`, JSON.stringify({ results, errors }, null, 2) + '\n');
console.log(JSON.stringify({ results, errors }, null, 2));
