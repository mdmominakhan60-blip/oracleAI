/* r06-p3: S15, S20–S26, S13 Кельтский крест — Сегодня/Библиотека/Профиль/Оплата */
/* Источник: design/r06/p3/ (HANDOFF S15–S26) */

app._r06 = app._r06 || { views: {} };

/* ── S15: today ── */
app._r06.views['today'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="today">
      <header class="section-head">
        <span class="section-head__date">Четверг, 11 сентября</span>
        <h1 class="section-head__title">Сегодня</h1>
      </header>
      <section class="today__forecast" aria-label="Прогноз дня">
        <div class="today__forecast-kicker">
          <img src="/static/img/agents/astro.jpg" alt="" style="width:18px;height:18px;border-radius:999px;object-fit:cover">
          Прогноз дня · Урания
        </div>
        <p class="today__forecast-text today__forecast--clamped" id="today-fc">Луна в Тельце мягко заземляет утро — день для тихих дел и завершения начатого. К вечеру Меркурий напомнит о недописанном: вернись к письму, которое откладывала.</p>
        <button type="button" class="today__expand" aria-expanded="false" aria-controls="today-fc" data-r06-toggle-expand>Развернуть <span aria-hidden="true">▾</span></button>
        <button type="button" class="btn btn-primary btn--block today__ask" data-goto="hub">Обсудить день</button>
      </section>
      <div class="today__blocks">
        <button type="button" class="today-card" data-goto="tarot-question">
          <span class="today-card__icon" aria-hidden="true">🃏</span>
          <span class="today-card__title">Карта дня</span>
          <span class="today-card__meta">Восьмёрка Пентаклей · ремесло и шаг за шагом</span>
          <span class="today-card__go">Открыть карту →</span>
        </button>
        <button type="button" class="today-card">
          <span class="today-card__icon" aria-hidden="true">🌙</span>
          <span class="today-card__title">Луна недели</span>
          <span class="today-card__meta">Растущая, 4 лунный день · 14° Тельца</span>
          <span class="today-card__go">Полный инструмент →</span>
        </button>
        <button type="button" class="today-card today-card--empty">
          <span class="today-card__icon" aria-hidden="true">📖</span>
          <span class="today-card__title">Дневник</span>
          <span class="today-card__meta">Сегодня ещё не записано. Две минуты вечером — и день останется с тобой.</span>
          <span class="today-card__go">Записать →</span>
        </button>
      </div>
    </main>
  </div>`;
};

/* ── S20: library ── */
app._r06.views['library'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="library">
      <header class="section-head">
        <h1 class="section-head__title">Библиотека</h1>
        <p class="section-head__sub">Всё, что ты уже получила: разборы, диалоги и записи дневника.</p>
      </header>
      <div class="seg-tabs" role="tablist" aria-label="Вкладки библиотеки">
        <button type="button" class="seg-tabs__tab" role="tab" aria-selected="true" id="tab-readings" aria-controls="pane-readings">Разборы</button>
        <button type="button" class="seg-tabs__tab" role="tab" aria-selected="false" id="tab-sessions" aria-controls="pane-sessions">Диалоги</button>
        <button type="button" class="seg-tabs__tab" role="tab" aria-selected="false" id="tab-diary" aria-controls="pane-diary">Дневник</button>
      </div>
      <div class="library__search field">
        <label class="visually-hidden" for="lib-q">Поиск по библиотеке</label>
        <input class="field__input" id="lib-q" type="search" placeholder="Поиск по названию и тексту">
      </div>
      <div role="tabpanel" id="pane-readings" aria-labelledby="tab-readings" style="margin-top:var(--space-2)">
        <button type="button" class="lib-row">
          <span class="lib-row__icon" aria-hidden="true">🃏</span>
          <span class="lib-row__body">
            <span class="lib-row__top"><span class="lib-row__name">Расклад «Прошлое · Настоящее · Будущее»</span><span class="lib-row__time">10 сентября</span></span>
            <span class="lib-row__preview">Колесо Фортуны говорит о повороте: то, что казалось застоем…</span>
            <span class="lib-row__src">Мадам Ленорман · Таролог <span class="badge badge--accent">оплачен</span></span>
          </span>
        </button>
        <button type="button" class="lib-row">
          <span class="lib-row__icon" aria-hidden="true">✳️</span>
          <span class="lib-row__body">
            <span class="lib-row__top"><span class="lib-row__name">Натальная карта</span><span class="lib-row__time">3 сентября</span></span>
            <span class="lib-row__preview">Солнце в Рыбах в 12 доме — дар к сопереживанию и тихой силе…</span>
            <span class="lib-row__src">Урания · Астролог</span>
          </span>
        </button>
        <button type="button" class="lib-row">
          <span class="lib-row__icon" aria-hidden="true">💞</span>
          <span class="lib-row__body">
            <span class="lib-row__top"><span class="lib-row__name">Синастрия с Даниилом</span><span class="lib-row__time">28 августа</span></span>
            <span class="lib-row__preview">Венера-Марс в квадрате: притяжение через трение, о чём важно договориться…</span>
            <span class="lib-row__src">Урания · Астролог</span>
          </span>
        </button>
        <div class="lib-stale" style="margin-top:var(--space-4)" role="status">
          <span class="lib-stale__icon" aria-hidden="true">🕰️</span>
          <div class="lib-stale__text">
            <strong>Этот разбор был построен на старых данных рождения.</strong> После изменения профиля история не переписывается: можно открыть как есть или построить заново.
            <div class="lib-stale__actions">
              <button type="button" class="btn btn-secondary" style="min-height:40px">Открыть как есть</button>
              <button type="button" class="btn btn-primary" style="min-height:40px">Построить заново</button>
            </div>
          </div>
        </div>
      </div>
      <div role="tabpanel" id="pane-sessions" aria-labelledby="tab-sessions" hidden style="margin-top:var(--space-2)"></div>
      <div role="tabpanel" id="pane-diary" aria-labelledby="tab-diary" hidden style="margin-top:var(--space-2)"></div>
    </main>
  </div>`;
};

