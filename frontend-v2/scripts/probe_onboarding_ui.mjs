/**
 * Живая браузерная проверка онбординга и записи профиля (этап 4.1).
 *
 * Отличие от scripts/routes.mjs: здесь важна СЕТЕВАЯ сторона — подсказки
 * городов и PATCH /api/profile с настоящей сессией. Без Telegram initData
 * backend отвечает 401 на всех защищённых ручках, поэтому initData
 * внедряется до загрузки приложения (как в routes.mjs).
 *
 * Пользователь берёся синтетический и ПОСЛЕ прогона сбрасывается в
 * незавершённое состояние флажком через bot-эндпоинт? Нет — сброс не делаем:
 * используем отдельный TG_ID, чтобы не ломать общие сценарии.
 *
 * Запуск:
 *   INIT_DATA=$(python3 scripts/make_init_data.py 10150) \
 *     node scripts/probe_onboarding_ui.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';

const URL = process.env.PROBE_URL ?? 'http://127.0.0.1:5180';
const INIT_DATA = process.env.INIT_DATA?.trim();
const TG_ID = Number(process.env.TG_ID ?? 10150);

let failures = 0;
const check = (ok, label, extra = '') => {
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${extra ? ' — ' + extra : ''}`);
};

if (!INIT_DATA) {
  console.error('нужен INIT_DATA (python3 scripts/make_init_data.py <tg_id>)');
  process.exit(2);
}

const EXE =
  process.env.CHROMIUM_PATH ??
  execFileSync('sh', ['-c', 'echo "$HOME/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"'])
    .toString()
    .trim();

const browser = await chromium.launch({
  executablePath: EXE,
  headless: true,
  args: ['--no-sandbox'],
});
const page = await browser.newPage({ viewport: { width: 420, height: 900 } });

const jsErrors = [];
page.on('pageerror', (error) => jsErrors.push(String(error)));

// initData до любых скриптов приложения — иначе /api/me уйдёт без подписи.
await page.addInitScript((data) => {
  Object.defineProperty(window, 'Telegram', {
    configurable: true,
    value: { WebApp: { initData: data } },
  });
}, INIT_DATA);

const requests = [];
page.on('response', (res) => {
  if (res.url().includes('/api/')) requests.push(`${res.status()} ${res.url().replace(URL, '')}`);
});

await page.goto(`${URL}/#/onboarding`, { waitUntil: 'networkidle' });

// ── Шаг 3: подсказки города ────────────────────────────────────────────────
await page.click('.onboarding__foot button.btn--primary');   // topic → birth
// Дата рождения: без неё completion честно упадёт 400 — это проверяется
// сценарием 6 в scripts/onboarding_profile.mjs, здесь заполняем.
await page.fill('#birth-date', '15.03.1992');
await page.click('.onboarding__foot button.btn--primary');   // birth → time
// Защита шага времени: при точном времени без него кнопка «Продолжить»
// заблокирована, чтобы не доходить до шага 5 и не получать общий отказ.
const blockedBeforeTime = await page
  .$eval('.onboarding__foot button.btn--primary', (b) => b.disabled)
  .catch(() => null);
check(
  blockedBeforeTime === true,
  'без времени на шаге «время и город» переход заблокирован',
  `disabled=${blockedBeforeTime}`,
);
// Время до города: проверка блокировки выше уже убедилась, что без времени
// не уйти, поэтому освобождаем шаг заранее.
await page.fill('#birth-time', '14:30');
await page.fill('#birth-city', 'моск');
await page.waitForSelector('.city-row', { timeout: 8000 });
const cities = await page.$$eval('.city-row', (rows) =>
  rows.map((r) => r.textContent.trim()),
);
check(cities.length > 0, 'подсказки городов пришли с сервера', `${cities.length}: ${cities.slice(0, 3).join(' | ')}`);
check(
  cities.some((c) => c.toLowerCase().includes('москва')),
  'Москва есть в подсказках',
  cities.join(' | '),
);
check(
  requests.some((r) => r.startsWith('200') && r.includes('/city/suggest')),
  'GET /api/city/suggest ответил 200',
  requests.find((r) => r.includes('city/suggest')) ?? 'нет запроса',
);

// Выбор города из подсказки кладёт `key`, а не `label`: для латинских
// подсказок (London) label сервер не принимает — 400 «Выбери город».
await page.click('.city-row');
const cityValue = await page.inputValue('#birth-city');
check(cityValue.length > 0, 'после выбора поле города заполнено', cityValue);
check(
  /[а-яё]/i.test(cityValue),
  'в поле — ключ словаря, а не латинский label',
  cityValue,
);

const unblocked = await page.$eval('.onboarding__foot button.btn--primary', (b) => b.disabled);
check(unblocked === false, 'переход разблокирован, когда время и город заполнены', `disabled=${unblocked}`);
await page.click('.onboarding__foot button.btn--primary');   // time → tone
await page.click('.onboarding__foot button.btn--primary');   // tone → age

// ── Шаг 5: 16+ и запись профиля ───────────────────────────────────────────
const confirm = await page.$('.age-row input[type=checkbox]');
await confirm.check();
const completeBtn = await page.$('.onboarding__foot button.btn--primary');
const disabledBefore = await completeBtn.isDisabled();
check(disabledBefore === false, 'кнопка завершения активна после 16+', `disabled=${disabledBefore}`);

// Дата рождения заполнена? Если пользователь уже проходил онбординг ранее,
// шаг birth был заполнен серверным значением — но в нашем потоке он пустой,
// поэтому completion честно упадёт 400, и мы проверяем именно эту честность.
const beforeDisabled = await completeBtn.isDisabled();
await completeBtn.click();

await page.waitForTimeout(5000);
const afterHash = await page.evaluate(() => window.location.hash);
const alertText = await page
  .$$eval('[role=alert]', (nodes) => nodes.map((n) => n.textContent.trim()).join(' | '))
  .catch(() => '');

if (afterHash.includes('first-insight')) {
  check(true, 'профиль сохранён, переход на First Insight', afterHash);
} else {
  check(
    alertText.length > 0,
    'профиль не сохранён молча: показана ошибка',
    `hash=${afterHash} alert="${alertText}"`,
  );
}

// Возврат на онбординг после успешного завершения не должен открываться:
// onboarded=true читается из /api/me, а не из локального флага.
await page.goto(`${URL}/#/onboarding`, { waitUntil: 'networkidle' });
await page.waitForTimeout(3000);
const blockedHash = await page.evaluate(() => window.location.hash);
const debugState = await page.evaluate(() => ({
  draft: window.localStorage.getItem('oracleai.onboarding.v1'),
  rootChildren: document.getElementById('root')?.children.length ?? 0,
}));
const showsOnboardingForm = await page.$('.onboarding__foot button.btn--primary');
const headText = await page.$eval('h1, .screen__title', (n) => n.textContent.trim()).catch(() => '');
check(
  !showsOnboardingForm,
  'завершённый онбординг не открывается повторно',
  `hash=${blockedHash} форма=${!!showsOnboardingForm} экран="${headText}" draft=${debugState.draft ? "есть" : "нет"}`,
);

check(jsErrors.length === 0, 'нет JS-ошибок', jsErrors.join(' | '));

// ── Settings: запись тона ─────────────────────────────────────────────────
await page.goto(`${URL}/#/settings`, { waitUntil: 'networkidle' });
// Экран рисует список тонов только после ответа /api/me (useMe): без ожидания
// селектор находится на скелетоне и ложно падает.
await page.waitForSelector('.tone-row', { timeout: 10000 });
const toneButtons = await page.$$('.tone-row');
check(toneButtons.length === 3, 'в настройках три тона', String(toneButtons.length));
if (toneButtons.length === 3) {
  const target = toneButtons[1];
  await target.click();
  await page.waitForTimeout(3500);
  const status = await page.$eval('.hint-text[aria-live=polite]', (n) => n.textContent.trim()).catch(() => '');
  check(
    /сохран|Сохранено/i.test(status),
    'после выбора тона показано состояние записи',
    status,
  );
}

console.log(`\nсетевые вызовы /api:\n${requests.map((r) => `  ${r}`).join('\n')}`);
console.log(`\n${failures === 0 ? 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' : `ПРОВАЛОВ: ${failures}`}`);
await browser.close();
process.exit(failures === 0 ? 0 : 1);
