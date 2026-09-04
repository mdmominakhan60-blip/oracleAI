import { $, get, state, fail, actions, setViewVisibility } from './core/runtime.js';
import { adminShellTemplate } from './layout/template.js';
import { DashboardFeature } from './features/dashboard.js';
import { UsersFeature } from './features/users.js';
import { CommerceFeature } from './features/commerce.js';
import { EngagementFeature } from './features/engagement.js';
import { ContentFeature } from './features/content.js';
import { SettingsFeature } from './features/settings.js';
import { ObservabilityFeature } from './features/observability.js';
import { LogsFeature } from './features/logs.js';

export class AdminApplication {
  constructor() {
    this.features = null;
    this.loaders = {};
  }

  init() {
    this.mountLayout();
    this.features = {
      dashboard: new DashboardFeature(),
      users: new UsersFeature(),
      commerce: new CommerceFeature(),
      engagement: new EngagementFeature(),
      content: new ContentFeature(),
      settings: new SettingsFeature(),
      observability: new ObservabilityFeature(),
      logs: new LogsFeature(),
    };
    this.features.logs.init();
    this.loaders = {
      dashboard: () => this.features.dashboard.load(),
      users: () => this.features.users.load(),
      orders: () => this.features.commerce.loadOrders(),
      catalog: () => this.features.commerce.loadCatalog(),
      promo: () => this.features.engagement.loadPromo(),
      broadcasts: () => this.features.engagement.loadBroadcasts(),
      content: () => this.features.content.load(),
      horoscopes: () => this.features.observability.loadHoroscopes(),
      costs: () => this.features.observability.loadCosts(),
      safety: () => this.features.observability.loadSafety(),
      settings: () => this.features.settings.load(),
      audit: () => this.features.observability.loadAudit(),
      reconciliation: () => this.features.commerce.loadReconciliation(),
      logs: () => this.features.logs.refresh(),
    };
    this.bindShellEvents();
    return this.bootstrap();
  }

  mountLayout() {
    const root = $('admin-root');
    if (!root) throw new Error('Admin layout root is missing');
    root.insertAdjacentHTML('beforebegin', adminShellTemplate);
    root.remove();
  }

  bindShellEvents() {
    document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => this.navigate(button.dataset.view)));
    $('refresh').addEventListener('click', () => this.load(state.view));
    $('period').addEventListener('change', (event) => { state.period = +event.target.value; if (state.view === 'dashboard') this.load('dashboard'); });
    $('demo-toggle').addEventListener('click', () => {
      if (state.role !== 'owner') return;
      state.demo = !state.demo;
      $('demo-toggle').textContent = state.demo ? 'ДЕМО: вкл.' : 'ДЕМО: выкл.';
      $('demo-toggle').setAttribute('aria-pressed', state.demo ? 'true' : 'false');
      $('demo-toggle').classList.toggle('active', state.demo);
      this.load('dashboard');
    });
  }

  async bootstrap() {
    try {
      const me = await get('/api/admin/me');
      state.role = me.role;
      state.tgId = me.tg_id;
      state.permissions = me.permissions;
      $('who').innerHTML = `<b>${this.escape(me.name)}</b><br>роль: ${this.escape(me.role)}`;
      if (state.role === 'owner') $('demo-toggle').classList.remove('hidden');
      $('gate').classList.add('hidden');
      $('shell').classList.remove('hidden');
      this.applyNavigationPermissions();
      get('/api/admin/health').then((health) => {
        $('health').innerHTML = `<span>БД: ${health.ok ? '✅' : '⚠️'}</span><span>${(health.users ?? 0).toLocaleString('ru-RU')} клиенток</span>${health.telegram_webapp_ready ? '<span>Бот: ✅</span>' : '<span class="bad" title="Задай HTTPS WEBAPP_URL на сервере">Бот: URL не задан</span>'}`;
      }).catch(() => {});
      await this.navigate('dashboard');
    } catch (error) {
      const message = error.status === 403 ? 'У этого аккаунта нет доступа к панели. Добавь свой Telegram id в ADMIN_ID.' : error.status === 401 ? 'Открой панель кнопкой из бота — нужна подпись Telegram.' : error.message;
      $('gate-msg').textContent = message;
    }
  }

  applyNavigationPermissions() {
    const requirements = { users: 'users:read', orders: 'dashboard', catalog: 'catalog', promo: 'promo', broadcasts: 'broadcast', content: 'content:read', settings: 'settings:read', audit: 'dashboard', reconciliation: 'dashboard', logs: 'dashboard', horoscopes: 'content:read', costs: 'dashboard', safety: 'users:read' };
    document.querySelectorAll('.nav-item').forEach((button) => {
      const permission = requirements[button.dataset.view];
      if (permission && !state.can(permission)) button.classList.add('hidden');
    });
  }

  async navigate(view) {
    state.view = view;
    setViewVisibility(view);
    await this.load(view);
  }

  async load(view) {
    try { await (this.loaders[view] || (() => Promise.resolve()))(); } catch (error) { fail(error); }
  }

  escape(value) {
    const element = document.createElement('div');
    element.textContent = value ?? '';
    return element.innerHTML;
  }
}

export const app = new AdminApplication();
app.init();