/* ── S21: profile ── */
app._r06.views['profile'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="profile">
      <header class="section-head">
        <h1 class="section-head__title">Профиль</h1>
      </header>
      <div class="profile-card">
        <img class="profile-card__avatar" src="/static/img/agents/oracle.jpg" alt="">
        <div class="profile-card__body">
          <div class="profile-card__name">Мария</div>
          <div class="profile-card__meta">05.03.1994 · 14:20 · Москва</div>
        </div>
        <span class="profile-card__plan badge badge--accent">VIP</span>
      </div>
      <section class="profile-group" aria-label="Данные и память">
        <h2 class="profile-group__title">Данные и память</h2>
        <div class="profile-list">
          <button type="button" class="profile-row"><span class="profile-row__icon" aria-hidden="true">🌍</span><span class="profile-row__label">Данные рождения</span><span class="profile-row__value">05.03.1994 · Москва</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row" data-goto="memory"><span class="profile-row__icon" aria-hidden="true">🧠</span><span class="profile-row__label">Контекст и память</span><span class="profile-row__value">12 фактов</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row"><span class="profile-row__icon" aria-hidden="true">💞</span><span class="profile-row__label">Сохранённые партнёры</span><span class="profile-row__value">1</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
        </div>
      </section>
      <section class="profile-group" aria-label="Тариф и оплата">
        <h2 class="profile-group__title">Тариф и оплата</h2>
        <div class="profile-list">
          <button type="button" class="profile-row" data-goto="plan"><span class="profile-row__icon" aria-hidden="true">✦</span><span class="profile-row__label">Тариф и баланс</span><span class="profile-row__value">VIP · 120 ✦</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row" data-goto="orders"><span class="profile-row__icon" aria-hidden="true">🧾</span><span class="profile-row__label">История заказов</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
        </div>
      </section>
      <section class="profile-group" aria-label="Настройки">
        <h2 class="profile-group__title">Настройки</h2>
        <div class="profile-list">
          <button type="button" class="profile-row" data-goto="notifications"><span class="profile-row__icon" aria-hidden="true">🔔</span><span class="profile-row__label">Уведомления</span><span class="profile-row__value">19:00 · Москва</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row"><span class="profile-row__icon" aria-hidden="true">🌐</span><span class="profile-row__label">Язык</span><span class="profile-row__value">Русский</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row"><span class="profile-row__icon" aria-hidden="true">✨</span><span class="profile-row__label">Анимация фона</span><span class="profile-row__value">Вкл</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
        </div>
      </section>
      <section class="profile-group" aria-label="Помощь и данные">
        <h2 class="profile-group__title">Помощь и данные</h2>
        <div class="profile-list">
          <button type="button" class="profile-row"><span class="profile-row__icon" aria-hidden="true">💬</span><span class="profile-row__label">Помощь и поддержка</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row"><span class="profile-row__icon" aria-hidden="true">🎁</span><span class="profile-row__label">Пригласить подругу</span><span class="profile-row__value">+50 ✦</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row"><span class="profile-row__icon" aria-hidden="true">📦</span><span class="profile-row__label">Мои данные</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
          <button type="button" class="profile-row profile-row--danger"><span class="profile-row__icon" aria-hidden="true">⚠️</span><span class="profile-row__label">Удалить аккаунт</span><span class="profile-row__chev" aria-hidden="true">›</span></button>
        </div>
      </section>
    </main>
  </div>`;
};

/* ── S22: memory ── */
app._r06.views['memory'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="subpage">
      <header class="screenheader" style="margin:0 -16px;width:calc(100% + 32px);min-width:0">
        <button type="button" class="screenheader__back" data-goto="profile" aria-label="Назад в профиль">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Профиль
        </button>
        <span class="screenheader__title">Контекст и память</span>
        <span class="screenheader__spacer"></span>
      </header>
      <p class="subpage__lede" style="margin-top:var(--space-2)">Лилит помнит то, чем ты поделилась. Удаление факта — навсегда; он больше не будет влиять на разборы.</p>
      <div class="profile-list">
        <div class="memory-row">
          <span class="memory-row__text">«Работаю с людьми, после смены нет сил разговаривать»<span class="memory-row__src">из разговора · 2 сентября</span></span>
          <button type="button" class="memory-row__del">Удалить</button>
        </div>
        <div class="memory-row">
          <span class="memory-row__text">«Тревожусь перед звонками с мамой — хочу научиться мягче»<span class="memory-row__src">из разговора · 20 августа</span></span>
          <button type="button" class="memory-row__del">Удалить</button>
        </div>
        <div class="memory-row">
          <span class="memory-row__text">«Пью кофе после 16:00 — плохо сплю»<span class="memory-row__src">дневник · 12 августа</span></span>
          <button type="button" class="memory-row__del">Удалить</button>
        </div>
      </div>
    </main>
  </div>`;
};

