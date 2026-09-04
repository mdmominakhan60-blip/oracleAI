/** Stable admin DOM shell. Feature modules render only inside these named regions. */
export const adminShellTemplate = String.raw`
<a class="skip-link" href="#app-main">К основному содержимому</a>

<div id="gate" class="gate">
  <div class="gate-card">
    <div class="gate-logo">🔮</div>
    <h1>Панель Оракула</h1>
    <p id="gate-msg" class="muted">Проверяю доступ…</p>
  </div>
</div>

<div id="shell" class="shell hidden">
  <aside class="sidebar">
    <div class="brand"><span>🔮</span><b>Оракул</b></div>
    <nav id="nav" aria-label="Разделы панели">
      <button class="nav-item active" data-view="dashboard"><i>📊</i>Дашборд</button>
      <button class="nav-item" data-view="users"><i>👥</i>Клиентки</button>
      <button class="nav-item" data-view="orders"><i>💳</i>Заказы</button>
      <button class="nav-item" data-view="reconciliation"><i>🧾</i>Сверка платежей</button>
      <button class="nav-item" data-view="catalog"><i>🏷</i>Тарифы и товары</button>
      <button class="nav-item" data-view="promo"><i>🎟</i>Промокоды</button>
      <button class="nav-item" data-view="broadcasts"><i>📣</i>Рассылки</button>
      <button class="nav-item" data-view="content"><i>✍️</i>Контент</button>
      <button class="nav-item" data-view="horoscopes"><i>♈</i>Гороскопы</button>
      <button class="nav-item" data-view="costs"><i>🧮</i>Себестоимость</button>
      <button class="nav-item" data-view="safety"><i>🛟</i>Безопасность</button>
      <button class="nav-item" data-view="settings"><i>⚙️</i>Настройки</button>
      <button class="nav-item" data-view="audit"><i>🗂</i>Аудит</button>
      <button class="nav-item" data-view="logs"><i>📡</i>Системные логи</button>
    </nav>
    <div class="sidebar-foot">
      <div id="who" class="who"></div>
      <div id="health" class="health"></div>
    </div>
  </aside>

  <main class="main" id="app-main" tabindex="-1">
    <header class="topbar">
      <h2 id="view-title">Дашборд</h2>
      <div class="topbar-actions">
        <label class="sr-only" for="period">Период аналитики</label><select id="period" class="input slim" aria-label="Период аналитики">
          <option value="7">7 дней</option>
          <option value="30" selected>30 дней</option>
          <option value="90">90 дней</option>
        </select>
        <button id="demo-toggle" class="btn demo-toggle hidden" type="button" aria-pressed="false">ДЕМО: выкл.</button>
        <button id="refresh" class="btn ghost">↻ Обновить</button>
      </div>
    </header>

    <!-- ДАШБОРД -->
    <section class="view active" id="view-dashboard">
      <div id="demo-banner" class="demo-banner hidden" role="status">
        <strong>ДЕМО-РЕЖИМ · тестовые данные</strong>
        <span>451 уникальный пользователь · 130 повторных · $328 покупок · 17 дней работы.</span>
        <span>Это не реальные пользователи, заказы, платежи или баланс. Операционный мониторинг ниже остаётся реальным.</span>
      </div>
      <div id="kpi" class="kpi-grid"></div>
      <div id="kpi-monetization" class="kpi-grid"></div>

      <div class="card payment-health-card">
        <div class="card-head"><h3>Платёжный контур</h3><span id="payment-health-updated" class="muted small"></span></div>
                  <div id="payment-health" class="payment-health" aria-live="polite"></div>

      </div>

      <div class="row-2">
        <div class="card">
          <div class="card-head"><h3>Динамика</h3>
            <div class="legend">
              <span><i class="dot dot-gold"></i>активные</span>
              <span><i class="dot dot-blue"></i>вопросы</span>
              <span><i class="dot dot-green"></i>регистрации</span>
            </div>
          </div>
          <div id="chart-activity" class="chart"></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>Воронка</h3></div>
          <div id="funnel"></div>
        </div>
      </div>

      <div class="row-2">
        <div class="card">
          <div class="card-head"><h3>Деньги, Stars</h3></div>
          <div id="chart-revenue" class="chart"></div>
          <div id="revenue-facts" class="facts"></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>Удержание, %</h3></div>
          <div id="retention" class="table-wrap"></div>
        </div>
      </div>

      <div class="row-3">
        <div class="card"><div class="card-head"><h3>Топ товаров</h3></div>
          <div id="top-products" class="table-wrap"></div></div>
        <div class="card"><div class="card-head"><h3>Каналы</h3></div>
          <div id="sources" class="table-wrap"></div></div>
        <div class="card"><div class="card-head"><h3>Кто приводит</h3></div>
          <div id="referrers" class="table-wrap"></div></div>
      </div>
    </section>

    <!-- КЛИЕНТКИ -->
    <section class="view" id="view-users">
      <div class="toolbar">
        <label class="sr-only" for="user-q">Поиск клиенток</label>
        <input id="user-q" class="input" aria-label="Поиск клиенток" placeholder="Имя, @username или id…">
        <label class="sr-only" for="user-segment">Сегмент клиенток</label>
        <select id="user-segment" class="input slim" aria-label="Сегмент клиенток"></select>
        <label class="sr-only" for="user-order">Сортировка клиенток</label>
        <select id="user-order" class="input slim" aria-label="Сортировка клиенток">
          <option value="created_at">Сначала новые</option>
          <option value="last_seen">По активности</option>
          <option value="ltv">По деньгам</option>
          <option value="name">По имени</option>
        </select>
        <span id="user-total" class="muted"></span>
      </div>
      <div class="card"><div id="users-table" class="table-wrap"></div></div>
      <div class="pager">
        <button id="users-prev" class="btn ghost">← Назад</button>
        <span id="users-page" class="muted"></span>
        <button id="users-next" class="btn ghost">Вперёд →</button>
      </div>
    </section>

    <!-- ЗАКАЗЫ -->
    <section class="view" id="view-orders">
      <div class="toolbar">
        <select id="order-status" class="input slim">
          <option value="">Все статусы</option>
          <option value="paid">Оплаченные</option>
          <option value="pending">Ожидают</option>
          <option value="refunded">Возвращённые</option>
        </select>
      </div>
      <div class="card"><div id="orders-table" class="table-wrap"></div></div>
    </section>

    <!-- СВЕРКА ПЛАТЕЖЕЙ -->
    <section class="view" id="view-reconciliation">
      <div class="card">
        <div class="card-head"><div><h3>Сверка платежей</h3><p class="muted small">Только owner. Действия не меняют статус оплаты.</p></div>
          <button id="reconciliation-export" class="btn ghost" type="button">Экспорт агрегатов</button></div>
        <div id="reconciliation-summary" class="payment-health"></div>
        <div id="reconciliation-table" class="table-wrap" aria-live="polite"></div>
        <div id="reconciliation-detail" class="card-subsection" hidden></div>
      </div>
      <div class="card">
        <div class="card-head"><div><h3>Уведомления владельца</h3><p class="muted small">Cooldown, тихие часы и опциональный второй webhook-канал.</p></div></div>
        <div id="payment-notification-form" class="form" aria-live="polite"></div>
      </div>
    </section>

    <!-- КАТАЛОГ -->
    <section class="view" id="view-catalog">
      <div class="card">
        <div class="card-head"><h3>Тарифы</h3>
          <span class="muted small">Цены в Stars. Изменения применяются сразу.</span></div>
        <div id="plans-table" class="table-wrap"></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Товары</h3>
          <span class="muted small">Одиночные расклады, разборы, вопросы, Кристаллы</span></div>
        <div id="products-table" class="table-wrap"></div>
      </div>
    </section>

    <!-- ПРОМОКОДЫ -->
    <section class="view" id="view-promo">
      <div class="row-2">
        <div class="card">
          <div class="card-head"><h3>Новая партия</h3></div>
          <div class="form">
            <label>Сколько кодов<input id="promo-count" class="input" type="number" value="20" min="1" max="1000"></label>
            <label>Партия (канал)<input id="promo-batch" class="input" aria-label="Партия промокодов" placeholder="etsy-listing-1"></label>
            <label>Что выдаём
              <select id="promo-kind" class="input">
                <option value="plan_days">Дни подписки</option>
                <option value="crystals">Кристаллы ✦</option>
                <option value="product">Товар по SKU</option>
              </select>
            </label>
            <label>Тариф<select id="promo-plan" class="input" aria-label="Тариф промокодов"></select></label>
            <label>Дней<input id="promo-days" class="input" type="number" value="30" min="1"></label>
            <label>Кристаллов<input id="promo-crystals" class="input" type="number" value="0" min="0"></label>
            <label>SKU товара<input id="promo-sku" class="input" aria-label="SKU товара" placeholder="spread_celtic"></label>
            <label>Активаций на код<input id="promo-uses" class="input" type="number" value="1" min="1"></label>
            <label>Срок действия, дней<input id="promo-valid" class="input" aria-label="Срок действия промокодов в днях" type="number" placeholder="без ограничения"></label>
            <button id="promo-create" class="btn gold">Создать партию</button>
          </div>
          <pre id="promo-out" class="codeblock hidden"></pre>
        </div>
        <div class="card">
          <div class="card-head"><h3>Партии</h3></div>
          <div id="promo-batches" class="table-wrap"></div>
        </div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Коды</h3>
          <span id="promo-batch-hint" class="muted small"></span>
          <label class="check"><input type="checkbox" id="promo-unused"> только неиспользованные</label>
        </div>
        <div id="promo-codes" class="table-wrap"></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Активации купонов</h3>
          <span class="muted small">Кто и когда применил код — клик по строке открывает клиентку</span>
        </div>
        <div id="promo-redemptions" class="table-wrap"></div>
      </div>
    </section>

    <!-- РАССЫЛКИ -->
    <section class="view" id="view-broadcasts">
      <div class="row-2">
        <div class="card">
          <div class="card-head"><h3>Новая рассылка</h3></div>
          <div class="form">
            <label>Название (для себя)<input id="bc-title" class="input" aria-label="Название рассылки" placeholder="Возврат спящих, июль"></label>
            <label>Сегмент<select id="bc-segment" class="input" aria-label="Сегмент рассылки"></select></label>
            <label>Текст (HTML можно)
              <textarea id="bc-body" class="input" aria-label="Текст рассылки" rows="7"
                placeholder="🌙 Я снова вижу твою звезду…"></textarea></label>
            <div class="row-2 tight">
              <label>Кнопка<input id="bc-btn-text" class="input" aria-label="Текст кнопки рассылки" placeholder="Открыть Оракула"></label>
              <label>Ссылка<input id="bc-btn-url" class="input" aria-label="Ссылка кнопки рассылки" placeholder="https://t.me/…"></label>
            </div>
            <div class="btn-row">
              <button id="bc-preview" class="btn ghost">Кому уйдёт?</button>
              <button id="bc-create" class="btn gold">Отправить</button>
            </div>
            <p id="bc-preview-out" class="muted"></p>
          </div>
        </div>
        <div class="card">
          <div class="card-head"><h3>История</h3></div>
          <div id="bc-list" class="table-wrap"></div>
        </div>
      </div>
    </section>

    <!-- КОНТЕНТ -->
    <section class="view" id="view-content">
      <div class="toolbar">
        <select id="content-kind" class="input slim">
          <option value="">Все виды</option>
          <option value="agent">Агенты (промпты)</option>
          <option value="persona">Образы Оракула</option>
          <option value="guide">Правила трактовки</option>
          <option value="copy">Тексты сценариев</option>
          <option value="faq">FAQ</option>
          <option value="spread">Расклады</option>
          <option value="practice">Практики</option>
        </select>
        <button id="content-new" class="btn ghost">+ Новая запись</button>
      </div>
      <div class="row-2 wide-left">
        <div class="card"><div id="content-list" class="list"></div></div>
        <div class="card">
          <div class="card-head"><h3 id="content-editor-title">Выбери запись</h3></div>
          <div id="content-editor" class="form"></div>
        </div>
      </div>
    </section>

    <!-- НАСТРОЙКИ -->
    <section class="view" id="view-settings">
      <div class="row-2">
        <div class="card">
          <div class="card-head"><h3>Значения</h3>
            <span class="muted small">Применяются без перезапуска</span></div>
          <div id="settings-list" class="form"></div>
        </div>
        <div>
          <div class="card">
            <div class="card-head"><h3>Фиче-флаги</h3></div>
            <div id="flags-list"></div>
          </div>
          <div class="card">
            <div class="card-head"><h3>Администраторы</h3></div>
            <div id="admins-list" class="table-wrap"></div>
            <div class="form tight">
              <div class="row-2 tight">
                <label>Telegram id<input id="admin-id" class="input" aria-label="Telegram ID администратора" type="number"></label>
                <label>Роль<select id="admin-role" class="input">
                  <option value="analyst">Аналитик (только чтение)</option>
                  <option value="support">Поддержка</option>
                  <option value="admin" selected>Администратор</option>
                  <option value="owner">Владелец</option>
                </select></label>
              </div>
              <label>Подпись (необязательно)<input id="admin-title" class="input" aria-label="Подпись администратора" maxlength="60"
                placeholder="Например: редактор контента"></label>
              <button id="admin-add" class="btn ghost">Добавить</button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ГОРОСКОПЫ -->
    <section class="view" id="view-horoscopes">
      <div class="toolbar">
        <label class="sr-only" for="horo-day">Дата гороскопа</label>
        <input id="horo-day" class="input slim" type="date" aria-label="Дата гороскопа">
        <button id="horo-build" class="btn gold">Собрать на день</button>
        <span id="horo-channels" class="muted"></span>
      </div>
      <div class="card">
        <div class="card-head"><h3>Двенадцать знаков</h3>
          <span class="muted small">Один текст на знак в сутки — на весь сервис,
            не по клиентке</span></div>
        <div id="horo-list" class="table-wrap"></div>
      </div>
    </section>

    <!-- СЕБЕСТОИМОСТЬ -->
    <section class="view" id="view-costs">
      <div id="cost-kpi" class="kpi-grid"></div>
      <div class="row-2">
        <div class="card">
          <div class="card-head"><h3>На что уходят токены</h3></div>
          <div id="cost-purpose" class="table-wrap"></div>
        </div>
        <div class="card">
          <div class="card-head"><h3>По моделям</h3></div>
          <div id="cost-models" class="table-wrap"></div>
        </div>
      </div>
    </section>

    <!-- БЕЗОПАСНОСТЬ -->
    <section class="view" id="view-safety">
      <div class="card">
        <div class="card-head"><h3>Срабатывания кризисного протокола</h3>
          <span class="muted small">Эти обращения не доходили до модели
            и не тратили лимит</span></div>
        <div id="safety-summary" class="table-wrap"></div>
      </div>
      <div class="card">
        <div class="card-head"><h3>Последние обращения</h3>
          <span class="muted small">Читать глазами: так настраивается фильтр</span>
        </div>
        <div id="safety-recent" class="table-wrap"></div>
      </div>
    </section>

    <!-- АУДИТ -->
    <section class="view" id="view-audit">
      <div class="card"><div id="audit-table" class="table-wrap"></div></div>
    </section>

    <!-- СИСТЕМНЫЕ ЛОГИ -->
    <section class="view" id="view-logs">
      <div class="card logs-card">
        <div class="card-head logs-head">
          <div><h3>Системные логи</h3><p class="muted small">Живой operational stream процесса. Секреты, initData, email и Telegram ID редактируются formatter-ом.</p></div>
          <div class="logs-actions"><span id="logs-status" class="badge off">Отключено</span><span id="logs-buffer" class="muted small"></span><button id="logs-pause" class="btn ghost" type="button" aria-pressed="false">Ⅱ Пауза</button><button id="logs-refresh" class="btn ghost" type="button">↻ Обновить</button><button id="logs-clear" class="btn ghost" type="button">Очистить экран</button></div>
        </div>
        <div class="toolbar logs-toolbar"><label class="sr-only" for="logs-level">Уровень лога</label><select id="logs-level" class="input slim" aria-label="Уровень лога"></select><label class="sr-only" for="logs-logger">Логгер</label><input id="logs-logger" class="input" aria-label="Фильтр логгера" placeholder="oracle.api…"><label class="sr-only" for="logs-query">Поиск по логам</label><input id="logs-query" class="input" aria-label="Поиск в логах" placeholder="Поиск в сообщении или полях…"></div>
        <div id="logs-list" class="logs-list" role="log" aria-live="polite" aria-label="Поток системных логов"><div class="empty">Логи загружаются…</div></div>
      </div>
    </section>
  </main>
</div>

<!-- Карточка клиентки -->
<div id="drawer" class="drawer hidden">
  <div class="drawer-bg" data-close></div>
  <div class="drawer-body">
    <button class="drawer-close" data-close>✕</button>
    <div id="drawer-content"></div>
  </div>
</div>

<div id="toast" class="toast"></div>
`;
