(function () {
  'use strict';

  const PLACEMENTS = [
    { code: 'moon_sign', icon: '☽', title: 'Луна', sub: 'эмоции и безопасность', prompt: 'Что мой Лунный знак говорит о моих эмоциональных потребностях?' },
    { code: 'rising_sign', icon: '↗', title: 'Асцендент', sub: 'первое впечатление', prompt: 'Объясни мой Асцендент и как я проявляюсь в мире.' },
    { code: 'venus_sign', icon: '♀', title: 'Венера', sub: 'ценности и близость', prompt: 'Что показывает моя Венера в любви и в том, что мне нравится?' },
    { code: 'mars_sign', icon: '♂', title: 'Марс', sub: 'действие и границы', prompt: 'Как мой Марс помогает мне действовать и защищать свои границы?' },
    { code: 'mercury_sign', icon: '☿', title: 'Меркурий', sub: 'мысль и речь', prompt: 'Как мой Меркурий влияет на мой стиль общения и решений?' },
    { code: 'jupiter_sign', icon: '♃', title: 'Юпитер', sub: 'рост и возможности', prompt: 'Где мой Юпитер приглашает меня расти и учиться?' },
    { code: 'saturn_sign', icon: '♄', title: 'Сатурн', sub: 'границы и мастерство', prompt: 'Какой навык помогает мне взрослее обращаться с Сатурном?' },
    { code: 'chiron_sign', icon: '⚷', title: 'Хирон', sub: 'уязвимость и ресурс', prompt: 'Как бережно исследовать тему моего Хирона?' },
    { code: 'juno_sign', icon: '⚭', title: 'Джуно', sub: 'доверие и союз', prompt: 'Что мой знак Джуно говорит о доверии и договорённостях?' },
    { code: 'asteroid_sign', icon: '✦', title: 'Астероиды', sub: 'забота и фокус', prompt: 'Что показывают мои Ceres, Vesta и Pallas?' },
    { code: 'north_node_sign', icon: '☊', title: 'Северный узел', sub: 'направление роста', prompt: 'Как раскрывается направление моего Северного узла и какой шаг ведёт меня вперёд?' },
    { code: 'south_node_sign', icon: '☋', title: 'Южный узел', sub: 'знакомые стратегии', prompt: 'Какие привычные стратегии показывает мой Южный узел?' },
    { code: 'uranus_sign', icon: '♅', title: 'Уран', sub: 'свобода и перемены', prompt: 'Как мой Уран связан со свободой и нестандартностью?' },
    { code: 'neptune_sign', icon: '♆', title: 'Нептун', sub: 'воображение и идеалы', prompt: 'Где мой Нептун просит яснее видеть границы?' },
    { code: 'pluto_sign', icon: '♇', title: 'Плутон', sub: 'трансформация', prompt: 'Что мой Плутон помогает мне перестроить глубже всего?' },
    { code: 'life_path', icon: '№', title: 'Жизненный путь', sub: 'число и повторяющиеся темы', prompt: 'Что моё число жизненного пути может подсветить в выборе целей?' },
    { code: 'chinese_zodiac', icon: '龍', title: 'Китайский зодиак', sub: 'животное и элемент года', prompt: 'Что мой китайский знак и элемент говорят о моём темпераменте?' },
  ];

  const cardFor = code => PLACEMENTS.find(item => item.code === code) || PLACEMENTS[0];
  const labelFor = code => cardFor(code).title;

  function resultValue(result) {
    if (!result) return '<p class="placement-muted">Выбери ориентир — я рассчитаю его по твоим данным рождения.</p>';
    if (result.error) return `<div class="placement-locked"><span>◌</span><div><b>Нужно больше точности</b><p>${esc(result.error)}</p><small>Это не ошибка карты: точность важнее красивого ответа.</small></div></div>`;
    if (Array.isArray(result.points)) {
      return `<div class="placement-points">${result.points.map(point => `
        <div class="placement-point">
          <div class="placement-point__head"><b>${esc(point.point || point.label)}</b><span>${esc(point.symbol || '')} ${esc(point.sign || '—')}</span></div>
          <div class="placement-point__meta">${point.degree != null ? `${esc(point.degree)}°` : ''}${point.element ? ` · ${esc(point.element)}` : ''}</div>
        </div>`).join('')}</div>`;
    }
    if (result.value != null) {
      return `<div class="placement-number"><span>${esc(result.value)}</span><div><b>Твоё число жизненного пути</b><small>${result.master_number ? 'Мастер-число · не сводим его дальше' : 'Редукция даты рождения'}</small></div></div>`;
    }
    if (result.animal) {
      return `<div class="placement-zodiac"><span>${esc(result.animal)}</span><div><b>${esc(result.element)} · ${esc(result.lunar_year)}</b><small>${result.boundary_adjusted ? 'Дата попала до китайского Нового года' : 'Год определён по лунно-солнечному календарю'}</small></div></div>`;
    }
    return `<div class="placement-sign"><span>${esc(result.symbol || '✦')}</span><div><b>${esc(result.sign || '—')}</b><small>${result.degree != null ? `${esc(result.degree)}° · ` : ''}${esc(result.precision === 'exact' ? 'точное время и место' : 'дата без подтверждённого времени')}</small></div></div>`;
  }

  function cardsHtml(selected) {
    return PLACEMENTS.map(item => `
      <button class="placement-card ${item.code === selected ? 'is-selected' : ''}" type="button" data-placement-code="${esc(item.code)}" aria-pressed="${item.code === selected ? 'true' : 'false'}">
        <span class="placement-card__icon" aria-hidden="true">${esc(item.icon)}</span>
        <span class="placement-card__copy"><b>${esc(item.title)}</b><small>${esc(item.sub)}</small></span>
        <span class="placement-card__arrow" aria-hidden="true">›</span>
      </button>`).join('');
  }

  app.featurePlacements = function () {
    if (this.chat.pending && this.chat.pending.kind === 'placements') return;
    this.placementState = { selected: 'moon_sign', result: null, loading: false };
    this.chat.pending = { kind: 'placements', loading: false, html: app.placementsHtml() };
    this.renderChat(document.getElementById('app-main'));
  };

  app.placementsHtml = function () {
    const state = this.placementState || { selected: 'moon_sign', result: null };
    const item = cardFor(state.selected);
    return `<section class="placement-explorer" aria-live="polite">
      <div class="placement-hero">
        <div class="placement-hero__eyebrow">ОРИЕНТИРЫ ТВОЕЙ КАРТЫ</div>
        <div class="placement-hero__title"><span>✦</span><div><h2>Не одна карта —<br><em>много способов</em> понять себя</h2><p>Выбери одну точку. Сначала — точный факт, затем — спокойный разговор с Уранией.</p></div></div>
        <div class="placement-trust"><span>◈</span> расчёт отдельно · интерпретация отдельно <span>·</span> ясный вектор роста</div>
      </div>
      <div class="placement-result-card">
        <div class="placement-result-card__top"><div><span class="placement-result-card__kicker">СЕЙЧАС СМОТРИМ</span><h3>${esc(item.icon)} ${esc(item.title)}</h3><p>${esc(item.sub)}</p></div><span class="placement-result-card__badge">${state.result ? (state.result.precision === 'exact' ? 'точно' : 'ориентир') : 'готово'}</span></div>
        ${state.loading ? '<div class="placement-loading"><i></i><i></i><i></i><span>Собираю твой точный ориентир…</span></div>' : resultValue(state.result)}
        <div class="placement-result-card__actions"><button class="btn btn-primary" type="button" data-act="fill" data-val="${esc(item.prompt)}">Спросить Уранию</button><span>Один факт · один следующий вопрос</span></div>
      </div>
      <div class="placement-section-head"><div><b>Все 17 ориентиров</b><small>Планеты, узлы, астероиды и числа</small></div><span>${PLACEMENTS.length}</span></div>
      <div class="placement-grid">${cardsHtml(state.selected)}</div>
    </section>`;
  };

  app.calculatePlacement = async function (code) {
    if (!code || (this.placementState && this.placementState.loading)) return;
    const key = this.chat.key, view = this.view;
    this.placementState = Object.assign({}, this.placementState, { selected: code, result: null, loading: true });
    const pend = this.chat.pending = { kind: 'placements', loading: true, html: app.placementsHtml() };
    this.renderChat(document.getElementById('app-main'));
    try {
      const body = await api('/api/placements/calculate', { method: 'POST', body: JSON.stringify({ placement: code }) });
      if (!widAlive(key, view, pend)) return;
      this.placementState = Object.assign({}, this.placementState, { result: body.result, loading: false });
      this.chat.pending = { kind: 'placements', loading: false, html: app.placementsHtml() };
      haptic('success');
    } catch (error) {
      if (!widAlive(key, view, pend)) return;
      this.placementState = Object.assign({}, this.placementState, { loading: false, result: { error: friendlyError(error, 'Не удалось получить расчёт. Попробуй ещё раз.') } });
      this.chat.pending = { kind: 'placements', loading: false, html: app.placementsHtml() };
      haptic('error');
    }
    this.renderChat(document.getElementById('app-main'));
  };

  document.addEventListener('click', event => {
    const target = event.target && event.target.closest ? event.target.closest('[data-placement-code]') : null;
    if (!target) return;
    event.preventDefault();
    tactile('select');
    app.calculatePlacement(target.dataset.placementCode);
  });
}());