/* ── S23: notifications ── */
app._r06.views['notifications'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="subpage">
      <header class="screenheader" style="margin:0 -16px;width:calc(100% + 32px);min-width:0">
        <button type="button" class="screenheader__back" data-goto="profile" aria-label="Назад в профиль">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Профиль
        </button>
        <span class="screenheader__title">Уведомления</span>
        <span class="screenheader__spacer"></span>
      </header>
      <p class="subpage__lede" style="margin-top:var(--space-2)">Приходят в Telegram. Время доставки считается по твоему текущему часовому поясу — он может отличаться от города рождения.</p>
      <div class="profile-list">
        <div class="notif-demo-row">
          <div class="notif-demo-row__body">
            <div class="notif-demo-row__name">Прогноз дня</div>
            <div class="notif-demo-row__hint">Каждое утро в 09:00 · время: Москва (UTC+3)</div>
          </div>
          <label class="switch"><input type="checkbox" checked aria-label="Прогноз дня"><span class="switch__track" aria-hidden="true"></span><span class="switch__thumb" aria-hidden="true"></span></label>
        </div>
        <div class="notif-demo-row">
          <div class="notif-demo-row__body">
            <div class="notif-demo-row__name">Лунный ритм</div>
            <div class="notif-demo-row__hint">Начало фазы · раз в несколько дней</div>
          </div>
          <label class="switch"><input type="checkbox" checked aria-label="Лунный ритм"><span class="switch__track" aria-hidden="true"></span><span class="switch__thumb" aria-hidden="true"></span></label>
        </div>
        <div class="notif-demo-row">
          <div class="notif-demo-row__body">
            <div class="notif-demo-row__name">Пауза всех уведомлений</div>
            <div class="notif-demo-row__hint">До 20 сентября · включается и снимается здесь же</div>
          </div>
          <label class="switch"><input type="checkbox" aria-label="Пауза всех уведомлений"><span class="switch__track" aria-hidden="true"></span><span class="switch__thumb" aria-hidden="true"></span></label>
        </div>
      </div>
    </main>
  </div>`;
};

/* ── S24: plan (тариф и баланс) ── */
app._r06.views['plan'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="subpage">
      <header class="screenheader" style="margin:0 -16px;width:calc(100% + 32px);min-width:0">
        <button type="button" class="screenheader__back" data-goto="profile" aria-label="Назад в профиль">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Профиль
        </button>
        <span class="screenheader__title">Тариф и баланс</span>
        <span class="screenheader__spacer"></span>
      </header>
      <div class="balance-box" style="margin-top:var(--space-3)">
        <span class="balance-box__icon" aria-hidden="true">✦</span>
        <span><span class="balance-box__label">Твои Кристаллы</span><br><span class="balance-box__amount">120 ✦</span></span>
        <button type="button" class="btn btn-secondary balance-box__buy">Пополнить</button>
      </div>
      <section class="plan-card plan-card--current" aria-label="Текущий тариф">
        <span class="plan-card__badge">Текущий</span>
        <div class="plan-card__top"><span class="plan-card__name">VIP</span><span class="plan-card__price">490 ₽<small>/мес</small></span></div>
        <p class="plan-card__tagline">Личный AI-проводник, память и регулярная глубина.</p>
        <ul class="plan-card__list">
          <li>Неограниченные разговоры с Лилит</li>
          <li>3 прогноза дня и карта дня</li>
          <li>Расклады Таро — включены, личный смысл отдельно</li>
          <li>Списание 11 октября · продление автоматическое</li>
        </ul>
      </section>
      <div class="pay-methods" role="group" aria-label="Способ оплаты">
        <button type="button" class="pay-method" aria-pressed="true"><span class="pay-method__icon" aria-hidden="true">⭐</span><span class="pay-method__name">Telegram Stars</span><span class="pay-method__hint">в окне Telegram</span></button>
        <button type="button" class="pay-method" aria-pressed="false"><span class="pay-method__icon" aria-hidden="true">💎</span><span class="pay-method__name">Криптоплатёж</span><span class="pay-method__hint">TON · USDT</span></button>
      </div>
      <button type="button" class="btn btn-primary btn--block" style="margin-top:var(--space-4)">Перейти на VIP Plus · 890 ₽/мес</button>
      <button type="button" class="promo-link" aria-expanded="false" id="promo-toggle">Есть промокод?</button>
    </main>
  </div>`;
};

