/* r06-p2: S11a–S12, S13a–S13d, S16–S18 — инструменты + Таро + виджеты */
/* Источник: design/r06/p2/ (HANDOFF S11–S18) */

app._r06 = app._r06 || { views: {} };

/* ── S11a: quick tool ── */
app._r06.views['tool-quick'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="tool-catalog" aria-label="Назад">
        <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <h1 class="screenheader__title">Быстрый прогноз</h1>
    </header>
    <div class="tool-view">
      <p class="tool-view__why">Личный прогноз на дату по натальной карте.</p>
      <div class="field">
        <label class="field__label" for="quick-date">Дата прогноза</label>
        <input class="field__input" id="quick-date" type="date">
      </div>
      <div class="tool-view__terms"><span aria-hidden="true">✦</span><span>Остаток: <strong>3 из 5</strong> прогнозов сегодня</span></div>
      <button class="btn btn-primary btn--block" data-goto="tool-run">Получить прогноз</button>
      <button class="btn btn-ghost btn--block" data-goto="tool-form">Изменить данные</button>
      <p class="tool-view__draft-note"><svg viewBox="0 0 16 16" aria-hidden="true" style="width:14px;height:14px;flex:none"><path d="M3 8.5l3.5 3.5L13 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>Черновик сохраняется при закрытии</p>
    </div>
  </div>`;
};

/* ── S11b: form tool (sinastria / vedic) ── */
app._r06.views['tool-form'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="tool-catalog" aria-label="Назад">
        <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <h1 class="screenheader__title">Синастрия</h1>
    </header>
    <div class="tool-view">
      <p class="tool-view__why">Совместимость по датам рождения.</p>
      <fieldset style="border:0;padding:0;margin:0 0 16px">
        <legend class="field__label" style="margin-bottom:8px">Твои данные</legend>
        <div class="review-list">
          <div class="review-row"><span class="review-row__label">Дата</span><span class="review-row__value">05.03.1994</span><button class="btn btn-ghost review-row__edit">Изменить</button></div>
          <div class="review-row"><span class="review-row__label">Город</span><span class="review-row__value">Москва</span><button class="btn btn-ghost review-row__edit">Изменить</button></div>
        </div>
      </fieldset>
      <div class="field">
        <label class="field__label" for="p-name">Имя партнёра</label>
        <input class="field__input" id="p-name" type="text" autocomplete="off">
      </div>
      <div class="date-seg">
        <div class="date-seg__seg date-seg__seg--day"><label class="field__label" for="p-day">День</label><input class="field__input" id="p-day" inputmode="numeric"></div>
        <div class="date-seg__seg"><label class="field__label" for="p-month">Месяц</label><input class="field__input" id="p-month"></div>
        <div class="date-seg__seg date-seg__seg--year"><label class="field__label" for="p-year">Год</label><input class="field__input" id="p-year" inputmode="numeric"></div>
      </div>
      <p class="field__error" id="p-time-err" role="alert" hidden>
        <svg viewBox="0 0 16 16" aria-hidden="true" style="width:16px;height:16px;flex:none"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 5v3.4l2.2 1.6" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
        Точность по домам снижена — будет указано в разборе.
      </p>
      <div class="tool-view__terms"><span aria-hidden="true">✦</span><span>Полный разбор: <strong>120 ✦</strong> или тариф «Проводник»</span></div>
      <button class="btn btn-primary btn--block" data-goto="tool-run">Построить разбор</button>
    </div>
  </div>`;
};

/* ── S11c: tool run (execution) ── */
app._r06.views['tool-run'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="tool-form" aria-label="Назад">←</button>
      <h1 class="screenheader__title">Выполнение</h1>
    </header>
    <div class="tool-view">
      <div class="run-status" role="status">
        <div class="run-status__step is-active" aria-current="step">Подготовка</div>
        <div class="run-status__step">Расчёт</div>
        <div class="run-status__step">Готово</div>
      </div>
      <div class="loader-ring"></div>
      <button class="btn btn-ghost" data-goto="result">Проверить статус</button>
    </div>
  </div>`;
};

/* ── S12: result ── */
app._r06.views['result'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="tool-run" aria-label="Назад">←</button>
      <h1 class="screenheader__title">Результат</h1>
    </header>
    <div class="result-view">
      <details class="result-view__details">
        <summary>Дома не считаны: Меркурий ретроградный</summary>
        <p>Карта строится по видимым позициям. Точность выше при прямом движении.</p>
      </details>
      <div class="result-view__body">
        <h2>Синастрия · Лилит ↔ Партнёр</h2>
        <p class="result-view__summary">Венера в 7-м — гармония в близких отношениях.</p>
      </div>
      <button class="btn btn-primary btn--block">Сохранить в Библиотеку</button>
    </div>
  </div>`;
};

