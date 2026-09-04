#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { launch } from 'chrome-launcher';
import lighthouse from 'lighthouse';
import { chromium } from 'playwright-core';
import axe from 'axe-core';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const OUT = path.join(ROOT, 'artifacts', process.env.QA_OUT_DIR || 'lighthouse-axe');
const LH_CATEGORIES = (process.env.LH_CATEGORIES || 'performance,accessibility,best-practices,seo').split(',').filter(Boolean);
const BASE = 'http://127.0.0.1:8080/';
const VIEWPORT = { width: 1440, height: 900 };
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome']).toString().trim();
const STATES = [
  { id: 'home', view: 'home' },
  { id: 'guides', view: 'hub' },
  { id: 'chat-oracle', view: 'chat', agent: 'oracle' },
  { id: 'chat-astro', view: 'chat', agent: 'astro' },
  { id: 'chat-tarot', view: 'chat', agent: 'tarot' },
  { id: 'chat-chiromant', view: 'chat', agent: 'chiromant' },
  { id: 'profile-summary', view: 'profile', tab: 'summary' },
  { id: 'profile-chart', view: 'profile', tab: 'chart' },
  { id: 'profile-history', view: 'profile', tab: 'history' },
  { id: 'profile-memory', view: 'profile', tab: 'memory' },
];

function stateUrl(state) {
  const url = new URL(BASE);
  url.searchParams.set('dev_user', '10001');
  url.searchParams.set('qa', '1');
  url.searchParams.set('qa_view', state.view);
  if (state.agent) url.searchParams.set('qa_agent', state.agent);
  if (state.tab) url.searchParams.set('qa_tab', state.tab);
  return url.toString();
}

function categoryScore(categories, id) {
  const score = categories?.[id]?.score;
  return typeof score === 'number' ? Math.round(score * 100) : null;
}

async function run() {
  await fs.rm(OUT, { recursive: true, force: true });
  await fs.mkdir(OUT, { recursive: true });
  const chrome = await launch({
    chromePath: CHROME_PATH,
    chromeFlags: ['--headless=new', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
  });
  const browser = await chromium.launch({
    executablePath: CHROME_PATH,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const axeContext = await browser.newContext({
    viewport: VIEWPORT, locale: 'ru-RU', reducedMotion: 'reduce',
    // DEV_KEY обязателен при DEV_MODE=1 (BUS-90): без заголовка dev_user ловит 401.
    extraHTTPHeaders: process.env.DEV_KEY ? { 'X-Dev-Key': process.env.DEV_KEY } : {},
  });
  const page = await axeContext.newPage();
  const summary = { generatedAt: new Date().toISOString(), viewport: VIEWPORT, states: [] };
  let gateFailed = false;

  try {
    for (const state of STATES) {
      const url = stateUrl(state);
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.waitForTimeout(state.view === 'chat' ? 1200 : 600);
      await page.addScriptTag({ content: axe.source });
      const axeResults = await page.evaluate(async () => {
        const result = await window.axe.run(document, {
          runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'best-practice'] },
        });
        return {
          violations: result.violations,
          incomplete: result.incomplete,
          passes: result.passes,
          inapplicable: result.inapplicable,
        };
      });
      await fs.writeFile(path.join(OUT, `${state.id}.axe.json`), JSON.stringify(axeResults, null, 2) + '\n');

      const lh = await lighthouse(url, {
        port: chrome.port,
        logLevel: 'silent',
        output: 'json',
        onlyCategories: LH_CATEGORIES,
        formFactor: 'desktop',
        screenEmulation: { mobile: false, width: VIEWPORT.width, height: VIEWPORT.height, deviceScaleFactor: 1 },
        throttlingMethod: 'provided',
        disableStorageReset: true,
        extraHeaders: process.env.DEV_KEY ? { 'X-Dev-Key': process.env.DEV_KEY } : {},
      });
      const lhr = lh.lhr;
      await fs.writeFile(path.join(OUT, `${state.id}.lighthouse.json`), JSON.stringify(lhr, null, 2) + '\n');
      if (axeResults.violations.length > 0 ||
          (LH_CATEGORIES.includes('accessibility') && categoryScore(lhr.categories, 'accessibility') !== 100)) {
        gateFailed = true;
      }
      summary.states.push({
        ...state,
        url,
        lighthouse: {
          performance: categoryScore(lhr.categories, 'performance'),
          accessibility: categoryScore(lhr.categories, 'accessibility'),
          bestPractices: categoryScore(lhr.categories, 'best-practices'),
          seo: categoryScore(lhr.categories, 'seo'),
          runtimeError: lhr.runtimeError || null,
        },
        axe: {
          violations: axeResults.violations.length,
          incomplete: axeResults.incomplete.length,
          passes: axeResults.passes.length,
          violationIds: axeResults.violations.map((item) => item.id),
          incompleteIds: axeResults.incomplete.map((item) => item.id),
        },
      });
      console.log(`${state.id}: Lighthouse a${summary.states.at(-1).lighthouse.accessibility ?? 'n/a'} / Axe violations ${axeResults.violations.length}`);
    }
  } finally {
    await axeContext.close();
    await browser.close();
    await chrome.kill();
  }
  await fs.writeFile(path.join(OUT, 'summary.json'), JSON.stringify(summary, null, 2) + '\n');
  console.log(JSON.stringify(summary, null, 2));
  if (gateFailed) {
    console.error('Frontend accessibility gate failed: inspect the per-state axe/Lighthouse reports.');
    process.exitCode = 1;
  }
}

run().catch((error) => {
  console.error(error.stack || error);
  process.exitCode = 1;
});