/* ── S24b: paywall ── */
app._r06.views['paywall'] = function (main) {
  main.innerHTML = `<div class="screen">
    <div class="tool-view" style="max-width:560px">
      <header class="screenheader" style="margin:0 -16px;width:calc(100% + 32px);min-width:0">
        <button type="button" class="screenheader__back" data-goto="tool-form" aria-label="Вернуться к инструменту">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Назад
        </button>
        <span class="screenheader__title">Тариф VIP</span>
        <span class="screenheader__spacer"></span>
      </header>
      <div class="paywall__return-note" role="status">
        <span aria-hidden="true">↩</span>
        <span>После оплаты вернёшься к <strong>разбору синастрии</strong> — черновик и вопрос сохранены.</span>
      </div>
      <div class="plan-card plan-card--current">
        <div class="plan-card__top"><span class="plan-card__name">VIP</span></div>
        <div class="paywall__price-row"><span class="paywall__price">490 ₽</span><span class="paywall__period">в месяц · отмена в любой момент</span></div>
        <ul class="paywall__what">
          <li>Неограниченные разговоры с Лилит</li>
          <li>Натальная карта и разборы Урании</li>
          <li>Расклады Таро — включены</li>
        </ul>
        <button type="button" class="btn btn-primary btn--block">Оплатить через Telegram Stars</button>
        <p class="paywall__legal">Оплата проходит в окне Telegram. Мы не видим и не храним данные карты.</p>
        <button type="button" class="btn btn-ghost btn--block paywall__no" data-goto="tool-form">Не сейчас</button>
      </div>
      <button type="button" class="promo-link" aria-expanded="false">Есть промокод?</button>
    </div>
  </div>`;
};

