/*
 * OracleAI payments surface.
 * The browser only requests server-created orders and opens provider links.
 * Prices, SKU, asset and entitlement are never trusted from rendered markup.
 */
(function () {
  'use strict';

  const ASSETS = [
    { code: 'TON', label: 'TON', icon: '◆', copy: { ru: 'Прямо в TON через Crypto Pay', en: 'Pay in TON through Crypto Pay' } },
    { code: 'USDT', label: 'USDT', icon: '₮', copy: { ru: 'Стабильная цена в долларах', en: 'A stable USD-denominated price' } },
    { code: 'BTC', label: 'BTC', icon: '₿', copy: { ru: 'Для оплаты в Bitcoin', en: 'Pay with Bitcoin' } },
  ];

  const PAYMENT_I18N = {
    ru: {
      space: 'ТВОЁ ПРОСТРАНСТВО', choose: 'Выбери свой ритм', heroCopy: 'Оплата без лишних шагов. Доступ откроется только после подтверждения провайдера.',
      balance: 'Твои Кристаллы', balanceHint: 'для разовых разборов', paymentMethod: 'Способ оплаты',
      stars: 'Telegram Stars', starsCopy: 'Быстро внутри Telegram', crypto: 'TON и крипта', cryptoCopy: 'TON, USDT или BTC',
      wallet: 'КРИПТОКОШЕЛЁК', payWith: 'Чем оплатить?', protectedInvoice: 'Защищённый invoice',
      cryptoNote: 'Сумма фиксируется в USD на сервере, а Crypto Pay показывает эквивалент в выбранной монете. Seed-фраза и приватные ключи не нужны.',
      starsTrustTitle: 'Оплата Stars внутри Telegram', starsTrustCopy: 'Никаких карт и лишних данных. Подписка и покупки активируются только после успешного платежа.',
      subscription: 'ПОДПИСКА', depth: 'Больше глубины каждый день', planCountOne: 'тариф', planCountFew: 'тарифа', planCountMany: 'тарифов',
      oneOff: 'РАЗОВЫЕ ПАКЕТЫ', reserve: 'Запас для важных вопросов', defaultPlan: 'Подписка', defaultPlanCopy: 'Больше глубины, памяти и личного ритма.', perPeriod: 'за период',
      popular: 'Самый популярный', openStars: 'Открыть оплату Stars', busy: 'Создаю защищённый заказ…',
      emptyPlans: 'Тарифы временно недоступны.', emptyProducts: 'Пакеты скоро появятся.', pay: 'Оплатить', payProduct: 'Оплатить {title}',
      footer: 'OracleAI не хранит данные карты или ключи кошелька. По вопросам оплаты можно открыть историю заказов и обратиться в поддержку.',
      orders: 'История заказов', noOrders: 'Заказов пока нет.', retry: 'Повторить',
      loadFailed: 'Не удалось открыть оплату. Попробуй ещё раз.', starsUnavailable: 'Stars сейчас недоступны. Попробуй чуть позже.',
      cryptoUnavailable: 'Крипто-оплата сейчас недоступна. Попробуй чуть позже.', invoiceOpened: 'Счёт открыт в Telegram',
      paid: 'Оплата прошла — доступ уже открывается ✦', paymentPassed: 'Оплата подтверждена — доступ уже открывается ✦', paymentFailed: 'Telegram не подтвердил оплату. Попробуй ещё раз.', payProduct: 'Оплатить продукт',
      cryptoOpened: asset => `Счёт ${asset} открыт. После оплаты заказ появится в истории.`,
      statuses: { pending: 'ожидает оплаты', paid: 'оплачен', failed: 'ошибка', refunded: 'возвращён' },
    },
    en: {
      space: 'YOUR SPACE', choose: 'Choose your rhythm', heroCopy: 'No unnecessary steps. Access opens only after the provider confirms your payment.',
      balance: 'Your Crystals', balanceHint: 'for one-off readings', paymentMethod: 'Payment method',
      stars: 'Telegram Stars', starsCopy: 'Fast inside Telegram', crypto: 'TON and crypto', cryptoCopy: 'TON, USDT or BTC',
      wallet: 'CRYPTO WALLET', payWith: 'Pay with', protectedInvoice: 'Protected invoice',
      cryptoNote: 'The server fixes the amount in USD; Crypto Pay shows the equivalent in your chosen coin. No seed phrase or private key is needed.',
      starsTrustTitle: 'Pay with Stars inside Telegram', starsTrustCopy: 'No cards or extra data. Subscriptions and purchases activate only after successful payment.',
      subscription: 'SUBSCRIPTION', depth: 'More depth every day', planCountOne: 'plan', planCountFew: 'plans', planCountMany: 'plans',
      oneOff: 'ONE-OFF PACKS', reserve: 'A reserve for important questions', defaultPlan: 'Subscription', defaultPlanCopy: 'More depth, memory and a personal rhythm.', perPeriod: 'per period',
      popular: 'MOST POPULAR', openStars: 'Open Stars checkout', busy: 'Creating a protected order…',
      emptyPlans: 'Plans are temporarily unavailable.', emptyProducts: 'Packs are coming soon.', pay: 'Pay', payProduct: 'Pay for {title}',
      footer: 'OracleAI does not store card data or wallet keys. Open your order history or contact support with payment questions.',
      orders: 'Order history', noOrders: 'No orders yet.', retry: 'Retry',
      loadFailed: 'Payment could not be opened. Please try again.', starsUnavailable: 'Stars are temporarily unavailable. Please try again later.',
      cryptoUnavailable: 'Crypto payments are temporarily unavailable. Please try again later.', invoiceOpened: 'Invoice opened in Telegram',
      paid: 'Payment received — access is opening ✦', paymentPassed: 'Payment confirmed — access is opening ✦', paymentFailed: 'Telegram did not confirm the payment. Please try again.', payProduct: 'Pay for product',
      cryptoOpened: asset => `Invoice for ${asset} opened. Your order will appear in history after payment.`,
      statuses: { pending: 'pending', paid: 'paid', failed: 'failed', refunded: 'refunded' },
    },
  };

  const PAYMENT_CATALOG = {
    en: {
      plans: {
        free: { title: '✦ Spark', tagline: 'A gentle return: your daily card and one question a week' },
        guide: { title: '✦✦ Guiding', tagline: 'One question and a personal forecast every day' },
        vip: { title: '✦✦✦ VIP Oracle', tagline: 'A personal astrologer 24/7 — less than one consultation' },
        vip_year: { title: '✦✦✦ VIP for a year', tagline: 'Eight months for the price of twelve' },
        concierge: { title: '👑 Concierge', tagline: 'Unlimited access, priority and exclusive readings' },
      },
      products: {
        spread_one: { title: 'Reading “One card”', description: 'A quick, honest answer to one question' },
        spread_three: { title: 'Reading “Past · Present · Future”', description: 'The classic: where it came from, where you are, where it leads' },
        spread_love: { title: 'Reading “Relationships”', description: 'You, them, what is between you and one piece of advice' },
        spread_choice: { title: 'Reading “Choose between two”', description: 'Two paths, their fruits and what you do not yet see' },
        spread_money: { title: 'Reading “Money and work”', description: 'Your resource, what slows you down and the first step' },
        spread_career: { title: 'Reading “Career and path”', description: 'Where you are, what blocks growth and where the path leads' },
        spread_work: { title: 'Reading “Work tension”', description: 'Whom to hear, what to avoid and how to leave with dignity' },
        spread_celtic: { title: 'Reading “Celtic Cross”', description: 'Ten cards for the full picture of a situation' },
        spread_year: { title: 'Reading “Wheel of the year”', description: 'Twelve cards — one for each month' },
        report_natal: { title: 'Full natal chart reading', description: 'Planets by houses, aspects, strengths and tasks — a long-form reading' },
        report_matrix: { title: 'Destiny Matrix — full reading', description: 'Every arcana: purpose, money, love and family patterns' },
        report_synastry: { title: 'Synastry: relationship reading', description: 'Elements, attraction, friction and the path ahead' },
        report_career: { title: 'Career and purpose — reading', description: 'Your strengths, what slows you down and when to act' },
        report_solar: { title: 'Yearly card forecast', description: 'Next year’s themes, peaks and the best months for decisions' },
        question_1: { title: '+1 question for the Oracle', description: 'One question beyond the daily limit' },
        question_5: { title: '+5 questions for the Oracle', description: 'Five questions beyond the limit, valid for one month' },
        crystals_100: { title: '100 ✦ Crystals', description: 'Currency for emergency magic' },
        crystals_250: { title: '250 ✦ Crystals', description: '15% better value' },
        crystals_600: { title: '600 ✦ Crystals', description: 'Best value + bonus' },
      },
    },
  };

  const payLang = () => oracleLang() === 'en' ? 'en' : 'ru';
  const payT = (key, fallback = '') => PAYMENT_I18N[payLang()][key] || fallback || key;
  const planCount = count => {
    const key = count === 1 ? 'planCountOne' : (payLang() === 'en' ? 'planCountFew' : (count >= 2 && count <= 4 ? 'planCountFew' : 'planCountMany'));
    return `${count} ${payT(key)}`;
  };
  const catalogText = (item, field, fallback = '') => {
    const key = item && (item.code || item.sku);
    const translated = PAYMENT_CATALOG[payLang()]?.plans?.[key]?.[field]
      || PAYMENT_CATALOG[payLang()]?.products?.[key]?.[field];
    return translated || (item && item[field]) || fallback || key || '';
  };
  const statusText = status => PAYMENT_I18N[payLang()].statuses?.[status] || status || '—';
  const pt = payT;
  const pf = (key, values = {}) => Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)), pt(key));
  const orderStatus = status => PAYMENT_I18N[payLang()].statuses?.[status] || status || 'pending';

  const money = value => {
    const number = Number(value || 0);
    return Number.isFinite(number) && number > 0 ? `$${number.toFixed(2)}` : '—';
  };

  const stars = value => `✦ ${Number(value || 0).toLocaleString(payLang() === 'en' ? 'en-US' : 'ru-RU')}`;
  const paymentState = () => app.payment || (app.payment = {
    data: null, loading: false, error: '', method: 'stars', asset: 'TON', billingPeriod: 'monthly', busy: '', orders: [],
  });

  function activeAsset() {
    const state = paymentState();
    return ASSETS.find(item => item.code === state.asset) || ASSETS[0];
  }

  function methodCard(method, icon, title, copy, active) {
    return `<button class="pay-method${active ? ' is-active' : ''}" data-act="payment-method" data-method="${method}" aria-pressed="${active ? 'true' : 'false'}">
      <span class="pay-method__icon">${icon}</span><span class="pay-method__copy"><b>${title}</b><small>${copy}</small></span><span class="pay-method__check">${active ? '✓' : ''}</span>
    </button>`;
  }

  function planCard(plan, featured) {
    const annual = paymentState().billingPeriod === 'annual';
    const price = Number((annual ? plan.annual_price_stars : plan.price_stars) || 0);
    const code = plan.code || plan.sku || 'ACCESS';
    return `<article class="pay-plan${featured ? ' pay-plan--featured' : ''}">
      ${featured ? `<span class="pay-plan__badge">${esc(payT('popular'))}</span>` : ''}
      <div class="pay-plan__top"><div><span class="pay-kicker">${esc(code)}</span><h3>${esc(catalogText(plan, 'title', payT('defaultPlan')))}</h3></div><span class="pay-plan__sigil">✦</span></div>
      <p>${esc(catalogText(plan, 'tagline', payT('defaultPlanCopy')))}</p>
      <div class="pay-price"><strong>${price ? stars(price) : (payLang() === 'en' ? 'By request' : 'По запросу')}</strong><small>${annual ? (payLang() === 'en' ? 'per year' : 'за год') : esc(payT('perPeriod'))}</small></div>
      <button class="btn btn-primary pay-cta" data-act="pay-stars" data-plan="${esc(code)}" ${price ? '' : 'disabled'}>${esc(payT('openStars'))}</button>
    </article>`;
  }

  function productCard(product, method, asset) {
    const crypto = method !== 'stars';
    const price = crypto ? money(product.price_usd || 0) : stars(product.price_stars || 0);
    const sku = esc(product.sku || '');
    const title = catalogText(product, 'title', payLang() === 'en' ? 'Pack' : 'Пакет');
    const description = catalogText(product, 'description', payLang() === 'en' ? 'Add a little reserve for important questions and readings.' : 'Добавь немного запаса для важных вопросов и разборов.');
    const disabled = crypto ? !product.price_usd : !product.price_stars;
    return `<article class="pay-product">
      <div class="pay-product__icon">${crypto ? asset.icon : '✦'}</div>
      <div class="pay-product__body"><h3>${esc(title)}</h3><p>${esc(description)}</p><span class="pay-product__meta">${crypto ? `${price} · ${asset.label}` : price}</span></div>
      <button class="pay-product__button" data-act="${crypto ? 'pay-crypto' : 'pay-stars'}" data-sku="${sku}" data-asset="${asset.code}" ${disabled ? 'disabled' : ''} aria-label="${esc(pf('payProduct', { title }))}">›</button>
    </article>`;
  }

  app.renderPayment = function (main) {
    const state = paymentState();
    const data = state.data || {};
    const method = state.method || 'stars';
    const asset = activeAsset();
    const canonical = data.catalog || {};
    const plans = (canonical.plans && canonical.plans.length ? canonical.plans : (data.plans || []))
      .filter(plan => plan.is_active !== 0 && plan.is_public !== 0);
    const legacyGroups = data.products && typeof data.products === 'object' ? data.products : data;
    const legacyProducts = Object.values(legacyGroups).filter(Array.isArray).flat();
    const canonicalProducts = [ ...(canonical.crystal_packs || []), ...(canonical.products || []) ];
    const allProducts = canonicalProducts.length ? canonicalProducts : legacyProducts;
    const crystalProducts = allProducts.filter(product => product.kind === 'crystals');
    const otherProducts = allProducts.filter(product => product.kind !== 'crystals');
    const busy = state.busy ? `<div class="pay-busy" role="status"><span class="loader-ring"></span><span>${esc(payT('busy'))}</span></div>` : '';
    const error = state.error ? `<div class="pay-alert pay-alert--error" role="alert">${esc(state.error)}<button class="btn btn-ghost" data-act="payment-retry">${esc(payT('retry'))}</button></div>` : '';
    const balance = Number(data.crystals || 0).toLocaleString(payLang() === 'en' ? 'en-US' : 'ru-RU');
    main.innerHTML = `<div class="screen pay-screen">
      <section class="pay-hero"><div class="pay-hero__orb">✦</div><div><span class="pay-kicker">${esc(payT('space'))}</span><h1>${esc(payT('choose'))}</h1><p>${esc(payT('heroCopy'))}</p></div></section>
      <section class="pay-balance"><span class="pay-balance__icon">✦</span><div><small>${esc(payT('balance'))}</small><strong>${balance}</strong></div><span class="pay-balance__hint">${esc(payT('balanceHint'))}</span></section>
      <div class="pay-methods" role="tablist" aria-label="${esc(payT('paymentMethod'))}">
        ${methodCard('stars', '★', payT('stars'), payT('starsCopy'), method === 'stars')}
        ${methodCard('crypto', '₿', payT('crypto'), payT('cryptoCopy'), method === 'crypto')}
      </div>
      ${method === 'crypto' ? `<section class="pay-asset-picker"><div class="pay-section-head"><div><span class="pay-kicker">${esc(payT('wallet'))}</span><h2>${esc(payT('payWith'))}</h2></div><span class="pay-safe">${esc(payT('protectedInvoice'))}</span></div><div class="pay-assets">${ASSETS.map(item => `<button class="pay-asset${item.code === asset.code ? ' is-active' : ''}" data-act="payment-asset" data-asset="${item.code}" aria-pressed="${item.code === asset.code ? 'true' : 'false'}"><b>${item.icon}</b><span>${item.label}</span></button>`).join('')}</div><p class="pay-note">${esc(asset.copy[payLang()])}<br>${esc(payT('cryptoNote'))}</p></section>` : `<section class="pay-trust"><span>✓</span><p><b>${esc(payT('starsTrustTitle'))}</b><br>${esc(payT('starsTrustCopy'))}</p></section>`}
      ${busy}${error}
      <section class="pay-section"><div class="pay-section-head"><div><span class="pay-kicker">${esc(payT('subscription'))}</span><h2>${esc(payT('depth'))}</h2></div><span class="pay-section-count">${esc(planCount(plans.length))}</span></div><div class="pay-period-toggle" role="tablist" aria-label="${payLang() === 'en' ? 'Billing period' : 'Период оплаты'}"><button class="btn btn-ghost ${state.billingPeriod === 'monthly' ? 'is-active' : ''}" data-act="payment-period" data-period="monthly">${payLang() === 'en' ? 'Monthly' : 'Месяц'}</button><button class="btn btn-ghost ${state.billingPeriod === 'annual' ? 'is-active' : ''}" data-act="payment-period" data-period="annual">${payLang() === 'en' ? 'Annual · save 2 months' : 'Год · экономия 2 месяцев'}</button></div><div class="pay-plans">${plans.length ? plans.map((plan, index) => planCard(plan, index === 1 || (plans.length === 1))).join('') : `<div class="pay-empty">${esc(payT('emptyPlans'))}</div>`}</div></section>
      <section class="pay-section"><div class="pay-section-head"><div><span class="pay-kicker">${esc(payT('oneOff'))}</span><h2>${esc(payT('reserve'))}</h2></div></div><div class="pay-products">${(method === 'crypto' ? crystalProducts : [...crystalProducts, ...otherProducts]).slice(0, 5).map(product => productCard(product, method, asset)).join('') || `<div class="pay-empty">${esc(payT('emptyProducts'))}</div>`}</div></section>
      <section class="pay-footer-note"><span>◌</span><p>${esc(payT('footer'))}</p><button class="btn btn-ghost" data-act="payment-orders">${esc(payT('orders'))}</button></section>
    </div>`;
  };

  app.loadPayments = async function () {
    const state = paymentState();
    state.loading = true; state.error = '';
    const main = document.getElementById('app-main');
    if (main) this.renderPayment(main);
    try {
      state.data = await api('/api/shop');
    } catch (e) {
      state.error = friendlyError(e, payT('loadFailed'));
    } finally {
      state.loading = false;
      if (this.view === 'payment' && main) this.renderPayment(main);
    }
  };

  app.goPayment = function () {
    this.view = 'payment';
    this.chat.key = null;
    this.renderNav();
    this.renderPayment(document.getElementById('app-main'));
    if (!paymentState().data && !paymentState().loading) this.loadPayments();
  };

  app.selectPaymentMethod = function (method) {
    const state = paymentState();
    state.method = method === 'crypto' ? 'crypto' : 'stars';
    state.error = '';
    this.renderPayment(document.getElementById('app-main'));
  };

  app.selectPaymentAsset = function (asset) {
    const state = paymentState();
    state.asset = ASSETS.some(item => item.code === asset) ? asset : 'TON';
    this.renderPayment(document.getElementById('app-main'));
  };

  app.selectPaymentPeriod = function (period) {
    const state = paymentState();
    state.billingPeriod = period === 'annual' ? 'annual' : 'monthly';
    state.error = '';
    this.renderPayment(document.getElementById('app-main'));
  };

  async function openProviderLink(link) {
    if (!link) throw new Error('Ссылка на оплату не создана');
    const telegram = tg && tg();
    if (telegram && typeof telegram.openLink === 'function') telegram.openLink(link);
    else window.open(link, '_blank', 'noopener,noreferrer');
  }

  app.payStars = async function (el, data) {
    const state = paymentState();
    if (state.busy) return;
    state.busy = 'stars'; state.error = '';
    this.renderPayment(document.getElementById('app-main'));
    try {
      const body = data.plan ? { plan: data.plan, billing_period: (paymentState().billingPeriod || 'monthly') } : { sku: data.sku };
      const invoice = await api('/api/shop/invoice', { method: 'POST', body: JSON.stringify(body) });
      const telegram = tg && tg();
      if (telegram && typeof telegram.openInvoice === 'function') {
        telegram.openInvoice(invoice.link, status => {
          if (status === 'paid') this.toast(payT('paid'));
          else if (status === 'failed') this.toast(payT('paymentFailed'));
          state.busy = ''; this.loadPayments();
        });
      } else {
        await openProviderLink(invoice.link);
        this.toast(payT('invoiceOpened'));
        state.busy = '';
      }
    } catch (e) {
      state.busy = ''; state.error = friendlyError(e, payT('starsUnavailable'));
    }
    if (this.view === 'payment') this.renderPayment(document.getElementById('app-main'));
  };

  app.payCrypto = async function (el, data) {
    const state = paymentState();
    if (state.busy) return;
    const asset = ASSETS.some(item => item.code === data.asset) ? data.asset : state.asset;
    state.busy = 'crypto'; state.error = '';
    this.renderPayment(document.getElementById('app-main'));
    try {
      const invoice = await api('/api/shop/crypto-invoice', {
        method: 'POST', body: JSON.stringify({ sku: data.sku, asset }),
      });
      await openProviderLink(invoice.link);
      this.toast(PAYMENT_I18N[payLang()].cryptoOpened(invoice.asset || asset));
    } catch (e) {
      state.error = friendlyError(e, payT('cryptoUnavailable'));
    } finally {
      state.busy = '';
      if (this.view === 'payment') this.renderPayment(document.getElementById('app-main'));
    }
  };

  app.retryPayments = function () { paymentState().data = null; this.loadPayments(); };

  app.showPaymentOrders = async function () {
    this.showModal(`<h3>${esc(payT('orders'))}</h3><button class="m-close" data-act="modal-close" aria-label="${esc(payT('orders'))}">✕</button><div id="payment-history-body" class="pay-orders"><div class="loader-ring"></div></div>`);
    await this.loadPaymentHistory();
  };

  app.loadPaymentHistory = async function () {
    const body = document.getElementById('payment-history-body');
    if (!body) return;
    try {
      const orders = await api('/api/shop/payment-history');
      const labels = payLang() === 'en'
        ? { created: 'Order created', paid: 'Payment confirmed', entitlement: 'Access or purchase granted', refunded: 'Refund issued' }
        : { created: 'Заказ создан', paid: 'Платёж подтверждён', entitlement: 'Доступ или покупка выданы', refunded: 'Оформлен возврат' };
      const pendingStage = payLang() === 'en' ? 'Awaiting server confirmation' : 'Ожидается подтверждение сервера';
      const awaitingProvider = payLang() === 'en' ? 'awaiting' : 'ожидается';
      const rows = (orders || []).slice(0, 10).map(order => `<article class="pay-order pay-order--timeline"><div class="pay-order__head"><strong>${esc(catalogText({ sku: order.sku }, 'title', order.title || (payLang() === 'en' ? 'Purchase' : 'Покупка')))}</strong><span>${esc(orderStatus(order.status))}</span></div><div class="pay-order__meta">${order.amount_stars ? stars(order.amount_stars) : '—'} · ${esc(order.provider || awaitingProvider)}</div><ol class="pay-timeline">${(order.stages || []).map(stage => `<li class="pay-timeline__item is-${esc(stage.state)}"><span class="pay-timeline__dot" aria-hidden="true"></span><span><b>${esc(labels[stage.key] || stage.key)}</b><small>${stage.at ? esc(new Date(stage.at).toLocaleString(payLang() === 'en' ? 'en-US' : 'ru-RU')) : pendingStage}</small></span></li>`).join('')}</ol></article>`).join('');
      body.innerHTML = rows || `<p class="pay-note">${esc(payT('noOrders'))}</p>`;
      if (rows) body.insertAdjacentHTML('afterbegin', `<p class="pay-note">${payLang() === 'en' ? 'Status is updated by the server. Closing this window does not change the payment.' : 'Статус обновляется с сервера. Закрытие окна не меняет платёж.'}</p>`);
    } catch (e) { body.innerHTML = `<p class="pay-note">${esc(friendlyError(e, payLang() === 'en' ? 'Order history is temporarily unavailable.' : 'История оплат временно недоступна.'))}</p><button class="btn btn-ghost" data-act="payment-history-refresh">${esc(payT('retry'))}</button>`; }
  };
}());
