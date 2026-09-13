#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const OUT = path.join(ROOT, 'artifacts', 'bus1140-size-matrix');
const CHROME_PATH = process.env.CHROME_PATH || '/home/softis/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome';
const BASE = 'http://127.0.0.1:8080/';
const VIEWPORTS = [
  { id: '320x568', width: 320, height: 568, label: 'mobile-small' },
  { id: '360x800', width: 360, height: 800, label: 'mobile-medium' },
  { id: '390x844', width: 390, height: 844, label: 'mobile-large' },
  { id: '430x932', width: 430, height: 932, label: 'mobile-xlarge' },
  { id: '768x1024', width: 768, height: 1024, label: 'tablet-portrait' },
  { id: '1024x768', width: 1024, height: 768, label: 'tablet-landscape' },
  { id: '1280x720', width: 1280, height: 720, label: 'desktop-hd' },
  { id: '1440x900', width: 1440, height: 900, label: 'desktop-sxga' },
  { id: '1920x1080', width: 1920, height: 1080, label: 'desktop-fhd' },
];
const STATES = [
  { id: 'home', view: 'home' },
  { id: 'chat-oracle', view: 'chat', agent: 'oracle' },
  { id: 'profile-summary', view: 'profile', tab: 'summary' },
];

function makeUrl(view, agent = '', tab = '') {
  const u = new URL(BASE);
  u.searchParams.set('dev_user', '10001');
  u.searchParams.set('qa', '1');
  u.searchParams.set('qa_view', view);
  if (agent) u.searchParams.set('qa_agent', agent);
  if (tab) u.searchParams.set('qa_tab', tab);
  return u.toString();
}

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const results = [];
try {
  await fs.rm(OUT, { recursive: true, force: true });
  await fs.mkdir(OUT, { recursive: true });

  for (const vp of VIEWPORTS) {
    const context = await browser.newContext({
      viewport: { width: vp.width, height: vp.height },
      locale: 'ru-RU',
      reducedMotion: 'reduce',
      bypassCSP: true,
      extraHTTPHeaders: process.env.DEV_KEY ? { 'X-Dev-Key': process.env.DEV_KEY } : {},
    });
    const page = await context.newPage();

    for (const state of STATES) {
      const url = makeUrl(state.view, state.agent || '', state.tab || '');
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.waitForTimeout(state.view === 'chat' ? 1200 : 600);

      const screenshotPath = path.join(OUT, `${vp.id}__${state.id}.png`);
      await page.screenshot({ path: screenshotPath, fullPage: true });

      const overflow = await page.evaluate(() => ({
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
        hasHorizontalScroll: document.documentElement.scrollWidth > window.innerWidth,
        bodyOverflow: document.body.scrollWidth > window.innerWidth,
      }));

      results.push({
        viewport: vp.id,
        width: vp.width,
        height: vp.height,
        state: state.id,
        url,
        screenshot: screenshotPath,
        overflow,
        pass: !overflow.hasHorizontalScroll && !overflow.bodyOverflow,
      });
      console.log(`${vp.id}/${state.id}: overflow=${overflow.hasHorizontalScroll || overflow.bodyOverflow}`);
    }

    await context.close();
  }
} finally { await browser.close(); }

await fs.writeFile(path.join(OUT, 'size-matrix-report.json'), JSON.stringify({ generatedAt: new Date().toISOString(), viewports: VIEWPORTS, results }, null, 2) + '\n');

const failures = results.filter(r => !r.pass);
if (failures.length > 0) {
  console.error(`Size matrix gate failed: ${failures.length} failures`);
  for (const f of failures) {
    console.error(`  ${f.viewport}/${f.state}: ${JSON.stringify(f.overflow)}`);
  }
  process.exitCode = 1;
} else {
  console.log(`Size matrix PASS: ${results.length} states × ${VIEWPORTS.length} viewports, 0 horizontal overflow`);
}
