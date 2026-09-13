/** Isolated visual/interaction fixture. Never connects to a real API or database.
 * Run: node scripts/redesign_preview.mjs
 * New account: /?scenario=new; saved account: /; errors: ?scenario=save-error.
 */
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const MINIAPP = path.join(ROOT, 'miniapp');
export const agents = [
  { code: 'oracle', name: 'Лилит', title: 'Личный Оракул', accent: '#e8c56b' },
  { code: 'astro', name: 'Урания', title: 'Астролог', accent: '#8cc8ff' },
  { code: 'tarot', name: 'Мадам Ленорман', title: 'Таролог', accent: '#e7a8d8' },
  { code: 'chiromant', name: 'Мира', title: 'Проводник ладони', accent: '#6fd6b0' },
].map(a => ({ ...a, avatar: `/static/img/agents/${a.code}.jpg`, greeting: 'С чего начнём? Расскажи, что сейчас важно для тебя.', capabilities: [] }));
const cities = [
  { key: 'кишинев', label: 'Кишинёв', country: 'Молдова', timezone: 'Europe/Chisinau' },
  { key: 'казань', label: 'Казань', country: 'Россия', timezone: 'Europe/Moscow' },
  { key: 'москва', label: 'Москва', country: 'Россия', timezone: 'Europe/Moscow' },
].map(c => ({ ...c, detail: `${c.country} · ${c.timezone}` }));
const initialMe = () => ({ tg_id: 710001, name: 'Анна', username: 'preview', oracle_name: 'Лилит',
  persona: 'gentle', lang: 'ru', gender: 'f', tz: 'Europe/Chisinau', birth_date: '1990-06-21',
  birth_time: '14:30', birth_time_precision: 'exact', birth_time_known: true, birth_city: 'Кишинёв',
  onboarded: true, onboarding_step: null, natal_technique: 'astrology', chart_mode: 'full',
  chart_precision: 'exact', sun: 'Близнецы', crystals: 0, sub_active: false, plan: 'free',
  questions_left: 0, questions_total: 0, allowance: { plan: 'free', left: 0, limit: 0 },
  memories: [], memory_enabled: true, morning_push: false, flags: {}, reports: [], entitlements: [],
  agents, feedback_pending: false,
});
const init = `<script>
window.Telegram={WebApp:{ready(){},expand(){},setHeaderColor(){},initDataUnsafe:{user:{id:710001,first_name:'Анна',language_code:'ru'}},themeParams:{},colorScheme:'dark',BackButton:{show(){},hide(){},onClick(){},offClick(){}},HapticFeedback:{impactOccurred(){},notificationOccurred(){},selectionChanged(){}},onEvent(){},offEvent(){}}};
localStorage.setItem('oracle_lang','ru');localStorage.setItem('oracle_intro_seen','1');localStorage.setItem('oracle_chat_guide_v2','1');
document.title='OracleAI · локальный стенд, тестовые данные';
</script>`;

