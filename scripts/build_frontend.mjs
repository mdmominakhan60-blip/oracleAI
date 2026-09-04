import { createHash } from 'node:crypto';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { transform } from 'esbuild';

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const DIST = path.join(MINIAPP, 'dist');

function contentHash(value) {
  return createHash('sha256').update(value).digest('hex').slice(0, 12);
}

async function read(relativePath) {
  return fs.readFile(path.join(MINIAPP, relativePath), 'utf8');
}

async function build() {
  const index = await fs.readFile(path.join(MINIAPP, 'index.html'), 'utf8');
  const styles = await fs.readFile(path.join(MINIAPP, 'styles.css'), 'utf8');
  const jsFiles = [...index.matchAll(/<script src="\/static\/js\/([^"?]+)\?v=\d+"><\/script>/g)].map((match) => `js/${match[1]}`);
  const cssFiles = [...styles.matchAll(/@import url\('css\/([^?'\)]+)/g)].map((match) => `css/${match[1]}`);
  if (!jsFiles.length || !cssFiles.length) throw new Error('Could not discover Mini App JS/CSS entry files');

  const jsSource = (await Promise.all(jsFiles.map(read))).join('\n;\n');
  const cssSource = (await Promise.all(cssFiles.map(read))).join('\n');
  const [jsResult, cssResult] = await Promise.all([
    transform(jsSource, {
      loader: 'js',
      target: 'es2020',
      minifySyntax: true,
      minifyWhitespace: true,
      minifyIdentifiers: false,
      legalComments: 'none',
    }),
    transform(cssSource, { loader: 'css', minify: true }),
  ]);

  await fs.rm(DIST, { recursive: true, force: true });
  await fs.mkdir(DIST, { recursive: true });
  const jsName = `app.${contentHash(jsResult.code)}.min.js`;
  const cssName = `app.${contentHash(cssResult.code)}.min.css`;
  await Promise.all([
    fs.writeFile(path.join(DIST, jsName), jsResult.code),
    fs.writeFile(path.join(DIST, cssName), cssResult.code),
    fs.writeFile(path.join(DIST, 'manifest.json'), `${JSON.stringify({ js: jsName, css: cssName, jsFiles, cssFiles }, null, 2)}\n`),
  ]);
  console.log(JSON.stringify({ js: jsName, css: cssName, jsFiles: jsFiles.length, cssFiles: cssFiles.length }, null, 2));
}

build().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
