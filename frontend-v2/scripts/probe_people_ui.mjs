/**
 * Живая браузерная проверка People, Person Profile и Timeline (этап 4.3).
 *
 * Проверяет в Chromium:
 * 1. Открытие #/people с пустым списком → EmptyState без фиктивных людей.
 * 2. Добавление человека через форму (имя, дата рождения, отношение, город).
 * 3. Появление созданного человека в списке.
 * 4. Переход в карточку человека #/people/:personId.
 * 5. Отображение реальных данных: имя, отношение, дата, город.
 * 6. Расчет совместимости через реальный POST /api/compat и показ баллов.
 * 7. Переход в таймлайн #/people/:personId/timeline → честное пустое состояние.
 * 8. Возврат в карточку человека.
 * 9. Удаление человека с подтверждением через реальный DELETE /api/partners/{id}.
 * 10. Возврат в список, проверка что он пуст.
 * 11. Открытие несуществующего ID #/people/999999 → состояние «Человек не найден».
 *
 * Запуск:
 *   INIT_DATA=$(python3 scripts/make_init_data.py <tg_id>) node scripts/probe_people_ui.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';

const EXE =
  process.env.CHROMIUM_PATH ??
  execFileSync('sh', ['-c', 'echo "$HOME/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"'])
    .toString()
    .trim();

let pass = 0,
  fail = 0;
const check = (ok, label, extra = '') => {
  if (ok) {
    pass++;
    console.log('PASS ' + label);
  } else {
    fail++;
    console.log('FAIL ' + label + ' ' + extra);
  }
};

const b = await chromium.launch({
  executablePath: EXE,
  headless: true,
  args: ['--no-sandbox'],
});
const p = await b.newPage({ viewport: { width: 420, height: 900 } });

const errs = [];
p.on('pageerror', (e) => errs.push(String(e)));
p.on('console', (m) => {
  if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) {
    errs.push(m.text());
  }
});

await p.addInitScript((d) => {
  Object.defineProperty(window, 'Telegram', {
    configurable: true,
    value: { WebApp: { initData: d } },
  });
}, process.env.INIT_DATA);

// ── 1. PeopleScreen: пустой список без фиктивных данных ──
await p.goto('http://127.0.0.1:5180/#/people', { waitUntil: 'networkidle' });

const heading = await p.$eval('.screen__title', (el) => el.textContent.trim());
check(heading === 'Люди', 'заголовок экрана «Люди»', heading);

const demoBadge = await p.$('.demo-badge');
check(!demoBadge, 'отсутствует демо-бейдж в PeopleScreen');

const items0 = await p.$$('.person-list li');
check(items0.length === 0, 'нет фиктивных людей в начале', `items=${items0.length}`);

const emptyState = await p.$('.state--empty');
check(!!emptyState, 'показано пустое состояние при отсутствии людей');

// ── 2. Открытие формы добавления человека ──
const addBtn = await p.$('button:has-text("Добавить")');
check(!!addBtn, 'кнопка добавления присутствует');
await addBtn.click();
await p.waitForSelector('#person-name', { timeout: 5000 });

// ── 3. Заполнение формы и отправка ──
await p.fill('#person-name', 'Дмитрий');
await p.fill('#person-birth-date', '1990-07-15');
await p.fill('#person-city', 'моск');
await p.waitForSelector('.city-row', { timeout: 8000 });
await p.click('.city-row'); // выбираем подсказку «Москва»

// Выбор отношения: друг
const friendChip = await p.$('.chip-row button:has-text("Друг")');
if (friendChip) await friendChip.click();

await p.click('form button[type=submit]');
await p.waitForTimeout(3000);

// ── 4. Появление созданного человека в списке ──
const peopleAfterAdd = await p.$$('.person-list li');
check(peopleAfterAdd.length === 1, 'после добавления в списке ровно 1 человек', `count=${peopleAfterAdd.length}`);

const personName = await p.$eval('.person-row__name', (el) => el.textContent.trim());
check(personName === 'Дмитрий', 'имя добавленного человека совпадает', personName);

const personMeta = await p.$eval('.person-row__meta', (el) => el.textContent.trim());
check(personMeta.includes('1990-07-15'), 'дата рождения отображается в карточке', personMeta);

// ── 5. Переход в Person Profile по клику ──
await p.click('.person-row');
await p.waitForTimeout(1000);

const hashProfile = await p.evaluate(() => window.location.hash);
check(/^#\/people\/\d+$/.test(hashProfile), 'переход по URL #/people/:id', hashProfile);

const profileTitle = await p.$eval('.screen__title', (el) => el.textContent.trim());
check(profileTitle === 'Дмитрий', 'заголовок профиля — имя человека', profileTitle);

const profileKicker = await p.$eval('.kicker', (el) => el.textContent.trim());
check(profileKicker === 'Друг', 'связь в кикере профиля — Друг', profileKicker);

const personDemoBadge = await p.$('.demo-badge');
check(!personDemoBadge, 'отсутствует демо-бейдж в PersonScreen');

// ── 6. Расчет совместимости через реальный POST /api/compat ──
const compatBtn = await p.$('.person-actions button:has-text("Совместимость")');
check(!!compatBtn, 'кнопка «Совместимость» присутствует');
await compatBtn.click();
await p.waitForSelector('.card--raised .card__title', { timeout: 10000 });

const compatTitle = await p.$eval('.card--raised .card__title', (el) => el.textContent.trim());
check(/Совместимость:\s*\d+%/i.test(compatTitle), 'показан реальный балл совместимости', compatTitle);

const verdictText = await p.$eval('.card--raised .pattern-text', (el) => el.textContent.trim()).catch(() => '');
check(verdictText.length > 0, 'показан вердикт совместимости от сервера', verdictText);

// ── 7. Переход в TimelineScreen ──
const timelineActionBtn = await p.$('.screen__action button:has-text("Наша история")');
check(!!timelineActionBtn, 'кнопка перехода в таймлайн присутствует');
await timelineActionBtn.click();
await p.waitForTimeout(1000);

const hashTimeline = await p.evaluate(() => window.location.hash);
check(/^#\/people\/\d+\/timeline$/.test(hashTimeline), 'переход в таймлайн #/people/:id/timeline', hashTimeline);

const timelineKicker = await p.$eval('.kicker', (el) => el.textContent.trim());
check(timelineKicker === 'Дмитрий', 'кикер таймлайна — имя человека', timelineKicker);

const timelineEmpty = await p.$('.state--empty');
check(!!timelineEmpty, 'таймлайн честно показывает пустое состояние (нет выдуманных связей)');

const timelineDemoBadge = await p.$('.demo-badge');
check(!timelineDemoBadge, 'отсутствует демо-бейдж в TimelineScreen');

// ── 8. Возврат в профиль человека ──
const backToProfileBtn = await p.$('.screen__action button');
await backToProfileBtn.click();
await p.waitForTimeout(1000);

const hashBack = await p.evaluate(() => window.location.hash);
check(/^#\/people\/\d+$/.test(hashBack), 'возврат в карточку человека', hashBack);

// ── 9. Удаление человека с подтверждением ──
const deleteBtn = await p.$('button:has-text("Удалить человека")');
check(!!deleteBtn, 'кнопка удаления присутствует');
await deleteBtn.click();
await p.waitForTimeout(400);

const confirmPrompt = await p.$('.form-error[role=alert]');
check(!!confirmPrompt, 'показан вопрос подтверждения удаления');

// Клик по «Да, удалить»
const confirmYesBtn = await p.$('button:has-text("Да, удалить")');
await confirmYesBtn.click();
await p.waitForTimeout(2500);

const hashAfterDelete = await p.evaluate(() => window.location.hash);
check(hashAfterDelete === '#/people', 'после удаления возврат в список #/people', hashAfterDelete);

const peopleAfterDelete = await p.$$('.person-list li');
check(peopleAfterDelete.length === 0, 'список людей снова пуст после удаления', `count=${peopleAfterDelete.length}`);

// ── 10. Открытие несуществующего человека ──
await p.goto('http://127.0.0.1:5180/#/people/999999', { waitUntil: 'networkidle' });
await p.waitForTimeout(1000);

const notFoundTitle = await p.$eval('.state--empty .state__title', (el) => el.textContent.trim()).catch(() => '');
check(/не найден/i.test(notFoundTitle), 'несуществующий ID показывает «Человек не найден»', notFoundTitle);

check(errs.length === 0, 'нет JS-ошибок в консоли', errs.join(' | ').slice(0, 300));

console.log(`\nИТОГ: ${pass} PASS, ${fail} FAIL`);
await b.close();
process.exit(fail > 0 ? 1 : 0);
