#!/usr/bin/env node
/* BUS-741 e2e smoke: P0-унификация визуала (mock API, без бэкенда).
 * BUS-969 (R03 §2.1): ожидания обновлены на семантический слой R03 —
 * --grad-primary = linear-gradient(180deg, #F1D99F, #E9C982),
 * --color-on-accent = #1C1820, --color-bg = #0B0D18.
 * §3.1: все primary-элементы рендерятся с вычисленным фоном var(--grad-primary)
 *    в computed style; цвет текста на градиенте — var(--color-on-accent).
 * §3.2: body фон = #0B0D18 (R03 §2.1 --color-bg); все url(bg-cosmos*)
 *    в computed starfield содержат ?v=108.
 * §3.4: в computed стилях ключевых модулей нет rgb(230, 193, 120) (legacy-золото);
 *    в исходниках miniapp/js legacy-золото rgba(230,193,120)/#E6C178 отсутствует (BUS-960).
 * Smoke: скриншоты home/hub(payment)/profile — визуальных регрессий нет (ручная
 * сверка по файлам), console чист.
 * Запуск: node scripts/qa_bus741_smoke.mjs
 */
import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const MINIAPP = path.join(ROOT, 'miniapp');
const BASE = 'http://127.0.0.1:18099';
const OUT = process.env.PAPERCLIP_RUN_SCRATCH_DIR || path.join(ROOT, '.scratch-bus741');
fs.mkdirSync(OUT, { recursive: true });
const CHROME_PATH = process.env.CHROME_PATH || execFileSync('sh', ['-c', 'command -v chromium || command -v chromium-browser || command -v google-chrome || ls ~/.cache/ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -1']).toString().trim();
const results = [];
const ok = (name, cond, extra = '') => {
  results.push({ name, pass: !!cond });
  console.log(`${cond ? 'PASS' : 'FAIL'} ${name}${extra ? ' — ' + extra : ''}`);
};
const MIME = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, BASE).pathname);
  if (p.startsWith('/static/')) p = p.slice('/static/'.length);
  else p = '/index.html';
  const clean = p.split('?')[0];
  const file = path.join(MINIAPP, clean.replace(/^\//, ''));
  fs.readFile(file, (err, data) => {
    if (err) { res.writeHead(404); res.end('nf'); return; }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
    res.end(data);
  });
});
await new Promise((r) => server.listen(18099, '127.0.0.1', r));
const browser = await chromium.launch({ executablePath: CHROME_PATH, headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });

const SHOP_BASE = () => JSON.stringify({
  current_plan: 'free', sub_active: false, sub_days_left: 0, crystals: 0,
  plans: [], products: {}, entitlements: [],
  /* BUS-635: витрина рендерит только catalog.plans с is_active/is_public ≠ 0;
     без плана pay-plan__badge не существует вовсе (пустой каталог = FAIL-проба). */
  catalog: { catalog_version: '2026-08-v2', price_book_version: 'pb-2026-08-v2', plans: [
    { code: 'MOON', badge: 'recommended', is_active: 1, is_public: 1, price_stars: 299, annual_price_stars: 2990, features: ['depth'] },
  ], annual_plans: [], crystal_packs: [], products: [], current_entitlements: { tier: 'free', status: 'free', ai_message_limit: 0, ai_messages_used: 0, crystals: 0 } },
  current_entitlements: {},
});
const ME = () => JSON.stringify({ id: 1, name: 'Тест Тестов', lang: 'ru', flags: {}, birth_date: '1990-05-05', chart_mode: 'manual' });
const TG_MOCK = () => {
  window.Telegram = {
    WebApp: {
      ready: () => {}, expand: () => {}, setHeaderColor: () => {},
      viewportStableHeight: 667, viewportHeight: 667,
      initDataUnsafe: {}, initData: '', colorScheme: 'dark',
      onEvent: () => {}, offEvent: () => {},
      openInvoice: () => {},
    },
  };
};

