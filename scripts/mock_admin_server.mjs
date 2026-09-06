#!/usr/bin/env node
// BUS-178: изолированный UI-стенд — реальный фронт админки + mock API
// с шейпами, снятыми с app/api/routers/admin.py и app/repo/*. Никаких
// реальных данных; проверяем верстку/поведение, не auth.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ADMIN = path.join(ROOT, 'admin');
const PORT = 8791;

const overview = {
  users_total: 451, users_today: 22, users_7d: 247, users_30d: 451,
  onboarded: 389, subs_active: 164, dau: 130, wau: 318, mau: 451,
  questions_today: 82, questions_7d: 512, readings_total: 736, readings_7d: 126,
  diary_7d: 74, stars_total: 17056, stars_30d: 14230, payers: 182,
  crystals_outstanding: 8420,
};
const sources = [
  { source: 'tg', users: 251, payers: 98, stars: 8200 },
  { source: 'instagram', users: 121, payers: 51, stars: 4100 },
  { source: 'organic', users: 79, payers: 33, stars: 1930 },
];
const retention = [
  { cohort: '2026-08-10', size: 214, d1: 64.0, d3: 48.0, d7: 31.0, d14: 21.0, d30: 12.0 },
  { cohort: '2026-08-17', size: 167, d1: 58.0, d3: 44.0, d7: 27.0, d14: 18.0, d30: 0.0 },
  { cohort: '2026-08-24', size: 70, d1: 61.0, d3: 46.0, d7: 29.0, d14: 0.0, d30: 0.0 },
];
const funnel = [
  ['Пришли', 451], ['Прошли знакомство', 389], ['Задали вопрос', 273],
  ['Вернулись на 2-й день', 196], ['Заплатили', 182],
].map(([step, value]) => ({ step, value, of_total: +(value * 100 / 451).toFixed(1) }));
const activation = {
  days: 30, cohort: 451,
  steps: [
    { step: 'Первая практика', event: 'first_ritual', value: 231, of_cohort: 51.3 },
    { step: 'Первый вопрос', event: 'first_question', value: 168, of_cohort: 37.3 },
    { step: 'Возврат D1', event: 'd1_return', value: 96, of_cohort: 21.3 },
    { step: 'Возврат D7', event: 'd7_return', value: 41, of_cohort: 9.1 },
  ],
};
const monetization_v2 = {
  window_days: 30,
  revenue: {
    paid_orders: 182, refunded_orders: 6, refund_rate_pct: 3.3, gross_stars: 14230,
    by_sku: [
      { sku: 'sub_vip', orders: 96, stars: 9600 },
      { sku: 'sub_plus', orders: 71, stars: 3550 },
      { sku: 'crystal_500', orders: 15, stars: 1080 },
    ],
  },
  subscription: {
    active_by_tier: { vip: 96, plus: 61, light: 7 },
    new_paid_users: 38, repeat_payers: 130,
  },
  crystals: {
    outstanding: 8420, purchased_outstanding: 5100, bonus_outstanding: 3320,
    repeat_purchase_users: 22,
    by_source: [
      { source: 'purchased', granted: 6800, spent: 1700 },
      { source: 'subscription_bonus', granted: 5200, spent: 1880 },
      { source: 'promo', granted: 900, spent: 200 },
    ],
  },
  funnel: {
    paywall_view: 1204, paywall_choice: 731, invoice_created: 655, paid: 182,
    first_paid_action: 214, subscription_lifecycle: 96, credit_pack_checkout_started: 88,
    credit_pack_paid: 15, credit_spent: 140, report_delivered: 63, refund_completed: 6,
  },
  cogs: {
    total_variable_cost_usd: 42.87,
    by_kind: [
      { event_kind: 'llm', events: 5120, cost_usd: 38.4 },
      { event_kind: 'pdf', events: 63, cost_usd: 2.1 },
      { event_kind: 'voice', events: 140, cost_usd: 2.37 },
    ],
  },
  contribution_margin_estimate: null,
};
const users = Array.from({ length: 50 }, (_, i) => ({
  tg_id: 700000000 + i,
  name: ['Анна', 'Мария', 'Вера', 'Ольга', 'Лида'][i % 5] + ' ' + ['П.', 'К.', 'С.', 'М.'][i % 4],
  username: i % 3 ? `user_${i}` : null,
  sub_level: i % 2 ? 'vip' : 'plus',
  sub_active: i % 4 !== 0,
  crystals: 120 + i * 7,
  ltv_stars: i % 5 ? 300 + i * 40 : 0,
  last_seen: new Date(Date.now() - i * 3600e3 * 5).toISOString(),
  created_at: new Date(Date.now() - i * 86400e3).toISOString(),
  tags: i % 6 === 0 ? ['vip'] : [],
}));

