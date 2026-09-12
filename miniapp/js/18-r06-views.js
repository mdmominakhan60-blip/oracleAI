/* BUS-1070 p1 R06: вспомогательные вьюхи (S01 StatusBanner, S02 auth-error,
 * S07 Sessions, S10 Sheet tools). Онбординг-рендер живёт в 18-onboarding.js.
 */
(function () {
  'use strict';

  /* ── S01: статус-баннер ── */

  app.renderStatusBanner = function (main, type, message) {
    if (!main) return;
    const banner = document.createElement('div');
    banner.className = 'status-banner status-banner--' + type;
    banner.setAttribute('role', 'alert');
    banner.setAttribute('aria-live', 'polite');
    banner.innerHTML = '<p>' + esc(message) + '</p>';
    main.prepend(banner);
  };

  app.showSessionExpired = function () {
    const main = document.getElementById('app-main');
    if (!main) return;
    this.view = 'expired';
    this.renderFrame();
    if (document.getElementById('app-main')) {
      this.renderStatusBanner(document.getElementById('app-main'), 'error',
        oracleLang() === 'en' ? 'Session expired. Please restart.' : 'Сессия истекла. Перезапустите приложение.');
    }
  };

  /* ── S07: список сессий ── */

  app.renderSessions = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const agents = this.agents && this.agents.length ? this.agents : AGENT_FALLBACK;

    function agentSpec(code) {
      return agents.find(function (a) { return a.code === code; }) || { code: code, name: code, avatar: '/static/img/oracle-mark.png' };
    }
    function timeLabel(ts) {
      const d = new Date(ts);
      const now = new Date();
      const diff = (now - d) / 1000;
      if (diff < 60) return en ? 'now' : 'сейчас';
      if (diff < 3600) return Math.floor(diff / 60) + (en ? 'm' : 'м');
      if (diff < 86400) return Math.floor(diff / 3600) + (en ? 'h' : 'ч');
      if (diff < 172800) return en ? 'yesterday' : 'вчера';
      return d.toLocaleDateString(oracleLang(), { day: 'numeric', month: 'short' });
    }

    const renderList = function (sessions) {
      const cards = sessions.map(function (s) {
        const a = agentSpec(s.agent || 'oracle');
        // Контракт API: threads несут title/last_at; превью строкой в прототипе,
        // но бекенд её не отдаёт — показываем заголовок, без выдуманных данных.
        const preview = s.title || (en ? 'No messages yet' : 'Нет сообщений');
        const ts = s.last_at || s.ts || s.created_at || Date.now();
        return '<div class="session-card" data-sess-row data-tid="' + esc(s.id) + '" style="position:relative">' +
          '<button type="button" class="session-card__main" data-act="open-session" data-tid="' + esc(s.id) + '" style="display:flex;gap:10px;align-items:center;min-width:0;flex:1;background:none;border:none;padding:0;text-align:left;cursor:pointer">' +
            '<img class="session-card__avatar" src="' + esc(a.avatar || '/static/img/agents/' + a.code + '.jpg') + '" alt="" width="36" height="36" loading="lazy" onerror="this.onerror=null;this.src=\'/static/img/oracle-mark.png\'">' +
            '<span class="session-card__body">' +
              '<span class="session-card__top">' +
                '<span class="session-card__name">' + esc(a.name) + '</span>' +
                '<span class="session-card__time">' + timeLabel(ts) + '</span>' +
              '</span>' +
              '<span class="session-card__preview">' + esc(preview) + '</span>' +
            '</span>' +
          '</button>' +
          '<button type="button" class="sess-del" data-act="sess-del" data-tid="' + esc(s.id) + '" aria-label="' + esc(en ? 'Delete conversation' : 'Удалить диалог') + '" style="flex:0 0 auto;width:32px;height:32px;display:grid;place-items:center;background:none;border:none;color:var(--color-text-muted);font-size:15px;cursor:pointer">✕</button>' +
          '<span class="session-card__confirm-label" aria-hidden="true" hidden></span>' +
        '</div>';
      }).join('');

      main.innerHTML = '<div class="screen">' +
        '<div class="screen__body">' +
          '<div class="screenheader">' +
            '<button type="button" class="screenheader__back" data-act="back" aria-label="' + esc(en ? 'Back' : 'Назад') + '">←</button>' +
            '<h1 class="screenheader__title">' + esc(t('sessionsTitle')) + '</h1>' +
          '</div>' +
          (cards ? '<div class="session-list" role="list">' + cards + '</div>' :
            '<div style="display:flex;flex-direction:column;align-items:center;gap:12px;padding:48px 24px;color:var(--color-text-muted)">' +
              '<span style="font-size:32px" aria-hidden="true">🔮</span>' +
              '<p style="font-size:16px;color:var(--color-text-secondary)">' + esc(t('sessionsEmptyCopy')) + '</p>' +
            '</div>'
          ) +
        '</div>' +
      '</div>';

      this.syncBackButton();
    }.bind(this);

    // Сессии агента — грузим при входе на вьюху, а не только из чата.
    const key = (this.chat && this.chat.key) || 'oracle';
    const cached = (this.chat && this.chat.sessions) || [];
    renderList(cached);
    api('/api/chat/' + key + '/sessions').then(function (rows) {
      if (app.view !== 'sessions') return;
      const fresh = Array.isArray(rows) ? rows : [];
      if (app.chat) app.chat.sessions = fresh;
      const changed = fresh.length !== cached.length || fresh.some(function (s, i) { return !cached[i] || s.id !== cached[i].id; });
      if (changed) renderList(fresh);
    }).catch(function () {});
  };

  /* ── S10: sheet инструментов ── */

  app.renderSheetTools = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    const agents = this.agents && this.agents.length ? this.agents : AGENT_FALLBACK;
    const tools = [
      { icon: '🎴', name: en ? 'Tarot · 10 spreads' : 'Таро · 10 раскладов', benefit: en ? 'Rider–Waite spreads in chat' : 'Расклады Райдера-Уэйта в чате', agent: 'tarot', locked: false },
      { icon: '🧭', name: en ? 'Destiny Matrix' : 'Матрица судьбы', benefit: en ? 'Lines, arcana, period focus' : 'Линии, арканы и фокус периода', locked: false },
      { icon: '📖', name: en ? 'Diary' : 'Дневник', benefit: en ? 'Day recording and observation' : 'Запись дня и практика наблюдения', locked: false },
      { icon: '🌙', name: en ? 'Moon week' : 'Луна недели', benefit: en ? 'Birth data required — fill profile' : 'Нужны данные рождения', locked: true },
    ];

    const rows = tools.map(function (tool) {
      return '<button type="button" class="tool-row" ' + (tool.locked ? 'aria-disabled="true" style="opacity:.55"' : 'data-act="tool-fn" data-fn="toggleToolbox"') + '>' +
        '<span class="tool-row__icon" aria-hidden="true">' + tool.icon + '</span>' +
        '<span class="tool-row__body">' +
          '<span class="tool-row__name">' + esc(tool.name) + '</span>' +
          '<span class="tool-row__benefit">' + esc(tool.benefit) + '</span>' +
        '</span>' +
        (tool.locked ? '<span class="tool-row__meta tool-row__meta--locked">' + esc(t('sheetLocked')) + '</span>' : '') +
      '</button>';
    }).join('');

    main.innerHTML = '<div class="sheet" role="dialog" aria-modal="true" aria-labelledby="r06-sheet-title">' +
      '<div class="sheet__header">' +
        '<h2 class="sheet__title" id="r06-sheet-title">' + esc(t('sheetTitle')) + '</h2>' +
        '<button type="button" class="sheet__close" data-act="back" aria-label="' + esc(en ? 'Close' : 'Закрыть') + '">✕</button>' +
      '</div>' +
      '<div class="sheet__search">' +
        '<label class="visually-hidden" for="r06-tool-search">' + esc(t('sheetSearch')) + '</label>' +
        '<input class="field__input" id="r06-tool-search" type="search" placeholder="' + esc(t('sheetSearch')) + '" style="width:100%">' +
      '</div>' +
      '<div class="sheet__body" role="list">' + rows + '</div>' +
    '</div>';

    this.syncBackButton();
  };
}());
