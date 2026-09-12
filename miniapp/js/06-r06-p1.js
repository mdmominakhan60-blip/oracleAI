/* r06-p1: S01–S12, S14 — онбординг + чат + наструменты + Таро */
/* Источник: design/r06/p1/ (HANDOFF S01–S14) */

app._r06 = app._r06 || { views: {} };

/* ── S01: session expired ── */
app._r06.views['session-expired'] = function (main) {
  main.innerHTML = `<div class="screen" data-auth-required>
    <div class="status-banner status-banner--error">
      <h2>Сессия истекла</h2>
      <p>Войдите заново, чтобы продолжить.</p>
      <div class="status-banner__actions">
        <button class="btn btn-primary" data-act="login">Войти заново</button>
        <button class="btn btn-ghost" data-act="help">Помощь</button>
      </div>
    </div>
  </div>`;
};

/* ── S02: auth error ── */
app._r06.views['auth-error'] = function (main) {
  const code = Math.random() > 0.5 ? 'blocked' : 'unknown';
  main.innerHTML = `<div class="screen" data-auth-required>
    <div class="status-banner status-banner--${code === 'blocked' ? 'error' : 'warning'}">
      <h2>${code === 'blocked' ? 'Доступ ограничен' : 'Не удалось войти'}</h2>
      <p>${code === 'blocked' ? 'Обратитесь в поддержку для разблокировки.' : 'Проверьте подключение и попробуйте снова.'}</p>
      <div class="status-banner__actions">
        <button class="btn btn-primary" data-act="login">Войти заново</button>
        <button class="btn btn-ghost" data-act="help">Помощь</button>
      </div>
    </div>
  </div>`;
};