export function createPreviewServer() {
  const states = new Map();
  const calls = [];
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    let id = (req.headers.cookie || '').match(/oracle_preview=([\w-]+)/)?.[1];
    if (!id || !states.has(id)) {
      id = randomUUID();
      const scenario = url.searchParams.get('scenario') || 'saved';
      states.set(id, { me: { ...initialMe(), onboarded: !['new', 'save-error'].includes(scenario) }, scenario, submissions: [] });
      res.setHeader('Set-Cookie', `oracle_preview=${id}; HttpOnly; SameSite=Strict; Path=/`);
    }
    const state = states.get(id);
    const json = (body, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(body)); };
    try {
      if (url.pathname.startsWith('/api/')) {
        let body = '';
        for await (const chunk of req) { body += chunk; if (body.length > 100000) { json({ detail: 'too_large' }, 413); return; } }
        const item = body ? JSON.parse(body) : {};
        calls.push({ id, method: req.method, path: url.pathname, query: url.search, body: item });
        const p = url.pathname;
        if (p === '/api/me') return json(state.me);
        if (p === '/api/agents') return json(agents);
        if (p === '/api/auth/session') return json({ session_token: 'isolated-preview' });
        if (p === '/api/profile') {
          state.submissions.push(item);
          if (state.scenario === 'save-error' && state.submissions.length === 1) return json({ detail: 'Тестовая ошибка сохранения. Повтори попытку.' }, 503);
          if (item.onboarding_complete) {
            if (!item.name || !item.birth_date || !item.birth_time_precision || !cities.some(c => c.key === item.city)) return json({ detail: 'Invalid onboarding fixture payload' }, 400);
            state.me = { ...state.me, name: item.name, birth_date: item.birth_date, birth_time: item.birth_time, birth_time_precision: item.birth_time_precision, birth_city: cities.find(c => c.key === item.city).label, onboarded: true };
          }
          return json({ ok: true, onboarded: state.me.onboarded, updated: Object.keys(item) });
        }
        if (p === '/api/city/suggest') {
          const q = (url.searchParams.get('q') || '').toLowerCase();
          return json({ items: q.length < 2 ? [] : cities.filter(c => c.key.includes(q)) });
        }
        if (p === '/api/today') return json({ forecast: 'Сегодня оставь место для одного важного дела. Выбери спокойный темп и начни с небольшого шага, который давно откладываешь.', moon: { name: 'Растущая Луна', day: 9, emoji: '🌓' } });
        if (p === '/api/moon/week') return json([]);
        if (p === '/api/diary') return json({ entries: [], streak: 0 });
        if (p === '/api/diary/prompt') return json({ text: 'Что сегодня принесло тебе спокойствие?', written_today: false });
        if (p === '/api/practices') return json({ items: [] });
        if (p === '/api/history') return json({ items: [{ kind: 'chat', entry_id: 901, source_id: 901, source_kind: 'oracle', title: 'Новый этап в работе', created_at: '2026-09-12T09:00:00Z', preview: 'Как выбрать следующий шаг?', action: { type: 'chat', agent: 'oracle', id: 901 } }], limit: 100, owner_scoped: true });
        if (p === '/api/memories' || p === '/api/reports' || p === '/api/tarot/history' || p === '/api/shop/payment-history') return json([]);
        if (p === '/api/notifications/preferences') return json({ morning_forecast: false });
        if (p === '/api/notifications') return json({ items: [], unread: 0 });
        if (p === '/api/shop') return json({ plans: [], products: [], providers: {}, current_plan: 'free', catalog: { plans: [], products: [] } });
        if (p === '/api/chart') return json({ detail: 'На стенде карта не построена.' }, 400);
        if (/^\/api\/chat\/[^/]+\/sessions$/.test(p)) return json([]);
        if (/^\/api\/chat\/[^/]+(?:\/sessions\/\d+)?$/.test(p) && req.method === 'GET') {
          const code = p.split('/')[3];
          return json({ agent: agents.find(a => a.code === code), thread_id: null, messages: [] });
        }
        if (p === '/api/public/config') return json({ bot_username: '', webapp_url: '' });
        if (req.method === 'POST' && /analytics|events|experiment/.test(p)) return json({ ok: true });
        return json({ detail: `Endpoint unavailable in isolated preview: ${p}` }, 501);
      }
      const relative = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname).replace(/^\/static\//, '').replace(/^\//, '');
      const file = path.resolve(MINIAPP, relative);
      if (!file.startsWith(MINIAPP + path.sep)) { res.writeHead(403); res.end(); return; }
      let content = await fs.readFile(file);
      const extension = path.extname(file);
      if (extension === '.html') content = content.toString().replace('<script src="https://telegram.org/js/telegram-web-app.js"></script>', init);
      const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
      res.writeHead(200, { 'Content-Type': mime[extension] || 'application/octet-stream', 'Cache-Control': 'no-store' });
      res.end(content);
    } catch (error) { json({ detail: error.code === 'ENOENT' ? 'Not found' : 'Preview error' }, error.code === 'ENOENT' ? 404 : 500); }
  });
  return { server, states, calls };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { server } = createPreviewServer();
  server.listen(Number(process.env.ORACLE_PREVIEW_PORT || 18555), '127.0.0.1', () => console.log(`Isolated preview (test data only): http://127.0.0.1:${server.address().port}`));
}
