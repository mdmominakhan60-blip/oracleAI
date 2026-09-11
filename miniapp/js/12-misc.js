/* misc: профиль, памяти, чтения, отчёты, полная карта, колокол, модалы */
  app.shareReading = async function(id) {
    try {
      const res = await fetch('/api/share/reading/' + id + '.png', { headers: authHeaders() });
      if (!res.ok) { this.toast('Картинка сейчас недоступна 🌙'); return; }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const file = new File([blob], 'oracle-tarot.png', { type: 'image/png' });
      if (navigator.share && navigator.canShare && navigator.canShare({ files: [file] })) {
        navigator.share({ title: 'Мой расклад Таро', files: [file] })
          .catch(() => this.downloadUrl(url, 'oracle-tarot.png'));
      } else {
        this.downloadUrl(url, 'oracle-tarot.png');
      }
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (e) { this.toast('Картинка сейчас недоступна 🌙'); }
  };

  app.refCopy = async function() {
    const link = this._refLink;
    if (!link) { this.toast('Ссылка ещё готовится…'); return; }
    haptic('light');
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(link);
        this.toast('Ссылка скопирована — можно поделиться ✨');
      } else {
        this.toast(link);
      }
    } catch (e) { this.toast('Ссылка: ' + link); }
  };
  // G004 «сбылось» на раскладе: обратная связь ценности

  app.setOutcome = async function(id, val) {
    haptic('soft');
    try {
      await api('/api/tarot/outcome/' + id, { method: 'POST', body: JSON.stringify({ outcome: val }) });
      this.toast(val === 'came_true' ? 'Рада, что сбылось! Возвращайся за следующим раскладом ✨'
        : val === 'partly' ? 'Отметим частично — главное, что откликнулось 🌙' : 'Поняла — жизнь вносит коррективы 🌙');
    } catch (e) { this.toast(friendlyError(e, 'Не получилось сохранить отметку. Попробуй ещё раз.')); }
  };

  app.softEmpty = function({ icon = '✦', eyebrow = '', title, copy, action = '', tone = '' }) {
    return `<div class="soft-empty ${tone ? 'soft-empty--' + tone : ''}">
      <div class="soft-empty__orb" aria-hidden="true">${icon}</div>
      ${eyebrow ? `<span class="soft-empty__eyebrow">${eyebrow}</span>` : ''}
      <h1 class="soft-empty__title">${title}</h1>
      <div class="soft-empty__copy">${copy}</div>
      ${action ? `<div class="soft-empty__action">${action}</div>` : ''}
    </div>`;
  };

  app.renderProfile = async function(main) {
    const me = this.me;
    const firstName = me && me.name ? esc(me.name.split(' ')[0]) : profileT('you');
    const streak = me && me.global_streak ? me.global_streak : 0;
    const questions = me && me.allowance && typeof me.allowance.left !== 'undefined' ? me.allowance.left : '—';
    const genderLabel = gendered(me, t('female'), t('male'), t('notSpecified'));
    const identityBlock = me && me.birth_date ? `
      <div class="glass" style="padding:14px 16px;font-size:13px">
        <div class="planet-line"><div class="p-ico">◌</div><div class="p-name">${profileT('birth')}</div><div class="p-val">${esc(me.birth_date)}</div></div>
        <div class="planet-line"><div class="p-ico">⌁</div><div class="p-name">${profileT('time')}</div><div class="p-val">${esc(me.birth_time_known ? me.birth_time : profileT('unknown'))}</div></div>
        <div class="planet-line"><div class="p-ico">⌖</div><div class="p-name">${profileT('city')}</div><div class="p-val">${esc(me.birth_city || '—')}</div></div>
      </div>` : `
      <div class="profile-empty">
        <div class="profile-empty-title">${profileT('buildChartTitle')}</div>
        <div class="profile-empty-copy">${profileT('buildChartCopy')}</div>
        <div class="seg-progress profile-empty-steps" aria-label="${profileFormat('stepOf', { n: 1, m: 3 })}"><span class="is-on">${profileT('date')}</span><i></i><span>${profileT('time').toLowerCase()}</span><i></i><span>${profileT('city').toLowerCase()}</span></div>
        <button class="btn btn-primary" style="width:100%;margin-top:14px" data-act="chat" data-chat="astro">${profileT('openMyChart')}</button>
      </div>`;
    main.innerHTML = `
      <div class="screen">
        <div class="profile-hero">
          <div class="profile-kicker">${profileT('space')}</div>
          <h1 class="profile-name">${firstName}, ${profileT('path')}</h1>
          <div class="profile-copy">${profileT('spaceCopy')}</div>
          <div class="ritual-meter"><span class="ritual-meter-label">${streak ? profileFormat('streakLabel', { count: streak }) : profileT('firstRitual')}</span><span class="ritual-meter-track"><span class="ritual-meter-fill" style="width:${Math.min(100, Math.max(18, streak ? 18 + streak * 8 : 18))}%"></span></span></div>
        </div>

        <div class="ptab-bar">
          <button class="ptab active" data-act="ptab" data-tab="summary">${profileT('summary')}</button>
          <button class="ptab" data-act="ptab" data-tab="chart">${profileT('chart')}</button>
          <button class="ptab" data-act="ptab" data-tab="history">${profileT('history')}</button>
          <button class="ptab" data-act="ptab" data-tab="memory">${profileT('memory')}</button>
        </div>

        <div class="ptab-pane active" id="ptab-summary">
          <div class="section-kicker">${profileT('yourStreak')}</div>
          <div class="glass" style="display:flex;align-items:center;gap:12px;padding:14px 16px;margin-bottom:11px">
            <span style="width:43px;height:43px;display:grid;place-items:center;border-radius:14px;background:rgba(245,212,139,.13);color:var(--champagne-300);font-size:21px;flex-shrink:0">✦</span>
            <div style="flex:1;min-width:0">
              <div style="color:var(--text-main);font-family:var(--font-serif);font-weight:700;font-size:17px">${streak ? profileFormat('streakHeadline', { count: streak }) : profileT('firstSign')}</div>
              <div style="font-size:12.5px;color:var(--text-soft);line-height:1.45;margin-top:3px">${streak ? profileT('streakContinue') : profileT('firstSignCopy')}</div>
            </div>
          </div>
          <div class="stat-row">
            <div class="stat"><div class="sv">${streak || '—'}</div><div class="sl">${profileT('rituals')}</div></div>
            <div class="stat"><div class="sv">${me && typeof me.crystals !== 'undefined' ? me.crystals : '—'}</div><div class="sl">${profileT('sparks')}</div></div>
            <div class="stat"><div class="sv">${questions}</div><div class="sl">${profileT('questions')}</div></div>
            <div class="stat"><div class="sv">${me && me.diary_streak ? me.diary_streak : '—'}</div><div class="sl">${profileT('notes')}</div></div>
          </div>
          <div class="spacer"></div>
          <div class="section-kicker">${profileT('yourFoundation')}</div>
          <div class="section-title">${profileT('birthData')}</div>
          ${identityBlock}
          <button class="glass language-row" data-act="gender" type="button" aria-label="${esc(t('changeGender'))}">
            <span class="language-row__copy"><b>${esc(t('gender'))}</b><small>${esc(genderLabel)}</small></span>
            <span class="language-row__chevron" aria-hidden="true">›</span>
          </button>
          <button class="glass language-row" data-act="language" type="button" aria-label="${esc(t('changeLanguage'))}">
            <span class="language-row__copy"><b>${esc(t('language'))}</b><small>${esc((me && me.lang) === 'en' ? t('english') : t('russian'))}</small></span>
            <span class="language-row__chevron" aria-hidden="true">›</span>
          </button>
          <div class="spacer"></div>
          <div id="profile-referral"></div>
          ${me && me.feedback_pending ? `<button class="glass language-row" data-act="survey-open" type="button" aria-label="${esc(oracleLang() === 'en' ? 'Open week survey' : 'Открыть опрос недели')}">
            <span class="language-row__copy"><b>${esc(oracleLang() === 'en' ? 'A Week with Oracle 🌙' : 'Неделя с Оракулом 🌙')}</b><small>${esc(oracleLang() === 'en' ? '5 questions · 40 Crystals' : '5 вопросов · 40 кристаллов')}</small></span>
            <span class="language-row__chevron" aria-hidden="true">›</span>
          </button>` : ''}
          <div class="spacer"></div>
          <section class="glass account-center" aria-labelledby="account-center-title">
            <div class="section-kicker">АККАУНТ И ПРИВАТНОСТЬ</div>
            <div class="account-center__title" id="account-center-title">Твои данные и оплаты</div>
            <p class="account-center__copy">История платежей строится по серверному статусу. Экспорт не включает тексты чатов, память, дневник или payload провайдера.</p>
            <div class="btn-row"><button class="btn btn-ghost" type="button" data-act="payment-history">История оплат</button><button class="btn btn-ghost" type="button" data-act="account-privacy">Центр приватности</button></div>
          </section>
          <div class="spacer"></div>
          <section class="glass account-danger" aria-labelledby="account-danger-title">
            <div class="section-kicker">${profileT('account')}</div>
            <div class="account-danger__title" id="account-danger-title">${profileT('deleteAccount')}</div>
            <p class="account-danger__copy">${profileT('deleteAccountCopy')}</p>
            <button class="btn btn-ghost account-danger__button" type="button" data-act="account-delete">${profileT('deleteAccount')}</button>
          </section>
        </div>

        <div class="ptab-pane" id="ptab-chart">
          <div class="section-title">${profileT('natalChart')}</div>
          <div id="profile-chart"><div class="glass"><div class="center-block"><div class="loader-ring"></div></div></div></div>
        </div>

        <div class="ptab-pane" id="ptab-history">
          <div class="section-title">${profileT('unifiedHistory')}</div>
          <div id="profile-unified-history"><div class="skeleton" style="height:150px;border-radius:16px"></div></div>
          <div class="spacer"></div>
          <div class="section-title">${profileT('latestReadings')}</div>
          <div id="profile-tarot"><div class="skeleton" style="height:80px;border-radius:16px"></div></div>
          <div class="spacer"></div>
          <div class="section-title">${profileT('reports')}</div>
          <div id="profile-reports"><div class="skeleton" style="height:60px;border-radius:16px"></div></div>
        </div>

        <div class="ptab-pane" id="ptab-memory">
          <div class="section-title">${profileT('memoryAbout')}</div>
          <div id="profile-memories"><div class="skeleton" style="height:60px;border-radius:16px"></div></div>
        </div>
      </div>`;
    this.loadProfileSections();
  };


  app.loadProfileSections = async function() {
    const refEl = document.getElementById('profile-referral');
    if (refEl) {
      try {
        const ref = await api('/api/referral');
        if (ref && ref.link) {
          refEl.innerHTML = `
            <div class="ref-card">
              <div class="ref-ico">🌙</div>
              <div class="ref-body">
                <div class="ref-title">${profileFormat('referralTitle', { bonus: ref.bonus_per_invite || '' })}</div>
                <div class="ref-desc">${esc(ref.share_text || profileT('referralFallback'))}</div>
              </div>
              <button class="btn btn-primary ref-btn" data-act="ref-copy">${profileT('copy')}</button>
            </div>`;
          this._refLink = ref.link;
        } else {
          refEl.innerHTML = '';
        }
      } catch (e) { refEl.innerHTML = ''; }
    }
    const chartEl = document.getElementById('profile-chart');
    const tarotEl = document.getElementById('profile-tarot');
    const repEl = document.getElementById('profile-reports');
    const historyEl = document.getElementById('profile-unified-history');
    const memEl = document.getElementById('profile-memories');

    // G001: три независимых запроса идут параллельно (.catch — чтобы не было
    // unhandledrejection до их await в блоках ниже)
    const pChart = api('/api/chart'); pChart.catch(() => {});
    const pTarot = api('/api/tarot/history'); pTarot.catch(() => {});
    const pReps = api('/api/reports'); pReps.catch(() => {});
    const pHistory = api('/api/history'); pHistory.catch(() => {});

    try {
      const history = await pHistory;
      const labelKeys = { report: 'historyReport', tarot: 'historyTarot', chat: 'historyChat', diary: 'historyDiary' };
      const actionFor = { report: 'report', tarot: 'reading', chat: 'history-chat', diary: 'history-diary' };
      const rows = (history.items || []).slice(0, 8);
      if (historyEl) {
        historyEl.innerHTML = rows.length ? rows.map(item => {
          const kind = item.kind || 'report';
          const attrs = kind === 'report'
            ? `data-kind="${esc(item.source_kind || 'natal')}" data-report-id="${Number(item.entry_id) || 0}"`
            : `data-id="${Number(item.entry_id) || 0}" data-agent="${esc(item.source_kind || 'oracle')}"`;
          return `<button class="history-item" data-act="${actionFor[kind] || 'report'}" ${attrs} type="button" aria-label="${esc(profileT(labelKeys[kind] || 'archive'))}: ${esc(item.title || '')}">
            <span class="history-item__icon" aria-hidden="true">${kind === 'tarot' ? '🎴' : kind === 'chat' ? '◌' : kind === 'diary' ? '✎' : '📜'}</span>
            <span class="history-item__body"><b>${esc(profileT(labelKeys[kind] || 'archive'))}</b><strong>${esc(item.title || '')}</strong><small>${esc(item.preview || fmtDay((item.created_at || '').slice(0, 10)))}</small></span><span class="history-item__chev" aria-hidden="true">›</span>
          </button>`;
        }).join('') : this.softEmpty({ icon: '✦', eyebrow: profileT('archive'), title: profileT('unifiedHistory'), copy: profileT('unifiedHistoryEmpty') });
      }
    } catch (e) {
      if (historyEl) historyEl.innerHTML = this.softEmpty({ icon: '✦', eyebrow: profileT('archive'), title: profileT('reportsUnavailable'), copy: profileT('tryLater'), tone: 'recovery' });
    }

    // натальная карта (по возможности — из /api/me, иначе /api/chart)
    try {
      const c = await pChart;
      const sun = c.sun || {}, asc = c.ascendant || {};
      const exactChart = c.precision === 'exact';
      const precisionCopy = exactChart
        ? profileFormat('ascendant', { sign: esc(asc.sign || '—') })
        : esc(c.note || profileT('chartNoTime'));
      const planets = (c.planets || []).slice(0, 8).map(p => `
        <div class="planet-line">
          <div class="p-ico">${SIGNS[p.sign] || ''}</div>
          <div class="p-name">${esc(p.name)}</div>
          <div class="p-val">${esc(p.sign)}${exactChart && p.house ? ' · ' + p.house : ''}</div>
        </div>`).join('');
      if (chartEl) chartEl.innerHTML = `
        <div class="glass" style="padding:16px">
          <div style="display:flex;align-items:center;gap:16px">
            <div class="chart-wheel" style="width:110px;height:110px">
              <div class="wheel-center"><div class="wc-s">${sun.symbol || '☉'}</div><div class="wc-t">${esc(sun.sign || '')}</div></div>
            </div>
            <div style="flex:1;font-size:13px">
              <div style="font-family:var(--font-serif);color:var(--gold-bright);font-size:14.5px">${esc(sun.sign || '—')}</div>
              <div style="color:var(--text-dim);font-size:12px;line-height:1.4">${precisionCopy}</div>
              <div style="margin-top:10px;display:flex;gap:8px">
                <button class="btn btn-ghost" style="padding:8px 12px;font-size:12px" data-act="chat" data-chat="astro">${profileT('ask')}</button>
                <button class="btn btn-ghost" style="padding:8px 12px;font-size:12px" data-act="full-chart">${profileT('fullChart')}</button>
              </div>
            </div>
          </div>
          <div style="margin-top:10px">${planets}</div>
          <div style="color:var(--text-faint);font-size:11px;margin-top:6px">${exactChart ? profileT('chartDetailExact') : profileT('chartDetailApprox')}</div>
        </div>`;
    } catch (e) {
      if (chartEl) chartEl.innerHTML = this.softEmpty({
        icon: '🌌', eyebrow: profileT('chartEyebrow'), title: profileT('chartMissing'),
        copy: profileT('chartMissingCopy'),
        action: `<button class="btn btn-primary" data-act="chat" data-chat="astro">${profileT('collectChart')}</button>`
      });
    }

    try {
      const rows = await pTarot;
      // компактно: до 3 строк + «Все N →» (тап открывает модал со всем списком)
      if (tarotEl) {
        if (!rows.length) {
          tarotEl.innerHTML = this.softEmpty({
            icon: '🎴', eyebrow: profileT('firstReadingEyebrow'), title: profileT('firstReadingTitle'),
            copy: profileT('firstReadingCopy'),
            action: `<button class="btn btn-primary" data-act="chat-fn" data-chat="tarot" data-fn="featureTarot">${profileT('askCards')}</button>`
          });
        } else {
          const shown = rows.slice(0, 3).map(r => `
            <div class="tight-card" data-act="reading" data-id="${r.id}">
              <span class="tc-emoji">${r.cards && r.cards[0] ? r.cards[0].emoji : '🎴'}</span>
              <div style="flex:1;min-width:0">
                <div class="tc-title">${esc(r.question || 'Расклад')}</div>
                <div class="tc-meta">${fmtDay(r.created_at.slice(0, 10))} · ${esc(r.spread || '')}</div>
              </div>
              <span class="tc-open">›</span>
            </div>`).join('');
          const more = rows.length > 3
            ? `<button class="more-row" data-act="all-readings">${profileFormat('allReadings', { count: rows.length })}</button>` : '';
          tarotEl.innerHTML = shown + more;
        }
      }
      this._readingsCache = rows;
    } catch (e) {
      if (tarotEl) tarotEl.innerHTML = this.softEmpty({
        icon: '🎴', eyebrow: profileT('readingsHistory'), title: profileT('readingsUnavailable'),
        copy: profileT('readingsUnavailableCopy'), tone: 'recovery',
        action: `<button class="btn btn-ghost" data-act="chat-fn" data-chat="tarot" data-fn="featureTarot">${profileT('openTarot')}</button>`
      });
    }

    try {
      const rep = await pReps;
      const ready = rep.ready || [];
      if (repEl) repEl.innerHTML = ready.length ? ready.map(r => `
        <div class="result-card" style="margin-bottom:8px" data-act="report" data-kind="${esc(r.kind)}" data-report-id="${Number(r.id) || 0}">
          <div class="rc-top">
            <span style="font-size:16px">📜</span>
            <div style="flex:1;min-width:0"><div class="rc-title" style="font-size:13px">${esc(r.title)}</div>
            <div class="rc-meta">${r.period || fmtDay((r.created_at || '').slice(0, 10))}</div></div>
            <span class="rc-open">›</span>
          </div>
        </div>`).join('') : this.softEmpty({
          icon: '✦', eyebrow: profileT('archive'), title: profileT('reportsEmpty'),
          copy: profileT('reportsEmptyCopy')
        });
    } catch (e) {
      if (repEl) repEl.innerHTML = this.softEmpty({
        icon: '✦', eyebrow: profileT('archive'), title: profileT('reportsUnavailable'),
        copy: profileT('tryLater'), tone: 'recovery'
      });
    }

    const mems = this.me && this.me.memories ? this.me.memories : [];
      // кнопка открывает модал управления памятью (просмотр/дата/удалить/добавить)
      if (memEl) memEl.innerHTML = `
        <button class="memory-open" data-act="memories">
          <span style="font-size:18px">🧠</span>
          <span style="flex:1;text-align:left">
            <div style="font-weight:600;font-size:14px">${profileT('memoryAbout')}</div>
            <div style="font-size:12px;color:var(--text-dim);margin-top:2px">${mems.length ? profileFormat('memoryCount', { count: mems.length }) : profileT('memoryEmpty')}</div>
          </span>
          <span style="color:var(--gold)">›</span>
        </button>`;
  };


  app.openHistoryChat = function(agent, id) {
    this.openChat(agent, () => this.openSession(id));
  };


  app.openDiary = async function(id) {
    try {
      const entry = await api('/api/diary/' + Number(id));
      this.showModal(`<h3>${esc(profileT('historyDiary'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button><div style="font-size:12px;color:var(--text-dim);margin:8px 0">${esc(fmtDay((entry.created_at || '').slice(0, 10)))}</div><div style="font-size:14px;line-height:1.65;white-space:pre-wrap">${esc(entry.text || '')}</div>`);
    } catch (e) { alert(friendlyError(e, 'Это временно. Попробуй ещё раз.')); }
  };


  app.openReport = async function(kind, reportId) {
    try {
      const suffix = Number(reportId) > 0 ? '?report_id=' + encodeURIComponent(Number(reportId)) : '';
      const r = await api('/api/reports/' + kind + suffix);
      this.showModal(`<h3>${esc(r.title)}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button><div style="font-size:13.5px;line-height:1.65;margin-top:8px">${rich(r.body)}</div>`);
    } catch (e) { alert(friendlyError(e, 'Это временно. Попробуй ещё раз.')); }
  };


  app.openReading = async function(id) {
    try {
      const rows = await api('/api/tarot/history');
      const r = rows.find(x => x.id === id) || rows[0];
      const cardStrip = (r.cards || []).map(c => `
        <div class="rc-strip"><img src="/static/img/tarot/${esc(c.img || 'm00')}.jpg" alt="${esc(c.name)}" loading="lazy">
          <span>${esc(c.name)}${c.reversed ? ' ↺' : ''}</span></div>`).join('');
      const cards = (r.cards || []).map(c => `${c.emoji} ${c.name}${c.reversed ? ' ↺' : ''} — ${c.meaning}`).join('\n');
      this.showModal(`<h3>🎴 ${esc(r.question || profileT('readingFallback'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
        <div class="rc-strip-row">${cardStrip}</div>
        <div style="font-size:12px;color:var(--text-dim);white-space:pre-wrap;margin:8px 0">${esc(cards)}</div>
        <div style="font-size:13.5px;line-height:1.65;white-space:pre-wrap">${esc(r.answer || '—')}</div>
        <button class="btn btn-primary" style="margin-top:14px" data-act="share-reading" data-id="${id}">${esc(profileT('saveStory'))}</button>
        <div class="outcome-row">
          <span class="outcome-q">${esc(profileT('outcomeQuestion'))}</span>
          <button class="outcome-chip" data-act="outcome" data-id="${id}" data-val="came_true">${esc(profileT('outcomeYes'))}</button>
          <button class="outcome-chip" data-act="outcome" data-id="${id}" data-val="partly">${esc(profileT('outcomePartial'))}</button>
          <button class="outcome-chip" data-act="outcome" data-id="${id}" data-val="no">${esc(profileT('outcomeNo'))}</button>
        </div>`);
    } catch (e) { alert(friendlyError(e, 'Это временно. Попробуй ещё раз.')); }
  };

  // тап по подсказке на карте агента: открывает чат и сразу отправляет вопрос

  app.askAgent = function(key, q) {
    this.openChat(key, () => this.doSend(q));
  };

  // Память: управление — просмотр с датой, удалить, добавить вручную.

  app.openMemories = async function() {
    this.showModal(`<h3>${esc(profileT('memoryTitle'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
      <div id="mem-body" style="margin-top:6px"><div class="loader-ring"></div></div>`);
    try {
      // «На паузе» означает, что Оракул не использует и не сохраняет новые факты.
      // Это не скрывает уже сохранённое от её владелицы: архив всегда остаётся доступен.
      const rows = await api('/api/memories');
      this._memFull = rows;
      this._memSearch = '';
      this.renderMemModal();
    } catch (e) {
      const body = document.getElementById('mem-body');
      if (body) body.innerHTML = this.softEmpty({
        icon: '🧠', eyebrow: profileT('memoryEyebrow'), title: profileT('memoryUnavailable'),
        copy: profileT('memoryUnavailableCopy'), tone: 'recovery'
      });
    }
  };


  app.renderMemModal = function() {
    const el = document.getElementById('mem-body');
    if (!el) return;
    const enabled = !(this.me && this.me.memory_enabled === false);
    const rows = this._memFull || [];
    const list = rows.map((m, index) => {
      const fact = String(m.fact || '');
      const haystack = esc(fact.toLowerCase());
      return `<article class="mem-manage-row" data-mem-item data-mem-text="${haystack}">
        <div class="mem-manage-row__top">
          <span class="mem-manage-index" aria-hidden="true">${String(index + 1).padStart(2, '0')}</span>
          <time class="mem-manage-meta">${esc((m.created_at || '').slice(0, 10)) || esc(profileT('noDate'))}</time>
          <button class="mem-del" data-act="del-mem" data-id="${m.id}" title="${esc(profileT('deleteFact'))}" aria-label="${esc(profileT('deleteFact'))}">${sigilIcon('spark')}</button>
        </div>
        <div class="mem-manage-txt">${esc(fact)}</div>
      </article>`;
    }).join('');
    const stateCopy = enabled ? profileT('memoryOnCopy') : profileT('memoryPausedCopy');
    const archive = rows.length ? `
      <div class="mem-search">
        ${sigilIcon('spark')}
        <input class="ipt" id="mem-search" type="search" placeholder="${esc(profileFormat('searchFacts', { count: rows.length, noun: rows.length === 1 ? profileT('factOne') : profileT('factMany') }))}" autocomplete="off" aria-label="${esc(profileT('searchFactAria'))}">
        <span class="mem-search-count" data-mem-count>${rows.length}</span>
      </div>
      <div class="mem-manage-list" data-mem-list>${list}</div>
      <div class="memory-search-empty" data-mem-empty hidden>${esc(profileT('searchEmpty'))}</div>`
      : `<div class="memory-empty">
          <span class="memory-empty__sigil">${sigilIcon('spark')}</span>
          <b>${esc(profileT('memoryQuiet'))}</b>
          <p>${esc(enabled ? profileT('memoryEmptyEnabled') : profileT('memoryEmptyPaused'))}</p>
        </div>`;
    el.innerHTML = `
      <section class="memory-hero ${enabled ? 'is-enabled' : 'is-paused'}">
        <div class="memory-hero__top">
          <div>
            <span class="memory-eyebrow">${esc(profileT('context'))}</span>
            <h4>${esc(profileT('memoryAboutTitle'))}</h4>
          </div>
          <button class="memory-switch ${enabled ? 'is-on' : ''}" data-act="toggle-memory" type="button" role="switch" aria-checked="${enabled}" aria-label="${esc(enabled ? profileT('pauseMemory') : profileT('enableMemory'))}">
            <span class="memory-switch__track" aria-hidden="true"><span></span></span>
            <span>${esc(enabled ? profileT('active') : profileT('paused'))}</span>
          </button>
        </div>
        <p>${esc(stateCopy)}</p>
        <div class="memory-hero__foot"><span>${rows.length} ${esc(rows.length === 1 ? profileT('factCountOne') : rows.length < 5 ? profileT('factCountFew') : profileT('factCountMany'))}</span><span>${esc(profileT('deleteAny'))}</span></div>
      </section>
      ${enabled ? `<div class="mem-add memory-add">
        <input class="ipt" id="mem-new" aria-label="${esc(profileT('addFact'))}" placeholder="${esc(profileT('addFactExample'))}" autocomplete="off" maxlength="500"/>
        <button class="send-btn" data-act="add-mem" title="${esc(profileT('addFact'))}" aria-label="${esc(profileT('addFact'))}">${sigilIcon('spark')}</button>
      </div>` : ''}
      <div class="memory-archive-head"><b>${esc(profileT('archiveTitle'))}</b><span>${esc(enabled ? profileT('archiveUsed') : profileT('archiveHidden'))}</span></div>
      ${archive}`;

    const search = el.querySelector('#mem-search');
    if (search) search.addEventListener('input', event => this.filterMemories(event.target.value));
  };

  app.filterMemories = function(query) {
    const normalized = String(query || '').trim().toLowerCase();
    const rows = Array.from(document.querySelectorAll('[data-mem-item]'));
    let visible = 0;
    rows.forEach(row => {
      const matched = !normalized || String(row.dataset.memText || '').includes(normalized);
      row.hidden = !matched;
      if (matched) visible += 1;
    });
    const count = document.querySelector('[data-mem-count]');
    const empty = document.querySelector('[data-mem-empty]');
    if (count) count.textContent = normalized ? visible + ' / ' + rows.length : rows.length;
    if (empty) empty.hidden = visible !== 0;
  };


  app.openPrivacyCenter = async function() {
    this.showModal(`<h3>Центр приватности</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button><div id="privacy-body" class="modal-body"><div class="loader-ring"></div></div>`);
    try {
      const privacy = await api('/api/account/privacy');
      const categories = (privacy.categories || []).map(item => `<div class="privacy-row"><b>${esc(item.label)}</b><span>${item.exportable ? 'доступно в экспорте' : 'не входит в экспорт'}</span></div>`).join('');
      document.getElementById('privacy-body').innerHTML = `<p class="modal-soft-copy">Удаление аккаунта анонимизирует профиль, а settlement-safe payment trace может сохраниться для финансовой отчётности. Анонимизация необратима.</p><div class="privacy-list">${categories}</div><div class="btn-row" style="margin-top:12px"><button class="btn btn-primary" data-act="account-export">Скачать мой экспорт</button><button class="btn btn-destructive" data-act="modal-close">Закрыть</button></div>`;
    } catch (e) { document.getElementById('privacy-body').innerHTML = `<p class="modal-soft-copy">${esc(friendlyError(e, 'Центр приватности временно недоступен.'))}</p>`; }
  };

  app.exportAccount = async function() {
    try {
      let url = '/api/account/export';
      const dev = new URLSearchParams(location.search).get('dev_user');
      if (dev) url += '?dev_user=' + encodeURIComponent(dev);
      const headers = Object.assign({ Accept: 'application/json' }, authHeaders());
      if (dev) {
        const devKey = localStorage.getItem('oracle_dev_key');
        if (devKey) headers['X-Dev-Key'] = devKey;
      }
      const response = await fetch(url, { headers });
      if (!response.ok) throw new Error('Не удалось подготовить экспорт');
      const blob = await response.blob();
      const href = URL.createObjectURL(blob); const link = document.createElement('a');
      link.href = href; link.download = 'oracle-account-export.json'; document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(href), 1000); this.toast('Экспорт подготовлен');
    } catch (e) { this.toast(friendlyError(e, 'Экспорт временно недоступен.')); }
  };

  app.deleteAccount = async function() {
    if (!window.confirm(profileT('deleteAccountConfirm'))) return;
    const button = document.querySelector('[data-act="account-delete"]');
    if (button) button.disabled = true;
    try {
      await api('/api/account/delete', {
        method: 'POST',
        body: JSON.stringify({ confirm: true })
      });
      this.me = null;
      this.chat = this.chat || {};
      this.chat.key = null;
      this.chat.tid = null;
      this.chat.messages = [];
      this.chat.pending = null;
      this.chat.busy = false;
      const nav = document.querySelector('.app-nav');
      if (nav) nav.hidden = true;
      const main = document.getElementById('app-main');
      if (main) main.innerHTML = `<div class="screen" data-account-deleted>
        <div class="soft-empty soft-empty--quiet" data-state="success">
          <div class="soft-empty__orb" aria-hidden="true">✦</div>
          <h1 class="soft-empty__title">${esc(profileT('deleteAccountDone'))}</h1>
          <div class="soft-empty__copy">${esc(profileT('deleteAccountDoneCopy'))}</div>
        </div>
      </div>`;
      haptic('success');
    } catch (e) {
      if (button) button.disabled = false;
      alert(friendlyError(e, profileT('deleteAccountFailed')));
    }
  };

  app.toggleMemory = async function() {
    const current = !(this.me && this.me.memory_enabled === false);
    try {
      await api('/api/profile', { method: 'POST', body: JSON.stringify({ memory_enabled: !current }) });
      this.me = await api('/api/me');
      // Факты остаются доступны владелице, даже когда новые сохранения и recall поставлены на паузу.
      this._memFull = await api('/api/memories');
      this._memSearch = '';
      this.renderMemModal();
      haptic('light');
    } catch (e) { alert(friendlyError(e, 'Это временно. Попробуй ещё раз.')); }
  };

  app.delMem = async function(id) {
    try {
      await api('/api/memories/' + id, { method: 'DELETE' });
      this._memFull = (this._memFull || []).filter(m => m.id !== id);
      this.renderMemModal();
      this.me = null; this.me = await api('/api/me');   // обновить счётчик памяти
    } catch (e) { alert(friendlyError(e, 'Это временно. Попробуй ещё раз.')); }
  };


  app.addMem = async function() {
    const input = document.getElementById('mem-new');
    const fact = (input && input.value || '').trim();
    if (fact.length < 3) { if (input) input.focus(); return; }
    try {
      await api('/api/memories', { method: 'POST', body: JSON.stringify({ fact }) });
      this._memFull = await api('/api/memories');
      this.renderMemModal();
      this.me = await api('/api/me');
    } catch (e) { alert(friendlyError(e, 'Это временно. Попробуй ещё раз.')); }
  };

  // «Все N раскладов»: полный список в модале

  app.openAllReadings = async function() {
    let rows = this._readingsCache;
    if (!rows) { try { rows = await api('/api/tarot/history'); } catch (e) { rows = []; } }
      const items = (rows || []).map(r => `
      <div class="tight-card" data-act="reading" data-id="${r.id}">
        <span class="tc-emoji">${r.cards && r.cards[0] ? r.cards[0].emoji : '🎴'}</span>
        <div style="flex:1;min-width:0">
          <div class="tc-title">${esc(r.question || profileT('readingFallback'))}</div>
          <div class="tc-meta">${fmtDay(r.created_at.slice(0, 10))} · ${esc(r.spread || '')}</div>
        </div>
        <span class="tc-open">›</span>
      </div>`).join('');
    this.showModal(`<h3>${esc(profileT('allReadingsTitle'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
      <div style="margin-top:8px">${items || `<div style="color:var(--text-faint);font-size:13px;text-align:center;padding:6px 0">${esc(profileT('readingsNone'))}</div>
        <button class="btn btn-primary" style="width:100%;margin-top:10px" data-act="chat-fn" data-chat="tarot" data-fn="featureTarot">${esc(profileT('firstCard'))}</button>`}</div>`);
  };

  // Полная натальная карта: скачивание красивого PDF-разбора (pdfgen).
  // Вместо маленького колёсного превью показываем готовый PDF-отчёт.

  app.openFullChart = async function() {
    try {
      const c = await api('/api/chart');
      if (!c || !(c.planets || []).length) {
        // Карты ещё нет — открываем сборщик карты вместо пустого PDF.
        this.openBuildChart();
        return;
      }
      this.toast('Готовим твой PDF-разбор… ✨');
      const blob = await apiBlob('/api/chart/pdf');
      this.downloadPdf(blob, 'oracle-natal-chart.pdf');
    } catch (e) {
      this.toast(friendlyError(e, 'PDF сейчас недоступен 🌙'));
    }
  };

  // Прямое скачивание PDF-файла (не картинки).
  app.downloadPdf = function(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = name || 'oracle-natal-chart.pdf';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    this.toast(oracleLang() === 'en' ? 'Your PDF report is saved ✨' : 'Твой PDF-разбор сохранён ✨');
  };

  // Если карта ещё не собрана — ведём пользователя в сборщик данных.
  app.openBuildChart = async function() {
    this.showModal(`<h3>${esc(profileT('fullChartTitle'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
      <div id="fc-body" style="margin-top:8px"><div class="loader-ring"></div></div>`);
    try {
      const c = await api('/api/chart');
      this.chart = c; // B2: для шаринга из полной карты
      const exactChart = c.precision === 'exact';
      const precisionNotice = !exactChart ? `<div class="chart-precision-note"><b>${esc(profileT('chartPrecision'))}</b><span>${esc(c.note || profileT('chartNoTimeShort'))}</span><small>${esc(profileT('chartPrecisionCopy'))}</small></div>` : '';
      const row = (ico, name, val) => `<div class="fc-row"><span class="fc-ico">${ico}</span><span class="fc-name">${esc(name)}</span><span class="fc-val">${val}</span></div>`;
      const pRows = (c.planets || []).map(p =>
        row(SIGNS[p.sign] || '•', p.name, `${esc(p.sign)} ${p.deg}°${exactChart && p.house ? ' · ' + profileT('house') + ' ' + p.house : ''}${p.retro ? ' ℞' : ''}`)).join('');
      const nRows = (c.nodes || []).map(n =>
        row('☊', n.name, `${esc(n.sign)} ${n.deg}°${exactChart && n.house ? ' · ' + profileT('house') + ' ' + n.house : ''}${n.retro ? ' ℞' : ''}`)).join('');
      const hRows = (c.houses || []).map(h =>
        row(`${h.n}`, `${h.n} ${profileT('house')}`, `${esc(h.sign)} ${h.deg}°`)).join('');
      const aRows = (c.aspects || []).slice(0, 12).map(a =>
        row(a.glyph || '◈', `${a.p1} — ${a.p2}`, `${a.aspect}${a.orb != null ? ' · ' + profileT('orb') + ' ' + a.orb + '°' : ''}`)).join('');
      document.getElementById('fc-body').innerHTML = `
        ${precisionNotice}
        ${this.chartProvenanceHtml(c)}
        <div class="fc-hero chart-engine-image-shell" style="margin-bottom:6px;display:flex;justify-content:center;align-items:center;background:rgba(14,13,30,.7);border-radius:var(--r-m);padding:10px;box-shadow:var(--sh-card);">
          ${this.chartImageHtml(c, 'full-chart-image', 'full')}
        </div>
        <div class="fc-card">
          <span class="fc-ico">☉</span>
          <div class="fc-card-body">
            <h4 class="fc-t">${esc(exactChart ? profileT('signAndRise') : profileT('solarFoundation'))}</h4>
            <div class="fc-desc"><b>${esc(profileT('sun'))} ${esc(c.sun && c.sun.sign || '')}</b> (${esc(c.sun && c.sun.element || '')}) — ${esc(profileT('signRiseCopy'))}${exactChart ? ` <b>${esc(profileFormat('ascendant', { sign: c.ascendant && c.ascendant.sign || '—' }))}</b> (${esc(c.ascendant && c.ascendant.deg ? Math.round(c.ascendant.deg) : '—')}°) — ${esc(profileT('ascendantCopy'))} <b>MC ${esc(c.mc && c.mc.sign || '—')}</b> — ${esc(profileT('mcCopy'))}` : ` ${esc(profileT('noTimeAssumptions'))}`}</div>
          </div>
        </div>
        <div class="fc-card">
          <span class="fc-ico">🌌</span>
          <div class="fc-card-body">
            <h4 class="fc-t">${esc(profileT('planets'))}</h4>
            <div class="fc-planets-grid">
              ${(c.planets || []).map(p => `
              <div class="fc-planet">
                <span class="pl-ico">${SIGNS[p.sign] || '•'}</span>
                <span class="pl-info"><span class="pl-t">${esc(p.name)} · ${esc(p.sign)}${exactChart && p.house ? ' · ' + esc(profileT('house')) + ' ' + p.house : ''}${p.retro ? ' ℞' : ''}</span><span class="pl-d">${p.deg ? p.deg + '°' : ''}</span></span>
              </div>`).join('')}
            </div>
          </div>
        </div>
        <div class="fc-card">
          <span class="fc-ico">☊</span>
          <div class="fc-card-body">
            <h4 class="fc-t">${esc(profileT('nodes'))}</h4>
            <div class="fc-planets-grid">
              ${(c.nodes || []).map(n => {
                const label = n.name && n.name.includes('Раху') ? profileT('rahu') : (n.name && n.name.includes('Кету') ? profileT('ketu') : n.name);
                return `<div class="fc-planet" style="min-width:190px;max-width:none">
                  <span class="pl-ico">☊</span>
                  <span class="pl-info"><span class="pl-t">${esc(n.sign)} ${n.deg}°${exactChart && n.house ? ' · ' + esc(profileT('house')) + ' ' + n.house : ''}${n.retro ? ' ℞' : ''}</span>
                  <span class="pl-d">${esc(label)}</span>
                </span>
                </div>`;
              }).join('')}
              ${(c.nodes || []).find(n => n.name && n.name.includes('Лилит')) ? `
              <div class="fc-planet" style="min-width:190px;max-width:none">
                <span class="pl-ico">⚫</span>
                <span class="pl-info"><span class="pl-t">${esc(profileT('lilith'))}</span>
                <span class="pl-d">${esc(profileT('lilithCopy'))}</span>
                </span>
              </div>` : ''}
            </div>
          </div>
        </div>
        <div class="fc-card">
          <span class="fc-ico">◈</span>
          <div class="fc-card-body">
            <h4 class="fc-t">${esc(profileT('aspects'))}</h4>
            <div style="font-size:11px;color:var(--text-faint);margin-bottom:6px">${esc(profileT('aspectsCopy'))}</div>
            <div class="asp-legend" style="margin-bottom:8px">
              <span class="asp-chip" style="color:var(--gold)">☌ ${esc(profileT('conjunction'))}</span><span class="asp-chip" style="color:var(--gold)">⚹ ${esc(profileT('sextile'))}</span><span class="asp-chip" style="color:var(--gold)">△ ${esc(profileT('trine'))}</span>
              <span class="asp-chip" style="color:var(--violet)">□ ${esc(profileT('square'))}</span><span class="asp-chip" style="color:#ff6b6b">☍ ${esc(profileT('opposition'))}</span>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:5px">
              ${(c.aspects || []).slice(0, 8).map(a => `
              <span class="chip" style="font-size:11.5px;padding:4px 8px">${esc(a.glyph || '◈')} <b>${esc(a.p1)} — ${esc(a.p2)}</b> · <em style="color:var(--text-faint)">${esc(a.aspect)}</em> · ${esc(profileT('orb'))} ${esc(a.orb != null ? a.orb + '°' : '')}</span>`).join('')}
            </div>
          </div>
        </div>
        ${exactChart ? `<div class="fc-card">
          <span class="fc-ico">🏠</span>
          <div class="fc-card-body">
            <h4 class="fc-t">${esc(profileT('houses'))}</h4>
            <div style="font-size:12px;color:var(--text-dim);line-height:1.55">
              ${(c.houses || []).map((h, i) => `<b style="color:var(--gold-bright)">${i + 1} ${esc(profileT('house'))} · ${esc(h.sign || '')}</b> ${h.deg ? h.deg + '°' : ''}${i < 11 ? ' · ' : ''}`).join('')}
            </div>
          </div>
        </div>` : ''}
        <button class="btn btn-primary" style="margin-top:14px" data-act="chat" data-chat="astro">${esc(profileT('askAstrologer'))}</button>
        <button class="btn btn-primary" style="width:100%;margin-top:8px" data-act="share-chart">${esc(profileT('shareChart'))}</button>
        <button class="btn btn-ghost" style="width:100%;margin-top:8px" data-act="fc-explain">${esc(profileT('simpleReading'))}</button>
        <div id="fc-explain" style="margin-top:12px"></div>`;
      this.hydrateChartImage(c, 'full-chart-image', 'full');
    } catch (e) {
      const body = document.getElementById('fc-body');
      if (body) body.innerHTML = this.softEmpty({
        icon: '🌌', eyebrow: profileT('fullChartTitle'), title: profileT('chartUnavailable'),
        copy: profileT('chartUnavailableCopy'), tone: 'recovery',
        action: `<button class="btn btn-ghost" data-act="modal-close">${esc(profileT('close'))}</button>`
      });
    }
  };

  // Разбор карты простыми словами: ИИ-объяснение по разделам (кэш на сервере).

  app.explainChart = async function() {
    const box = document.getElementById('fc-explain');
    if (!box) return;
    if (box.dataset.loaded) {
      box.style.display = box.style.display === 'none' ? 'block' : 'none';
      return;
    }
    box.innerHTML = '<div class="loader-ring" style="margin:10px auto"></div>';
    try {
      const r = await api('/api/chart/interpret', { method: 'POST' });
      box.dataset.loaded = '1';
      box.innerHTML = '<div class="glass fc-explain">' + richMd(r.text) + '</div>';
    } catch (e) {
      box.innerHTML = this.softEmpty({
        icon: '✦', eyebrow: profileT('chartReading'), title: profileT('chartReadingUnavailable'),
        copy: profileT('chartReadingUnavailableCopy'), tone: 'recovery'
      });
    }
  };

  app.openGender = function() {
    const current = (this.me && this.me.gender) || null;
    this.showModal(`<h3>${esc(t('gender'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
      <p class="modal-soft-copy">${esc(t('genderCopy'))}</p>
      <div class="language-picker gender-picker">
        <button class="language-choice ${current === 'f' ? 'active' : ''}" data-act="set-gender" data-gender="f"><b>${esc(t('female'))} ♀</b><small>${esc(t('femaleCopy'))}</small></button>
        <button class="language-choice ${current === 'm' ? 'active' : ''}" data-act="set-gender" data-gender="m"><b>${esc(t('male'))} ♂</b><small>${esc(t('maleCopy'))}</small></button>
        <button class="language-choice gender-choice--skip ${current === null ? 'active' : ''}" data-act="set-gender" data-gender=""><b>${esc(t('notSpecified'))}</b><small>${esc(t('notSpecifiedCopy'))}</small></button>
      </div>`);
  };

  app.setGender = async function(gender) {
    const next = ['f', 'm'].includes(gender) ? gender : null;
    const previous = (this.me && this.me.gender) || null;
    if (next === previous) { this.closeModal(); return; }
    haptic('light');
    try {
      await api('/api/profile', { method: 'PATCH', body: JSON.stringify({ gender: next }) });
      this.me = Object.assign({}, this.me, { gender: next });
      this.closeModal();
      this.go('profile');
      this.toast(t('saved'));
    } catch (e) { this.toast(friendlyError(e, 'Не удалось сохранить выбор. Попробуй ещё раз.')); }
  };

  app.openLanguage = function() {
    const current = (this.me && this.me.lang) || 'ru';
    this.showModal(`<h3>${esc(t('language'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
      <p class="modal-soft-copy">${esc(t('languageCopy'))}</p>
      <div class="language-picker">
        <button class="language-choice ${current === 'ru' ? 'active' : ''}" data-act="set-lang" data-lang="ru"><b>${esc(t('russian'))}</b><small>Русский</small></button>
        <button class="language-choice ${current === 'en' ? 'active' : ''}" data-act="set-lang" data-lang="en"><b>${esc(t('english'))}</b><small>English</small></button>
      </div>`);
  };

  app.setLanguage = async function(lang) {
    if (!['ru', 'en'].includes(lang)) return;
    const previous = (this.me && this.me.lang) || 'ru';
    if (lang === previous) { this.closeModal(); return; }
    try {
      await api('/api/profile', { method: 'POST', body: JSON.stringify({ lang }) });
      localStorage.setItem('oracle_lang', lang);
      try { document.documentElement.lang = lang; } catch (e) {}
      this.me = Object.assign({}, this.me, { lang });
      syncDocumentLocale();
      this.closeModal();
      if (typeof this.refreshPalmLocale === 'function') this.refreshPalmLocale();
      this.renderFrame();
      this.go(this.view || 'profile');
      this.toast(t('saved'));
    } catch (e) { this.toast(friendlyError(e, 'Не удалось сменить язык. Попробуй ещё раз.')); }
  };

  // панель уведомлений: прогноз дня + утреннее напоминание

  app.openBell = async function() {
    this.markBellSeen && this.markBellSeen();
    const en = oracleLang() === 'en';
    const bellTitle = en ? 'Notifications' : 'Уведомления';
    this.showModal(`<h3>${esc(bellTitle)}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
      <div id="bell-body" style="margin-top:8px"><div class="loader-ring"></div></div>`);
    try {
      if (!this.today) this.today = await api('/api/today');
      const t = this.today;
      const inbox = await api('/api/notifications?limit=20');
      const push = this.me && this.me.morning_push;
      const items = (inbox.items || []).map(item => `<article class="glass notification-item${item.read_at ? '' : ' notification-item--unread'}">
        <div class="notification-item__meta"><b>${esc(item.title || (en ? 'Notification' : 'Уведомление'))}</b><small>${esc(fmtDate(item.created_at || ''))}</small></div>
        <div class="notification-item__body">${esc(item.body || '')}</div>
      </article>`).join('');
      const inboxTitle = en ? 'Inbox' : 'Входящие';
      const empty = en ? 'Nothing new yet.' : 'Пока новых уведомлений нет.';
      const markRead = en ? 'Mark all as read' : 'Отметить всё прочитанным';
      document.getElementById('bell-body').innerHTML = `
        <div class="glass" style="padding:14px 16px">
          <div style="font-size:12px;color:var(--text-faint);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px">${en ? 'Today' : 'Сегодня'} · ${fmtDate()}</div>
          <div style="font-size:13.5px;line-height:1.6">${esc(t.forecast)}</div>
        </div>
        <div class="mem-row" style="margin-top:10px;align-items:center">
          <span class="mem-dot">🌅</span>
          <span class="mem-txt" style="flex:1">${en ? 'Morning forecast in Telegram' : 'Утренний прогноз в боте'}</span>
          <button class="btn btn-ghost notification-toggle" data-act="notifications-toggle" type="button">${push ? (en ? 'on' : 'вкл') : (en ? 'off' : 'выкл')}</button>
        </div>
        <div class="notification-inbox" aria-live="polite"><div class="section-kicker">${esc(inboxTitle)} · ${Number(inbox.unread_count || 0)}</div>${items || `<div class="notification-empty">${esc(empty)}</div>`}${inbox.unread_count ? `<button class="btn btn-ghost" data-act="notifications-read-all" type="button">${esc(markRead)}</button>` : ''}</div>
        <div style="color:var(--text-faint);font-size:11.5px;margin-top:10px">${en ? 'Only server-owned summaries appear here. Private chat text and provider payloads are excluded.' : 'Здесь показываются только серверные сводки. Тексты приватных чатов и payload провайдеров не включаются.'}</div>`;
    } catch (e) {
      const body = document.getElementById('bell-body');
      if (body) body.innerHTML = this.softEmpty({
        icon: '🌙', eyebrow: bellTitle, title: en ? 'Quiet for now' : 'Пока тихо',
        copy: en ? 'A new forecast or reminder will wait here.' : 'Когда появится новый прогноз или напоминание, оно будет ждать тебя здесь.', tone: 'quiet'
      });
    }
  };

  app.toggleMorningNotifications = async function() {
    const next = !(this.me && this.me.morning_push);
    try {
      const updated = await api('/api/notifications/preferences', { method: 'PATCH', body: JSON.stringify({ morning_forecast: next }) });
      this.me = Object.assign({}, this.me, { morning_push: !!updated.morning_forecast });
      await this.openBell();
    } catch (e) {
      this.toast(friendlyError(e, oracleLang() === 'en' ? 'Notification settings are temporarily unavailable.' : 'Настройки уведомлений временно недоступны.'));
    }
  };

  app.markNotificationsRead = async function() {
    try {
      await api('/api/notifications/read-all', { method: 'POST', body: '{}' });
      await this.openBell();
    } catch (e) {
      this.toast(friendlyError(e, oracleLang() === 'en' ? 'Notifications are temporarily unavailable.' : 'Уведомления временно недоступны.'));
    }
  };


  // A11y (BUS-133, A-5): единая точка фокус-менеджмента всех app-modal.
  // activeElement ДО создания оверлея — иначе триггер уже под overlay-контекстом.
  app.showModal = function(html, variant = '') {
    // Ревью BUS-133 (minor): trigger читаем ДО remove() старого модала — при каскадном
    // confirm поверх модала activeElement после remove() уже body.
    const trigger = document.activeElement;
    const old = document.getElementById('app-modal');
    if (old) old.remove();   // один модал за раз — без дублей id и наложений
    this._modalTrigger = trigger;
    const ov = document.createElement('div');
    ov.className = 'modal-overlay' + (variant === 'full' ? ' full' : '');
    ov.id = 'app-modal';
    ov.innerHTML = `<div class="modal${variant === 'full' ? ' full' : ''}" role="dialog" aria-modal="true" tabindex="-1">${html}</div>`;
    // aria-labelledby ставим только при найденном заголовке — ссылка на пустой id хуже её отсутствия
    const h3 = ov.querySelector('.modal > h3, .modal .picker-title, .modal .fb-title');
    if (h3) {
      if (!h3.id) h3.id = 'app-modal-title';
      ov.querySelector('.modal').setAttribute('aria-labelledby', h3.id);
    }
    ov.addEventListener('click', e => { if (e.target === ov) app.closeModal(); });
    document.body.appendChild(ov);
    // Фокус на первый интерактивный элемент (или на сам диалог, если разметка без контролов — picker rows и т.п.)
    const focusables = this.modalFocusables(ov.querySelector('.modal'));
    const first = focusables[0] || ov.querySelector('.modal');
    if (first) setTimeout(() => first.focus(), 0);
    if (typeof app.syncBackButton === 'function') app.syncBackButton();
  };

  // Интерактивные потомки диалога: ссылки и элементы с tabindex тоже участвуют в Tab-цикле.
  app.modalFocusables = function(root) {
    if (!root) return [];
    return Array.from(root.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
      .filter(el => el.offsetParent !== null || el === document.activeElement);
  };

  // A11y (BUS-133, A-3): активный диалог для Esc/Tab — app-modal или открытый te-sheet.
  app.activeDialog = function() {
    const modal = document.querySelector('#app-modal .modal');
    if (modal) return modal;
    const tool = document.getElementById('tool-expand');
    if (tool && tool.classList.contains('open')) return tool.querySelector('.te-sheet');
    return null;
  };

  // Цикл Tab/Shift+Tab внутри диалога; возвращает true, если событие поглощено.
  app.trapTabKey = function(dlg, event) {
    const focusables = this.modalFocusables(dlg);
    const active = document.activeElement;
    if (!focusables.length) {
      if (!dlg.contains(active)) { event.preventDefault(); dlg.focus(); }
      return true;
    }
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (event.shiftKey) {
      if (active === first || !dlg.contains(active)) { event.preventDefault(); last.focus(); return true; }
    } else if (active === last || !dlg.contains(active)) {
      event.preventDefault(); first.focus(); return true;
    }
    return false;
  };

  app.closeModal = function() {
    const el = document.getElementById('app-modal');
    const trigger = this._modalTrigger;
    this._modalTrigger = null;
    if (el) el.remove();
    // A11y (BUS-133, A-5): возврат фокуса на триггер — иначе SR/Tab остаются «в пустоте».
    if (trigger && document.contains(trigger) && typeof trigger.focus === 'function') trigger.focus();
    if (typeof app.syncBackButton === 'function') app.syncBackButton();
  };

  // FE-005/FE-007: деструктивные действия подтверждаются фирменным модалом,
  // а не системным window.confirm — тот блокирует фокус в Telegram WebView
  // и выглядит чужеродно. Колбэк живёт в app._confirmCb, кнопки — data-act.
  app.confirmAction = function(title, copy, confirmLabel, onYes) {
    this._confirmCb = typeof onYes === 'function' ? onYes : null;
    const cancel = oracleLang() === 'en' ? 'Cancel' : 'Отмена';
    this.showModal(`<h3>${esc(title)}</h3>
      <button class="m-close" data-act="modal-close" aria-label="${esc(profileT('closeAria'))}">✕</button>
      <div style="font-size:13.5px;line-height:1.6;margin:6px 0 14px;color:var(--text-soft)">${esc(copy)}</div>
      <div style="display:flex;gap:10px">
        <button class="btn btn-ghost" style="flex:1" type="button" data-act="confirm-no">${esc(cancel)}</button>
        <button class="btn btn-primary" style="flex:1" type="button" data-act="confirm-yes">${esc(confirmLabel)}</button>
      </div>`);
  };