/* ── S13a: tarot question ── */
app._r06.views['tarot-question'] = function (main) {
  const examples = ['Что мне даст новая работа?', 'Как проходит этот период?', 'На что обратить внимание?'];
  main.innerHTML = `<div class="screen">
    <div class="tarot">
      <header class="chat-header">
        <button class="screenheader__back" data-goto="hub" aria-label="Назад">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Чат
        </button>
        <img class="chat-header__avatar" src="/static/img/agents/tarot.jpg" alt="">
        <span><span class="chat-header__name">Мадам Ленорман</span><br><span class="chat-header__role">Таролог</span></span>
      </header>
      <div class="tarot__feed"><div class="tarot__panel">
        <div class="tarot-question">
          <label class="tarot-question__label" for="tarot-q">Твой вопрос к картам</label>
          <input class="field__input tarot-question__input" id="tarot-q" type="text" placeholder="Сформулируйте вопрос…">
          <p class="field__hint">Примеры — подстановщики:</p>
          <div class="tarot-examples" role="group" aria-label="Примеры">
            ${examples.map(e => `<button class="tarot-examples__item" type="button">${e}</button>`).join('')}
          </div>
        </div>
        <button class="btn btn-primary btn--block" data-goto="tarot-reveal">Вытянуть карты</button>
      </div></div>
    </div>
  </div>`;
};

/* ── S13b: tarot reveal ── */
app._r06.views['tarot-reveal'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="tarot">
      <header class="chat-header">
        <button class="screenheader__back" data-goto="tarot-question" aria-label="Вопрос">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <img class="chat-header__avatar" src="/static/img/agents/tarot.jpg" alt="">
        <span><span class="chat-header__name">Мадам Ленорман</span><br><span class="chat-header__role">Таролог</span></span>
      </header>
      <div class="tarot__feed"><div class="tarot__panel">
        <div class="tarot-scene" id="tarot-draw-scene">
          <div class="tarot-scene__fan" aria-hidden="true">
            <img class="tarot-scene__card-back tarot-scene__card-back--1" src="/static/img/card-back.jpg" alt="">
            <img class="tarot-scene__card-back tarot-scene__card-back--2" src="/static/img/card-back.jpg" alt="">
            <img class="tarot-scene__card-back tarot-scene__card-back--3" src="/static/img/card-back.jpg" alt="">
          </div>
          <p class="tarot-scene__status">Колода собирает расклад…</p>
        </div>
        <section hidden id="tarot-reveal-block">
          <div class="tarot-reveal__counter"><span id="tarot-counter">Открыто 0 из 3</span><button class="btn btn-ghost" id="tarot-show-all">Показать сразу</button></div>
          <div class="tarot-cards" role="group" aria-label="Карты расклада">
            <div class="tcard" data-i="0"><button class="tcard__frame" aria-label="Карта 1" aria-pressed="false"><img class="tcard__img" src="/static/img/tarot/cups02.jpg" alt=""><img class="tcard__back" src="/static/img/card-back.jpg" alt="" aria-hidden="true"></button><span class="tcard__pos"><span class="tcard__pos-name">Прошлое</span></span></div>
            <div class="tcard" data-i="1"><button class="tcard__frame" aria-label="Карта 2" aria-pressed="false"><img class="tcard__img" src="/static/img/tarot/wands03.jpg" alt=""><img class="tcard__back" src="/static/img/card-back.jpg" alt="" aria-hidden="true"></button><span class="tcard__pos"><span class="tcard__pos-name">Настоящее</span></span></div>
            <div class="tcard" data-i="2"><button class="tcard__frame" aria-label="Карта 3" aria-pressed="false"><img class="tcard__img" src="/static/img/tarot/m19.jpg" alt=""><img class="tcard__back" src="/static/img/card-back.jpg" alt="" aria-hidden="true"></button><span class="tcard__pos"><span class="tcard__pos-name">Будущее</span></span></div>
          </div>
          <div class="tarot-interpret__gate">
            <strong>Личный смысл расклада</strong> — 80 ✦<br>
            <button class="btn btn-primary" data-goto="tarot-reading" style="min-height:44px">Получить разбор</button>
          </div>
        </section>
      </div></div>
    </div>
  </div>`;
};

/* ── S13c: tarot zoom ── */
app._r06.views['tarot-zoom'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="tarot">
      <header class="chat-header">
        <button class="screenheader__back" data-goto="tarot-reveal" aria-label="К раскладу">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <span><span class="chat-header__name">Мадам Ленорман</span><br><span class="chat-header__role">Таролог</span></span>
      </header>
      <div class="tarot__feed"><div class="card-zoom">
        <img class="card-zoom__img" src="/static/img/tarot/cups02.jpg" alt="Двойка Кубков">
        <p class="card-zoom__caption"><span class="tcard__pos-name">Двойка Кубков</span> · Прошлое · прямая</p>
      </div></div>
    </div>
  </div>`;
};