/* ── S03: Welcome / intent ── */
app._r06.views['welcome'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="onboarding">
      <div class="onboarding__header">
        <h1 class="onboarding__title">С чего начнём?</h1>
        <p class="onboarding__why">Выберите направление — остальное откроется после.</p>
      </div>
      <div class="intent-list" role="group" aria-label="Намерение">
        <button class="intent-card" data-intent="chat" data-goto="chat">
          <span class="intent-card__icon" aria-hidden="true">🔮</span>
          <span class="intent-card__name">Обсудить вопрос</span>
          <span class="intent-card__hint">Без ввода данных — просто начните разговор</span>
        </button>
        <button class="intent-card" data-intent="astro" data-goto="chart">
          <span class="intent-card__icon" aria-hidden="true">🌌</span>
          <span class="intent-card__name">Натальная карта</span>
          <span class="intent-card__hint">Понадобятся дата, время и город</span>
        </button>
        <button class="intent-card" data-intent="tarot" data-goto="tarot">
          <span class="intent-card__icon" aria-hidden="true">🎴</span>
          <span class="intent-card__name">Расклад Таро</span>
          <span class="intent-card__hint">Достаточно вопроса</span>
        </button>
      </div>
    </div>
  </div>`;
};

/* ── S04: onboarding 5-step wizard ── */
app._r06.views['onboarding'] = function (main) {
  const step = parseInt(main.dataset.obStep || '1');
  const maxStep = 5;
  const segs = Array.from({ length: maxStep }, (_, i) =>
    `<div class="seg-progress__seg${i < step ? ' is-active' : ''}"></div>`
  ).join('');

  const stepsHtml = {
    1: `<section class="onboarding__step" id="ob-step-1">
      <h1 class="onboarding__title">С чего начнём знакомство?</h1>
      <p class="onboarding__why">Выберите, что попробовать первым.</p>
      <div class="intent-list" role="group">
        <button class="intent-card" data-goto="ob-step-2" data-intent="chat">
          <span class="intent-card__icon" aria-hidden="true">🔮</span>
          <span><span class="intent-card__name">Обсудить вопрос</span><br><span class="intent-card__hint">Без данных</span></span>
        </button>
        <button class="intent-card" data-goto="ob-step-2" data-intent="astro">
          <span class="intent-card__icon" aria-hidden="true">🌌</span>
          <span><span class="intent-card__name">Натальная карта</span><br><span class="intent-card__hint">Дата, время, город</span></span>
        </button>
        <button class="intent-card" data-goto="ob-step-2" data-intent="tarot">
          <span class="intent-card__icon" aria-hidden="true">🎴</span>
          <span><span class="intent-card__name">Таро</span><br><span class="intent-card__hint">Достаточно вопроса</span></span>
        </button>
      </div>
    </section>`,
    2: `<section class="onboarding__step" id="ob-step-2">
      <h1 class="onboarding__title">Как к вам обращаться?</h1>
      <div class="field">
        <label class="field__label" for="ob-name">Имя</label>
        <input class="field__input" id="ob-name" type="text" autocomplete="given-name" placeholder="Например, Анна">
      </div>
    </section>`,
    3: `<section class="onboarding__step" id="ob-step-3">
      <h1 class="onboarding__title">Дата рождения</h1>
      <div class="date-seg">
        <div class="date-seg__seg date-seg__seg--day">
          <label class="field__label" for="ob-day">День</label>
          <input class="field__input" id="ob-day" inputmode="numeric" placeholder="14">
        </div>
        <div class="date-seg__seg">
          <label class="field__label" for="ob-month">Месяц</label>
          <input class="field__input" id="ob-month" placeholder="март">
        </div>
        <div class="date-seg__seg date-seg__seg--year">
          <label class="field__label" for="ob-year">Год</label>
          <input class="field__input" id="ob-year" inputmode="numeric" placeholder="1994">
        </div>
      </div>
    </section>`,
    4: `<section class="onboarding__step" id="ob-step-4">
      <h1 class="onboarding__title">Время рождения</h1>
      <div class="choice-list" role="group">
        <button class="choice-row" aria-pressed="true">Точно <span class="choice-row__note">часы и минуты</span></button>
        <button class="choice-row" aria-pressed="false">Примерно <span class="choice-row__note">интервал</span></button>
        <button class="choice-row" aria-pressed="false">Не знаю <span class="choice-row__note">без времени</span></button>
      </div>
    </section>`,
    5: `<section class="onboarding__step" id="ob-step-5">
      <h1 class="onboarding__title">Город рождения</h1>
      <div class="combobox">
        <label class="field__label visually-hidden" for="ob-city">Город</label>
        <input class="field__input" id="ob-city" type="text" role="combobox" placeholder="Начните вводить…">
      </div>
    </section>`
  };

  main.innerHTML = `<div class="screen">
    <div class="onboarding">
      <div class="onboarding__progress">
        <div class="onboarding__progress-meta">
          <span id="ob-step-label">Шаг ${step} из ${maxStep}</span>
          <span>OracleAI</span>
        </div>
        <div class="seg-progress" role="progressbar" aria-valuemin="1" aria-valuemax="${maxStep}" aria-valuenow="${step}">${segs}</div>
      </div>
      ${stepsHtml[step] || ''}
      <footer class="onboarding__footer">
        <button type="button" class="btn btn-primary btn--block" id="ob-next" data-goto="ob-step-${Math.min(step + 1, maxStep + 1)}">Продолжить</button>
      </footer>
    </div>
  </div>`;
};

/* ── S05: chat empty state ── */
app._r06.views['chat-empty'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="chat">
      <header class="chat-header">
        <button class="screenheader__back" data-goto="hub" aria-label="Назад">←</button>
        <img class="chat-header__avatar" src="/static/img/agents/oracle.jpg" alt="">
        <div>
          <div class="chat-header__name">Лилит</div>
          <div class="chat-header__role">Личный оракул</div>
        </div>
      </header>
      <div class="empty-chat">
        <img class="empty-chat__portrait" src="/static/img/agents/oracle.jpg" alt="">
        <div class="empty-chat__greeting">С чего начнём?</div>
        <p class="empty-chat__role">Я рядом. Расскажи, что болит или о чём думаешь.</p>
        <div class="empty-chat__examples" aria-label="Примеры вопросов">
          <button class="empty-chat__example">Что меня сейчас держит на месте?</button>
          <button class="empty-chat__example">Помоги понять мой сон про воду</button>
          <button class="empty-chat__example">Как прожить эту неделю спокойнее</button>
        </div>
      </div>
      <footer class="composer">
        <div class="composer__row">
          <button class="composer__tools" data-open-sheet aria-label="Инструменты">
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M6 10h8M9 15h2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
            Инструменты
          </button>
          <div class="composer__input-wrap">
            <label class="visually-hidden" for="chat-input-empty">Сообщение</label>
            <textarea class="composer__input" id="chat-input-empty" rows="1" placeholder="Напиши вопрос…"></textarea>
          </div>
          <button class="composer__send" aria-label="Отправить" disabled>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10l14-7-5 14-2.5-5.5L3 10z" fill="currentColor"/></svg>
          </button>
        </div>
      </footer>
    </div>
  </div>`;
};

