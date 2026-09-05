#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright-core';
import axe from 'axe-core';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const OUT = path.join(ROOT, 'artifacts', process.env.QA_OUT_DIR || 'lighthouse-axe-final');
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome']).toString().trim();
const STATES = [
  ['home', 'home'], ['guides', 'hub'],
  ['chat-oracle', 'chat', 'oracle'], ['chat-astro', 'chat', 'astro'],
  ['chat-tarot', 'chat', 'tarot'], ['chat-chiromant', 'chat', 'chiromant'],
  ['profile-summary', 'profile', '', 'summary'], ['profile-chart', 'profile', '', 'chart'],
  ['profile-history', 'profile', '', 'history'], ['profile-memory', 'profile', '', 'memory'],
];

function makeUrl(view, agent = '', tab = '') {
  const u = new URL('http://127.0.0.1:8080/');
  u.searchParams.set('dev_user', '10001'); u.searchParams.set('qa', '1'); u.searchParams.set('qa_view', view);
  if (agent) u.searchParams.set('qa_agent', agent);
  if (tab) u.searchParams.set('qa_tab', tab);
  return u.toString();
}

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 }, locale: 'ru-RU', reducedMotion: 'reduce', bypassCSP: true,
  // DEV_KEY обязателен при DEV_MODE=1 (BUS-90): без заголовка dev_user ловит 401.
  extraHTTPHeaders: process.env.DEV_KEY ? { 'X-Dev-Key': process.env.DEV_KEY } : {},
});
const page = await context.newPage();
const results = [];
try {
  await fs.rm(OUT, { recursive: true, force: true }); await fs.mkdir(OUT, { recursive: true });
  for (const [id, view, agent = '', tab = ''] of STATES) {
    const url = makeUrl(view, agent, tab);
    await page.goto(url, { waitUntil: 'networkidle' }); await page.waitForTimeout(view === 'chat' ? 1200 : 600);
    await page.addScriptTag({ content: axe.source });
    const result = await page.evaluate(async () => window.axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'best-practice'] } }));
    await fs.writeFile(path.join(OUT, `${id}.json`), JSON.stringify(result, null, 2) + '\n');
    results.push({ id, url, violations: result.violations.length, incomplete: result.incomplete.length, passes: result.passes.length, violationIds: result.violations.map((item) => item.id), incompleteIds: result.incomplete.map((item) => item.id) });
    console.log(`${id}: violations=${result.violations.length} incomplete=${result.incomplete.length} passes=${result.passes.length}`);
  }
} finally { await context.close(); await browser.close(); }
await fs.writeFile(path.join(OUT, 'summary.json'), JSON.stringify({ generatedAt: new Date().toISOString(), viewport: { width: 1440, height: 900 }, states: results }, null, 2) + '\n');
if (results.some((item) => item.violations > 0)) {
  console.error('Axe accessibility gate failed: inspect the per-state JSON reports.');
  process.exitCode = 1;
}
