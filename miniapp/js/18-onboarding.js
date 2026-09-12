/* BUS-1070 p1 R06: Welcome + Onboarding (S03 + S04).
 * Онбординг — 5 шагов: намерение → имя → дата → время → город → проверка.
 * Состояние в app.onboardingData; шаг хранится в data-ob-step на .onboarding.
 * E23: prefers-reduced-motion обрабатывается в CSS, JS не зависит от анимаций.
 */
(function () {
  'use strict';

  const ONB_STEPS = 5;
  const CITY_SUGGESTIONS = ['Казань', 'Караганда', 'Касабланка'];

  app.renderWelcome = function (main) {
    if (!main) return;
    const en = oracleLang() === 'en';
    document.querySelector('.app-nav').hidden = true;
    main.innerHTML = `
      <div class="screen" style="display:flex;align-items:center;justify-content:center;min-height:100%;text-align:center;padding:24px 20px">
        <div style="display:flex;flex-direction:column;align-items:center;gap:14px;max-width:320px">
          <span class="brand-mark" style="width:56px;height:56px;color:var(--color-accent)" aria-hidden="true">${sigilIcon('brand')}</span>
          <h1 style="color:var(--color-text-primary);font:700 26px/1.15 var(--font-display);margin:0">OracleAI</h1>
          <p style="color:var(--color-text-soft);font-size:var(--font-size-body);line-height:1.5;margin:0">${esc(en ? 'Your gentle daily ritual' : 'Твой мягкий ритуал дня')}</p>
          <button class="btn btn-primary" style="width:min(280px,100%);margin-top:8px" data-act="go" data-goto="onboarding">${esc(en ? 'Continue' : 'Продолжить')}</button>
        </div>
      </div>`;
    this.syncBackButton();
  };

  app.startOnboarding = function () {
    this.onboardingData = { intent: '', name: '', date: { day: '', month: '', year: '' }, time: '', timeKnown: null, city: '' };
    this.view = 'onboarding';
    this.syncBg();
    this.renderNav();
    this.syncBackButton();
    const main = document.getElementById('app-main');
    if (main) this.renderOnboarding(main, 1);
  };

  app.renderOnboarding = function (main, step) {
    if (!main) return;
    const isReview = step === 'review';
    const s = isReview ? ONB_STEPS + 1 : Number(step);
    if (isNaN(s) || s < 1 || s > ONB_STEPS + 1) return;

    const en = oracleLang() === 'en';
    const d = this.onboardingData || {};
    const stepLabel = isReview ? ONB_STEPS : s;
    const progressHtml = `<div class="seg-progress">
      <span>${esc(t('obStep', '').replace('{n}', stepLabel).replace('{m}', ONB_STEPS))}</span>
      <i class="${s > 1 && !isReview ? 'is-on' : ''}"></i>
      <span class="${isReview ? 'is-on' : ''}">${esc(t('obStep', '').replace('{n}', ONB_STEPS).replace('{m}', ONB_STEPS))}</span>
    </div>`;

    let bodyHtml = '';
    let title = '', copy = '', nextLabel = '';
    if (s === 1) {
      title = t('obIntentTitle'); copy = t('obIntentCopy'); nextLabel = t('obNext');
      bodyHtml = this._obStep1(d);
    } else if (s === 2) {
      title = t('obNameTitle'); copy = t('obNameCopy'); nextLabel = t('obNext');
      bodyHtml = this._obStep2(d);
    } else if (s === 3) {
      title = t('obDateTitle'); copy = t('obDateCopy'); nextLabel = t('obNext');
      bodyHtml = this._obStep3(d);
    } else if (s === 4) {
      title = t('obTimeTitle'); copy = t('obTimeCopy'); nextLabel = t('obNext');
      bodyHtml = this._obStep4(d);
    } else if (s === 5) {
      title = t('obCityTitle'); copy = t('obCityCopy'); nextLabel = t('obNext');
      bodyHtml = this._obStep5(d);
    } else {
      title = t('obReviewTitle'); copy = t('obReviewCopy'); nextLabel = t('obStart');
      bodyHtml = this._obReview(d);
    }

    const showBack = s > 1;
    main.innerHTML = `
      <div class="onboarding" data-ob-step="${isReview ? 'review' : s}">
        ${progressHtml}
        <div>
          <h2 class="onboarding__title">${esc(title)}</h2>
          <p class="onboarding__why">${esc(copy)}</p>
        </div>
        <div class="onboarding__step" ${isReview ? 'hidden' : ''}>
          ${bodyHtml}
        </div>
        ${isReview ? `<div>${bodyHtml}</div>` : ''}
        <div class="onboarding__footer" ${isReview ? 'hidden' : ''}>
          <p class="onboarding__footer-note--info" data-ob-error hidden role="alert" aria-live="polite"></p>
          <div style="display:flex;gap:8px">
            ${showBack ? `<button class="btn btn-ghost" style="flex:1" data-act="ob-back" type="button">${esc(t('obBack'))}</button>` : ''}
            <button class="btn btn-primary" style="flex:1" data-act="ob-next" type="button">${esc(nextLabel)}</button>
          </div>
        </div>
        ${isReview ? `
        <div class="onboarding__footer">
          <p class="onboarding__footer-note--info" data-ob-error hidden role="alert" aria-live="polite"></p>
          <div style="display:flex;gap:8px">
            <button class="btn btn-ghost" style="flex:1" data-act="ob-back" type="button">${esc(t('obBack'))}</button>
            <button class="btn btn-primary" style="flex:1" data-act="ob-next" type="button">${esc(t('obStart'))}</button>
          </div>
        </div>` : ''}
      </div>`;

    // фокус на первый управляемый элемент
    const focusTarget = main.querySelector('input:not([type="hidden"]), [data-intent], .combobox__input, [data-ob-jump]');
    if (focusTarget) setTimeout(() => focusTarget.focus(), 80);

    this.syncBackButton();
  };

  /* ── шаги онбординга ── */

  app._obStep1 = function (d) {
    const en = oracleLang() === 'en';
    const intents = [
      { code: 'oracle', icon: '🔮', name: en ? 'Conversation & Oracle' : 'Разговор и Оракул', hint: en ? 'Personal guidance and gentle questions' : 'Личные напоминания и бережные вопросы' },
      { code: 'astro', icon: '🌌', name: en ? 'Astrology & Natal chart' : 'Астрология и натальная карта', hint: en ? 'Planets, houses and birth map' : 'Планеты, дома и карта рождения' },
      { code: 'tarot', icon: '🃏', name: en ? 'Tarot readings' : 'Таро и расклады', hint: en ? 'Real Rider–Waite spreads in chat' : 'Настоящие расклады Райдера-Уэйта в чате' },
    ];
    return `<div style="display:flex;flex-direction:column;gap:8px" role="list" aria-label="${esc(t('obIntentTitle'))}">
      ${intents.map(i => `
        <button class="intent-card" type="button" role="listitem" data-intent="${i.code}" aria-label="${esc(i.name)}" aria-pressed="false">
          <span class="intent-card__icon" aria-hidden="true">${i.icon}</span>
          <span style="min-width:0;text-align:left">
            <span class="intent-card__name">${esc(i.name)}</span>
            <span class="intent-card__hint">${esc(i.hint)}</span>
          </span>
        </button>`).join('')}
    </div>`;
  };

  app._obStep2 = function (d) {
    const hint = d.name ? t('obNameHint') : '';
    return `<div style="display:flex;flex-direction:column;gap:6px">
      <label class="field__label" for="ob-name">${esc(t('obNameTitle'))}</label>
      <input class="field__input" id="ob-name" type="text" autocomplete="name" minlength="2" maxlength="60"
        value="${esc(d.name || '')}" placeholder="" aria-required="true" aria-invalid="false" aria-describedby="ob-name-hint ob-name-err">
      ${hint ? `<p class="field__hint" id="ob-name-hint">${esc(hint)}</p>` : ''}
      <p class="field__error" id="ob-name-err" hidden role="alert"><span aria-hidden="true">⚠</span><span></span></p>
    </div>`;
  };

  app._obStep3 = function (d) {
    const en = oracleLang() === 'en';
    const dd = d.date || {};
    return `<div style="display:flex;flex-direction:column;gap:6px">
      <label class="field__label">${esc(t('obDateTitle'))}</label>
      <p class="field__hint" style="margin-bottom:4px">${esc(t('obDateHint'))}</p>
      <div class="date-seg" role="group" aria-label="${en ? 'Day, month, year' : 'День, месяц, год'}">
        <div class="date-seg__seg date-seg__seg--day">
          <label class="field__label" for="ob-day">${en ? 'Day' : 'День'}</label>
          <input class="field__input" id="ob-day" type="number" min="1" max="31" inputmode="numeric" value="${esc(dd.day || '')}" aria-required="true">
        </div>
        <div class="date-seg__seg">
          <label class="field__label" for="ob-month">${en ? 'Month' : 'Месяц'}</label>
          <input class="field__input" id="ob-month" type="number" min="1" max="12" inputmode="numeric" value="${esc(dd.month || '')}" aria-required="true">
        </div>
        <div class="date-seg__seg date-seg__seg--year">
          <label class="field__label" for="ob-year">${en ? 'Year' : 'Год'}</label>
          <input class="field__input" id="ob-year" type="number" min="1900" max="${new Date().getFullYear()}" inputmode="numeric" value="${esc(dd.year || '')}" aria-required="true">
        </div>
      </div>
      <p class="field__error" data-ob-date-err hidden role="alert"><span aria-hidden="true">⚠</span><span>${esc(t('obDateError'))}</span></p>
    </div>`;
  };

  app._obStep4 = function (d) {
    const en = oracleLang() === 'en';
    const options = [
      { key: 'exact', label: t('obTimeExact'), note: t('obTimeExactNote'), showFields: true },
      { key: 'approx', label: t('obTimeApprox'), note: t('obTimeApproxNote'), showFields: true },
      { key: 'dontknow', label: t('obTimeDontKnow'), note: t('obTimeDontKnowNote'), showFields: false },
    ];
    const active = d.timeKnown || 'dontknow';
    const timeParts = (d.time || '').split(':');
    return `<div style="display:flex;flex-direction:column;gap:8px" role="radiogroup" aria-label="${esc(t('obTimeTitle'))}">
      <p style="color:var(--color-text-soft);font-size:var(--font-size-body);line-height:1.5;margin:0">${esc(t('obTimeCopy'))}</p>
      ${options.map(o => `
        <button class="choice-row" type="button" role="radio" aria-checked="${active === o.key}" data-time-choice="${o.key}" aria-pressed="${active === o.key}">
          <span style="min-width:0;text-align:left">
            <span style="color:var(--color-text-primary);font-weight:700;font-size:var(--font-size-body)">${esc(o.label)}</span>
            <span class="choice-row__note">${esc(o.note)}</span>
          </span>
          <span aria-hidden="true" style="flex:0 0 auto;color:var(--color-text-muted);font-size:13px">${active === o.key ? '✓' : ''}</span>
        </button>`).join('')}
      <div ${active !== 'dontknow' ? '' : 'hidden'} data-time-fields aria-label="${en ? 'Hours and minutes' : 'Часы и минуты'}" style="display:flex;gap:8px;margin-top:4px">
        <div style="flex:1;min-width:0">
          <label class="field__label" for="ob-hour">${en ? 'Hours' : 'Часы'}</label>
          <input class="field__input" id="ob-hour" type="number" min="0" max="23" inputmode="numeric" value="${esc(timeParts[0] || '')}" placeholder="0–23">
        </div>
        <div style="flex:1;min-width:0">
          <label class="field__label" for="ob-min">${en ? 'Minutes' : 'Минуты'}</label>
          <input class="field__input" id="ob-min" type="number" min="0" max="59" inputmode="numeric" value="${esc(timeParts[1] || '')}" placeholder="0–59">
        </div>
      </div>
    </div>`;
  };

  app._obStep5 = function (d) {
    const en = oracleLang() === 'en';
    return `<div class="combobox" style="display:flex;flex-direction:column;gap:6px" aria-expanded="false" aria-haspopup="listbox" aria-label="${esc(t('obCityTitle'))}">
      <label class="field__label" for="ob-city">${esc(t('obCityTitle'))}</label>
      <p class="field__hint" style="margin-bottom:2px">${esc(t('obCityCopy'))}</p>
      <input class="field__input combobox__input" id="ob-city" type="text" autocomplete="off" inputmode="text"
        value="${esc(d.city || '')}" placeholder="${esc(t('obCityPlaceholder'))}" aria-autocomplete="list" aria-controls="ob-city-list" role="combobox">
      <ul class="combobox__list" id="ob-city-list" role="listbox" style="display:none"></ul>
      <p class="combobox__status" data-ob-city-status hidden>${esc(t('obCityLoading'))}</p>
    </div>`;
  };

  app._obReview = function (d) {
    const en = oracleLang() === 'en';
    const dd = d.date || {};
    const dateStr = dd.day && dd.month && dd.year ? `${dd.day}.${dd.month}.${dd.year}` : (en ? 'not specified' : 'не указана');
    const timeStr = d.timeKnown === 'dontknow' ? (en ? 'unknown' : 'не знаю') : (d.time || (en ? 'not specified' : 'не указано'));
    const intentLabels = { oracle: en ? 'Conversation & Oracle' : 'Разговор и Оракул', astro: en ? 'Astrology & Natal chart' : 'Астрология и натальная карта', tarot: en ? 'Tarot readings' : 'Таро и расклады' };
    const nameLabel = t('obNameTitle').replace('?', '').replace('?', '').trim();
    return `<div style="display:flex;flex-direction:column;gap:8px" aria-label="${esc(t('obReviewTitle'))}">
      <div class="review-row">
        <span class="review-row__label">${esc(en ? 'Direction' : 'Направление')}</span>
        <span class="review-row__value">${esc(intentLabels[d.intent] || d.intent || '—')}</span>
        <button class="review-row__edit" type="button" data-ob-jump="1" aria-label="${esc(en ? 'Edit direction' : 'Изменить направление')}">✎</button>
      </div>
      <div class="review-row">
        <span class="review-row__label">${esc(nameLabel)}</span>
        <span class="review-row__value">${esc(d.name || '—')}</span>
        <button class="review-row__edit" type="button" data-ob-jump="2" aria-label="${esc(en ? 'Edit name' : 'Изменить имя')}">✎</button>
      </div>
      <div class="review-row">
        <span class="review-row__label">${esc(t('obDateTitle'))}</span>
        <span class="review-row__value">${esc(dateStr)}</span>
        <button class="review-row__edit" type="button" data-ob-jump="3" aria-label="${esc(en ? 'Edit date' : 'Изменить дату')}">✎</button>
      </div>
      <div class="review-row">
        <span class="review-row__label">${esc(t('obTimeTitle'))}</span>
        <span class="review-row__value">${esc(timeStr)}</span>
        <button class="review-row__edit" type="button" data-ob-jump="4" aria-label="${esc(en ? 'Edit time' : 'Изменить время')}">✎</button>
      </div>
      <div class="review-row">
        <span class="review-row__label">${esc(t('obCityTitle'))}</span>
        <span class="review-row__value">${esc(d.city || '—')}</span>
        <button class="review-row__edit" type="button" data-ob-jump="5" aria-label="${esc(en ? 'Edit city' : 'Изменить город')}">✎</button>
      </div>
    </div>`;
  };

  /* ── выбор намерения ── */

  app._obPickIntent = function (code) {
    this.onboardingData.intent = code;
    const cards = document.querySelectorAll('.intent-card[data-intent]');
    cards.forEach(function (c) { c.setAttribute('aria-pressed', c.dataset.intent === code ? 'true' : 'false'); });
    haptic('select');
  };

  /* ── валидации ── */

  app._obValidateStep = function (step) {
    const errEl = document.querySelector('[data-ob-error]');
    const showErr = (msg) => {
      if (!errEl) return false;
      errEl.hidden = false;
      const span = errEl.querySelector('span:last-child');
      if (span) span.textContent = msg;
      return false;
    };
    const clearErr = () => { if (errEl) errEl.hidden = true; };

    if (step === 2) {
      const name = (document.getElementById('ob-name')?.value || '').trim();
      if (name.length < 2) {
        const input = document.getElementById('ob-name');
        if (input) { input.setAttribute('aria-invalid', 'true'); input.focus(); }
        return showErr(t('obNameError'));
      }
      this.onboardingData.name = name;
      clearErr();
    }
    if (step === 3) {
      const day = parseInt(document.getElementById('ob-day')?.value, 10);
      const month = parseInt(document.getElementById('ob-month')?.value, 10);
      const year = parseInt(document.getElementById('ob-year')?.value, 10);
      if (!day || !month || !year) return showErr(t('obDateError'));
      const date = new Date(year, month - 1, day);
      if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
        return showErr(t('obDateError'));
      }
      this.onboardingData.date = { day: String(day), month: String(month), year: String(year) };
      clearErr();
    }
    if (step === 4) {
      const choice = document.querySelector('[data-time-choice][aria-pressed="true"]')?.dataset.timeChoice || 'dontknow';
      this.onboardingData.timeKnown = choice;
      if (choice !== 'dontknow') {
        const h = document.getElementById('ob-hour')?.value || '';
        const m = document.getElementById('ob-min')?.value || '';
        this.onboardingData.time = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      } else {
        this.onboardingData.time = '';
      }
    }
    if (step === 5) {
      const city = (document.getElementById('ob-city')?.value || '').trim();
      if (!city) return false;
      this.onboardingData.city = city;
    }
    return true;
  };

  app._obAdvance = function () {
    const container = document.querySelector('.onboarding');
    const currentStep = container ? (container.dataset.obStep === 'review' ? 'review' : Number(container.dataset.obStep)) : 1;

    if (currentStep === 'review') {
      this._obSubmit();
      return;
    }

    if (currentStep <= ONB_STEPS) {
      if (!this._obValidateStep(currentStep)) return;
    }

    if (currentStep < ONB_STEPS) {
      this.renderOnboarding(document.getElementById('app-main'), currentStep + 1);
    } else if (currentStep === ONB_STEPS) {
      this.renderOnboarding(document.getElementById('app-main'), 'review');
    }
  };

  app._obBack = function () {
    const container = document.querySelector('.onboarding');
    const currentStep = container ? (container.dataset.obStep === 'review' ? ONB_STEPS + 1 : Number(container.dataset.obStep)) : 1;

    if (currentStep === 'review' || currentStep > ONB_STEPS) {
      this.renderOnboarding(document.getElementById('app-main'), ONB_STEPS);
    } else if (currentStep > 1) {
      this.renderOnboarding(document.getElementById('app-main'), currentStep - 1);
    } else {
      this.go('home');
    }
  };

  app._obSubmit = function () {
    const d = this.onboardingData || {};
    const payload = {
      name: d.name || undefined,
      birth_date: (d.date && d.date.year && d.date.month && d.date.day)
        ? `${d.date.year}-${String(d.date.month).padStart(2, '0')}-${String(d.date.day).padStart(2, '0')}`
        : undefined,
      birth_time: d.time || undefined,
      birth_time_known: d.timeKnown === 'exact' ? 'exact' : d.timeKnown === 'approx' ? 'approx' : undefined,
      city: d.city || undefined,
      intent: d.intent || undefined,
    };
    api('/api/profile', { method: 'POST', body: JSON.stringify(payload) }).catch(() => {});
    // Локальный маркер пройденного онбординга: без него новичок без
    // ответа сервера увидит welcome повторно при следующем заходе.
    try { localStorage.setItem('oracle_onboarding_done', '1'); } catch (e) {}
    if (d.intent && d.intent !== 'oracle') {
      this.openChat(d.intent);
    } else {
      this.go('hub');
    }
    haptic('success');
  };

})();