/* ── S06: chat dialog ── */
app._r06.views['chat-dialog'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="chat">
      <header class="chat-header">
        <button class="screenheader__back" data-goto="hub" aria-label="Назад">← Назад</button>
        <img class="chat-header__avatar" src="/static/img/agents/oracle.jpg" alt="">
        <div>
          <div class="chat-header__name">Лилит</div>
          <div class="chat-header__role">Личный оракул</div>
        </div>
        <span class="chat-header__spacer"></span>
        <button class="chat-header__btn" aria-label="Меню">⋯</button>
      </header>
      <div class="chat__feed" id="chat-feed" tabindex="0" aria-label="Переписка">
        <div class="msg msg--agent">
          <div class="msg__head">
            <img class="msg__agent-avatar" src="/static/img/agents/oracle.jpg" alt="">
            <span class="msg__agent-name">Лилит</span>
          </div>
          <div class="msg__bubble">
            <p>Я рядом. Расскажи, что болит или о чём думаешь.</p>
          </div>
        </div>
        <button class="newmsg-pivot" id="newmsg-demo" hidden>Новое сообщение ↓</button>
      </div>
      <footer class="composer">
        <div class="composer__row">
          <button class="composer__tools" data-open-sheet aria-label="Инструменты">
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M6 10h8M9 15h2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          </button>
          <div class="composer__input-wrap">
            <label class="visually-hidden" for="chat-input-dialog">Сообщение</label>
            <textarea class="composer__input" id="chat-input-dialog" rows="1" placeholder="Напиши вопрос…"></textarea>
          </div>
          <button class="composer__send" aria-label="Отправить">
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 10l14-7-5 14-2.5-5.5L3 10z" fill="currentColor"/></svg>
          </button>
          <button class="composer__stop" aria-label="Остановить">
            <svg viewBox="0 0 20 20" aria-hidden="true"><rect x="6" y="6" width="8" height="8" rx="1.5" fill="currentColor"/></svg>
          </button>
        </div>
      </footer>
    </div>
  </div>`;
};

/* ── S07: sessions history ── */
app._r06.views['sessions'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="sessions-list">
      <header class="screenheader">
        <h1 class="screenheader__title">Диалоги</h1>
        <button class="screenheader__action" aria-label="Новый диалог">+</button>
      </header>
      <div class="sessions-list__items">
        <button class="session-card" data-goto="chat-dialog">
          <img class="session-card__avatar" src="/static/img/agents/oracle.jpg" alt="">
          <div class="session-card__body">
            <div class="session-card__title">Лилит</div>
            <div class="session-card__preview">Что меня сейчас держит на месте?</div>
          </div>
          <div class="session-card__meta">
            <span class="session-card__time">сегодня</span>
            <button class="session-card__delete" aria-label="Удалить">×</button>
          </div>
        </button>
        <button class="session-card" data-goto="chat-dialog">
          <img class="session-card__avatar" src="/static/img/agents/oracle.jpg" alt="">
          <div class="session-card__body">
            <div class="session-card__title">Урания</div>
            <div class="session-card__preview">Сатурн в 10-м — потребность в смысле</div>
          </div>
          <div class="session-card__meta">
            <span class="session-card__time">вчера</span>
            <button class="session-card__delete" aria-label="Удалить">×</button>
          </div>
        </button>
      </div>
    </div>
  </div>`;
};