/* ── S25: pay pending ── */
app._r06.views['pay-pending'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="subpage">
      <header class="screenheader" style="margin:0 -16px;width:calc(100% + 32px);min-width:0">
        <button type="button" class="screenheader__back" data-goto="plan" aria-label="Назад к тарифу">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Тариф
        </button>
        <span class="screenheader__title">Ожидание оплаты</span>
        <span class="screenheader__spacer"></span>
      </header>
      <div class="pay-pending" role="status" style="margin-top:var(--space-3)">
        <div class="tool-run__spinner" aria-hidden="true"></div>
        <div class="pay-pending__title">Проверяем оплату</div>
        <p class="pay-pending__text">Это занимает обычно меньше минуты. Счёт уже создан — не оплачивай повторно, даже если окно закрылось.</p>
        <button type="button" class="btn btn-secondary">Проверить статус</button>
      </div>
    </main>
  </div>`;
};

/* ── S26: orders ── */
app._r06.views['orders'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="subpage">
      <header class="screenheader" style="margin:0 -16px;width:calc(100% + 32px);min-width:0">
        <button type="button" class="screenheader__back" data-goto="profile" aria-label="Назад в профиль">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Профиль
        </button>
        <span class="screenheader__title">История заказов</span>
        <span class="screenheader__spacer"></span>
      </header>
      <div class="profile-list" style="margin-top:var(--space-3)">
        <div class="order-row">
          <div class="order-row__body">
            <div class="order-row__name">VIP · подписка, месяц</div>
            <div class="order-row__meta">10 сентября · 490 ₽ · Telegram Stars</div>
          </div>
          <span class="order-row__status status-chip status-chip--paid">Оплачен</span>
        </div>
        <div class="order-row">
          <div class="order-row__body">
            <div class="order-row__name">Личный смысл расклада</div>
            <div class="order-row__meta">8 сентября · 80 ✦</div>
          </div>
          <span class="order-row__status status-chip status-chip--paid">Оплачен</span>
        </div>
        <div class="order-row">
          <div class="order-row__body">
            <div class="order-row__name">VIP Plus · подписка, месяц</div>
            <div class="order-row__meta">7 сентября · 890 ₽</div>
          </div>
          <span class="order-row__status status-chip status-chip--pending">Ожидает</span>
        </div>
        <div class="order-row">
          <div class="order-row__body">
            <div class="order-row__name">100 ✦ Кристаллов</div>
            <div class="order-row__meta">5 сентября · 350 ₽</div>
          </div>
          <span class="order-row__status status-chip status-chip--unknown">Неизвестно</span>
          <button type="button" class="btn btn-ghost order-row__check">Проверить статус</button>
        </div>
        <div class="order-row">
          <div class="order-row__body">
            <div class="order-row__name">Синастрия с Даниилом</div>
            <div class="order-row__meta">1 сентября · 120 ✦</div>
          </div>
          <span class="order-row__status status-chip status-chip--failed">Отменён</span>
        </div>
      </div>
    </main>
  </div>`;
};

