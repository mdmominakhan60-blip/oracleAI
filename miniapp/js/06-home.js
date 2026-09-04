/* home: домашний экран + хаб */
  app.renderHome = function(main) {
    const t = this.today;
    const pulse = this.dailyPulse || {};
    const diary = pulse.diary || {};
    const prompt = pulse.prompt || {};
    const practices = (pulse.practices && pulse.practices.items) || [];
    const activePractice = practices.find(p => p.started && !p.finished) || practices.find(p => !p.finished) || null;
    // Домашний экран должен оставаться полезным даже при временной недоступности API.
    const homeAgents = (this.agents.length ? this.agents : AGENT_FALLBACK)
      .map(a => this.normalizeAgent(a, a.code));
    const diaryDone = !!prompt.written_today;
    const ritualCompleted = (diaryDone ? 1 : 0) + (activePractice && activePractice.last_done ? 1 : 0);
    const ritualTone = ritualCompleted === 2
      ? (oracleLang() === 'en'
        ? 'Your ritual is complete for today. You can simply stay with that feeling.'
        : gendered(this.me, 'Ты уже выбрала себя сегодня. Можно просто побыть в этом ощущении.', 'Ты уже выбрал себя сегодня. Можно просто побыть в этом ощущении.', 'Сегодня ритуал уже завершён. Можно просто побыть в этом ощущении.'))
      : ritualCompleted === 1 ? homeT('ritualOneDone') : homeT('ritualNoneDone');
    const welcomeName = oracleLang() === 'en'
      ? (this.me && this.me.name ? `Glad you’re here, <em>${esc(this.me.name.split(' ')[0])}</em>.` : 'Glad you’re here.')
      : (this.me && this.me.name
        ? `${gendered(this.me, 'Рада видеть тебя', 'Рад видеть тебя', 'Рады видеть тебя')}, <em>${esc(this.me.name.split(' ')[0])}</em>.`
        : gendered(this.me, 'Рада, что ты здесь.', 'Рад, что ты здесь.', 'Рады, что ты здесь.'));
    const seasonalVariant = experimentVariant('home_ritual_entry', ['control', 'seasonal']);
    trackExperiment('home_ritual_entry', seasonalVariant);
    const seasonIndex = Math.floor(((new Date().getMonth() + 1) % 12) / 3);
    const seasonalMoments = homeT('seasonal').map(([title, copy]) => ({ title, copy }));
    const seasonal = seasonalMoments[seasonIndex];
    main.innerHTML = `
      <div class="screen">
        <section class="welcome-card" aria-label="${esc(homeT('ritualLabel'))}">
          <div class="welcome-card__top">
            <span class="welcome-card__kicker">${homeT('welcomeKicker')}</span>
            <span class="welcome-card__date">${fmtDate()}</span>
          </div>
          <div class="welcome-card__main">
            <div class="welcome-card__signal" aria-hidden="true"><span></span><i>✦</i></div>
            <div class="welcome-card__copy">
              <div class="welcome-card__greeting">${welcomeName}</div>
              <h1>${homeT('welcomeTitle')}</h1>
              <p>${homeT('welcomeCopy')}</p>
            </div>
          </div>
          <div class="welcome-card__prompt"><span class="welcome-card__prompt-mark" aria-hidden="true">↗</span><span>${homeT('welcomePrompt')}</span><span class="welcome-card__prompt-line" aria-hidden="true"></span></div>
          <button class="ritual-cta" data-act="chat" data-chat="oracle" aria-label="${homeT('ritualCta')}"><span>${homeT('ritualCta')}</span><span aria-hidden="true">→</span></button>
          ${seasonalVariant === 'seasonal' ? `<div class="welcome-card__season" aria-label="${homeT('seasonalAria')}"><span class="welcome-card__season-sigil" aria-hidden="true">✦</span><div><span>${homeT('seasonalKicker')}</span><b>${seasonal.title}</b><p>${seasonal.copy}</p></div></div>` : ''}
        </section>

        <section class="daily-ritual daily-ritual--${ritualCompleted === 2 ? 'complete' : ritualCompleted ? 'in-progress' : 'begin'}" aria-label="${homeT('rhythmAria')}">
          <div class="daily-ritual-head"><div><div class="section-kicker">${homeT('rhythmKicker')}</div><h2>${homeT('rhythmTitle')}</h2></div><output class="daily-ritual-score" aria-label="${homeFormat('stepsAria', { count: ritualCompleted })}">${ritualCompleted}<span>/2</span></output></div>
          <div class="daily-ritual-progress" aria-hidden="true"><i style="--ritual-progress:${ritualCompleted / 2}"></i></div>
          <p class="daily-ritual-status">${ritualTone}</p>
          <div class="daily-ritual-grid">
            <button class="daily-step ${diaryDone ? 'is-done' : ''}" data-act="chat-fn" data-chat="oracle" data-fn="featureDiary" aria-label="${homeT(diaryDone ? 'diaryDoneAria' : 'diaryOpenAria')}">
              <span class="daily-step-mark">${diaryDone ? '✓' : '◌'}</span><span class="daily-step-copy"><b>${homeT(diaryDone ? 'diaryDone' : 'diaryOpen')}</b><small>${diaryDone ? homeT('diaryDoneCopy') : esc(prompt.prompt || homeT('diaryPromptFallback'))}</small></span><span class="daily-step-arrow">›</span>
            </button>
            ${activePractice ? `<button class="daily-step ${activePractice.last_done ? 'is-done' : ''}" data-act="p-action" data-code="${esc(activePractice.code)}" data-a="${activePractice.started ? 'done' : 'start'}" aria-label="${homeT(activePractice.started ? 'practiceDoneAria' : 'practiceStartAria')}">
              <span class="daily-step-mark">${activePractice.last_done ? '✓' : esc(activePractice.emoji || '✦')}</span><span class="daily-step-copy"><b>${esc(activePractice.title)}</b><small>${esc(activePractice.started ? (activePractice.today_step || homeT('practiceStepFallback')) : (activePractice.goal || activePractice.about || homeT('practiceFallback')))}</small></span><span class="daily-step-arrow">›</span>
            </button>` : ''}
          </div>
          <p class="daily-ritual-note">${homeT('ritualNote')}</p>
        </section>

        ${this.moonWeek && this.moonWeek[0] ? (() => {
          const wd = oracleLang() === 'en' ? WD_SHORT_EN : WD_SHORT;
          const mon = oracleLang() === 'en' ? MON_EN : MON_RU;
          const tv = t && t.moon ? t.moon : { name: this.moonWeek[0].name, day: this.moonWeek[0].day, advice: this.moonWeek[0].advice, emoji: this.moonWeek[0].emoji };
          const tIdx = this.moonWeek.findIndex(d => d.day === tv.day);
          const rows = this.moonWeek.map((d, i) => {
            const wdS = wd[d.weekday];
            const monS = mon[parseInt(d.date.slice(5, 7), 10) - 1] || '';
            const today = t && t.moon && d.day === t.moon.day;
            return `<div class="mc-day${today ? ' today' : ''}" data-i="${i}" data-act="moon-day">
              <div class="mc-row">
                <span class="mc-ico">${moonSvg(d.emoji)}</span>
                <span class="mc-main">
                  <span class="mc-wd">${wdS} · ${d.day_num} ${monS}${today ? ` <b>· ${homeT('today')}</b>` : ''}</span>
                  <span class="mc-nm">${esc(d.name)} <em class="mc-ln">${homeFormat('lunarDay', { day: d.day })}</em></span>
                </span>
                <span class="mc-chev">▾</span>
              </div>
              <div class="mc-detail" hidden><div class="mc-adv">${esc(d.advice)}</div></div>
            </div>`;
          }).join('');
          const atEmoji = e => e && e.includes('🌕') ? (oracleLang() === 'en' ? 'Full moon' : 'Полнолуние') : e && e.includes('🌑') ? (oracleLang() === 'en' ? 'New moon' : 'Новолуние') : null;
          const key = this.moonWeek.find(d => atEmoji(d.emoji));
          const noteCopy = oracleLang() === 'en'
            ? { 'New moon': 'A good time to begin and set an intention.', 'Full moon': 'Energy is rising — strengthen what you have begun.' }
            : { 'Новолуние': 'Хорошее время начинать и загадывать.', 'Полнолуние': 'Энергия на подъёме — закрепляй начатое.' };
          const note = key ? `<div class="moon-note">${atEmoji(key.emoji)} — <b>${key.day_num} ${mon[Number(key.date.slice(5, 7), 10) - 1]}</b>. ${noteCopy[atEmoji(key.emoji)]}</div>` : '';
          return `<div class="spacer"></div>
            <div class="moon-section">
              <div class="moon-head">
                <div class="section-title" style="margin:0">${homeT('moonTitle')}</div>
                <button class="moon-toggle" data-act="moon-week"><span class="mt-lbl">${homeT('week')}</span><span class="mo-chev">▾</span></button>
              </div>
              <div class="moon-today" data-act="moon-week">
                <span class="mc-ico mc-ico-sm">${moonSvg(tv.emoji)}</span>
                <div class="mt-main">
                  <div class="mt-name">${esc(tv.name)} · ${homeFormat('lunarDay', { day: tv.day })}</div>
                  <div class="mt-adv">${esc(tv.advice)}</div>
                </div>
                <span class="mt-cta">${homeT('moonWeek')}<span class="mo-chev">›</span></span>
              </div>
              <div class="moon-week" id="moon-week">${rows}${note}</div>
            </div>`;
        })() : ''}

        <div class="spacer"></div>
        <div class="section-kicker">${homeT('personal')}</div>
        <div class="section-title">${homeT('todaySign')}</div>
        <div class="forecast-flow">
          ${t ? esc(t.forecast) : `<div class="forecast-fallback"><b>${homeT('forecastFallbackTitle')}</b><span>${homeT('forecastFallbackCopy')}</span></div>`}
        </div>

        ${t && t.card ? `
        <div class="spacer"></div>
        <div class="section-kicker">${homeT('daySymbol')}</div>
        <div class="section-title">${homeT('cardNearby')}</div>
        <div class="card-day card-day-big">
          <div class="tarot-card-big" data-act="flip-card" title="Перевернуть карту">
            <div class="tb-inner">
              <div class="tb-face tb-front" style="background-image:url('/static/img/tarot/${esc(t.card.img || 'm00')}.jpg')">
                <span class="tb-arc">${esc(toRoman(t.card.num))}</span>
              </div>
              <div class="tb-face tb-back">
                <span class="tb-arc tb-back-arc">${esc(toRoman(t.card.num))}</span>
                <span class="tb-mean">${esc(t.card.meaning)}</span>
                <span class="tb-hint2">✦</span>
              </div>
            </div>
          </div>
          <div style="flex:1;min-width:0">
            <div class="cd-name">${esc(t.card.name)}</div>
            <div class="cd-note">${homeT('cardCopy')}</div>
            <div class="cd-hint">${homeT('cardHint')}</div>
          </div>
        </div>` : ''}

        ${t && t.next_action && t.next_action.kind ? `
        <div class="spacer"></div>
        <div class="section-kicker">${homeT('nextKicker')}</div>
        <div class="section-title">${homeT('nextTitle')}</div>
        <div class="glass na-card">
          <span class="na-ico">${esc(t.next_action.emoji || '✨')}</span>
          <div class="na-body">
            <div class="na-title">${esc(t.next_action.title)}</div>
            <div class="na-text">${esc(t.next_action.text)}</div>
          </div>
          ${t.next_action.fn
            ? `<button class="btn btn-primary na-btn" data-act="chat-fn" data-chat="${esc(t.next_action.chat || 'oracle')}" data-fn="${esc(t.next_action.fn)}">${esc(t.next_action.cta)}</button>`
            : `<span class="na-empty">${esc(t.next_action.cta)}</span>`}
        </div>` : ''}

        <div class="spacer"></div>
        <div class="section-kicker">${homeT('chooseMood')}</div>
        <div class="section-title">${homeT('talkTo')}</div>
        <div class="dock-grid">
          ${homeAgents.map(a => `
                          <button class="dock-item dock-item--${esc(a.code)}" type="button" style="${this.agentThemeStyle(a, a.code)}" data-act="chat" data-chat="${a.code}" aria-label="${homeFormat('openChatAria', { name: esc(a.name) })}">

              <span class="dock-orb" style="${this.agentThemeStyle(a, a.code)}"><img class="dock-face" src="${esc(a.avatar || `/static/img/agents/${a.code}.jpg`)}" alt="" width="66" height="66" loading="lazy" decoding="async" onerror="this.onerror=null;this.src='/static/img/oracle-mark.png'"></span>
              <span class="dock-name">${esc(a.name.split(' ')[0])}</span>
              ${a.title ? `<span class="dock-role">${esc(a.title)}</span>` : ''}
            </button>`).join('')}
        </div>
        <div class="home-agent-note">${oracleLang() === 'en' ? 'Each guide sees your story in a different way. Begin with the voice that resonates today.' : 'Каждый проводник смотрит на твою историю по-своему. Начни с того, чей голос откликается сегодня.'}</div>
      </div>`;
  };

  /* ═══ ХАБ АГЕНТОВ ═══ */

  app.renderHub = function(main) {
    if (this.chat.key) return this.renderChat(main);
    const outcomes = {
      oracle: oracleLang() === 'en' ? 'Untangle one question' : 'Разобрать один вопрос',
      astro: oracleLang() === 'en' ? 'Map and rhythms' : 'Карта и ритмы',
      tarot: oracleLang() === 'en' ? 'A spread with context' : 'Расклад и контекст',
      chiromant: oracleLang() === 'en' ? 'Photo and observations' : 'Фото и наблюдения'
    };
    const list = (this.agents.length ? this.agents : [
      { code: 'oracle', name: 'Лилит', title: 'Личный Оракул', emoji: '🔮', accent: '#e8c56b' },
      { code: 'astro', name: 'Урания', title: 'Астролог', emoji: '🌌', accent: '#7fb4e8' },
      { code: 'tarot', name: 'Мадам Ленорман', title: 'Таролог', emoji: '🎴', accent: '#c58bd8' },
      { code: 'chiromant', name: 'Мира', title: 'Проводник ладони', emoji: '✋', accent: '#e2a45e', avatar: '/static/img/agents/chiromant.jpg' },
    ]).map(a => this.normalizeAgent(a, a.code));
    main.innerHTML = `
      <div class="screen">
        <div class="hub-head">
          <h1>${homeT('guidesTitle')}</h1>
          <p>${homeT('guidesCopy')}</p>
        </div>
        <div class="agent-list">
          ${list.map(a => `
            <div class="agent-card agent-card--${esc(a.code)} ${this.chat.key === a.code ? 'glow' : ''}" style="${this.agentThemeStyle(a, a.code)}" data-act="chat" data-chat="${a.code}">
              <div class="ac-top">
                <div class="agent-avatar">${agentSprite(a)}</div>
                <div style="flex:1;min-width:0">
                  <div class="ac-head">
                    <div class="agent-title">${esc(a.name)}</div>
                  </div>
                  <div class="agent-role">${esc(a.title || a.code)}</div>
                  <div class="agent-outcome">${esc(outcomes[a.code] || (oracleLang() === 'en' ? 'A gentle next step' : 'Бережный следующий шаг'))}</div>
                  <div class="agent-last">${esc(a.last_text || a.tagline || homeT('listening'))}</div>
                  <div class="agent-proof-row" role="group" aria-label="${homeT('profileQuality')}">
                    <span class="agent-proof-badge">✦ ${homeT('evidenceFirst')}</span>
                    ${(a.capabilities && a.capabilities.length) ? `<span class="agent-proof-count">${homeFormat('toolCount', { count: a.capabilities.length })}</span>` : ''}
                  </div>
                  <span class="online-label">${homeT('nearby')}</span>
                </div>
                <button class="btn btn-ghost" style="padding:7px 12px;font-size:12px" data-act="chat" data-chat="${a.code}" aria-label="${homeFormat('openChatAria', { name: esc(a.name) })}">${homeT('start')}</button>
              </div>
              ${(a.suggestions && a.suggestions.length) ? `
              <div class="agent-ask-chips">
                ${a.suggestions.slice(0, 3).map(s => `
                  <button type="button" class="ask-chip" data-act="ask" data-chat="${a.code}" data-q="${esc(s)}">${esc(s)}</button>`).join('')}
              </div>` : ''}
              <div class="section-kicker" style="margin:15px 0 7px;color:var(--ac)">${homeT('ask')}</div>
              <div class="agent-chips">
                ${(FEATURES[a.code] || []).slice(0, 4).map(f => `
                  <button class="tool" style="${this.agentThemeStyle(a, a.code)}" data-act="chat-fn" data-chat="${a.code}" data-fn="${f.h}" aria-label="${esc(f.t)}: ${esc(f.d || '')}">
                    <span class="tool-ico" aria-hidden="true">${sigilIcon(f.id)}</span>
                    <span class="tool-txt"><span class="tool-t">${esc(f.t)}</span>${f.d ? `<span class="tool-d">${esc(f.d)}</span>` : ''}</span>
                  </button>`).join('')}
              </div>
              ${a.code === 'astro' ? `<section class="vedic-surface" aria-label="${oracleLang() === 'en' ? 'Vedic capabilities' : 'Ведические возможности'}">
                <div class="vedic-surface__head"><div><div class="section-kicker">${oracleLang() === 'en' ? 'Vedic / Lahiri' : 'Ведическая · Лахири'}</div><h2>${oracleLang() === 'en' ? 'Calculated, then interpreted' : 'Сначала расчёт, потом смысл'}</h2></div><span class="vedic-proof">29 tools · evidence</span></div>
                <div class="vedic-grid">
                  <button class="vedic-card" data-act="chat-fn" data-chat="astro" data-fn="featureVedicChart"><b>☊</b><span>${oracleLang() === 'en' ? 'Kundli' : 'Кундали'}</span><small>${oracleLang() === 'en' ? 'Lahiri sidereal chart' : 'Сидерическая карта Лахири'}</small></button>
                  <button class="vedic-card" data-act="chat-fn" data-chat="astro" data-fn="featureVedicDasha"><b>◷</b><span>Vimshottari</span><small>${oracleLang() === 'en' ? 'Dasha timeline' : 'Таймлайн даша'}</small></button>
                  <button class="vedic-card" data-act="chat-fn" data-chat="astro" data-fn="featureVedicPanchang"><b>◐</b><span>Panchang</span><small>${oracleLang() === 'en' ? 'Tithi · Rahu Kaal' : 'Титхи · Раху-кала'}</small></button>
                  <button class="vedic-card" data-act="chat-fn" data-chat="astro" data-fn="featureVedicGuna"><b>∞</b><span>Guna Milan</span><small>${oracleLang() === 'en' ? 'Ashtakoot breakdown' : 'Разбор аштакуты'}</small></button>
                </div>
                <p class="vedic-surface__note">${oracleLang() === 'en' ? 'Tradition, time quality and limitations stay visible in every calculation.' : 'Традиция, точность времени и ограничения видны в каждом расчёте.'}</p>
              </section>` : ''}
            </div>`).join('')}
        </div>
      </div>`;
  };

  /* ═══ ЧАТ — ГЛАВНЫЙ ИНСТРУМЕНТ ═══ */