/* ── S08/S09: agent selector (sheet) ── */
app._r06.views['agent-select'] = function (main) {
  const agents = app.agents || [
    { code: 'oracle', name: 'Лилит', title: 'Личный оракул', emoji: '🔮', accent: '#e8c56b' },
    { code: 'astro', name: 'Урания', title: 'Астролог', emoji: '🌠', accent: '#8cc8ff' },
    { code: 'tarot', name: 'Мадам Ленорман', title: 'Таролог', emoji: '🃏', accent: '#e7a8d8' }
  ];
  const items = agents.map(a => `<button class="agent-card" data-agent="${a.code}">
    <span class="agent-card__avatar" style="--ac:${a.accent}">${a.emoji}</span>
    <div><div class="agent-card__name">${a.name}</div><div class="agent-card__title">${a.title}</div></div>
  </button>`).join('');
  main.innerHTML = `<div class="screen">
    <div class="sheet-overlay">
      <div class="sheet" role="dialog" aria-label="Выбор агента">
        <div class="sheet__header">
          <h2 class="sheet__title">Другой специалист</h2>
          <button class="sheet__close" aria-label="Закрыть">×</button>
        </div>
        <div class="sheet__body">${items}</div>
      </div>
    </div>
  </div>`;
};

/* ── S10: tool catalog (sheet) ── */
app._r06.views['tool-catalog'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="sheet-overlay">
      <div class="sheet" role="dialog" aria-label="Каталог инструментов">
        <div class="sheet__header">
          <h2 class="sheet__title">Инструменты</h2>
          <button class="sheet__close" aria-label="Закрыть">×</button>
        </div>
        <div class="sheet__search">
          <input class="field__input" placeholder="Поиск инструмента…" aria-label="Поиск">
        </div>
        <div class="sheet__body">
          <button class="tool-card" data-goto="tool-quick" disabled>
            <div class="tool-card__name">Быстрый расчёт</div>
            <div class="tool-card__note">Требуются данные карты</div>
          </button>
          <button class="tool-card" data-goto="tool-form">
            <div class="tool-card__name">Синастрия</div>
            <div class="tool-card__note">Отношения с партнёром</div>
          </button>
          <button class="tool-card" data-goto="tool-form">
            <div class="tool-card__name">Веды</div>
            <div class="tool-card__note">Периоды и транзиты</div>
          </button>
        </div>
      </div>
    </div>
  </div>`;
};

/* ── S11a: quick tool ── */
app._r06.views['tool-quick'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="tool-catalog" aria-label="Назад">←</button>
      <h1 class="screenheader__title">Быстрый расчёт</h1>
    </header>
    <div class="tool-view">
      <p class="tool-view__note">Остаток тарифа: <b>3 ✦</b></p>
      <button class="btn btn-primary btn--block" disabled>Запустить (нужны данные)</button>
      <button class="btn btn-ghost btn--block" data-goto="tool-form">Ввести данные</button>
    </div>
  </div>`;
};

/* ── S11b: form tool ── */
app._r06.views['tool-form'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="tool-catalog" aria-label="Назад">←</button>
      <h1 class="screenheader__title">Синастрия</h1>
    </header>
    <div class="tool-view">
      <div class="field">
        <label class="field__label" for="tool-partner-date">Дата партнёра</label>
        <input class="field__input" id="tool-partner-date" type="date">
        <p class="field__hint">Точность выше при известном времени</p>
      </div>
      <button class="btn btn-primary btn--block">Рассчитать (150 ✦)</button>
    </div>
  </div>`;
};

/* ── S11c: tool run ── */
app._r06.views['tool-run'] = function (main) {
  main.innerHTML = `<div class="screen">
    <header class="screenheader">
      <button class="screenheader__back" data-goto="tool-form" aria-label="Назад">←</button>
      <h1 class="screenheader__title">Выполнение</h1>
    </header>
    <div class="tool-view">
      <div class="run-status" role="status" aria-current="step">
        <div class="run-status__step is-active">Подготовка</div>
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
