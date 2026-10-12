import { createHash } from 'node:crypto';
import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * Production-сборка OracleAI V2 под существующий контракт раздачи.
 *
 * ФАКТИЧЕСКИЙ production-путь (проверено по app/api/main.py, не по документации):
 *   - сервер раздаёт `miniapp/index.html` и подменяет CSS/JS на записи из
 *     `miniapp/dist/manifest.json` (`_miniapp_index_body`, main.py:309-347);
 *   - `miniapp/dist/` смонтирован как `/static` (main.py:393), поэтому бандл
 *     `app.<hash>.min.js` отдаётся по `/static/dist/app...`;
 *   - в `APP_ENV=production` отсутствующий или нечитаемый manifest — RuntimeError
 *     при старте (fail-fast, FE-002), fallback на исходники запрещён.
 *
 * Контракт имён (scripts/check_frontend_build.py):
 *   `^app\.[0-9a-f]{12}\.min\.(js|css)$` для `js` и `css` из manifest; в manifest
 *   дополнительно должны быть `jsFiles`/`cssFiles`, сверяемые с index.html.
 *
 * Поэтому: файлы пишутся СРАЗУ с требуемыми именами (переименование по хешу
 * содержимого), а manifest.json следуюет за ними в том же каталоге.
 */

/**
 * Имя файла в контракте miniapp: ровно 12 hex-символов (`[0-9a-f]{12}`).
 *
 * SHA-256, обрезанный до 12 символов — тот же приём, что в
 * scripts/build_frontend.mjs (contentHash). Детерминированный: одинаковый
 * исходник даёт одинаковое имя (cache-busting работает), и без двусмысленностей
 * короткого хеша — bundle ~300 КБ меняет имя при любой правке содержимого.
 */
function hashedName(source: string, ext: 'js' | 'css'): string {
  return `app.${createHash('sha256').update(source).digest('hex').slice(0, 12)}.min.${ext}`;
}

/**
 * Приводит имена артефактов к контракту miniapp и пишет manifest.json.
 * Совместимость: check_frontend_build.py требует не فقط имён, но и совпадения
 * количества исходных модулей — для V2 это одна точка входа, поэтому
 * jsFiles/cssFiles описывают граф сборки, а не захардкоженные счётчики.
 */
function miniappContract(): Plugin {
  return {
    name: 'oracleai-miniapp-contract',
    enforce: 'post',
    generateBundle(_options, bundle) {
      const manifest: Record<string, unknown> = {};

      for (const chunk of Object.values(bundle)) {
        if (chunk.type === 'chunk') {
          const name = hashedName(chunk.code ?? '', 'js');
          const previous = chunk.fileName;
          chunk.fileName = name;
          manifest.js = name;
          manifest.jsFiles = ['frontend-v2/src/main.tsx'];
          renameInHtml(bundle, previous, name);
        } else if (chunk.fileName.endsWith('.css')) {
          const source = String(chunk.source);
          const name = hashedName(source, 'css');
          const previous = chunk.fileName;
          chunk.fileName = name;
          manifest.css = name;
          // V2 держит весь CSS в трёх токен-слоях; в manifest — фактический граф.
          manifest.cssFiles = [
            'frontend-v2/src/styles/tokens.css',
            'frontend-v2/src/styles/base.css',
            'frontend-v2/src/styles/components.css',
          ];
          renameInHtml(bundle, previous, name);
        }
      }

      this.emitFile({
        type: 'asset',
        fileName: 'manifest.json',
        source: JSON.stringify(manifest, null, 2),
      });
    },
  };
}

/**
 * Vite вставляет в index.html ссылки с исходными именами (`./assets/...`).
 * После переименования бандла под контракт miniapp HTML остаётся с мёртвыми
 * путями — поэтому переписываем ссылки в самом шаблоне. Иначе production
 * открывал бы страницу без JS и CSS.
 */
function renameInHtml(bundle: Record<string, unknown>, from: string, to: string): void {
  const html = bundle['index.html'];
  if (!html || html.type !== 'asset' || typeof html.source !== 'string') return;
  const escaped = from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  html.source = html.source.replace(
    new RegExp(`(["'\./])${escaped}`, 'g'),
    (_full, prefix: string) => `${prefix}${to}`,
  );
}

export default defineConfig({
  plugins: [react(), miniappContract()],
  // Сборка раздаётся тем же origin, что и API (main.py монтирует /static),
  // поэтому базовый путь относительный.
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // В production статика (картинки/шрифты) раздаётся сервером с /static,
    // поэтому public/ НЕ копируется: иначе legacy-файлы miniapp/ дублировались бы
    // внутрь V2-сборки (17 МБ) и появлялось бы два источника правды.
    // Для dev-раздачи public/ нужен — там он подменяется отдельно ниже.
    copyPublicDir: process.env.NODE_ENV !== 'production' || process.env.VITE_COPY_PUBLIC === '1',
    // Сервер вставляет ровно одну строку <script>: один входной чанк.
    rollupOptions: { output: { inlineDynamicImports: true } },
    assetsInlineLimit: 0,
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.API_TARGET ?? 'http://172.29.0.2:8080', changeOrigin: true },
      '/static': { target: process.env.API_TARGET ?? 'http://172.29.0.2:8080', changeOrigin: true },
    },
  },
});