/* ── S13: tarot grid (Кельтский крест) ── */
app._r06.views['tarot-grid'] = function (main) {
  const positions = [
    { n: 1, name: 'Суть', card: 'm00.jpg', label: 'Шут', open: true },
    { n: 2, name: 'Пересечение', card: 'm01.jpg', label: 'Маг', open: true },
    { n: 3, name: 'Основание', card: 'm02.jpg', label: 'Жрица', open: true },
    { n: 4, name: 'Недавнее прошлое', card: 'pents09.jpg', label: 'Девятка Пентаклей', open: true },
    { n: 5, name: 'Возможное', card: 'wands03.jpg', label: '', open: false },
    { n: 6, name: 'Ближайшее будущее', card: 'swords10.jpg', label: '', open: false },
    { n: 7, name: 'Ты сам', card: 'cups02.jpg', label: '', open: false },
    { n: 8, name: 'Окружение', card: 'm17.jpg', label: '', open: false },
    { n: 9, name: 'Надежды и страхи', card: 'm19.jpg', label: '', open: false },
    { n: 10, name: 'Итог', card: 'm04.jpg', label: '', open: false }
  ];
  const cells = positions.map(p => `<button type="button" class="tarot-grid__cell${p.open ? ' is-open' : ''}" aria-pressed="${p.open}" aria-label="Позиция ${p.n}, ${p.name}${p.open ? `. ${p.label}, карта открыта` : ''}"><span class="tarot-grid__cell-num" aria-hidden="true">${p.n}</span><img class="tarot-grid__cell-img" src="/static/img/tarot/${p.card}" alt="${p.open ? `${p.label}, позиция ${p.n}` : ''}"></button>`).join('');
  main.innerHTML = `<div class="screen">
    <div class="tool-view" style="max-width:640px">
      <header class="screenheader" style="margin:0 -16px;width:calc(100% + 32px);min-width:0">
        <button type="button" class="screenheader__back" data-goto="tarot-question" aria-label="Назад">
          <svg viewBox="0 0 20 20" aria-hidden="true" style="width:18px;height:18px"><path d="M12 4l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Назад
        </button>
        <span class="screenheader__title">Кельтский крест · 10 карт</span>
        <span class="screenheader__spacer"></span>
      </header>
      <p class="tarot-scene__status" style="margin-bottom:var(--space-3)">Открыто 4 из 10 · открывай по порядку позиций</p>
      <div class="tarot-grid" role="group" aria-label="Позиции расклада">${cells}</div>
      <div class="tarot-grid__list">
        <details class="result-details">
          <summary class="result-details__summary">Позиции списком — для выбора без попадания в клетку</summary>
          <div class="result-details__body">
            <p style="margin:0">1 · Суть — Шут · начало пути без гарантий<br>2 · Пересечение — Маг · чем владеешь<br>3 · Основание — Жрица · что уже знаешь<br>4 · Недавнее — Девятка Пентаклей · опора на себя<br>5–10 · закрыты</p>
          </div>
        </details>
      </div>
    </div>
  </div>`;
};

