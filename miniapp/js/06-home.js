/* home: домашний экран + хаб */
  app.renderHome = function(main) {
    const t = this.today;
    const pulse = this.dailyPulse || {};
    const diary = pulse.diary || {};
    const prompt = pulse.prompt || {};
    const practices = (pulse.practices && pulse.practices.items) || [];
    const activePractice = practices.find(p => p.started && !p.finished) || practices.find(p => !p.finished) || null;
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
    const seasonal = homeT('seasonal')[seasonIndex];
    // Чип луны в hero: t.moon, иначе fallback на первую строку недели (§8 спеки).
    const moonChip = (t && t.moon) || (this.moonWeek && this.moonWeek[0]
      ? { name: this.moonWeek[0].name, day: this.moonWeek[0].day, emoji: this.moonWeek[0].emoji }
      : null);
    main.innerHTML = `
      <div class="screen">
        <section class="welcome-card" aria-label="${esc(homeT('ritualLabel'))}">
          <div class="welcome-card__top">
            <span class="welcome-card__kicker">${homeT('welcomeKicker')}</span>
            <span class="welcome-card__date">${fmtDate()}</span>
          </div>
          <div class="welcome-card__greeting">${welcomeName}</div>
          ${seasonalVariant === 'seasonal' ? `<p class="welcome-card__season-line">${seasonal[0]}</p>` : ''}
          ${moonChip ? `<div class="today-moon-chip">
            <span class="mc-ico mc-ico-sm" aria-hidden="true">${moonSvg(moonChip.emoji)}</span>
            <span class="today-moon-chip__txt">${esc(moonChip.name)} · ${homeFormat('lunarDay', { day: moonChip.day })}</span>
          </div>` : ''}
          <div class="hero-forecast">
            <div class="section-kicker" style="margin:0">${homeT('todaySign')}</div>
            ${t
              ? `<div class="forecast-flow forecast-clamped" id="hero-forecast-txt">${esc(t.forecast)}</div>
                 <button class="forecast-expand" type="button" data-act="forecast-expand" aria-expanded="false" aria-controls="hero-forecast-txt">${homeT('focusExpand')}<span class="mo-chev" aria-hidden="true">▾</span></button>`
              : t === null
                ? `<div class="forecast-flow"><div class="forecast-fallback"><b>${homeT('forecastFallbackTitle')}</b><span>${homeT('forecastFallbackCopy')}</span></div></div>`
                : `<div class="forecast-flow forecast-loading" aria-hidden="true"><span class="skeleton forecast-sk"></span><span class="skeleton forecast-sk"></span><span class="skeleton forecast-sk"></span></div>`}
          </div>
          <button class="ritual-cta" data-act="chat" data-chat="oracle" aria-label="${homeT('focusAskToday')}"><span>${homeT('focusAskToday')}</span><span aria-hidden="true">→</span></button>
          ${t && t.next_action && t.next_action.fn ? `
          <button class="hero-next-link" type="button" data-act="chat-fn" data-chat="${esc(t.next_action.chat || 'oracle')}" data-fn="${esc(t.next_action.fn)}">
            <span class="hero-next-prefix">${homeT('heroNextPrefix')}</span><span class="hero-next-title">${esc(t.next_action.title)}</span><span class="mo-chev" aria-hidden="true">›</span>
          </button>` : ''}
        </section>

        <div class="spacer"></div>
        <div class="home-acc" id="home-acc-ritual">
          <button class="home-acc-head" type="button" data-act="home-acc" aria-expanded="false" aria-controls="home-acc-ritual-body">
            <span class="home-acc-ico" aria-hidden="true">◌</span>
            <span class="home-acc-name">${homeT('rhythmTitle')}</span>
            ${ritualCompleted === 2
              ? '<span class="home-acc-badge home-acc-badge--done" aria-label="' + homeFormat('stepsAria', { count: 2 }) + '">✓✓</span>'
              : `<output class="home-acc-badge" aria-label="${homeFormat('stepsAria', { count: ritualCompleted })}">${ritualCompleted}<span>/2</span></output>`}
            <span class="mo-chev" aria-hidden="true">▾</span>
          </button>
          <div class="home-acc-body" id="home-acc-ritual-body" hidden>
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
          </div>
        </div>

        ${t && t.card ? `
        <div class="home-acc" id="home-acc-card">
          <button class="home-acc-head" type="button" data-act="home-acc" aria-expanded="false" aria-controls="home-acc-card-body">
            <img class="home-acc-thumb" src="/static/img/tarot/${esc(t.card.img || 'm00')}.jpg" alt="" width="32" height="32" loading="lazy" decoding="async">
            <span class="home-acc-name">${homeT('cardNearby')}</span>
            <span class="home-acc-badge">${esc(t.card.name)} · ${esc(toRoman(t.card.num))}</span>
            <span class="mo-chev" aria-hidden="true">▾</span>
          </button>
          <div class="home-acc-body" id="home-acc-card-body" hidden>
            <div class="card-day card-day-big">
              <button class="tarot-card-big" type="button" data-act="flip-card" aria-label="${homeT('flipCardAria')}">
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
              </button>
              <div style="flex:1;min-width:0">
                <div class="cd-name">${esc(t.card.name)}</div>
                <div class="cd-note">${homeT('cardCopy')}</div>
                <div class="cd-hint">${homeT('cardHint')}</div>
              </div>
            </div>
          </div>
        </div>` : ''}

        ${this.moonWeek && this.moonWeek[0] ? (() => {
          const wd = oracleLang() === 'en' ? WD_SHORT_EN : WD_SHORT;
          const mon = oracleLang() === 'en' ? MON_EN : MON_RU;
          const tv = t && t.moon ? { ...this.moonWeek[0], name: t.moon.name, day: t.moon.day, advice: t.moon.advice, emoji: t.moon.emoji } : this.moonWeek[0];
          const rows = this.moonWeek.map((d, i) => {
            const wdS = wd[d.weekday];
            const monS = mon[parseInt(d.date.slice(5, 7), 10) - 1] || '';
            const today = t && t.moon && d.day === t.moon.day;
            const formula = moonFormula(d);
            return `<div class="mc-day${today ? ' today' : ''}" data-i="${i}" data-act="moon-day">
              <div class="mc-row">
                <span class="mc-ico">${moonSvg(d.emoji)}</span>
                <span class="mc-main">
                  <span class="mc-wd">${wdS} · ${d.day_num} ${monS}${today ? ` <b>· ${homeT('today')}</b>` : ''}</span>
                  <span class="mc-nm">${esc(d.name)}${d.moon_sign && d.moon_sign.sign ? ` <span class="mc-sign">${esc(SIGNS[d.moon_sign.sign] || '')} ${esc(d.moon_sign.sign)}</span>` : ''}</span>
                  ${formula ? `<span class="mc-formula">${esc(formula)}</span>` : ''}
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
          return `<div class="home-acc" id="home-acc-moon">
            <button class="home-acc-head" type="button" data-act="home-acc" aria-expanded="false" aria-controls="home-acc-moon-body">
              <span class="mc-ico mc-ico-sm" aria-hidden="true">${moonSvg(tv.emoji)}</span>
              <span class="home-acc-name">${homeT('moonTitle')}</span>
              <span class="home-acc-badge">${esc(tv.name)} · ${homeT('accMoonBadge')}</span>
              <span class="mo-chev" aria-hidden="true">▾</span>
            </button>
            <div class="home-acc-body" id="home-acc-moon-body" hidden>
              <div class="moon-section">
                <div class="moon-today" data-act="moon-week">
                  <span class="mc-ico mc-ico-sm">${moonSvg(tv.emoji)}</span>
                  <div class="mt-main">
                    <div class="mt-name">${esc(tv.name)} · ${homeFormat('lunarDay', { day: tv.day })}</div>
                    ${(() => {
                      const f = moonFormula(tv);
                      return f ? `<div class="mt-formula">${esc(f)}</div><div class="mt-adv">${esc((tv.lunar_day && tv.lunar_day.path) || tv.advice)}</div>`
                               : `<div class="mt-adv">${esc(tv.advice)}</div>`;
                    })()}
                  </div>
                  <span class="mt-cta">${homeT('moonWeek')}<span class="mo-chev">›</span></span>
                </div>
                <!-- BUS-517: неделя сразу видна при открытии аккордеона (§6: 1 тап),
                     moon-today переключает свёрнутость строк-дней. -->
                <div class="moon-week show" id="moon-week">${rows}${note}</div>
              </div>
            </div>
          </div>`;
        })() : `
        <!-- BUS-649 Э7b: loading/error/empty по постановке. moonWeek===null — это
             загрузка или ошибка API; различаем по флагу, который ставит loadToday. -->
        ${(() => {
          const st = this.moonWeekState || (this.moonWeek === null ? 'loading' : 'empty');
          const headIco = '<span class="mc-ico mc-ico-sm" aria-hidden="true">' + moonSvg('🌑') + '</span>';
          const head = `<button class="home-acc-head" type="button" data-act="home-acc" aria-expanded="false" aria-controls="home-acc-moon-body">
              ${headIco}
              <span class="home-acc-name">${homeT('moonTitle')}</span>
              <span class="mo-chev" aria-hidden="true">▾</span>
            </button>
            <div class="home-acc-body" id="home-acc-moon-body" hidden>
              <div class="moon-section">${
                st === 'loading'
                  ? '<div class="moon-state moon-state--loading" role="status" aria-live="polite"><div class="loader-ring"></div></div>'
                  : st === 'error'
                    ? `<div class="moon-state moon-state--error"><div class="ms-ico">☾</div><div class="ms-txt">${esc(homeT('moonLoadError'))}</div></div>`
                    : `<div class="moon-state moon-state--empty"><div class="ms-ico">🌙</div><div class="ms-txt">${esc(homeT('moonEmpty'))}</div></div>`
              }</div>
            </div>`;
          return `<div class="home-acc" id="home-acc-moon">${head}</div>`;
        })()}`}
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
      <div class="screen guide-screen">
        <header class="hub-head">
          <span class="section-kicker">${oracleLang() === 'en' ? 'YOUR CONVERSATIONS' : 'ТВОИ РАЗГОВОРЫ'}</span>
          <h1>${oracleLang() === 'en' ? 'What is on your mind?' : 'О чём хочется поговорить?'}</h1>
          <p>${oracleLang() === 'en' ? 'Choose a guide. Start with a question, a thought, or what you feel.' : 'Выбери проводника. Начни с вопроса, мысли или того, что чувствуешь.'}</p>
        </header>
        <div class="observatory-guides">
          ${list.map((a, i) => `
            <button type="button" class="guide-entry ${i === 0 ? 'guide-entry--featured' : ''}" data-act="chat" data-chat="${esc(a.code)}">
              <img src="${['oracle', 'astro', 'tarot', 'chiromant'].includes(a.code) ? '/static/img/agents/' + a.code + '-photo.webp' : esc(a.avatar)}" alt="" width="190" height="220" decoding="async">
              <span class="guide-entry__copy">
                <span class="section-kicker">${esc(chatAgentField(a, 'title'))}</span>
                <strong>${esc(chatAgentField(a, 'name'))}</strong>
                <span>${esc(outcomes[a.code] || a.tagline || '')}</span>
                <span class="guide-entry__link">${oracleLang() === 'en' ? 'Open conversation' : 'Открыть разговор'} ↗</span>
                <span class="agent-proof-row">${(a.capabilities || []).map(c => `<span class="agent-proof-badge">${esc(c)}</span>`).join('')}</span>
              </span>
            </button>`).join('')}
        </div>
        <button class="btn btn-ghost guide-history" data-act="go" data-goto="sessions">${oracleLang() === 'en' ? 'Conversation history' : 'История разговоров'}</button>
      </div>`;
  };

  /* ═══ ЧАТ — ГЛАВНЫЙ ИНСТРУМЕНТ ═══ */