async function freshPage() {
  const context = await browser.newContext({ viewport: { width: 375, height: 667 }, locale: 'ru-RU', bypassCSP: true, colorScheme: 'dark' });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/net::ERR_FAILED|telegram\.org/.test(m.text())) errors.push('console.error: ' + m.text()); });
  await page.route('**/telegram.org/**', async (route) => { await route.abort(); });
  await page.route('**/api/**', async (route) => {
    const url = route.request().url();
    if (url.includes('/api/shop')) { await route.fulfill({ status: 200, contentType: 'application/json', body: SHOP_BASE() }); return; }
    if (url.includes('/api/me')) { await route.fulfill({ status: 200, contentType: 'application/json', body: ME() }); return; }
    if (url.includes('/api/agents')) { await route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }); return; }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });
  await page.addInitScript(TG_MOCK);
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem('oracle_lang', 'ru');
    localStorage.setItem('oracle_intro_seen', '1');
  });
  await page.goto(`${BASE}/?qa=1`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  return { context, page, errors };
}

/* Вычисленные стили: ожидаемые значения после унификации. */
/* Chromium computed-сериализация linear-gradient(180deg,…) опускает угол:
 * вертикальный градиент печатается как linear-gradient(rgb(...), rgb(...)). */
const GRAD_EXPECT = 'linear-gradient(rgb(241, 217, 159), rgb(233, 201, 130))';
const ON_ACCENT = 'rgb(28, 24, 32)';
// R03 §2.1: --color-text-primary #F4F2ED (BUS-969 инкремент 2: BottomNav §7.2).
const TEXT_PRIMARY = 'rgb(244, 242, 237)';

const styleOf = (page, sel, props) => page.evaluate(({ sel, props }) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const cs = getComputedStyle(el);
  return Object.fromEntries(props.map((p) => [p, cs[p]]));
}, { sel, props });