/* ── States matrix (образцы состояний §11.2) ── */
app._r06.views['states'] = function (main) {
  main.innerHTML = `<div class="screen">
    <main class="today">
      <header class="section-head">
        <h1 class="section-head__title">Состояния</h1>
        <p class="section-head__sub">Образцы состояний экранов: skeleton, empty, paywall, ошибка, сессия.</p>
      </header>
      <section class="profile-group" aria-label="Loading">
        <h2 class="profile-group__title">Loading (skeleton)</h2>
        <div class="state-cell">
          <p class="today__forecast-text" style="margin-bottom:var(--space-2)">Сегодня</p>
          <span class="skeleton skeleton--w60"></span>
          <span class="skeleton" style="margin-top:6px"></span>
          <span class="skeleton skeleton--w80" style="margin-top:6px"></span>
        </div>
      </section>
      <section class="profile-group" aria-label="Empty">
        <h2 class="profile-group__title">Empty (нет данных — не ноль)</h2>
        <div class="state-cell">
          <div class="empty-state">
            <span class="empty-state__icon" aria-hidden="true">✳️</span>
            <div class="empty-state__title">Разборов пока нет</div>
            <p class="empty-state__text">Построй натальную карту или вытяни расклад — они появятся здесь.</p>
            <button type="button" class="btn btn-secondary" data-goto="tool-catalog">Открыть инструменты</button>
          </div>
        </div>
      </section>
      <section class="profile-group" aria-label="Нет доступа">
        <h2 class="profile-group__title">Нет доступа → paywall</h2>
        <div class="state-cell">
          <div class="status-banner status-banner--info">
            <span class="status-banner__icon" aria-hidden="true">✦</span>
            <div>
              <div class="status-banner__title">Разбор синастрии входит в VIP</div>
              <p class="status-banner__text">Черновик сохранён — вернёшься к нему после оплаты.</p>
              <div class="status-banner__actions">
                <button type="button" class="btn btn-primary" style="min-height:40px" data-goto="paywall">Смотреть тариф</button>
                <button type="button" class="btn btn-ghost" style="min-height:40px" data-goto="tool-form">Не сейчас</button>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section class="profile-group" aria-label="Ошибка сети">
        <h2 class="profile-group__title">Ошибка сети / offline</h2>
        <div class="state-cell">
          <div class="status-banner status-banner--error" role="alert">
            <span class="status-banner__icon" aria-hidden="true">⚠️</span>
            <div>
              <div class="status-banner__title">Нет соединения</div>
              <p class="status-banner__text">Прогноз не загрузился. Проверь интернет и повтори.</p>
              <div class="status-banner__actions"><button type="button" class="btn btn-secondary" style="min-height:40px">Повторить</button></div>
            </div>
          </div>
        </div>
      </section>
      <section class="profile-group" aria-label="Сессия истекла">
        <h2 class="profile-group__title">Session expired</h2>
        <div class="state-cell">
          <div class="status-banner status-banner--error" role="alert">
            <span class="status-banner__icon" aria-hidden="true">🔐</span>
            <div>
              <div class="status-banner__title">Сессия истекла</div>
              <p class="status-banner__text">Войди заново, чтобы продолжить. Данные и черновики сохранены.</p>
              <div class="status-banner__actions">
                <button type="button" class="btn btn-primary" style="min-height:40px">Войти заново</button>
                <button type="button" class="btn btn-ghost" style="min-height:40px">Помощь</button>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section class="profile-group" aria-label="Запись не найдена">
        <h2 class="profile-group__title">Запись не найдена (deep link)</h2>
        <div class="state-cell">
          <div class="lib-stale" role="status">
            <span class="lib-stale__icon" aria-hidden="true">🔍</span>
            <div class="lib-stale__text">
              <strong>Разбор не найден</strong> — возможно, он удалён или ссылка устарела.
              <div class="lib-stale__actions"><button type="button" class="btn btn-secondary" style="min-height:40px" data-goto="library">В библиотеку</button></div>
            </div>
          </div>
        </div>
      </section>
      <section class="profile-group" aria-label="Ошибка поля">
        <h2 class="profile-group__title">Ошибка поля</h2>
        <div class="state-cell">
          <div class="field" style="max-width:360px">
            <label class="field__label" for="st-city">Город рождения</label>
            <input class="field__input" id="st-city" value="Москв" aria-invalid="true" aria-describedby="st-city-err">
            <p class="field__error" id="st-city-err"><svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.4"/><path d="M8 5v3.5M8 10.6v.4" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>Выбери город из подсказок — так часовой пояс будет верным</p>
          </div>
        </div>
      </section>
    </main>
  </div>`;
};
