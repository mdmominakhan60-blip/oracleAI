/* day-7 опрос (BUS-240): форма 5 вопросов, submit, благодарность, opt-out.
 *
 * Источник строк: seed content_items BUS-234 + канон BUS-179 §3.
 * В miniapp строки не дублируются в UI — единый FB_I18N на модуль.
 * При появлении /api/copy эндпоинта заменяется на fetch — логика не меняется.
 */

(function () {
  'use strict';

  const FB_I18N = {
    ru: {
      head: 'Неделя с Оракулом 🌙',
      intro: 'Пять коротких вопросов. За развёрнутый отзыв — 40 кристаллов ✦ на баланс (хватит на глубокий расклад Таро). Действуют 90 дней.',
      hint: 'Пара предложений — и 40 кристаллов твои ✦ (от 50 символов)',
      skip: 'Пропустить',
      other: 'Другое…',
      otherPlaceholder: 'Свой вариант…',
      submit: 'Отправить',
      sending: 'Отправляю…',
      thanksBonus: 'Спасибо, что рассказала! ✨\n40 кристаллов уже на твоём балансе — хватит на глубокий расклад Таро.',
      thanksSaved: 'Спасибо, твой отзыв сохранён 🌙',
      back: 'Вернуться к Оракулу',
      error: 'Не удалось отправить. Попробуй ещё раз.',
      q_like: 'Что зацепило больше всего?',
      q_blocker: 'Что мешает пользоваться?',
      q_nps: 'Насколько вероятно, что ты порекомендуешь Оракула подруге (0–10)?',
      q_dream: 'Чего не хватает? О чём мечтаешь, когда думаешь про Оракула?',
      q_next: 'Что добавить в первую очередь?',
      ariaStep: 'Шаг 1 из 5: опрос «Неделя с Оракулом»',
      ariaStepName: 'Шаг {n} из {m}',
    },
    en: {
      head: 'A Week with Oracle 🌙',
      intro: 'Five short questions. For a thoughtful review — 40 Crystals ✦ to your balance (enough for an in-depth Tarot reading). Valid for 90 days.',
      hint: 'A couple of sentences — and 40 Crystals are yours ✦ (50+ characters)',
      skip: 'Skip',
      other: 'Other…',
      otherPlaceholder: 'Your own variant…',
      submit: 'Submit',
      sending: 'Sending…',
      thanksBonus: 'Thank you for sharing! ✨\n40 Crystals are already on your balance — enough for an in-depth Tarot reading.',
      thanksSaved: 'Thank you — your review is saved 🌙',
      back: 'Back to Oracle',
      error: 'Could not send. Please try again.',
      q_like: 'What did you enjoy most?',
      q_blocker: 'What gets in the way?',
      q_nps: 'How likely are you to recommend Oracle to a friend (0–10)?',
      q_dream: 'What\'s missing? What do you dream of when you think of Oracle?',
      q_next: 'What should we add first?',
      ariaStep: 'Step 1 of 5: Week with Oracle survey',
      ariaStepName: 'Step {n} of {m}',
    }
  };

  const FB_CHOICES = {
    ru: {
      like: [
        { code: 'forecasts', label: 'Прогнозы' },
        { code: 'tarot', label: 'Таро' },
        { code: 'diary', label: 'Дневник и практики' },
        { code: 'voice', label: 'Голос и ответы' },
        { code: 'chart', label: 'Астрокарта' },
      ],
      blocker: [
        { code: 'offtopic', label: 'Ответы не по делу' },
        { code: 'slow', label: 'Долго ждать' },
        { code: 'paywall', label: 'Мало бесплатного' },
        { code: 'lost', label: 'Непонятно, что дальше' },
        { code: 'nothing', label: 'Ничего не мешает' },
        { code: 'other', label: 'Другое…' },
      ],
      next: [
        { code: 'compat', label: 'Совместимость' },
        { code: 'practices', label: 'Больше практик' },
        { code: 'lunar', label: 'Лунный ритм' },
        { code: 'personal', label: 'Персональные советы' },
        { code: 'other', label: 'Другое…' },
      ],
    },
    en: {
      like: [
        { code: 'forecasts', label: 'Forecasts' },
        { code: 'tarot', label: 'Tarot' },
        { code: 'diary', label: 'Diary & practices' },
        { code: 'voice', label: 'Voice & answers' },
        { code: 'chart', label: 'Birth chart' },
      ],
      blocker: [
        { code: 'offtopic', label: 'Answers miss the mark' },
        { code: 'slow', label: 'Too long a wait' },
        { code: 'paywall', label: 'Too little for free' },
        { code: 'lost', label: 'Unclear what comes next' },
        { code: 'nothing', label: 'Nothing gets in the way' },
        { code: 'other', label: 'Other…' },
      ],
      next: [
        { code: 'compat', label: 'Compatibility' },
        { code: 'practices', label: 'More practices' },
        { code: 'lunar', label: 'Lunar rhythm' },
        { code: 'personal', label: 'Personal guidance' },
        { code: 'other', label: 'Other…' },
      ],
    }
  };

  const FB_QUESTIONS = ['like', 'blocker', 'nps', 'dream', 'next'];

  // язык читаем на момент рендера, а не загрузки модуля: me.lang приходит
  // из /api/me уже после script-загрузки
  const langKey = () => (oracleLang() === 'en' ? 'en' : 'ru');
  function fb(key) { return FB_I18N[langKey()][key] || key; }
  function fbFormat(key, vars) { return fb(key).replace(/\{(\w+)\}/g, (_, k) => vars[k] !== undefined ? vars[k] : `{${k}}`); }
  // ── state ──────────────────────────────────────────────────────────

  app._surveyOpen = false;
  app._surveyStep = 0;
  app._surveyAnswers = {};
  app._surveyBusy = false;

  // ── open / close ──────────────────────────────────────────────────

  app.openSurvey = function () {
    if (this._surveyOpen) return;
    this._surveyOpen = true;
    this._surveyStep = 0;
    this._surveyAnswers = {};
    this._surveyBusy = false;
    haptic('soft');
    this.renderSurvey();
  };

  app.closeSurvey = function () {
    this._surveyOpen = false;
    this._surveyStep = 0;
    this._surveyAnswers = {};
    this._surveyBusy = false;
    this.closeModal();
    if (typeof this.syncBackButton === 'function') this.syncBackButton();
  };

  // ── render ────────────────────────────────────────────────────────

  app.renderSurvey = function () {
    if (this._surveyStep >= FB_QUESTIONS.length) {
      this.renderThanks();
      return;
    }
    const code = FB_QUESTIONS[this._surveyStep];
    const html = this.surveyStepHtml(code);
    this.showModal(html, 'full');
    if (typeof this.syncBackButton === 'function') this.syncBackButton();
    // back-button → закрыть форму (не Esc — модал сам обрабатывает)
    if (!this._surveyBackHandler) {
      this._surveyBackHandler = () => { if (app._surveyOpen) app.closeSurvey(); };
      if (tg() && tg().BackButton) {
        tg().BackButton.onClick(this._surveyBackHandler);
        tg().BackButton.show();
      }
    }
  };

  app.surveyStepHtml = function (code) {
    const i = this._surveyStep;
    const prev = i > 0 ? FB_QUESTIONS[i - 1] : null;
    const saved = this._surveyAnswers[code];
    const choices = FB_CHOICES[langKey()][code];
    const isNps = code === 'nps';
    const isText = code === 'dream';
    const isOther = saved && saved.choice === 'other';

    let body = '';

    if (isNps) {
      body = `<div class="fb-nps" role="radiogroup" aria-label="${esc(fb('q_' + code))}">` +
        Array.from({length: 11}, (_, n) =>
          `<button type="button" class="fb-nps-btn${saved && saved.score === n ? ' active' : ''}"
                    data-act="survey-choice" data-code="${code}" data-score="${n}"
                    aria-pressed="${saved && saved.score === n}">${n}</button>`
        ).join('') + '</div>' +
        `<div class="fb-nps-labels"><span>0</span><span>10</span></div>`;
    } else if (isText) {
      body = `<textarea class="fb-text" id="fb-dream-text" rows="4" maxlength="4000"
                    placeholder="${esc(fb('q_' + code))}" aria-label="${esc(fb('q_' + code))}">${esc(saved && saved.text || '')}</textarea>` +
        `<p class="fb-hint">${esc(fb('hint'))}</p>`;
    } else if (choices) {
      body = '<div class="fb-choices">' +
        choices.map(c =>
          `<button type="button" class="fb-choice-btn${saved && saved.choice === c.code ? ' active' : ''}"
                    data-act="survey-choice" data-code="${code}" data-choice="${c.code}">${esc(c.label)}</button>`
        ).join('') + '</div>';
      if (isOther || (saved && saved.choice === 'other')) {
        body += `<textarea class="fb-text fb-other-text" id="fb-other-text" rows="2" maxlength="4000"
                      placeholder="${esc(fb('otherPlaceholder'))}" aria-label="${esc(fb('other'))}">${esc(saved && saved.text || '')}</textarea>`;
      }
    }

    const skipBtn = isText
      ? `<button type="button" class="btn btn-ghost fb-skip" data-act="survey-skip">${esc(fb('skip'))}</button>`
      : '';

    return `
      <div class="fb-header">
        <h3 class="fb-title">${esc(fb('head'))}</h3>
        <div class="seg-progress fb-progress" role="group" aria-label="${esc(fbFormat('ariaStepName', { n: i + 1, m: FB_QUESTIONS.length }))}">
          ${FB_QUESTIONS.map((_, k) => `<i${k <= i ? ' class="is-on"' : ''}></i>`).join('')}
        </div>
      </div>
      ${i === 0 ? `<p class="fb-step-intro">${esc(fb('intro'))}</p>` : ''}
      <p class="fb-step-q">${esc(fb('q_' + code))}</p>
      <div class="fb-body">${body}</div>
      <div class="fb-actions">
        ${prev ? `<button type="button" class="btn btn-ghost" data-act="survey-back">←</button>` : '<span></span>'}
        ${skipBtn}
        <button type="button" class="btn btn-primary fb-next" data-act="survey-next"
                ${(!saved && !isText) ? 'disabled' : ''}>${esc(i === FB_QUESTIONS.length - 1 ? fb('submit') : '→')}</button>
      </div>`;
  };

  app.renderThanks = function () {
    // благодарность — закрывается только кнопкой, back-button скрыт
    if (tg() && tg().BackButton) tg().BackButton.hide();
    // бонус-гейты на сервере: текст благодарности соответствует факту гранта
    const text = this._surveyBonus ? fb('thanksBonus') : fb('thanksSaved');
    const html = `
      <div class="fb-thanks">
        <div class="fb-thanks__orb" aria-hidden="true">✨</div>
        <h3 class="fb-thanks__title">${esc(text)}</h3>
        <button type="button" class="btn btn-primary" data-act="survey-close"
                style="margin-top:18px">${esc(fb('back'))}</button>
      </div>`;
    // переиспользуем модал, но уже без back-handler
    this.showModal(html, 'full');
  };

  // ── actions (делегируются через 15-actions → survey-*) ───────────

  app.surveyAdvance = function () {
    if (this._surveyBusy) return;
    const code = FB_QUESTIONS[this._surveyStep];
    const answer = this._surveyAnswers[code];

    // dream: текст опционален — пустой/нет ответа = шаг пропущен
    if (code !== 'dream' && !answer) return;

    if (this._surveyStep === FB_QUESTIONS.length - 1) {
      this.surveySubmit();
      return;
    }
    this._surveyStep++;
    haptic('light');
    this.renderSurvey();
  };

  app.surveyBack = function () {
    if (this._surveyStep > 0) {
      this._surveyStep--;
      haptic('light');
      this.renderSurvey();
    }
  };

  app.surveySkip = function () {
    const code = FB_QUESTIONS[this._surveyStep];
    if (code === 'dream') {
      delete this._surveyAnswers[code];
      this._surveyStep++;
      haptic('light');
      this.renderSurvey();
    }
  };

  app.surveyChoice = function (el) {
    const code = el.dataset.code;
    const choice = el.dataset.choice;
    const score = el.dataset.score;

    haptic('light');

    if (score !== undefined) {
      this._surveyAnswers[code] = { score: parseInt(score, 10) };
    } else if (choice) {
      const existing = this._surveyAnswers[code] || {};
      // уход с «Другое…» на обычный вариант — текст не отправляем
      const text = choice === 'other' ? (existing.text || '') : '';
      this._surveyAnswers[code] = { choice, text };

      // other впервые → показать textarea, перерендерить шаг
      if (choice === 'other' && existing.choice !== 'other') {
        this.renderSurvey();
        setTimeout(() => {
          const ta = document.getElementById('fb-other-text');
          if (ta) ta.focus();
        }, 50);
        return;
      }
    }

    // обновить active-состояние кнопок без полного рендера
    const container = el.parentElement;
    container.querySelectorAll('.fb-choice-btn, .fb-nps-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    el.classList.add('active');
    el.setAttribute('aria-pressed', 'true');

    // включить Next
    const next = container.closest('.modal')?.querySelector('.fb-next');
    if (next) next.disabled = false;
  };

  // синхронизация textarea → state; вызывается из 13-events.js на input
  app.surveySyncInput = function (ta) {
    const code = FB_QUESTIONS[this._surveyStep];
    if (!ta || !ta.id) return;
    if (code === 'dream' && ta.id === 'fb-dream-text') {
      const prev = this._surveyAnswers[code] || {};
      this._surveyAnswers[code] = { ...prev, text: ta.value };
    } else if ((code === 'blocker' || code === 'next') && ta.id === 'fb-other-text') {
      const prev = this._surveyAnswers[code] || {};
      this._surveyAnswers[code] = { ...prev, text: ta.value };
    }
  };

  app.surveySubmit = async function () {
    if (this._surveyBusy) return;
    this._surveyBusy = true;

    // собрать answers из state
    const answers = FB_QUESTIONS
      .filter(code => this._surveyAnswers[code])
      .map(code => {
        const a = this._surveyAnswers[code];
        const entry = { question_code: code };
        if (a.score !== undefined) entry.score = a.score;
        else if (a.choice) { entry.choice = a.choice; if (a.text) entry.text = a.text; }
        else if (a.text) entry.text = a.text;
        return entry;
      })
      // пустой текст без choice/score = шаг без ответа (набрал и стёр)
      .filter(entry => entry.choice || entry.score !== undefined ||
                       (entry.text && entry.text.trim()));

    if (!answers.length) {
      this._surveyBusy = false;
      return;
    }

    const submitBtn = document.querySelector('.fb-next');
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = fb('sending');
    }

    try {
      const res = await api('/api/feedback', {
        method: 'POST',
        body: JSON.stringify({ answers, survey_code: 'day7_v1' })
      });
      this._surveyBonus = !!(res && res.bonus_granted);
      if (this._surveyBonus) {
        haptic('success');
      } else {
        haptic('soft');
      }
      // снять флаг в локальном me (чтобы не открывался повторно в этой сессии)
      if (this.me) {
        this.me = Object.assign({}, this.me, { feedback_pending: false });
      }
      this._surveyStep = FB_QUESTIONS.length; // → thanks
      this.renderSurvey();
    } catch (e) {
      this.toast(fb('error'));
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = fb('submit');
      }
      this._surveyBusy = false;
    }
  };

  // ── back-button cleanup ───────────────────────────────────────────

  const origClose = app.closeModal;
  app.closeModal = function () {
    if (this._surveyBackHandler && tg() && tg().BackButton) {
      tg().BackButton.offClick(this._surveyBackHandler);
      tg().BackButton.hide();
      this._surveyBackHandler = null;
    }
    // закрытие в обход closeSurvey (Esc, крестик) — сбросить состояние формы,
    // чтобы boot-хук при следующем запуске мог открыть её заново
    this._surveyOpen = false;
    origClose.call(this);
  };

  // ── boot hook: показ формы по feedback_pending из /api/me ─────────

  const _origBoot = app.boot;
  app.boot = async function () {
    await _origBoot.call(this);
    if (!this._surveyOpen && this.me && this.me.feedback_pending) {
      // QA-гейт: ?survey=1 принудительно открывает форму поверх любого экрана
      const force = new URLSearchParams(location.search).get('survey') === '1';
      if (force || this.view === 'home') {
        setTimeout(() => this.openSurvey(), 400);
      }
    }
  };

})();
