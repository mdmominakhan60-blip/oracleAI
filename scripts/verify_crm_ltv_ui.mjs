#!/usr/bin/env node
// BUS-312: UI-верификация очереди внимания, LTV-таба и gift-формы на mock-стенде
// (desktop + mobile, светлая/тёмная тема, axe wcag2a/aa).
import fs from 'node:fs/promises';
import { chromium } from '/home/softis/apps/oraclAI/oracleAI/node_modules/playwright-core/index.mjs';
import axe from 'axe-core';

const OUT = process.argv[2] || '/tmp/bus312-ui-evidence';
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

    // ── 1. Очередь внимания ────────────────────────────────────────────────
    await page.click('.nav-item[data-view="attention-queue"]');
    await page.waitForSelector('#view-attention-queue.active', { timeout: 5000 });
    await page.waitForFunction(() => document.querySelectorAll('#queue-list .queue-card').length > 0, { timeout: 5000 });

    const cards = await page.$$eval('#queue-list .queue-card', (nodes) => nodes.length);
    results.push(`[${name}] карточек в очереди: ${cards}`);
    const summary = (await page.textContent('#queue-header .queue-summary')).replace(/\s+/g, ' ').trim();
    results.push(`[${name}] сводка: ${summary.slice(0, 90)}`);

    // overdue-бейдж
    const overdueBadges = await page.$$eval('#queue-list .queue-card-badges .badge', (nodes) =>
      nodes.map((n) => n.textContent.trim()).filter((t) => /просроч/i.test(t)));
    results.push(`[${name}] overdue-бейджи: ${overdueBadges.length ? overdueBadges.join(', ') : 'нет'}`);

    // открыть плейбук pb-7 (Q1 refund, первая карточка) — он рендерится в drawer
    await page.click('#queue-list .queue-card .queue-playbook');
    await page.waitForSelector('#drawer:not(.hidden) #pb-text', { timeout: 5000 });
    const pbMsg = await page.inputValue('#pb-text');
    results.push(`[${name}] плейбук pb-7 открыт, текст: ${pbMsg.trim().slice(0, 60)}…`);
    await page.screenshot({ path: `${OUT}/queue-${name}.png`, fullPage: false });
    await page.click('#drawer .drawer-close');
    await page.waitForFunction(() => document.querySelector('#drawer').classList.contains('hidden'), { timeout: 5000 });

    // axe для очереди
    await page.addScriptTag({ content: axe.source });
    const axeQueue = await page.evaluate(async () => window.axe.run('#view-attention-queue', { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } }));
    await fs.writeFile(`${OUT}/axe-queue-${name}.json`, JSON.stringify({ violations: axeQueue.violations }, null, 2) + '\n');
    const viosQ = axeQueue.violations.map((v) => `${v.id}(${v.nodes.length})`);
    results.push(`[${name}] axe очередь: ${viosQ.length ? viosQ.join(', ') : 'нет'}`);

    // закрыть плейбук (Esc/крестик не гарантирован) — просто уходим в users
    await page.keyboard.press('Escape');

    // ── 2. Карточка клиентки: LTV-таб + gift-форма ─────────────────────────
    await page.click('.nav-item[data-view="users"]');
    await page.waitForSelector('#view-users.active', { timeout: 5000 });
    await page.waitForFunction(() => document.querySelectorAll('#users-table tbody tr').length > 0, { timeout: 5000 });
    await page.click('#users-table tbody tr');
    await page.waitForSelector('#drawer:not(.hidden)', { timeout: 5000 });
    await page.waitForSelector('.u-tab[data-pane="ltv"]', { timeout: 5000 });

    // gift-форма (owner: eligible) — до/после
    await page.waitForFunction(() => {
      const b = document.querySelector('#gift-body');
      return b && !/Проверяем/.test(b.textContent);
    }, { timeout: 5000 });
    const giftText = (await page.textContent('#gift-body')).replace(/\s+/g, ' ').trim();
    results.push(`[${name}] gift-форма: ${giftText.slice(0, 70)}`);

    // LTV-таб
    await page.click('.u-tab[data-pane="ltv"]');
    await page.waitForTimeout(200);
    const ltvPaneVisible = await page.isVisible('.u-pane[data-pane="ltv"]');
    results.push(`[${name}] LTV-таб виден: ${ltvPaneVisible}`);
    const ltvStats = await page.$$eval('.u-pane[data-pane="ltv"] .u-stat', (nodes) =>
      nodes.map((n) => n.textContent.replace(/\s+/g, ' ').trim()));
    results.push(`[${name}] LTV-метрики: ${ltvStats.join(' · ').slice(0, 140)}`);
    const nba = (await page.textContent('.u-pane[data-pane="ltv"]')).match(/Что сделать/);
    results.push(`[${name}] next_best_action блок: ${nba ? 'есть' : 'нет'}`);
    const tlItems = await page.$$eval('.u-pane[data-pane="ltv"] .timeline div', (nodes) => nodes.length);
    results.push(`[${name}] таймлайн касаний: ${tlItems}`);

    await page.screenshot({ path: `${OUT}/ltv-${name}.png`, fullPage: false });

    // gift submit: reason обязателен
    await page.click('.u-tab[data-pane="actions"]');
    await page.waitForTimeout(200);
    await page.fill('#gf-reason', 'компенсация теста BUS-312');
    await page.click('#gf-do');
    await page.waitForFunction(() => /OP[A-Z0-9]+/.test(document.querySelector('#gift-body')?.textContent || ''), { timeout: 5000 });
    const giftResult = (await page.textContent('#gift-body')).replace(/\s+/g, ' ').trim();
    results.push(`[${name}] gift выдан: ${giftResult.slice(0, 90)}`);
    await page.screenshot({ path: `${OUT}/gift-${name}.png`, fullPage: false });

    // тёмная тема
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.waitForTimeout(200);
    await page.click('.u-tab[data-pane="ltv"]');
    await page.screenshot({ path: `${OUT}/ltv-${name}-dark.png`, fullPage: false });

    // axe для карточки (весь drawer)
    const axeCard = await page.evaluate(async () => window.axe.run('#drawer', { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] } }));
    await fs.writeFile(`${OUT}/axe-drawer-${name}.json`, JSON.stringify({ violations: axeCard.violations }, null, 2) + '\n');
    const viosC = axeCard.violations.map((v) => `${v.id}(${v.nodes.length})`);
    results.push(`[${name}] axe карточка: ${viosC.length ? viosC.join(', ') : 'нет'}`);

    await page.keyboard.press('Escape');
  } catch (error) {
    errors.push(`[${name}] FAIL: ${error.message}`);
    try { await page.screenshot({ path: `${OUT}/fail-${name}.png`, fullPage: true }); } catch { /* ignore */ }
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
