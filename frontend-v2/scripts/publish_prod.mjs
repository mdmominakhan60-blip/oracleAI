/**
 * Публикация production-сборки V2 в miniapp/dist под конкретным именем.
 *
 * ЗАЧЕМ: backend подставляет в miniapp/index.html записи из miniapp/dist/manifest.json
 * (app/api/main.py). V2 собирается в frontend-v2/dist — поэтому копирование
 * в общий каталог должно быть ЯВНЫМ, обратимым и не затрагивать legacy-файлы.
 *
 * Использование:
 *   node scripts/publish_prod.mjs --dry-run   # показать, что легло бы
 *   node scripts/publish_prod.mjs             # скопировать app.*.min.{js,css}+manifest
 *   node scripts/publish_prod.mjs --revert    # удалить только файлы V2 (по manifest)
 *
 * Безопасность: скрипт НИКОГДА не удаляет чужие файлы и не трогает index.html —
 * только собственные артефакты, перечисленные в manifest.json.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const DIST = path.join(ROOT, '..', 'frontend-v2', 'dist');
const TARGET = path.join(ROOT, '..', 'miniapp', 'dist');
const args = process.argv.slice(2);
const dryRun = args.includes('--dry-run');
const revert = args.includes('--revert');

function readManifest() {
  const file = path.join(DIST, 'manifest.json');
  if (!fs.existsSync(file)) {
    console.error('нет frontend-v2/dist/manifest.json — сначала npm run build');
    process.exit(1);
  }
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

/** Что удалять при откате: артефакты V2 из miniapp/dist + служебные маркеры. */
function publishedFiles() {
  const m = readManifest();
  return [m.js, m.css, 'v2.json', 'v2index.html'].filter(Boolean);
}

if (revert) {
  const files = publishedFiles();
  for (const name of files) {
    const p = path.join(TARGET, name);
    if (!fs.existsSync(p)) continue;
    if (dryRun) { console.log(`[dry-run] удалил бы ${name}`); continue; }
    fs.unlinkSync(p);
    console.log(`удалён ${name}`);
  }
  console.log(revert ? 'откат завершён (legacy-файлы не тронуты)' : '');
  process.exit(0);
}

const m = readManifest();
fs.mkdirSync(TARGET, { recursive: true });

/**
 * Публикация во временный файл + атомарное переименование.
 *
 * ПОЧЕМУ ТАК: `rename()` внутри одной файловой системы — атомарная операция
 * POSIX: наблюдатель либо видит старый файл, либо новый, никогда — половину.
 * Несколько подряд идущих `copyFileSync` такой гарантии НЕ дают: обрыв между
 * ними оставляет в каталоге файл, у которого нет согласованного marker'а.
 *
 * ПОРЯДОК: сначала артефакты (js/css), потом marker v2.json, потом шаблон.
 * Сервер включает V2 только при наличии v2.json, поэтому неполный набор из
 * тех файлов, что пишутся ДО маркёра, backend'у не виден — он продолжит
 * отдавать legacy. Это дополнительный барьер, а не атомарность:原子ность даёт
 * именно rename для КАЖДОГО файла, а не порядок записи набора.
 */
function publishAtomic(src, dest, label) {
  const tmp = `${dest}.tmp-${process.pid}`;
  fs.copyFileSync(src, tmp);
  fs.renameSync(tmp, dest);
  console.log(`опубликован ${label}`);
}

function writeAtomic(content, dest, label) {
  const tmp = `${dest}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, content);
  fs.renameSync(tmp, dest);
  console.log(`опубликован ${label}`);
}

for (const name of [m.js, m.css]) {
  const src = path.join(DIST, name);
  if (!fs.existsSync(src)) {
    console.error(`в сборке нет ${name}`);
    process.exit(1);
  }
  const dest = path.join(TARGET, name);
  if (dryRun) { console.log(`[dry-run] ${src} -> ${dest}`); continue; }
  publishAtomic(src, dest, name);
}

// v2.json — marker, по которому backend отличает бандл V2 от legacy
// (общий manifest.json в этом каталоге принадлежит scripts/build_frontend.mjs).
// v2index.html — шаблон оболочки V2: сервер подставляет в него имена бандла.
const marker = JSON.stringify({ js: m.js, css: m.css, publishedAt: new Date().toISOString() }, null, 2);
const template = fs.existsSync(path.join(DIST, 'index.html'))
  ? fs.readFileSync(path.join(DIST, 'index.html'), 'utf8')
  : "<!doctype html><html lang='ru'><head><meta charset='utf-8'></head><body><div id='root'></div></body></html>";

if (dryRun) {
  console.log('[dry-run] записал бы v2.json и v2index.html');
  process.exit(0);
}

// Снапшот предыдущего состояния: если публикация прервётся между записями,
// откатываем опубликованное, чтобы не осталось несогласованного набора.
const previous = new Map();
for (const name of [...publishedFiles()]) {
  const p = path.join(TARGET, name);
  previous.set(name, fs.existsSync(p) ? fs.readFileSync(p) : null);
}

try {
  writeAtomic(template, path.join(TARGET, 'v2index.html'), 'v2index.html');
  writeAtomic(marker, path.join(TARGET, 'v2.json'), 'v2.json (marker V2)');
} catch (error) {
  console.error(`публикация прервана: ${error.message}`);
  console.error('откат к предыдущему состоянию…');
  for (const [name, content] of previous) {
    const p = path.join(TARGET, name);
    try {
      if (content === null) fs.unlinkSync(p);
      else fs.writeFileSync(p, content);
      console.log(`  восстановлен ${name}`);
    } catch (restoreError) {
      console.error(`  НЕ УДАЛОСЬ восстановить ${name}: ${restoreError.message}`);
    }
  }
  process.exit(1);
}