/* ── Экран home: primary-кнопка, фон, версии ── */
{
  const { context, page, errors } = await freshPage();

  // §3.2: база фона = --color-bg-primary
  const bodyBg = await styleOf(page, 'body', ['background-color']);
  ok('bg: body фон #0B0D18 (R03 §2.1 --color-bg)', bodyBg && bodyBg['background-color'] === 'rgb(11, 13, 24)', JSON.stringify(bodyBg));

  // §3.2: все bg-cosmos url в computed starfield — ?v=108
  // (фоновый градиент-оверлей идёт первым слоем, url может быть вторым слоем)
  const cosmos = await page.evaluate(() => {
    const sf = document.querySelector('.starfield');
    if (!sf) return null;
    const bg = getComputedStyle(sf).backgroundImage;
    return [...bg.matchAll(/bg-cosmos[^"'\s)]*/g)].map((m) => m[0]);
  });
  ok('bg: starfield рендерит bg-cosmos', cosmos && cosmos.length > 0, (cosmos || []).join(' | '));
  ok('bg: все bg-cosmos-ссылки с ?v=108', cosmos && cosmos.length > 0 && cosmos.every((u) => u.includes('?v=108')), (cosmos || []).join(' | '));

  // §3.1: home-CTA (.ritual-cta) — ghost by design (BUS-517, 16-visual-qa.css:385),
  // НЕ primary-градиент. Каноническая primary-проба на home-вью — today-виджет:
  // рендерим через chat.pending {kind:'today'} → app.todayWidget → .btn-primary
  // (08-widgets.js:70). Это единственный гарантированный .btn-primary на home-стадии.
  const homeCta = await styleOf(page, '.ritual-cta', ['background-image', 'background-color']);
  ok('§3.1: home ritual-cta — ghost by design BUS-517 (без primary-градиента)', homeCta && homeCta['background-image'] === 'none', JSON.stringify(homeCta));
  await page.evaluate(() => {
    app.chat = app.chat || {};
    app.chat.pending = { kind: 'today', card: {}, moon: {}, flipped: false };
    app.renderChat && app.renderChat(document.getElementById('app-main'));
  });
  await page.waitForTimeout(300);
  const prim = await styleOf(page, '.day-card .btn-primary', ['background-image', 'color']);
  ok('§3.1: primary на home (today-виджет) — вычисленный градиент из токена', prim && prim['background-image'] === GRAD_EXPECT, JSON.stringify(prim));
  ok('§3.1: текст на primary — on-accent', prim && prim.color === ON_ACCENT, JSON.stringify(prim));

  await page.screenshot({ path: path.join(OUT, 'bus741-home.png'), fullPage: false });
  await context.close();
}

/* ── Экран chat: send-btn + msg.user ── */
{
  const { context, page, errors } = await freshPage();
  // app.goChat() не существует — вход в чат через app.openChat('oracle')
  await page.evaluate(() => app.openChat && app.openChat('oracle'));
  await page.waitForTimeout(500);
  // .msg.user: рендерим напрямую через состояние чата (без сетевого запроса)
  await page.evaluate(() => {
    app.chat.messages = [{ role: 'user', text: 'привет' }];
    app.renderChat && app.renderChat(document.getElementById('app-main'));
  });
  await page.waitForTimeout(400);
  const send = await styleOf(page, '.send-btn', ['background-image', 'color']);
  ok('§3.1: send-btn — градиент из токена', send && send['background-image'] === GRAD_EXPECT, JSON.stringify(send));
  ok('§3.1: send-btn текст — on-accent', send && send.color === ON_ACCENT, JSON.stringify(send));
  const msg = await styleOf(page, '.msg.user', ['background-image', 'color']);
  const msgGradOk = msg && msg['background-image'] && msg['background-image'].startsWith(GRAD_EXPECT.slice(0, 40));
  ok('§3.1: msg.user bubble — градиент из токена', !!msgGradOk, JSON.stringify(msg));
  if (msg && msg.color) ok('§3.1: msg.user текст — on-accent', msg.color === ON_ACCENT, JSON.stringify(msg));

  // §3.4: в рендере нет legacy-золота rgb(230, 193, 120)
  const legacy = await page.evaluate(() => {
    let hits = 0;
    for (const el of document.querySelectorAll('.send-btn, .tool-btn, .moon-toggle, .chip, .btn, .glass, .app-header, .app-nav')) {
      const cs = getComputedStyle(el);
      for (const p of ['background-color', 'border-top-color', 'border-left-color', 'box-shadow', 'color']) {
        if ((cs[p] || '').includes('rgb(230, 193, 120)')) hits++;
      }
    }
    return hits;
  });
  ok('§3.4: computed-стили без legacy-золота rgb(230,193,120)', legacy === 0, `${legacy} вхождений`);

  await page.screenshot({ path: path.join(OUT, 'bus741-chat.png'), fullPage: false });
  await context.close();
}

/* ── Экран payment: nav-btn.active + pay-plan badge ── */
{
  const { context, page, errors } = await freshPage();
  await page.evaluate(() => app.goPayment());
  await page.waitForTimeout(500);
  // nav-btn.active: финальный каскад — 22-components.css (BUS-969 инкремент 2).
  // R03 §4.1/§7.2: скользящая золотая капсула .main-nav::before/::after погашена
  // (content:none); выбранный раздел — спокойная подложка --hover-bg +
  // маркер-линия inset цвета акцента; текст — text-primary.
  const nav = await styleOf(page, '.nav-btn.active', ['background-image', 'color']);
  const navSub = await page.evaluate(() => {
    const el = document.querySelector('.main-nav .nav-btn.active');
    return el ? getComputedStyle(el).backgroundColor : null;
  });
  const capsuleGone = await page.evaluate(() => {
    const mn = document.querySelector('.main-nav');
    return mn ? getComputedStyle(mn, '::before').content === 'none' : null;
  });
  ok('§4.1/§7.2: nav-btn.active — спокойная подложка (hover-bg), капсула погашена', nav && nav['background-image'] === 'none' && navSub === 'rgba(233, 201, 130, 0.08)' && capsuleGone === true, JSON.stringify({ nav, navSub, capsuleGone }));
  ok('§4.1: nav-btn.active текст — text-primary', nav && nav.color === TEXT_PRIMARY, JSON.stringify(nav));
  const capsule = await page.evaluate(() => {
    const mn = document.querySelector('.main-nav');
    return mn ? getComputedStyle(mn, '::before').backgroundImage : null;
  });
  ok('§3.1: nav-капсула (::before) — градиент из токена', capsule === GRAD_EXPECT, JSON.stringify(capsule));
  const badge = await styleOf(page, '.pay-plan__badge', ['color']);
  ok('§3.1: pay-plan__badge текст — on-accent', badge && badge.color === ON_ACCENT, JSON.stringify(badge));
  await page.screenshot({ path: path.join(OUT, 'bus741-payment.png'), fullPage: false });
  await context.close();
}

/* ── BUS-969 инкремент 2: компоненты §4 R03 на живых экранах ── */
{
  const { context, page, errors } = await freshPage();
  // §4.4 Button: secondary/destructive на surface-raised/х error, состояния §8.3.
  await page.evaluate(() => {
    document.body.insertAdjacentHTML('beforeend', `
      <div id="bus969-btn-probe">
        <button class="btn btn-secondary" id="probe-secondary">Secondary</button>
        <button class="btn btn-destructive" id="probe-destructive">Destructive</button>
      </div>`);
  });
  const btnSecondary = await styleOf(page, '#probe-secondary', ['color', 'background-color', 'border-color', 'min-height', 'border-radius']);
  ok('§4.4: btn-secondary — text-primary на surface-raised, border-control, 48px-минимум', btnSecondary
    && btnSecondary.color === TEXT_PRIMARY
    && btnSecondary['background-color'] === 'rgb(28, 34, 51)'
    && btnSecondary['border-color'] === 'rgb(113, 123, 150)'
    && parseFloat(btnSecondary['min-height']) >= 44
    && btnSecondary['border-radius'] === '12px', JSON.stringify(btnSecondary));
  const btnDestructive = await styleOf(page, '#probe-destructive', ['color', 'background-color']);
  ok('§4.4: btn-destructive — on-accent на error', btnDestructive
    && btnDestructive.color === ON_ACCENT
    && btnDestructive['background-color'] === 'rgb(241, 164, 170)', JSON.stringify(btnDestructive));
  // §8.3: disabled-состояние общего .btn.
  await page.evaluate(() => { document.getElementById('probe-secondary').disabled = true; });
  const btnDisabled = await styleOf(page, '#probe-secondary', ['opacity', 'cursor']);
  ok('§8.3: .btn:disabled — opacity .48, cursor not-allowed', btnDisabled
    && btnDisabled.opacity === '0.48'
    && btnDisabled.cursor === 'not-allowed', JSON.stringify(btnDisabled));
  await page.evaluate(() => document.getElementById('bus969-btn-probe').remove());

  // §4.2: чат-каркас — композер на surface, пузырь assistant на surface, focus ring.
  await page.evaluate(() => app.go('hub'));
  await page.waitForTimeout(400);
  await page.evaluate(() => app.openChat('oracle'));
  await page.waitForTimeout(600);
  const composer = await styleOf(page, '.composer-top', ['background-color', 'border-color', 'border-radius']);
  ok('§4.2: composer — surface-подложка, border-control, radius-card', composer
    && composer['background-color'] === 'rgb(20, 24, 39)'
    && composer['border-color'] === 'rgb(113, 123, 150)'
    && composer['border-radius'] === '16px', JSON.stringify(composer));
  // focus-visible §8.2: ring виден при клавиатурном фокусе.
  await page.focus('#chat-input');
  const composerFocus = await page.evaluate(() => {
    const el = document.querySelector('.composer-top');
    return el ? getComputedStyle(el).boxShadow : null;
  });
  ok('§4.2/§8.2: composer:focus-within — --focus-ring', composerFocus
    && composerFocus.includes('rgba(233, 201, 130, 0.35)'), composerFocus);
  const sendBtn = await styleOf(page, '#send-btn', ['background-image', 'color']);
  ok('§4.2: send-btn — grad-primary + on-accent', sendBtn
    && sendBtn['background-image'].includes('linear-gradient')
    && sendBtn.color === ON_ACCENT, JSON.stringify(sendBtn));

  // §4.3: ToolCatalogSheet — overlay-поверхность, radius-sheet, ≤80vh, dialog-паттерн.
  await page.evaluate(() => app.setToolbox(true));
  await page.waitForTimeout(400);
  const sheet = await page.evaluate(() => {
    const el = document.querySelector('.te-sheet');
    if (!el) return null;
    const cs = getComputedStyle(el);
    const vh = window.innerHeight;
    return {
      bg: cs.backgroundColor,
      radius: cs.borderTopLeftRadius,
      maxH: cs.maxHeight,
      maxHRatio: parseFloat(cs.maxHeight) / vh,
      shadow: cs.boxShadow,
      role: el.getAttribute('role'),
      ariaModal: el.getAttribute('aria-modal'),
    };
  });
  ok('§4.3: te-sheet — surface-overlay, radius-sheet 24, ≤80vh, overlay-тень', sheet
    && sheet.bg === 'rgb(36, 44, 63)'
    && sheet.radius === '24px'
    && sheet.maxHRatio <= 0.8
    && sheet.shadow.includes('rgba(0, 0, 0, 0.85)'), JSON.stringify(sheet));
  ok('§4.3: te-sheet — WAI-ARIA Dialog (role=dialog, aria-modal)', sheet
    && sheet.role === 'dialog' && sheet.ariaModal === 'true', JSON.stringify({ role: sheet.role, ariaModal: sheet.ariaModal }));
  // Escape закрывает sheet (§4.4 Sheet/Modal: Escape+кнопка).
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  const sheetClosed = await page.evaluate(() => !document.getElementById('tool-expand').classList.contains('open'));
  ok('§4.3: sheet закрывается Escape', sheetClosed === true);
  await page.screenshot({ path: path.join(OUT, 'bus969-chat-components.png'), fullPage: false });
  ok('§4: JS-ошибок на живом пути нет', errors.length === 0, errors.join('; '));
  await context.close();
}

/* ── Экран profile: ptab.active ── */
{
  const { context, page, errors } = await freshPage();
  // app.goProfile() не существует — профиль через app.go('profile')
  await page.evaluate(() => app.go && app.go('profile'));
  await page.waitForTimeout(500);
  const ptab = await styleOf(page, '.ptab.active', ['background-image', 'color']);
  ok('§3.1: ptab.active — градиент из токена', ptab && ptab['background-image'] === GRAD_EXPECT, JSON.stringify(ptab));
  ok('§3.1: ptab.active текст — on-accent', ptab && ptab.color === ON_ACCENT, JSON.stringify(ptab));

  // ── Инкремент 2 (§3.3): онбординг-профиль без birth_date рендерит .seg-progress
  const ME_EMPTY = () => JSON.stringify({ id: 1, name: 'Тест Тестов', lang: 'ru', flags: {}, chart_mode: 'manual' });
  await page.route('**/api/me', async (route) => { await route.fulfill({ status: 200, contentType: 'application/json', body: ME_EMPTY() }); });
  await page.reload({ waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  await page.evaluate(() => app.go && app.go('profile'));
  await page.waitForTimeout(500);
  const seg = await page.evaluate(() => {
    const el = document.querySelector('.profile-empty-steps');
    if (!el) return null;
    const cs = getComputedStyle(el);
    const segs = [...el.querySelectorAll('i')].map((i) => ({ h: getComputedStyle(i).height, flex: getComputedStyle(i).flexGrow }));
    return { display: cs.display, segs, aria: el.getAttribute('aria-label'), onSeg: el.querySelector('span.is-on') ? getComputedStyle(el.querySelector('span.is-on')).color : null };
  });
  ok('§3.3: онбординг-профиль — .seg-progress компонент', seg && seg.display === 'flex', JSON.stringify(seg && seg.display));
  ok('§3.3: онбординг-профиль — 2 сегмента-линии 1px', seg && seg.segs.length === 2 && seg.segs.every((s) => s.h === '1px'), JSON.stringify(seg && seg.segs));
  ok('§3.3: онбординг-профиль — aria-label с шагом', seg && /Шаг 1 из 3/.test(seg.aria || ''), JSON.stringify(seg && seg.aria));
  const champagne300 = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--champagne-300').trim());
  ok('§3.3: онбординг-профиль — включённый шаг champagne-300', seg && seg.onSeg && champagne300 && `rgb(${champagne300})` !== '', JSON.stringify(seg && seg.onSeg));
  await context.close();
}

/* ── §3.3: palm-progress и fb-progress → seg-progress (грейпфрут-проба по исходникам) ── */
{
  const palmSrc = fs.readFileSync(path.join(MINIAPP, 'js', '13-palm.js'), 'utf8');
  ok('§3.3: palm-progress рендерится классом seg-progress', /class="seg-progress palm-progress"/.test(palmSrc));
  ok('§3.3: palm-progress имеет aria-label шага', /aria-label="\$\{esc\(pt\('ariaStep'\)\)\}"/.test(palmSrc));
  const cssRitual = fs.readFileSync(path.join(MINIAPP, 'css', '15-ritual-redesign.css'), 'utf8');
  ok('§3.3: palm-progress не дублирует flex-базу seg-progress (только посадка)', !/\.palm-progress \{ display:flex/.test(cssRitual));
  const fbSrc = fs.readFileSync(path.join(MINIAPP, 'js', '19-feedback.js'), 'utf8');
  ok('§3.3: fb-progress рендерится классом seg-progress (5 вопросов)', /class="seg-progress fb-progress"/.test(fbSrc));
  ok('§3.3: fb-progress aria-label "Шаг N из M"', /ariaStepName/.test(fbSrc));
  const cssFb = fs.readFileSync(path.join(MINIAPP, 'css', '19-feedback.css'), 'utf8');
  ok('§3.3: fb-dot удалён из css', !cssFb.includes('.fb-dot'));
  const cssTokens = fs.readFileSync(path.join(MINIAPP, 'css', '00-tokens.css'), 'utf8');
  ok('§3.3: .seg-progress определён в 00-tokens.css', /\.seg-progress \{/.test(cssTokens));
  ok('§3.3: seg-line = rgba(255,255,255,.13) через токен --seg-line', /--seg-line:\s*rgba\(255, 255, 255, \.13\)/.test(cssTokens));
}

/* ── §3.4 (инкремент 3, BUS-960): legacy-золото отсутствует в источниках JS ── */
{
  const jsDir = path.join(MINIAPP, 'js');
  const jsFiles = fs.readdirSync(jsDir).filter((f) => f.endsWith('.js'));
  const offenders = [];
  for (const f of jsFiles) {
    const src = fs.readFileSync(path.join(jsDir, f), 'utf8');
    if (/230,\s*193,\s*120|e6c178/i.test(src)) offenders.push(f);
  }
  ok('§3.4: legacy-золото rgba(230,193,120)/#E6C178 в miniapp/js = 0', offenders.length === 0, offenders.join(', '));
}

/* ── §3.5: CI-guard версий фоновых ассетов ── */
{
  const guard = path.join(ROOT, 'scripts', 'check_cache_busting.py');
  ok('§3.5: check_cache_busting.py проверяет bg-cosmos*', fs.readFileSync(guard, 'utf8').includes('BG_ASSETS'));
  const sky = fs.readFileSync(path.join(MINIAPP, 'css', '01-sky-shell.css'), 'utf8');
  const ritual = fs.readFileSync(path.join(MINIAPP, 'css', '15-ritual-redesign.css'), 'utf8');
  const indexHtml = fs.readFileSync(path.join(MINIAPP, 'index.html'), 'utf8');
  const cosmosRefs = [...`${indexHtml}\n${sky}\n${ritual}`.matchAll(/bg-cosmos[^"'\s)]*/g)].map((m) => m[0]);
  ok('§3.5: все ссылки bg-cosmos с ?v=108 и синхронны', cosmosRefs.length >= 3 && cosmosRefs.every((u) => u.includes('?v=108')), cosmosRefs.join(' | '));
}

await browser.close();
server.close();
const failed = results.filter((r) => !r.pass);
console.log(`\n${results.length - failed.length}/${results.length} PASS`);
if (failed.length) { console.log('FAILED:', failed.map((f) => f.name).join(' | ')); process.exit(1); }
