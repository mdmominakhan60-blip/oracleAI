#!/usr/bin/env node
// BUS-237: UI-верификация экрана R6 «Отзывы» на mock-стенде (desktop + mobile).
import fs from 'node:fs/promises';
import { chromium } from '/home/softis/apps/oraclAI/oracleAI/node_modules/playwright-core/index.mjs';
import axe from 'axe-core';

const OUT = process.argv[2] || '/tmp/paperclip-run-bus-237-e248e4be-1d5-PUwN46/ui-evidence';
const CHROME_PATH = process.env.CHROME_PATH || '/usr/bin/google-chrome-stable';
const BASE = 'http://127.0.0.1:8791';
const results = [];
const errors = [];

await fs.mkdir(OUT, { recursive: true });
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
    await page.click('.nav-item[data-view="feedback"]');
    await page.waitForSelector('#view-feedback.active', { timeout: 5000 });
    await page.waitForFunction(() => document.querySelector('#fb-responses tbody tr'), { timeout: 5000 });

    const npsScore = await page.textContent('#fb-nps-score');
    const kpiText = (await page.textContent('#fb-kpi')).replace(/\s+/g, ' ').trim().slice(0, 80);
    results.push(`[${name}] NPS score: ${npsScore.trim()}`);
    results.push(`[${name}] KPI: ${kpiText}`);
    const headers = await page.$$eval('#fb-responses thead th', (cells) => cells.map((c) => c.textContent.trim()));
    results.push(`[${name}] колонки: ${headers.join(', ')}`);
    const quote = (await page.textContent('#fb-responses .fb-quote')).trim().slice(0, 40);
    results.push(`[${name}] free text: ${quote}…`);
    const badges = await page.$$eval('#fb-responses .badge', (nodes) => nodes.map((n) => n.textContent.trim()));
    results.push(`[${name}] модерация-бейджи: ${badges.join(' | ')}`);

    await page.selectOption('#fb-question', 'like');
    await page.waitForTimeout(300);
    const choiceVisible = await page.isVisible('#fb-choice-wrap #fb-choice');
    results.push(`[${name}] выбор варианта при вопросе «Понравилось»: ${choiceVisible}`);
    const totalAfter = await page.textContent('#fb-total');
    results.push(`[${name}] total после фильтра like: ${totalAfter.trim()}`);
    await page.selectOption('#fb-question', '');

    await page.screenshot({ path: `${OUT}/feedback-${name}.png`, fullPage: false });
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.waitForTimeout(200);
    await page.screenshot({ path: `${OUT}/feedback-${name}-dark.png`, fullPage: false });

    await page.addScriptTag({ content: axe.source });
    const axeResult = await page.evaluate(async () => window.axe.run('#view-feedback', { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } }));
    await fs.writeFile(`${OUT}/axe-feedback-${name}.json`, JSON.stringify({ violations: axeResult.violations }, null, 2) + '\n');
    const vios = axeResult.violations.map((v) => `${v.id}(${v.nodes.length})`);
    results.push(`[${name}] axe violations: ${vios.length ? vios.join(', ') : 'нет'}`);
  } catch (error) {
    errors.push(`[${name}] FAIL: ${error.message}`);
  } finally {
    await context.close();
  }
}

await checkViewport('desktop');
await checkViewport('mobile');
await browser.close();

await fs.writeFile(`${OUT}/results.txt`, [...results, '', ...errors.map((e) => `ERROR: ${e}`)].join('\n') + '\n');
console.log(results.join('\n'));
if (errors.length) {
  console.error('\nERRORS:\n' + errors.join('\n'));
  process.exit(1);
}
console.log('\nALL CHECKS PASSED');
