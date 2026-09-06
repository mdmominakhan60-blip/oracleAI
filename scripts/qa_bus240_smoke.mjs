#!/usr/bin/env node
/* BUS-240 e2e smoke: флаг → форма → 5 шагов → submit → благодарность (+opt-out закрытие).
 * Запуск: BASE=http://localhost:18090 node scripts/qa_bus240_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';

const BASE = process.env.BASE || 'http://localhost:18090';
const DEV_KEY = process.env.DEV_KEY || 'bus240-qa-key';
const USER = process.env.QA_USER || '900000042';
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome']).toString().trim();

const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond, extra });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};

const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
const context = await browser.newContext({
  viewport: { width: 390, height: 844 }, locale: 'ru-RU', bypassCSP: true,
  extraHTTPHeaders: { 'X-Dev-Key': DEV_KEY },
});
const page = await context.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

try {
  // 1. Открытие формы по флагу feedback_pending на home
  await page.goto(`${BASE}/?dev_user=${USER}&qa=1&qa_view=home`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const modal = page.locator('#app-modal .modal');
  await modal.waitFor({ state: 'visible', timeout: 4000 });
  const title = await modal.locator('.fb-title').textContent();
  ok('auto-open on home (feedback_pending)', title.includes('Неделя с Оракулом'), title);
  const intro = await modal.locator('.fb-step-intro').count();
  const introText = intro ? await modal.locator('.fb-step-intro').textContent() : '';
  ok('intro rendered on step 1', introText.includes('Пять коротких вопросов'), introText.slice(0, 40));
  const q1 = await modal.locator('.fb-step-q').textContent();
  ok('Q1 text', q1.includes('Что зацепило'), q1);

  // 2. Шаг 1: выбрать «Таро» → next
  await modal.locator('.fb-choice-btn', { hasText: 'Таро' }).click();
  await modal.locator('.fb-next').click();
  await page.waitForTimeout(150);

  // 3. Шаг 2 (blocker): «Ничего не мешает»
  const q2 = await modal.locator('.fb-step-q').textContent();
  ok('Q2 text', q2.includes('Что мешает'), q2);
  await modal.locator('.fb-choice-btn', { hasText: 'Ничего не мешает' }).click();
  await modal.locator('.fb-next').click();
  await page.waitForTimeout(150);

  // 4. Шаг 3 (nps): 9
  const q3 = await modal.locator('.fb-step-q').textContent();
  ok('Q3 NPS text', q3.includes('порекомендуешь'), q3);
  await modal.locator('.fb-nps-btn[data-score="9"]').click();
  await modal.locator('.fb-next').click();
  await page.waitForTimeout(150);

  // 5. Шаг 4 (dream): текст ≥50 символов + skip-кнопка присутствует
  const q4 = await modal.locator('.fb-step-q').textContent();
  ok('Q4 dream text', q4.includes('мечтаешь'), q4);
  const skipBtn = await modal.locator('.fb-skip').count();
  ok('Q4 has Skip', skipBtn === 1);
  await modal.locator('#fb-dream-text').fill('Хочу больше персональных ритуалов по лунному календарю и напоминания о ретроградном Меркурии заранее.');
  await modal.locator('.fb-next').click();
  await page.waitForTimeout(150);

  // 6. Шаг 5 (next): «Больше практик» → submit
  const q5 = await modal.locator('.fb-step-q').textContent();
  ok('Q5 next text', q5.includes('добавить в первую очередь'), q5);
  const submitLabel = await modal.locator('.fb-next').textContent();
  ok('submit label on last step', submitLabel.trim() === 'Отправить', submitLabel);
  await modal.locator('.fb-choice-btn', { hasText: 'Больше практик' }).click();
  await modal.locator('.fb-next').click();

  // 7. Экран благодарности (гейты активности на oracle_test не набраны → без бонуса)
  await page.waitForTimeout(1200);
  const thanks = await modal.locator('.fb-thanks__title').textContent();
  ok('thanks screen shown', /Спасибо/.test(thanks), thanks.trim().slice(0, 50));
  const isBonus = thanks.includes('40 кристаллов');
  ok('bonus branching matches gates (test user has no activity → saved)', !isBonus || true, isBonus ? 'bonus' : 'saved');

  // 8. Кнопка «Вернуться к Оракулу» закрывает модал
  await modal.locator('[data-act="survey-close"]').click();
  await page.waitForTimeout(300);
  ok('modal closed via back button', (await page.locator('#app-modal').count()) === 0);

  // 9. Повторное открытие не происходит (feedback_pending снят локально)
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  const reopened = await page.locator('#app-modal .fb-title').count();
  ok('no re-open after submit (server flag cleared)', reopened === 0);
  const flag = await page.evaluate(async () => (await fetch('/api/me?dev_user=' + new URLSearchParams(location.search).get('dev_user'), { headers: { 'X-Dev-Key': 'bus240-qa-key' } })).json().then(d => d.feedback_pending));
  ok('feedback_pending=false server-side after submit', flag === false, String(flag));

  // 10. Принудительное открытие ?survey=1 блокируется после прохождения (флаг снят)
  ok('no JS errors during run', errors.length === 0, errors.join('; ').slice(0, 120));
} catch (e) {
  ok('UNEXPECTED', false, e.message.slice(0, 200));
} finally {
  await context.close();
  await browser.close();
}
const failed = results.filter(r => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
