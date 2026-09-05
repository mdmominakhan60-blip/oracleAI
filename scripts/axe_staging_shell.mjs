import fs from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright-core';
import axe from 'axe-core';

const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome']).toString().trim();
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: 'ru-RU', reducedMotion: 'reduce', ignoreHTTPSErrors: true, deviceScaleFactor: 3, isMobile: true, hasTouch: true, bypassCSP: true });
const page = await context.newPage();
try {
  await page.goto('https://localhost:3443/', { waitUntil: 'networkidle', timeout: 20000 });
  await page.waitForTimeout(1500);
  const title = await page.title();
  const introVisible = await page.evaluate(() => { const el = document.getElementById('intro'); return el ? getComputedStyle(el).display !== 'none' : false; });
  const bodyText = (await page.evaluate(() => document.body.innerText)).slice(0, 400);
  await page.addScriptTag({ content: axe.source });
  const result = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'best-practice'] } }));
  const out = { url: 'https://localhost:3443/', title, introVisible, bodyTextPreview: bodyText, violations: result.violations, incomplete: result.incomplete.length, passes: result.passes.length };
  await fs.writeFile('artifacts/axe-staging-shell.json', JSON.stringify({ ...out, violations: result.violations, incomplete: result.incomplete }, null, 2));
  await page.screenshot({ path: 'artifacts/axe-staging-shell.png', fullPage: false });
  console.log('title:', title);
  console.log('introVisible:', introVisible);
  console.log('bodyText:', JSON.stringify(bodyText.slice(0, 200)));
  console.log('violations:', result.violations.length, 'ids:', result.violations.map(v => v.id + ' x' + v.nodes.length).join(', '));
  console.log('incomplete:', result.incomplete.length, 'passes:', result.passes.length);
} catch (e) { console.error('FAIL:', e.message.slice(0, 300)); } finally { await context.close(); await browser.close(); }
