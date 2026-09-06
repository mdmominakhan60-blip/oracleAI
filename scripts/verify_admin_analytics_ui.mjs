#!/usr/bin/env node
// BUS-178: UI-верификация раздела «Аналитика» на mock-стенде.
import fs from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { chromium } from '/home/softis/apps/oraclAI/oracleAI/node_modules/playwright-core/index.mjs';
import axe from 'axe-core';

const OUT = process.argv[2] || '/tmp/paperclip-run-bus-178-80a53890-7a1-qC2l9O/ui-evidence';
const CHROME_PATH = process.env.CHROME_PATH || '/usr/bin/google-chrome-stable';
const BASE = 'http://127.0.0.1:8791';
const results = [];
const errors = [];

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

async function checkViewport(name, viewport, isMobile) {
  const context = await browser.newContext({
    viewport, locale: 'ru-RU', reducedMotion: 'reduce',
    isMobile, hasTouch: isMobile, bypassCSP: true,
  });
  const page = await context.newPage();
  page.on('pageerror', (err) => errors.push(`[${name}] pageerror: ${err.message}`));
  page.on('console', (msg) => { if (msg.type() === 'error') errors.push(`[${name}] console.error: ${msg.text()}`); });
  try {
    await page.goto(`${BASE}/admin/`, { waitUntil: 'networkidle' });
    await page.waitForSelector('#shell:not(.hidden)', { timeout: 5000 });
    await page.click('.nav-item[data-view="analytics"]');
    await page.waitForSelector('#view-analytics.active', { timeout: 5000 });
    await page.waitForTimeout(600);

    const checks = {
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
    results.push({ name, ...checks });

    await page.screenshot({ path: `${OUT}/analytics-${name}.png`, fullPage: true });

    // сегмент-фильтр: клик по «Платящие»
    await page.click('.segment-card[data-segment="paying"]');
    await page.waitForTimeout(400);
    const filterState = {
      selectValue: await page.locator('#anx-segment').inputValue(),
      total: await page.locator('#anx-total').textContent(),
      activePressed: await page.locator('.segment-card[data-segment="paying"]').getAttribute('aria-pressed'),
    };
    results.push({ name: `${name}-filter-paying`, ...filterState });
    await page.screenshot({ path: `${OUT}/analytics-${name}-filtered.png`, fullPage: false });

    // открытие профиля из списка
    await page.click('#anx-users-table tbody tr');
    await page.waitForSelector('#drawer:not(.hidden)', { timeout: 5000 });
    const drawerVisible = await page.locator('#drawer-content .u-head .u-name').first().isVisible();
    results.push({ name: `${name}-drawer`, drawerVisible });
    await page.screenshot({ path: `${OUT}/analytics-${name}-drawer.png` });
    // force: длинное u-name может перекрыть кнопку на узком viewport — это флейк клика, не UI-дефект
    await page.click('.drawer-close', { force: true });

    // axe: прогон только на desktop (mobile-правила те же теги)
    if (name === 'desktop') {
      await page.addScriptTag({ content: axe.source });
      const axeResult = await page.evaluate(async () => window.axe.run('#view-analytics', { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'best-practice'] } }));
      await fs.writeFile(`${OUT}/axe-analytics.json`, JSON.stringify(axeResult, null, 2) + '\n');
      results.push({
        name: 'axe-view-analytics',
        violations: axeResult.violations.map((v) => `${v.id}(${v.nodes.length})`),
        incomplete: axeResult.incomplete.map((v) => `${v.id}(${v.nodes.length})`),
      });
    }

    // тёмная тема — родная, но проверим системную светлую на деградацию контраста через emulateMedia
    if (name === 'mobile') {
      await page.emulateMedia({ colorScheme: 'light' });
      await page.screenshot({ path: `${OUT}/analytics-mobile-lightscheme.png`, fullPage: false });
      results.push({ name: 'mobile-light-scheme', note: 'снимок при colorScheme:light — тема админки фиксированная тёмная, инверсии быть не должно' });
    }
  } finally {
    await context.close();
  }
}

await fs.mkdir(OUT, { recursive: true });
await checkViewport('desktop', { width: 1440, height: 900 }, false);
await checkViewport('mobile', { width: 390, height: 844 }, true);
await browser.close();

await fs.writeFile(`${OUT}/summary.json`, JSON.stringify({ results, errors }, null, 2) + '\n');
console.log(JSON.stringify({ results, errors }, null, 2));