function json(res, code, body) {
  res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8' });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const p = url.pathname;

  // статика админки — redirect на trailing slash: относительные @import
  // в admin.css резолвятся от базового URL документа
  if (p === '/admin') {
    res.writeHead(301, { Location: '/admin/' });
    return res.end();
  }
  if (p === '/admin/') {
    const html = (await fs.readFile(path.join(ADMIN, 'index.html'), 'utf8'))
      .replaceAll('__ADMIN_ASSET_VERSION__', 'mock');
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    return res.end(html);
  }
  if (p.startsWith('/admin/static/')) {
    const rel = p.replace('/admin/static/', '').split('?')[0];
    try {
      const file = await fs.readFile(path.join(ADMIN, rel));
      const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' };
      res.writeHead(200, { 'Content-Type': types[path.extname(rel)] || 'application/octet-stream' });
      return res.end(file);
    } catch {
      res.writeHead(404); return res.end();
    }
  }
  // axe-core перезапрашивает @import-стили относительно документа, а не CSS —
  // отдаём те же файлы, чтобы color-contrast реально считался, а не уходил в incomplete
  if (p.startsWith('/admin/styles/')) {
    const rel = p.replace('/admin/', '').split('?')[0];
    try {
      const file = await fs.readFile(path.join(ADMIN, rel));
      res.writeHead(200, { 'Content-Type': 'text/css' });
      return res.end(file);
    } catch {
      res.writeHead(404); return res.end();
    }
  }
  if (p === '/favicon.ico') {
    res.writeHead(204); return res.end();
  }
  if (p === '/api/admin/me') {
    return json(res, 200, { tg_id: 100000001, role: 'owner', name: 'Владелец', permissions: ['*'] });
  }
  if (p === '/api/admin/health') {
    return json(res, 200, { ok: true, users: 451, telegram_webapp_ready: true });
  }
  if (p === '/api/admin/payment-health') {
    return json(res, 200, { status: 'ok', checked_at: new Date().toISOString(), stale_pending_threshold_hours: 2, checks: { pending_orders_stale: 0, failed_orders_24h: 0, webhook_failures_24h: {}, reconciliation: {}, webhook_timeline: [] }, providers: {} });
  }
  if (p === '/api/admin/dashboard') {
    return json(res, 200, {
      overview, funnel, activation, retention,
      monetization_v2, timeseries: [], sources, top_products: [],
      top_referrers: [], promo_batches: [], monetization: {}, revenue: {},
    });
  }
  if (p === '/api/admin/dashboard/demo') {
    return json(res, 200, { overview, funnel, activation, retention, sources, monetization_v2 });
  }
  if (p === '/api/admin/users') {
    const q = (url.searchParams.get('q') || '').toLowerCase();
    const segment = url.searchParams.get('segment') || 'all';
    let items = users;
    if (segment === 'paying') items = items.filter((u) => u.ltv_stars > 0);
    if (segment === 'never_paid') items = items.filter((u) => !u.ltv_stars);
    if (segment === 'active_sub') items = items.filter((u) => u.sub_active);
    if (segment === 'expired') items = items.filter((u) => !u.sub_active);
    if (segment === 'onboarded') items = items.filter((_, i) => i % 7 !== 0);
    if (segment === 'not_onboarded') items = items.filter((_, i) => i % 7 === 0);
    if (segment === 'active_7d') items = items.filter((_, i) => i < 30);
    if (q) items = items.filter((u) => (u.name || '').toLowerCase().includes(q) || (u.username || '').includes(q));
    const offset = +url.searchParams.get('offset') || 0;
    const limit = +url.searchParams.get('limit') || 50;
    return json(res, 200, {
      items: items.slice(offset, offset + limit),
      total: items.length,
      segments: ['active_7d', 'active_sub', 'all', 'expired', 'expiring_3d', 'never_paid', 'not_onboarded', 'onboarded', 'paying', 'push_on', 'sleeping_14d'],
    });
  }
  if (/^\/api\/admin\/users\/\d+$/.test(p)) {
    const tgId = +p.split('/').pop();
    const u = users.find((x) => x.tg_id === tgId) || users[0];
    return json(res, 200, {
      user: { tg_id: u.tg_id, name: u.name, username: u.username, created_at: u.created_at, source: 'telegram', sub_level: u.sub_level, sub_until: new Date(Date.now() + 86400e3 * 12).toISOString(), crystals: u.crystals, ltv_stars: u.ltv_stars, birth_date: null, birth_city: null, tz: 'UTC', oracle_name: 'Луна', persona: 'soft', status: 'active' },
      sub_active: u.sub_active, sub_days_left: 12, questions_today: 3, diary_streak: 5,
      chart: { sun: { sign: 'Лев', element: 'Огонь', symbol: '♌' }, mode: 'modern' },
      plan: { title: 'VIP' }, entitlements: [], tags: u.tags, notes: [], memories: [],
      events: [
        { name: 'miniapp_open', surface: 'miniapp', created_at: new Date().toISOString() },
        { name: 'paywall_view', surface: 'miniapp', props_json: '{"surface":"miniapp"}', created_at: new Date().toISOString() },
      ],
      threads: [], readings: [], reports: [], orders: [{ title: 'VIP на месяц', amount_stars: 100, amount_crystals: 0, status: 'paid', paid_at: new Date().toISOString() }], crystals_history: [],
      referrals: { level1: 2 }, referral: {},
    });
  }
  res.writeHead(404); res.end();
});

server.listen(PORT, '127.0.0.1', () => console.log(`mock admin on http://127.0.0.1:${PORT}/admin`));
