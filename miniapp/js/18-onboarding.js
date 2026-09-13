/* BUS-1070 p1 R06: Welcome + Onboarding (S03 + S04).
 * Онбординг — 5 шагов: намерение → имя → дата → время → город → проверка.
 * Состояние в app.onboardingData; шаг хранится в data-ob-step на .onboarding.
 * E23: prefers-reduced-motion обрабатывается в CSS, JS не зависит от анимаций.
 */
(function () {
  'use strict';

  const ONB_STEPS = 5;

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
    const me = this.me || {};
    const [by = "", bm = "", bd = ""] = (me.birth_date || '').split('-');
    this.onboardingData = this.onboardingData || {
      intent: ['oracle', 'astro', 'tarot', 'chiromant'].includes(me.intent || me.goal) ? (me.intent || me.goal) : '',
      name: me.name || '',
      date: { day: bd, month: bm, year: by },
      time: me.birth_time || '',
      timeKnown: me.birth_time_precision === 'unknown' ? 'dontknow' : (me.birth_time_precision || (me.birth_time ? 'exact' : 'dontknow')),
      city: me.birth_city || '',
      cityKey: '',
    };
    this.view = 'onboarding';
    this.syncBg();
    this.renderNav();
    this.syncBackButton();
    const main = document.getElementById('app-main');
    const resume = { intent: 1, goal: 1, language: 1, name: 2, gender: 3, date: 3, time: 4, city: 5, confirm: 5, technique: 5, persona: 5 }[me.onboarding_step] || 1;
    if (main) this.renderOnboarding(main, me.onboarded === false ? resume : 1);
  };

  app.renderOnboarding = function (main, step) {
    if (!main || this._obSaving) return;
    this._obCityRequest = (this._obCityRequest || 0) + 1;
    clearTimeout(this._obCityTimer);
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
        <div class="onboarding__step">${bodyHtml}</div>
        <div class="onboarding__footer">
          <p class="onboarding__footer-note--info" data-ob-error hidden role="alert" aria-live="polite"></p>
          <div style="display:flex;gap:8px">
            ${showBack ? `<button class="btn btn-ghost" style="flex:1" data-act="ob-back" type="button">${esc(t('obBack'))}</button>` : ''}
            <button class="btn btn-primary" style="flex:1" data-act="ob-next" type="button">${esc(nextLabel)}</button>
          </div>
        </div>
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
        <button class="intent-card" type="button" data-intent="${i.code}" aria-label="${esc(i.name)}" aria-pressed="${d.intent === i.code}">
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
    const now = new Date();
    const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    const value = dd.year && dd.month && dd.day ? `${dd.year}-${String(dd.month).padStart(2, '0')}-${String(dd.day).padStart(2, '0')}` : '';
    return `<div style="display:flex;flex-direction:column;gap:6px">
      <label class="field__label" for="ob-date-picker">${en ? 'Choose a date or enter it below' : 'Выбери дату или введи ниже'}</label>
      <input class="field__input" id="ob-date-picker" type="date" min="1900-01-01" max="${today}" value="${esc(value)}">
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
        value="${esc(d.city || '')}" maxlength="60" placeholder="${esc(t('obCityPlaceholder'))}" aria-autocomplete="list" aria-expanded="false" aria-controls="ob-city-list" aria-describedby="ob-city-status" role="combobox">
      <ul class="combobox__list" id="ob-city-list" role="listbox" style="display:none"></ul>
      <p class="combobox__status" id="ob-city-status" data-ob-city-status role="status">${esc(d.cityKey ? (en ? 'Confirmed: ' : 'Выбран: ') + [d.city, d.cityDetail].filter(Boolean).join(', ') : (en ? 'Type at least 2 characters and select a result.' : 'Введи от 2 букв и выбери город из списка.'))}</p>
      <button class="btn btn-ghost" type="button" data-ob-city-search>${en ? 'Find / change city' : 'Найти / изменить город'}</button>
      <button class="btn btn-ghost" type="button" data-ob-city-retry hidden>${en ? 'Retry search' : 'Повторить поиск'}</button>
    </div>`;
  };

  app._obReview = function (d) {
    const en = oracleLang() === 'en';
    const dd = d.date || {};
    const dateStr = dd.day && dd.month && dd.year ? `${dd.day}.${dd.month}.${dd.year}` : (en ? 'not specified' : 'не указана');
    const timeStr = d.timeKnown === 'dontknow' ? (en ? 'unknown' : 'не знаю') : (d.time || (en ? 'not specified' : 'не указано')) + (d.timeKnown === 'approx' ? (en ? ' · approximate' : ' · примерно') : (en ? ' · exact' : ' · точно'));
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
      errEl.textContent = msg;
      return false;
    };
    const clearErr = () => { if (errEl) errEl.hidden = true; };

    if (step === 1 && !this.onboardingData.intent) return showErr(t('obIntentTitle'));
    if (step === 2) {
      const name = (document.getElementById('ob-name')?.value || '').trim();
      if (name.length < 2 || name.length > 60) {
        const input = document.getElementById('ob-name');
        if (input) { input.setAttribute('aria-invalid', 'true'); input.focus(); }
        return showErr(t('obNameError'));
      }
      this.onboardingData.name = name;
      document.getElementById('ob-name')?.setAttribute('aria-invalid', 'false');
      clearErr();
    }
    if (step === 3) {
      const day = Number(document.getElementById('ob-day')?.value);
      const month = Number(document.getElementById('ob-month')?.value);
      const year = Number(document.getElementById('ob-year')?.value);
      if (!day || !month || !year) return showErr(t('obDateError'));
      const date = new Date(year, month - 1, day);
      if (year < 1900 || date > new Date() || date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
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
        if (!/^\d{1,2}$/.test(h) || !/^\d{1,2}$/.test(m) || Number(h) > 23 || Number(m) > 59) {
          return showErr(oracleLang() === 'en' ? 'Enter hours (0–23) and minutes (0–59), or choose unknown.' : 'Укажи часы (0–23) и минуты (0–59) или выбери «Не знаю».');
        }
        this.onboardingData.time = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
      } else {
        this.onboardingData.time = '';
      }
    }
    if (step === 5) {
      const city = (document.getElementById('ob-city')?.value || '').trim();
      if (!city || !this.onboardingData.cityKey || city !== this.onboardingData.city) {
        const input = document.getElementById('ob-city');
        if (input) { input.setAttribute('aria-invalid', 'true'); input.focus(); }
        return showErr(t('obCityError'));
      }
      this.onboardingData.city = city;
      clearErr();
    }
    return true;
  };

  app._obAdvance = function () {
    if (this._obSaving) return;
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
    if (this._obSaving) return;
    this._obCaptureDraft();
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

  app._obSubmit = async function () {
    if (this._obSaving) return;
    const d = this.onboardingData || {};
    // Bot steps can arrive out of order; never submit an incomplete resume.
    const dd = d.date || {};
    const missing = !d.intent ? 1 : !d.name || d.name.trim().length < 2 ? 2 : !dd.year || !dd.month || !dd.day ? 3 : !d.cityKey ? 5 : null;
    if (missing) {
      this.renderOnboarding(document.getElementById('app-main'), missing);
      return;
    }
    const payload = {
      name: d.name || undefined,
      birth_date: (d.date && d.date.year && d.date.month && d.date.day)
        ? `${d.date.year}-${String(d.date.month).padStart(2, '0')}-${String(d.date.day).padStart(2, '0')}`
        : undefined,
      birth_time: d.timeKnown === 'dontknow' ? null : (d.time || undefined),
      birth_time_precision: d.timeKnown === 'dontknow' ? 'unknown' : d.timeKnown,
      city: d.cityKey || undefined,
      intent: d.intent || undefined,
      onboarding_complete: true,
    };
    this._obSaving = true;
    const container = document.querySelector('.onboarding');
    const buttons = container ? [...container.querySelectorAll('button')] : [];
    const next = container?.querySelector('[data-act="ob-next"]');
    const error = container?.querySelector('[data-ob-error]');
    if (error) error.hidden = true;
    buttons.forEach(button => { button.disabled = true; });
    container?.setAttribute('aria-busy', 'true');
    if (next) next.textContent = oracleLang() === 'en' ? 'Saving…' : 'Сохраняем…';
    try {
      await api('/api/profile', { method: 'POST', body: JSON.stringify(payload) });
    } catch (e) {
      if (error) { error.hidden = false; error.textContent = oracleLang() === 'en' ? 'Could not save. Your entries are kept. Please retry.' : 'Не удалось сохранить. Данные остались в форме. Попробуй ещё раз.'; }
      return;
    } finally {
      this._obSaving = false;
      container?.removeAttribute('aria-busy');
      buttons.forEach(button => { button.disabled = false; });
      if (next) next.textContent = oracleLang() === 'en' ? 'Retry' : 'Повторить';
    }
    this.me = { ...this.me, ...payload, birth_city: d.city, onboarded: true, onboarding_step: null };
    this.onboardingData = null;
    if (d.intent && d.intent !== 'oracle') {
      this.openChat(d.intent);
    } else {
      this.go('hub');
    }
    haptic('success');
  };

  app._obCaptureDraft = function () {
    const d = this.onboardingData;
    if (!d) return;
    const value = id => document.getElementById(id)?.value;
    if (value('ob-name') !== undefined) d.name = value('ob-name');
    if (value('ob-day') !== undefined) d.date = { day: value('ob-day'), month: value('ob-month'), year: value('ob-year') };
    if (value('ob-hour') !== undefined) d.time = `${value('ob-hour')}:${value('ob-min')}`;
  };

  app._obSearchCity = async function (input) {
    const request = this._obCityRequest = (this._obCityRequest || 0) + 1;
    const q = input.value.trim();
    const list = document.getElementById('ob-city-list');
    const status = document.querySelector('[data-ob-city-status]');
    const retry = document.querySelector('[data-ob-city-retry]');
    if (!list || !status) return;
    const en = oracleLang() === 'en';
    this.onboardingData.city = q;
    this.onboardingData.cityKey = '';
    this.onboardingData.cityDetail = '';
    this._obCities = [];
    this._obCityIndex = -1;
    list.style.display = 'none';
    list.innerHTML = '';
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    retry.hidden = true;
    status.hidden = false;
    status.textContent = q.length < 2 ? (en ? 'Type at least 2 characters.' : 'Введи минимум 2 буквы.') : t('obCityLoading');
    if (q.length < 2) return;
    try {
      const result = await api('/api/city/suggest?q=' + encodeURIComponent(q));
      if (request !== this._obCityRequest || !input.isConnected) return;
      this._obCities = (result.items || []).filter(city => city.key && city.label);
      list.innerHTML = this._obCities.map((city, i) => `<li class="combobox__option" id="ob-city-option-${i}" role="option" data-city-pick="${i}" aria-selected="false"><span>${esc(city.label)}</span><small>${esc(city.detail || city.country || '')}</small></li>`).join('');
      list.style.display = this._obCities.length ? 'block' : 'none';
      input.setAttribute('aria-expanded', String(!!this._obCities.length));
      status.textContent = this._obCities.length ? (en ? 'Select your city.' : 'Выбери свой город.') : (en ? 'No cities found. Try another spelling.' : 'Город не найден. Попробуй другое написание.');
    } catch (e) {
      if (request !== this._obCityRequest || !input.isConnected) return;
      status.textContent = en ? 'Search failed. Please retry.' : 'Не удалось найти город. Повтори поиск.';
      retry.hidden = false;
    }
  };

  app._obSelectCity = function (index) {
    const city = this._obCities?.[index];
    const input = document.getElementById('ob-city');
    if (!city || !input) return;
    this._obCityRequest++;
    this.onboardingData.city = city.label;
    this.onboardingData.cityKey = city.key;
    this.onboardingData.cityDetail = city.detail || city.country || '';
    input.value = city.label;
    input.setAttribute('aria-invalid', 'false');
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    document.getElementById('ob-city-list').style.display = 'none';
    document.querySelector('[data-ob-city-status]').textContent = (oracleLang() === 'en' ? 'Confirmed: ' : 'Выбран: ') + [city.label, city.detail || city.country].filter(Boolean).join(', ');
    input.focus();
  };

})();
