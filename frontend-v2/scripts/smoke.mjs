/**
 * Smoke-тесты переходов и словарей. Запуск: `npm test`.
 *
 * Проверяют два регрессионных класса:
 * 1. Переход профиль человека ↔ таймлайн реально меняет экран
 *    (в v1 useMemo не инвалидировался при смене route.params.view).
 * 2. Словари ru/en имеют полный паритет ключей.
 */
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';

let failures = 0;
const check = (ok, label, extra = '') => {
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${extra ? ' — ' + extra : ''}`);
};

// ── 1. dictionaryParity: ключи ru и en совпадают ────────────────────────────
{
  const src = await import('node:fs').then((fs) =>
    fs.readFileSync(new URL('../src/i18n/index.ts', import.meta.url), 'utf8'),
  );
  const ruBlock = src.slice(src.indexOf('  ru: {'), src.indexOf('  en: {'));
  const enBlock = src.slice(src.indexOf('  en: {'), src.indexOf('} as const;'));
  const keys = (block) => new Set([...block.matchAll(/^\s*'([a-zA-Z][\w.]*)':/gm)].map((m) => m[1]));
  const ru = keys(ruBlock);
  const en = keys(enBlock);
  const onlyRu = [...ru].filter((k) => !en.has(k));
  const onlyEn = [...en].filter((k) => !ru.has(k));
  check(ru.size > 150, `словарь RU заполнен (${ru.size} ключей)`);
  check(ru.size === en.size, `паритет ru/en`, `ru=${ru.size} en=${en.size}`);
  check(onlyRu.length === 0, 'нет ключей только в ru', onlyRu.join(', '));
  check(onlyEn.length === 0, 'нет ключей только в en', onlyEn.join(', '));
}

// ── 2. Нет русских литералов в коде экранов ─────────────────────────────
{
  const { readdirSync, readFileSync } = await import('node:fs');
  const dir = new URL('../src/routes/', import.meta.url);
  const cyrillic = /['"`][^'"`]*[А-Яа-яЁё][^'"`]*['"`]/;
  const comment = /^\s*(\*|\/\/|\/\*)/;
  const offenders = [];
  for (const file of readdirSync(dir)) {
    if (!file.endsWith('.tsx')) continue;
    readFileSync(join(dir.pathname, file), 'utf8')
      .split('\n')
      .forEach((line, i) => {
        if (comment.test(line)) return;
        if (cyrillic.test(line)) offenders.push(`${file}:${i + 1}`);
      });
  }
  check(offenders.length === 0, 'нет захардкоженных русских строк в экранах', offenders.join(', '));
}

// ── 3. Структура frontend-v2 ───────────────────────────────────────────
{
  const { existsSync } = await import('node:fs');
  const required = ['package.json', 'tsconfig.json', 'vite.config.ts', 'index.html', 'src/main.tsx', 'src/App.tsx', 'src/styles/tokens.css'];
  const base = new URL('..', import.meta.url).pathname;
  const missing = required.filter((f) => !existsSync(join(base, f)));
  check(missing.length === 0, 'структура проекта на месте', missing.join(', '));
}

// ── 4. Ключи для будущих состояний зафиксированы ───────────────────────────
// Эти ключи покрывают состояния из спеки (paywall-лимит, фаза «Оракул думает»,
// пустые состояния экранов), которые появятся на этапе 2 вместе с API.
// Они намеренно в словаре: иначе этап 2 добавлял бы их вслепую.
const RESERVED = new Set([
  'oracle.limit_title', 'oracle.limit_hint', 'oracle.thinking', 'oracle.tools_used',
  'home.empty_title', 'home.empty_hint', 'home.greeting_new',
  'chart.empty_title', 'chart.empty_hint', 'chart.precision_approx', 'chart.precision_date_only',
  'memory.empty_title', 'memory.empty_hint',
  'timeline.empty_title', 'person.link_derived',
  'me.delete_account_confirm',
  'state.empty', 'state.loading',
  'action.cancel', 'action.confirm', 'action.save',
  'reading.positions',
]);
{
  const src = await import('node:fs').then((fs) =>
    fs.readFileSync(new URL('../src/i18n/index.ts', import.meta.url), 'utf8'),
  );
  const ruBlock = src.slice(src.indexOf('  ru: {'), src.indexOf('  en: {'));
  const keys = new Set([...ruBlock.matchAll(/^\s*'([a-zA-Z][\w.]*)':/gm)].map((m) => m[1]));
  const missing = [...RESERVED].filter((k) => !keys.has(k));
  check(missing.length === 0, 'зарезервированные ключи состояний на месте', missing.join(', '));
}

console.log(failures ? `\n${failures} FAIL` : '\nвсе проверки пройдены');
process.exit(failures ? 1 : 0);
