(function () {
  'use strict';

  const PALM_TOPICS = {
    heart_line: 'Линия сердца', head_line: 'Линия головы', life_line: 'Линия жизни',
    fate_line: 'Линия судьбы', sun_line: 'Линия Солнца', relationship_line: 'Линии отношений',
    mount_venus: 'Холм Венеры', mount_moon: 'Холм Луны', fingers: 'Пальцы', unknown: 'Наблюдение'
  };
  const PALM_TOPICS_EN = {
    heart_line: 'Heart line', head_line: 'Head line', life_line: 'Life line', fate_line: 'Fate line',
    sun_line: 'Sun line', relationship_line: 'Relationship lines', mount_venus: 'Mount of Venus',
    mount_moon: 'Mount of Moon', fingers: 'Fingers', unknown: 'Observation'
  };
  const PALM_DETAIL_LABELS = {
    life: 'Линия жизни', head: 'Линия головы', heart: 'Линия сердца', fate: 'Линия судьбы', sun: 'Линия Солнца',
    relationship: 'Линии отношений', children: 'Линии детей', travel: 'Линии путешествий', mercury: 'Линия Меркурия',
    venus: 'Холм Венеры', jupiter: 'Холм Юпитера', saturn: 'Холм Сатурна', apollo: 'Холм Аполлона',
    moon: 'Холм Луны', mars: 'Холм Марса', thumb: 'Большой палец', index: 'Указательный палец',
    middle: 'Средний палец', ring: 'Безымянный палец', little: 'Мизинец'
  };
  const PALM_DETAIL_LABELS_EN = {
    life: 'Life line', head: 'Head line', heart: 'Heart line', fate: 'Fate line', sun: 'Sun line',
    relationship: 'Relationship lines', children: 'Children lines', travel: 'Travel lines', mercury: 'Mercury line',
    venus: 'Mount of Venus', jupiter: 'Mount of Jupiter', saturn: 'Mount of Saturn', apollo: 'Mount of Apollo',
    moon: 'Mount of Moon', mars: 'Mount of Mars', thumb: 'Thumb', index: 'Index finger',
    middle: 'Middle finger', ring: 'Ring finger', little: 'Little finger'
  };
  const VISIBILITY = { clear: 'видно', partial: 'частично', unclear: 'неясно', not_visible: 'не видно' };
  const VISIBILITY_EN = { clear: 'visible', partial: 'partial', unclear: 'unclear', not_visible: 'not visible' };
  const PALM_I18N = {
    ru: {
      title: 'Чтение ладони', subtitle: 'Я опишу только видимые зоны на фото и свяжу их с вопросами, важными именно тебе.',
      guideTitle: 'Как снять ладонь', guide: 'Нужно 2 фото: ① раскрытая ладонь целиком, ② ладонь ребром (согнутая). Камера сверху, ровный свет, без бликов, фильтров и украшений, вся ладонь от запястья до кончиков пальцев в кадре.',
      full: 'целиком', glare: 'без бликов', fingers: 'пальцы свободны', camera: 'Сфотографировать ладонь', cameraSmall: 'Камера · один кадр', gallery: 'Выбрать из галереи', gallerySmall: 'JPEG, PNG или WebP · до 8 МБ',
      folded: '② Ладонь ребром: согни пальцы к центру и поверни кисть боком к камере — так видны линии отношений, детей и путешествий.', privacy: 'Фото используется для текущего разбора. Сохраняются только структурированные observations и технический fingerprint; исходное изображение не сохраняется. Удалить чтение можно из истории.',
      disclaimer: 'Мира читает только различимые линии и зоны: чем яснее кадр, тем глубже разбор. Раскрытая ладонь даёт линии жизни/головы/сердца/судьбы, холмы и пальцы; кадр ребром — линии отношений и путешествий.', looking: 'Смотрю на линии', checking: 'Проверяю качество кадра и отделяю наблюдаемое от интерпретации…', photo: 'Фото', quality: 'Качество', observations: 'Наблюдения', ariaStep: 'Шаг 2 из 3: фото — качество — наблюдения',
      result: 'Что видно на ладони', needs: 'Нужен более ясный кадр', qualityLabel: 'Качество кадра', boundaries: 'Границы чтения', prompts: 'Вопросы к себе', more: 'Подробнее с Мирой', newPhoto: 'Новое фото', retry: 'Переснять фото', change: 'Изменить', usable: 'свет/резкость пригодны', checkFrame: 'нужна проверка кадра', precheck: 'детерминированная проверка изображения', viewUnknown: 'ракурс не указан', details: 'Показать карту зон и техник',
      typeError: 'Выбери JPEG, PNG или WebP. Другие форматы не отправляются.', sizeError: 'Выбери изображение до 8 МБ.', failTitle: 'Не получилось прочитать фото', failCopy: 'Проверь кадр и попробуй ещё раз.',
      privacyLabel: 'Приватность изображения', detected: 'ладонь распознана', notDetected: 'ладонь не подтверждена', observed: 'наблюдается', inferred: 'осторожная интерпретация', unknown: 'не подтверждено', notSupported: 'не поддерживается', openPalm: 'раскрытая ладонь', foldedEdge: 'согнутый край',
      photoAdvice: 'Какой кадр дослать', sourceLabel: 'Источник фотографии', noDetails: 'На этом кадре пока недостаточно деталей для уверенного чтения.', noDescription: 'Описание отсутствует', noDetailDescription: 'Отдельное описание не передано', requestFailed: 'Не удалось прочитать фото',
    },
    en: {
      title: 'Palm reading', subtitle: 'I will describe only visible zones in the photo and connect them to questions that matter to you.',
      guideTitle: 'How to photograph your palm', guide: 'Send 2 photos: ① whole open palm, ② palm edge-on (folded). Camera from above, even light, no glare, filters or jewellery, the whole palm from wrist to fingertips in frame.',
      full: 'whole palm', glare: 'no glare', fingers: 'fingers clear', camera: 'Take a palm photo', cameraSmall: 'Camera · one frame', gallery: 'Choose from gallery', gallerySmall: 'JPEG, PNG or WebP · up to 8 MB',
      folded: '② Palm edge-on: fold your fingers toward the centre and turn the hand sideways to the camera — this shows relationship, children and travel lines.', privacy: 'The photo is used for the current reading. Only structured observations and a technical fingerprint are retained; the original image is not stored. You can delete the reading from history.',
      disclaimer: 'Mira reads only distinguishable lines and zones: the clearer the frame, the deeper the reflection. An open palm reveals life/head/heart/fate lines, mounts and fingers; the edge-on shot shows relationship and travel lines.', looking: 'Looking at the lines', checking: 'Checking image quality and separating observations from interpretation…', photo: 'Photo', quality: 'Quality', observations: 'Observations', ariaStep: 'Step 2 of 3: photo — quality — observations',
      result: 'What is visible on your palm', needs: 'A clearer photo is needed', qualityLabel: 'Image quality', boundaries: 'Reading boundaries', prompts: 'Questions for reflection', more: 'Ask Mira for more', newPhoto: 'New photo', retry: 'Retake photo', change: 'Change', usable: 'light/sharpness are usable', checkFrame: 'frame needs checking', precheck: 'deterministic image check', viewUnknown: 'view not specified', details: 'Show zone and technique map',
      typeError: 'Choose JPEG, PNG or WebP. Other formats are not sent.', sizeError: 'Choose an image up to 8 MB.', failTitle: 'The photo could not be read', failCopy: 'Check the frame and try again.',
      privacyLabel: 'Image privacy', detected: 'palm detected', notDetected: 'palm not confirmed', observed: 'observed', inferred: 'qualified inference', unknown: 'not confirmed', notSupported: 'not supported', openPalm: 'open palm', foldedEdge: 'folded edge',
      photoAdvice: 'Which photo to send next', sourceLabel: 'Photo source', noDetails: 'This frame does not yet contain enough detail for a confident reading.', noDescription: 'No description available', noDetailDescription: 'No separate description was provided', requestFailed: 'The photo could not be read',
    },
  };
  const pt = key => (PALM_I18N[oracleLang()] || PALM_I18N.ru)[key] || PALM_I18N.ru[key] || key;
  const evidenceStateLabel = state => ({ observed: pt('observed'), inferred: pt('inferred'), unknown: pt('unknown'), not_supported: pt('notSupported') }[state] || pt('unknown'));
  const viewTypeLabel = view => ({ open_palm: pt('openPalm'), folded_edge: pt('foldedEdge') }[view] || pt('viewUnknown'));
  const palmGuide = () => `
    <div class="palm-guide" role="note">
      <b>${esc(pt('guideTitle'))}</b>
      <span>${esc(pt('guide'))}</span>
      <div class="palm-guide__steps"><i>1</i><i>2</i><i>3</i><small>${esc(pt('full'))}</small><small>${esc(pt('glare'))}</small><small>${esc(pt('fingers'))}</small></div>
    </div>`;

  app.featurePalm = function () {
    if (this.chat.pending && this.chat.pending.kind === 'palm') return;
    this.chat.pending = { kind: 'palm', loading: false, html: app.palmPickerHtml() };
    this.renderChat(document.getElementById('app-main'));
  };

  app.palmPickerHtml = function () {
    const preview = this._palmPreview ? `<div class="palm-preview"><img src="${esc(this._palmPreview)}" alt="${esc(pt('title'))}"><button type="button" class="palm-preview__clear" data-act="tool-fn" data-fn="featurePalm">${esc(pt('change'))}</button></div>` : '';
    return `<section class="palm-result" aria-live="polite">
      <div class="w-title">✋ ${esc(pt('title'))}</div>
      <p class="w-sub">${esc(pt('subtitle'))}</p>
      ${preview}
      ${palmGuide()}
      <div class="palm-upload-actions" role="group" aria-label="${esc(pt('sourceLabel'))}">
        <label class="palm-upload palm-upload--primary" for="palm-camera">
          <span class="palm-upload__icon" aria-hidden="true">⌾</span>
          <b>${esc(pt('camera'))}</b>
          <small>${esc(pt('cameraSmall'))}</small>
        </label>
        <label class="palm-upload" for="palm-gallery">
          <span class="palm-upload__icon" aria-hidden="true">＋</span>
          <b>${esc(pt('gallery'))}</b>
          <small>${esc(pt('gallerySmall'))}</small>
        </label>
      </div>
      <input id="palm-camera" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" capture="environment" data-palm-input>
      <input id="palm-gallery" class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" data-palm-input>
      <p class="palm-disclaimer">${esc(pt('disclaimer'))}</p>
      <div class="palm-limitations"><b>${esc(pt('privacyLabel'))}</b><p>${esc(pt('privacy'))}</p></div>
    </section>`;
  };

  app.palmLoadingHtml = function () {
    const preview = this._palmPreview ? `<div class="palm-preview palm-preview--loading"><img src="${esc(this._palmPreview)}" alt="${esc(pt('title'))}"><span>◌</span></div>` : '';
    return `<section class="palm-result" role="status" aria-live="polite">
      <div class="w-title">✋ ${esc(pt('looking'))}</div>
      ${preview}
      <div class="seg-progress palm-progress" role="group" aria-label="${esc(pt('ariaStep'))}"><span class="is-on">${esc(pt('photo'))}</span><i class="is-on"></i><span class="is-on">${esc(pt('quality'))}</span><i></i><span>${esc(pt('observations'))}</span></div>
      <div class="palm-loading"><span></span><span></span><span></span></div>
      <p class="w-sub">${esc(pt('checking'))}</p>
    </section>`;
  };

  function textFromResult(result) {
    const narrative = (result.narrative || '').trim();
    if (narrative) {
      const obs = Array.isArray(result.observations) ? result.observations : [];
      const topics = obs.length
        ? `<div class="palm-narrative-topics">${obs.slice(0, 5).map(o => {
            const topic = (oracleLang() === 'en' ? PALM_TOPICS_EN[o.topic] : PALM_TOPICS[o.topic]) || o.topic || pt('unknown');
            return `<span>${esc(topic)}</span>`;
          }).join('')}</div>`
        : '';
      return `<p class="palm-narrative">${esc(narrative)}</p>${topics}`;
    }
    const obs = Array.isArray(result.observations) ? result.observations : [];
    if (!obs.length) return `<p class="palm-muted">${esc(pt('noDetails'))}</p>`;
    return obs.slice(0, 6).map(item => {
      const topic = (oracleLang() === 'en' ? PALM_TOPICS_EN[item.topic] : PALM_TOPICS[item.topic]) || item.topic || pt('unknown');
      const visibility = (oracleLang() === 'en' ? VISIBILITY_EN[item.visibility] : VISIBILITY[item.visibility]) || pt('unknown');
      const confidence = Math.round(Number(item.confidence || 0) * 100);
      return `
      <div class="palm-observation">
        <div><b>${esc(topic)}</b><span>${esc(visibility)} · ${esc(evidenceStateLabel(item.evidence_state))} · ${confidence}%</span></div>
        <div class="palm-confidence"><i style="width:${confidence}%"></i></div>
        <p>${esc(item.summary || pt('noDescription'))}</p>
      </div>`;
    }).join('');
  }

  function detailRows(result) {
    const labels = oracleLang() === 'en' ? PALM_DETAIL_LABELS_EN : PALM_DETAIL_LABELS;
    const items = [];
    ['lines', 'mounts', 'fingers'].forEach(group => {
      Object.entries(result[group] || {}).forEach(([key, value]) => {
        const values = Array.isArray(value) ? value : [value];
        values.forEach((detail, index) => {
          if (!detail || typeof detail !== 'object') return;
          items.push({ label: `${labels[key] || key}${values.length > 1 ? ` · ${index + 1}` : ''}`, detail });
        });
      });
    });
    return items.slice(0, 12).map(({ label, detail }) => {
      const visibility = (oracleLang() === 'en' ? VISIBILITY_EN[detail.visibility] : VISIBILITY[detail.visibility]) || pt('unknown');
      const confidence = Math.round(Number(detail.confidence || 0) * 100);
      return `<div class="palm-detail-row"><div><b>${esc(label)}</b><span>${esc(visibility)} · ${esc(evidenceStateLabel(detail.evidence_state))} · ${confidence}%</span></div><div class="palm-confidence"><i style="width:${confidence}%"></i></div><p>${esc(detail.summary || detail.shape || pt('noDetailDescription'))}</p></div>`;
    }).join('');
  }

  // DOM-002: при status=needs_photo рендерим конкретную инструкцию, какой
  // ракурс дослать (линии отношений/детей видны только на согнутой ладони) —
  // обещание промпта больше не висит без UX-пути.
  app.palmHtml = function (result) {
    this._palmResult = result;
    const q = result.image_quality || {};
    const pre = result.visual_precheck || {};
    const needs = result.status === 'needs_photo';
    const limitations = Array.isArray(result.limitations) ? result.limitations : [];
    const prompts = Array.isArray(result.interpretive_prompts) ? result.interpretive_prompts : [];
    const pa = result.photo_assessment || {};
    const detected = result.hand_detected ? pt('detected') : pt('notDetected');
    const preCopy = pre.width ? `${pre.width}×${pre.height} · ${pre.status === 'usable' ? pt('usable') : pt('checkFrame')}` : pt('precheck');
    const details = detailRows(result);
    return `<section class="palm-result" aria-live="polite">
      <div class="w-title">✋ ${needs ? esc(pt('needs')) : esc(pt('result'))}</div>
      <div class="palm-quality" style="--quality:${Math.round(Number(q.score || 0) * 100)}"><b>${esc(pt('qualityLabel'))}</b><span>${Math.round(Number(q.score || 0) * 100)}%</span></div>
      <div class="palm-evidence-strip"><span>◉ ${esc(detected)}</span><span>⌁ ${esc(viewTypeLabel(pa.view_type))}</span><span>✦ ${esc(preCopy)}</span></div>
      ${textFromResult(result)}
      ${details ? `<details class="palm-details"><summary>${esc(pt('details'))} <span>⌄</span></summary><div class="palm-detail-list">${details}</div></details>` : ''}
      ${needs && Array.isArray(pa.advice) && pa.advice.length ? `<div class="palm-limitations"><b>${esc(pt('photoAdvice'))}</b><p>${pa.advice.map(esc).join('<br>')}</p></div>` : ''}
      ${limitations.length ? `<div class="palm-limitations"><b>${esc(pt('boundaries'))}</b><p>${limitations.map(esc).join('<br>')}</p></div>` : ''}
      ${prompts.length ? `<div class="palm-prompts"><b>${esc(pt('prompts'))}</b>${prompts.slice(0, 3).map(p => `<p>“${esc(p)}”</p>`).join('')}</div>` : ''}
      <p class="palm-disclaimer">${esc(pt('disclaimer'))}</p>
      <div class="palm-limitations"><b>${esc(pt('privacyLabel'))}</b><p>${esc(pt('privacy'))}</p></div>
      <div class="palm-actions">
        ${needs
          ? `<button class="btn btn-ghost" data-act="tool-fn" data-fn="featurePalm">${esc(pt('retry'))}</button>`
          : `<button class="btn btn-primary" data-act="ask" data-chat="chiromant" data-q="${esc(oracleLang() === 'en' ? 'Explain my palm in more detail from this photo: lines, mounts and hand shape.' : 'Разбери мою ладонь подробнее по этому снимку: линии, холмы и тип руки.')}">${esc(pt('more'))}</button><button class="btn btn-ghost" data-act="tool-fn" data-fn="featurePalm">${esc(pt('newPhoto'))}</button>`}
      </div>
    </section>`;
  };

  app.refreshPalmLocale = function () {
    const pending = this.chat && this.chat.pending;
    if (!pending || pending.kind !== 'palm') return;
    if (pending.loading) pending.html = this.palmLoadingHtml();
    else if (this._palmResult) pending.html = this.palmHtml(this._palmResult);
    else pending.html = this.palmPickerHtml();
  };

  async function upload(file) {
    if (!file) return;
    const allowed = ['image/jpeg', 'image/png', 'image/webp'];
    if (file.type && !allowed.includes(file.type.toLowerCase())) {
      app._palmResult = null;
      app.chat.pending = { kind: 'palm', loading: false, html: `<section class="palm-result"><div class="w-title">✋ ${esc(pt('title'))}</div><p class="palm-muted">${esc(pt('typeError'))}</p><button class="btn btn-ghost" data-act="tool-fn" data-fn="featurePalm">${esc(pt('change'))}</button></section>` };
      app.renderChat(document.getElementById('app-main'));
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      app._palmResult = null;
      app.chat.pending = { kind: 'palm', loading: false, html: `<section class="palm-result"><div class="w-title">✋ ${esc(pt('needs'))}</div><p class="palm-muted">${esc(pt('sizeError'))}</p><button class="btn btn-ghost" data-act="tool-fn" data-fn="featurePalm">${esc(pt('retry'))}</button></section>` };
      app.renderChat(document.getElementById('app-main'));
      return;
    }
    const key = app.chat.key, view = app.view;
    try {
      if (app._palmObjectUrl) URL.revokeObjectURL(app._palmObjectUrl);
      app._palmObjectUrl = URL.createObjectURL(file);
      app._palmPreview = app._palmObjectUrl;
    } catch (e) { app._palmObjectUrl = ''; app._palmPreview = ''; }
    const pend = app.chat.pending = { kind: 'palm', loading: true, html: app.palmLoadingHtml() };
    app.renderChat(document.getElementById('app-main'));
    try {
      const devUser = new URLSearchParams(location.search).get('dev_user');
      const devHeaders = {};
      if (devUser) {
        const devKey = localStorage.getItem('oracle_dev_key');
        if (devKey) devHeaders['X-Dev-Key'] = devKey;
      }
      const response = await fetch('/api/palm' + (devUser ? '?dev_user=' + devUser : ''), {
        method: 'POST',
        headers: Object.assign({ 'Content-Type': file.type },
          authHeaders(), devHeaders),
        body: file,
      });
      let body = null;
      try { body = await response.json(); } catch (e) {}
      if (!response.ok) throw new Error((body && body.detail) || pt('requestFailed'));
      if (!widAlive(key, view, pend)) return;
      app._palmResult = body;
      app.chat.pending = { kind: 'palm', loading: false, html: app.palmHtml(body) };
      haptic('success');
    } catch (e) {
      if (!widAlive(key, view, pend)) return;
      app._palmResult = null;
      app.chat.pending = { kind: 'palm', loading: false, html: `<section class="palm-result"><div class="w-title">✋ ${esc(pt('failTitle'))}</div><p class="palm-muted">${esc(friendlyError(e, pt('failCopy')))}</p>${palmGuide()}<button class="btn btn-ghost" data-act="tool-fn" data-fn="featurePalm">${esc(pt('retry'))}</button></section>` };
      haptic('error');
    }
    app.renderChat(document.getElementById('app-main'));
  }

  document.addEventListener('change', e => {
    const input = e.target && e.target.matches && e.target.matches('[data-palm-input]') ? e.target : null;
    if (input && input.files && input.files[0]) {
      const file = input.files[0];
      input.value = '';
      upload(file);
    }
  });
}());