/* ── S13d: tarot reading ── */
app._r06.views['tarot-reading'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="tarot">
      <header class="chat-header">
        <button class="screenheader__back" data-goto="tarot-reveal" aria-label="К картам">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <span><span class="chat-header__name">Мадам Ленорман</span><br><span class="chat-header__role">Таролог</span></span>
      </header>
      <div class="tarot__feed"><div class="tarot__panel">
        <h1 class="tarot-reading__title">Личный смысл расклада</h1>
        <div class="tarot-reading__verdict" role="note">
          <strong>Итог:</strong> менять — да, но не сгоряча. Прошлое держит привычкой; настоящее даёт силы; будущее — самое светлое.
        </div>
        <div class="result__actions">
          <button class="btn btn-primary">Обсудить в чате</button>
          <button class="btn btn-secondary">В библиотеку</button>
        </div>
        <p class="result__saved-note">
          <svg viewBox="0 0 16 16" aria-hidden="true" style="width:14px;height:14px;flex:none"><path d="M3 8.5l3.5 3.5L13 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Расклад сохранён — возврат без нового draw.
        </p>
      </div></div>
    </div>
  </div>`;
};

/* ── S16: synastry (alias tool-form) ── */
app._r06.views['synastry'] = app._r06.views['tool-form'];

/* ── S17: vedic periods (alias tool-form) ── */
app._r06.views['vedic'] = app._r06.views['tool-form'];

/* ── S18: widgets (moon/career/matrix/palm) ── */
app._r06.views['widgets'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="home" aria-label="Назад">←</button>
      <h1 class="screenheader__title">Инструменты</h1>
    </header>
    <div class="widgets-grid">
      <button class="widget-card" data-goto="widget-moon">
        <span class="widget-card__icon" aria-hidden="true">🌙</span>
        <span class="widget-card__name">Луна</span>
        <span class="widget-card__hint">Фаза и ритмы недели</span>
      </button>
      <button class="widget-card" data-goto="widget-career">
        <span class="widget-card__icon" aria-hidden="true">💼</span>
        <span class="widget-card__name">Карьера</span>
        <span class="widget-card__hint">10-й дом и профессиональный путь</span>
      </button>
      <button class="widget-card" data-goto="widget-matrix">
        <span class="widget-card__icon" aria-hidden="true">🔢</span>
        <span class="widget-card__name">Матрица</span>
        <span class="widget-card__hint">Линии и арканы</span>
      </button>
      <button class="widget-card" data-goto="widget-palm">
        <span class="widget-card__icon" aria-hidden="true">✋</span>
        <span class="widget-card__name">Ладонь</span>
        <span class="widget-card__hint">Читатель ладони Мира</span>
      </button>
    </div>
  </div>`;
};
