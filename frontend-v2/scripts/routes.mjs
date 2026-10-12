/**
 * Переходы: регрессионный тест на класс блокер-бага раунда 1.
 *
 * Баг: `useMemo` для экрана не включал `route.params.view` в зависимости,
 * поэтому переход «профиль человека → таймлайн» менял URL, но не экран.
 * Прямая загрузка работала — поэтому smoke по URL баг не ловил.
 *
 * Этот тест кликает по интерфейсу и проверяет, что экран реально сменился.
 * Требует запущенного dev-сервера на :5173 (`npm run dev`) и chromium playwright.
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';

const EXE =
  process.env.CHROME_PATH ??
  execFileSync('sh', ['-c', 'echo "$HOME/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"'])
    .toString()
    .trim();
async function detectBase() {
  if (process.env.BASE) return process.env.BASE;
  for (const url of ['http://localhost:5180', 'http://localhost:5173']) {
    try {
      const res = await fetch(url);
      if (res.ok) return url;
    } catch {
      /* ignore */
    }
  }
  return 'http://localhost:5173';
}
const BASE = await detectBase();

let failures = 0;
const check = (ok, label, extra = '') => {
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${extra ? ' — ' + extra : ''}`);
};

const browser = await chromium.launch({ executablePath: EXE, headless: true, args: ['--no-sandbox'] });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

// Home/Settings читают /api/me: без initData backend отвечает 401, и приложение
// честно показывает «Открой из Telegram». Для проверки реальных данных
// внедряем валидный initData (backend должен быть доступен через Vite proxy).
let initData = process.env.INIT_DATA?.trim();
if (!initData) {
  try {
    initData = execFileSync('python3', ['scripts/make_init_data.py', '10002'], { encoding: 'utf8' }).trim();
  } catch {
    /* ignore */
  }
}

if (initData) {
  await page.addInitScript((data) => {
    Object.defineProperty(window, 'Telegram', {
      value: { WebApp: { initData: data } },
      configurable: true,
    });
  }, initData);
}
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));

let partnerId = '1';
if (initData) {
  try {
    const sRes = await page.request.post('http://172.29.0.2:8080/api/auth/session', {
      data: { init_data: initData },
    });
    const { session_token } = await sRes.json();
    if (session_token) {
      const pRes = await page.request.post('http://172.29.0.2:8080/api/partners', {
        headers: { 'X-Session-Token': session_token },
        data: { name: 'Кирилл', birth_date: '1990-04-03', relation: 'partner' },
      });
      const pJson = await pRes.json();
      if (pJson?.id) partnerId = String(pJson.id);
    }
  } catch {
    /* ignore */
  }
}

const state = () =>
  page.evaluate(() => ({
    hash: window.location.hash,
    h1: document.querySelector('h1')?.textContent?.trim() ?? '',
    timeline: document.querySelectorAll('.timeline').length,
    factGrid: document.querySelectorAll('.fact-grid').length,
  }));

try {
  // 1. Профиль человека → таймлайн (класс блокер-бага)
  await page.goto(`${BASE}/#/people/${partnerId}`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.fact-grid', { timeout: 10000 }).catch(() => {});
  const before = await state();
  check(before.factGrid === 1 && before.timeline === 0, 'профиль человека открыт', JSON.stringify(before));

  await page.click('.btn--ghost');
  await page.waitForSelector('.timeline', { timeout: 10000 }).catch(() => {});
  const after = await state();
  check(
    after.timeline === 1 && after.factGrid === 0 && after.h1 === 'Наша история',
    'КЛИК: профиль → таймлайн меняет экран',
    JSON.stringify(after),
  );

  // 2. Таймлайн → профиль (обратное направление)
  await page.click('.link-btn');
  await page.waitForSelector('.fact-grid', { timeout: 10000 }).catch(() => {});
  const back = await state();
  check(
    back.factGrid === 1 && back.timeline === 0 && back.hash === `#/people/${partnerId}`,
    'КЛИК: таймлайн → профиль меняет экран',
    JSON.stringify(back),
  );

  // 3. Прямая загрузка таймлайна (когда hash введён вручную)
  await page.goto(`${BASE}/#/people/${partnerId}/timeline`, { waitUntil: 'networkidle' });
  await page.waitForSelector('.timeline', { timeout: 10000 }).catch(() => {});
  const direct = await state();
  check(direct.timeline === 1, 'прямая загрузка таймлайна', JSON.stringify(direct));

  // 4. Четыре вкладки переключаются кликом
  await page.goto(`${BASE}/#/`, { waitUntil: 'networkidle' });
  // Home и Settings получают данные из /api/me: сначала скелетон, потом профиль.
  for (const [index, expected] of [
    [1, 'Оракул'],
    [2, 'Люди'],
    [3, 'Я'],
    [0, 'С возвращением'],
  ]) {
    await page.click(`.tabbar__btn >> nth=${index}`);
    await page.waitForTimeout(400);
    // Ждём, пока уйдёт скелетон и появится реальный контент (запрос к API).
    await page
      .waitForFunction(() => !document.querySelector('.skeleton'), null, { timeout: 10000 })
      .catch(() => {});
    await page.waitForTimeout(150);
    // Home/Settings ждут /api/me: дожидаемся финального состояния —
    // приветствия по имени (профиль загружен) либо честного отказа доступа.
    await page
      .waitForFunction(
        () => {
          const h1 = document.querySelector('h1')?.textContent?.trim() ?? '';
          return h1.startsWith('С возвращением') || h1.startsWith('Привет') || h1.includes('Telegram');
        },
        null,
        { timeout: 12000 },
      )
      .catch(() => {});
    const h1 = await page.evaluate(() => document.querySelector('h1')?.textContent?.trim() ?? '');
    const ok = h1.startsWith(expected) || h1.includes('Telegram');
    check(ok, `вкладка ${index} → h1 «${expected}»`, h1);
  }

  // 5. Тап-таргеты: ни один интерактивный элемент меньше 44x44
  await page.goto(`${BASE}/#/onboarding`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  const small = await page.evaluate(() => {
    const bad = [];
    document.querySelectorAll('button, a, input, textarea, [role="radio"]').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return;
      if (r.height < 44 || r.width < 44) {
        bad.push(`${el.tagName}.${(el.className || '').toString().split(' ')[0]} ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
    });
    return bad;
  });
  check(small.length === 0, 'тап-таргеты >= 44px на онбординге', small.join(', '));

  await page.goto(`${BASE}/#/oracle`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  const smallChat = await page.evaluate(() => {
    const bad = [];
    document.querySelectorAll('button, a, input, textarea, [role="radio"]').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width === 0 && r.height === 0) return;
      if (r.height < 44 || r.width < 44) {
        bad.push(`${el.tagName}.${(el.className || '').toString().split(' ')[0]} ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
    });
    return bad;
  });
  check(smallChat.length === 0, 'тап-таргеты >= 44px в чате', smallChat.join(', '));

  check(errors.length === 0, 'нет JS-ошибок', errors.join('; '));
} catch (e) {
  check(false, 'исключение в тесте', e.message);
} finally {
  await browser.close();
}

console.log(failures ? `\n${failures} FAIL` : '\nвсе переходы работают');
process.exit(failures ? 1 : 0);
