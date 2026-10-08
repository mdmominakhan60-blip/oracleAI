/** Interaction + visual QA against real Mini App code with isolated API fixtures.
 * Does NOT prove live Telegram, payment-provider or production backend behavior.
 */
import { chromium } from 'playwright-core';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createPreviewServer } from './redesign_preview.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = process.env.ORACLE_QA_OUT || '/tmp/oracleai-design-qL7gjN3l/qa';
const CHROME = process.env.CHROME_PATH || '/home/softis/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome';
const results = [];
const check = (name, passed, detail = '') => { results.push({ name, passed: !!passed, detail }); console.log(`${passed ? 'PASS' : 'FAIL'} ${name}${detail ? ': ' + detail : ''}`); };
const { server, calls } = createPreviewServer();
await fs.mkdir(OUT, { recursive: true });
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ executablePath: CHROME, args: ['--no-sandbox'] });
const pageErrors = [];
async function newPage(scenario = 'saved', width = 390, height = 844) {
  const context = await browser.newContext({ viewport: { width, height }, locale: 'ru-RU', reducedMotion: 'reduce' });
  const page = await context.newPage();
  page.on('pageerror', error => pageErrors.push(error.message));
  await page.route('**/*', route => route.request().url().startsWith(base) ? route.continue() : route.abort());
  await page.goto(`${base}/?scenario=${scenario}`);
  await page.waitForFunction(() => window.app?.me && document.querySelector('#app-main')?.textContent.trim().length > 0);
  await page.evaluate(() => document.fonts.ready);
  return { context, page };
}
async function next(page, step) {
  await page.locator('[data-act="ob-next"]').click();
  await page.waitForSelector(`.onboarding[data-ob-step="${step}"]`);
}
try {
  const { context, page } = await newPage('save-error');
  await page.locator('[data-intent="astro"]').click();
  await page.locator('#ob-name').fill('А');
  await page.locator('[data-act="ob-next"]').click();
  check('Name validation shows readable error', await page.locator('[data-ob-error]').isVisible() && !!(await page.locator('[data-ob-error]').textContent()).trim());
  await page.locator('#ob-name').fill('Анна');
  await next(page, 3);
  await page.locator('#ob-day').fill('31'); await page.locator('#ob-month').fill('2'); await page.locator('#ob-year').fill('1990');
  await page.locator('[data-act="ob-next"]').click();
  check('Invalid calendar date stays on step', await page.locator('.onboarding').getAttribute('data-ob-step') === '3');
  await page.locator('#ob-day').fill('21'); await page.locator('#ob-month').fill('6');
  await next(page, 4);
  await page.locator('[data-time-choice="exact"]').click();
  // A resumed profile may already contain a valid time; explicitly test blank input.
  await page.locator('#ob-hour').fill('');
  await page.locator('#ob-min').fill('');
  await page.locator('[data-act="ob-next"]').click();
  check('Blank exact time is not midnight', await page.locator('.onboarding').getAttribute('data-ob-step') === '4');
  await page.locator('[data-time-choice="approx"]').click();
  await page.locator('#ob-hour').fill('14'); await page.locator('#ob-min').fill('30');
  await next(page, 5);
  await page.locator('#ob-city').fill('несуществующий');
  await page.locator('[data-act="ob-next"]').click();
  check('Unconfirmed city cannot continue', await page.locator('.onboarding').getAttribute('data-ob-step') === '5');
  await page.locator('#ob-city').fill('киши');
  await page.locator('[data-city-pick]').first().waitFor();
  check('City request uses real API contract', calls.some(c => c.path === '/api/city/suggest' && c.query.includes('q=')));
  check('City suggestions show country', (await page.locator('#ob-city-list').textContent()).includes('Молдова'));
  await page.screenshot({ path: path.join(OUT, 'onboarding-city-mobile.png') });
  await page.locator('#ob-city').press('ArrowDown'); await page.locator('#ob-city').press('Enter');
  await next(page, 'review');
  await page.screenshot({ path: path.join(OUT, 'onboarding-review-mobile.png') });
  await page.locator('[data-act="ob-next"]').click();
  await page.waitForFunction(() => !app._obSaving);
  check('Failed save stays on review', await page.locator('.onboarding[data-ob-step="review"]').count() === 1);
  check('Failed save retains form and retry', await page.locator('[data-ob-error]').isVisible() && await page.locator('[data-act="ob-next"]').isEnabled());
  await page.locator('[data-act="ob-next"]').click();
  await page.waitForFunction(() => !document.querySelector('.onboarding'));
  const save = calls.filter(c => c.path === '/api/profile' && c.body.onboarding_complete).at(-1)?.body;
  check('Successful save carries approximate precision and confirmed key', save?.birth_time_precision === 'approx' && save?.birth_time === '14:30' && save?.city === 'кишинев');
  await page.reload(); await page.waitForFunction(() => window.app?.me?.onboarded);
  check('Completed account is not re-onboarded', await page.locator('.onboarding').count() === 0);
  await context.close();

  const resumed = await newPage('resume-time');
  await resumed.page.waitForSelector('.onboarding[data-ob-step="4"]');
  check('Partial bot profile resumes at missing time', await resumed.page.locator('.onboarding').getAttribute('data-ob-step') === '4');
  await resumed.page.locator('[data-act="ob-back"]').click();
  check('Partial bot profile retains its saved birth date',
    await resumed.page.locator('#ob-day').inputValue() === '21' &&
    await resumed.page.locator('#ob-month').inputValue() === '06' &&
    await resumed.page.locator('#ob-year').inputValue() === '1990');
  await resumed.context.close();

  for (const width of [360, 390, 768, 1440]) {
    const { context, page } = await newPage('saved', width, width >= 768 ? 1000 : 844);
    const colors = await page.evaluate(() => ({ accent: getComputedStyle(document.documentElement).getPropertyValue('--color-accent-hover').trim(), background: getComputedStyle(document.documentElement).getPropertyValue('--color-bg').trim() }));
    check(`${width}: semantic tokens resolve`, !!colors.accent && !!colors.background, JSON.stringify(colors));
    for (const view of ['home', 'hub', 'library', 'profile']) {
      await page.locator(`#main-nav [data-goto="${view}"]`).click();
      await page.waitForTimeout(180);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      check(`${width}: ${view} no horizontal overflow`, !overflow);
      await page.screenshot({ path: path.join(OUT, `${view}-${width}.png`) });
    }
    await page.locator('#main-nav [data-goto="hub"]').click();
    const mutationsBefore = calls.filter(c => c.method !== 'GET').length;
    await page.locator('[data-act="chat"][data-chat="oracle"]').first().click();
    await page.locator('#chat-input').waitFor();
    check(`${width}: opening agent does not send paid request`, calls.filter(c => c.method !== 'GET' && /\/chat\//.test(c.path)).length === 0);
    check(`${width}: legacy chat clutter removed`, await page.locator('.chat-proof-strip, .agent-tabs, .agent-intro').count() === 0);
    await page.screenshot({ path: path.join(OUT, `chat-${width}.png`) });
    await page.locator('#chat-input').fill('Хочу обсудить новый этап в работе.');
    if (width < 768) {
      await page.setViewportSize({ width, height: 500 });
      await page.locator('#chat-input').focus();
      const box = await page.locator('#chat-input').boundingBox();
      check(`${width}: composer stays reachable in compact viewport`, box && box.y >= 0 && box.y + box.height <= 501);
      await page.screenshot({ path: path.join(OUT, `chat-compact-${width}.png`) });
    }
    await page.addScriptTag({ path: path.join(ROOT, 'node_modules/axe-core/axe.min.js') });
    const a11y = await page.evaluate(async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21aa'] } })).violations.map(v => ({ id: v.id, impact: v.impact, nodes: v.nodes.length })));
    check(`${width}: chat no serious/critical accessibility violations`, !a11y.some(v => ['serious', 'critical'].includes(v.impact)), JSON.stringify(a11y));
    await context.close();
  }
} catch (error) {
  check('QA runner completes', false, error.stack);
} finally {
  check('No uncaught browser errors', pageErrors.length === 0, pageErrors.join('; '));
  await fs.writeFile(path.join(OUT, 'results.json'), JSON.stringify({ fixtureOnly: true, results, pageErrors, apiCalls: calls }, null, 2));
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
process.exitCode = results.some(r => !r.passed) ? 1 : 0;
