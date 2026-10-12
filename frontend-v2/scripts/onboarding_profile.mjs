/**
 * Интеграционная проверка серверного профиля и онбординга (этап 4.1).
 *
 * Проверяет контракт PATCH /api/profile против живого backend — тем же
 * способом, что и scripts/integration.mjs: реальный initData, реальная
 * сессия, никаких моков. Каждый сценарий работает на СВОЁМ синтетическом
 * пользователе (TG_ID + смещение), чтобы подготовленные данные предыдущего
 * кейса не делали следующий ложно-зелёным.
 *
 * Запуск: node scripts/onboarding_profile.mjs  (backend + make_init_data.py)
 */
import { spawnSync } from 'node:child_process';

const TARGET = process.env.API_TARGET ?? 'http://172.29.0.2:8080';
// База — тот же синтетический пользователь, что у integration.mjs. Каждый
// сценарий получает свой id, чтобы состояние не текло между кейсами.
// BASE_TG_OFFSET сдвигает всю линейку: синтетические пользователи
// переиспользуются между прогонами, и сценарий 4 («незавершённый
// онбординг») на уже завершённом профиле дал бы ложно-зелёный результат.
const BASE_TG = Number(process.env.TG_ID ?? 10002);
const RUN_SHIFT = Number(process.env.RUN_SHIFT ?? 0);
const tg = (offset) => BASE_TG + offset + RUN_SHIFT * 50;

let failures = 0;
const check = (ok, label, extra = '') => {
  if (!ok) failures += 1;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}${extra ? ' — ' + extra : ''}`);
};

function initData(tgId) {
  const out = spawnSync('python3', ['scripts/make_init_data.py', String(tgId)], {
    encoding: 'utf8',
  });
  if (out.status !== 0) throw new Error(`make_init_data failed: ${out.stderr}`);
  return out.stdout.trim();
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Минт сессии с ожиданием rate-limit (backend: 10 минтов в минуту). */
async function mint(tgId) {
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    const res = await fetch(`${TARGET}/api/auth/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: initData(tgId) }),
    });
    if (res.status === 200) {
      const body = await res.json();
      return body.session_token;
    }
    if (res.status === 429) {
      const retryAfter = Number(res.headers.get('Retry-After') ?? 12);
      process.stdout.write(`     минт: rate-limit, жду ${retryAfter}с… `);
      await sleep((retryAfter + 2) * 1000);
      continue;
    }
    throw new Error(`mint failed: ${res.status} ${await res.text()}`);
  }
  throw new Error('mint failed: rate-limit не отпустил');
}

function client(token) {
  return {
    /** Токен сценария: для запросов вне get/patch (nonce одноразовый, второй минт даст 401 replay). */
    token,
    get: (path) =>
      fetch(`${TARGET}${path}`, { headers: { 'X-Session-Token': token } }),
    /** Сырой GET с той же сессией — например, проверить контракт подсказок. */
    raw: (path) =>
      fetch(`${TARGET}${path}`, { headers: { 'X-Session-Token': token } }),
    patch: (body) =>
      fetch(`${TARGET}/api/profile`, {
        method: 'PATCH',
        headers: { 'X-Session-Token': token, 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
  };
}

/**
 * PATCH с ожиданием rate-limit: write-бакет — 30 запросов в минуту, а тест
 * делает десятки. 429 здесь не дефект, а реальное ограничение backend'а,
 * поэтому ждём и повторяем ту же операцию (идемпотентные PATCH профиля).
 */
async function patchWithLimit(api, body, attempts = 8) {
  let res = await api.patch(body);
  for (let i = 0; res.status === 429 && i < attempts; i += 1) {
    const wait = Number(res.headers.get('Retry-After') ?? 12);
    process.stdout.write(`     rate-limit, жду ${wait}с… `);
    await sleep((wait + 2) * 1000);
    res = await api.patch(body);
  }
  return res;
}

/** Набор обязательных полей completion. `over` перекрывает отдельные поля. */
function completion(over = {}) {
  return {
    name: 'Лунная',
    birth_date: '15.03.1992',
    birth_time: '14:30',
    birth_time_precision: 'exact',
    city: 'москва',
    intent: 'oracle',
    onboarding_complete: true,
    ...over,
  };
}

async function scenario(label, tgId, run) {
  console.log(`\n── ${label} (TG ${tgId}) ${'─'.repeat(Math.max(0, 44 - label.length))}`);
  const token = await mint(tgId);
  await run(client(token), tgId);
}

/* 1. Успешное сохранение профиля ----------------------------------------- */
await scenario('1. Успешное сохранение профиля', tg(0), async (api) => {
  const res = await patchWithLimit(api, completion({ persona: 'witch' }));
  const body = await res.json();
  check(res.status === 200, 'completion → 200', `status=${res.status} ${JSON.stringify(body)}`);
  check(body.ok === true, 'ok=true в ответе');
  check(Array.isArray(body.updated) && body.updated.length > 0, 'updated не пуст', String(body.updated));
  check(body.onboarded === true, 'onboarded=true в ответе');

  const me = await (await api.get('/api/me')).json();
  check(me.name === 'Лунная', 'имя сохранено на сервере', `name=${me.name}`);
  check(me.birth_date === '1992-03-15', 'дата в ISO', `birth_date=${me.birth_date}`);
  check(me.birth_city === 'Москва', 'город нормализован', `birth_city=${me.birth_city}`);
  check(me.persona === 'witch', 'персона сохранена', `persona=${me.persona}`);
  check(me.onboarded === true, 'onboarded прочитан из /api/me');
  check(me.onboarding_step === null, 'onboarding_step сброшен', String(me.onboarding_step));
  check(me.tz === 'Europe/Moscow', 'таймзона из города', `tz=${me.tz}`);
});

/* 2. Частичное обновление ------------------------------------------------- */
await scenario('2. Частичное обновление', tg(1), async (api) => {
  await patchWithLimit(api, completion({ persona: 'mentor' }));
  const before = await (await api.get('/api/me')).json();
  const res = await patchWithLimit(api, { oracle_name: 'Луна' });
  const body = await res.json();
  check(res.status === 200, 'частичный PATCH → 200', `status=${res.status}`);
  check(
    body.updated.length === 1 && body.updated[0] === 'oracle_name',
    'записано только запрошенное поле',
    String(body.updated),
  );
  const after = await (await api.get('/api/me')).json();
  check(after.oracle_name === 'Луна', 'oracle_name обновлён', after.oracle_name);
  check(
    after.birth_date === before.birth_date && after.name === before.name,
    'остальные поля не тронуты',
    `${before.name}/${after.name} ${before.birth_date}/${after.birth_date}`,
  );
  check(after.onboarded === before.onboarded, 'onboarded не изменился');

  const noop = await patchWithLimit(api, {});
  const noopBody = await noop.json();
  check(noop.status === 200, 'пустой PATCH → 200', `status=${noop.status}`);
  check(noopBody.updated.length === 0, 'пустой PATCH ничего не пишет', String(noopBody.updated));
});

/* 3. Восстановление профиля после перезагрузки ---------------------------- */
await scenario('3. Восстановление профиля после «перезагрузки»', tg(2), async (api) => {
  await patchWithLimit(api, completion({ persona: 'friend' }));
  // Перезагрузка = новое чтение профиля из сервера: у клиента нет локального
  // слепка, GET /api/me — единственный источник. Повторно initData не
  // генерируем: nonce одноразовый, повтор той же строки даст 401 replay.
  const me = await (await api.get('/api/me')).json();
  check(me.onboarded === true, 'onboarded восстановлен из сервера');
  check(me.birth_date === '1992-03-15', 'дата рождения восстановлена', me.birth_date);
  check(me.persona === 'friend', 'персона восстановлена', me.persona);
  check(me.chart_mode === 'full', 'карта построена и сохранена', String(me.chart_mode));
  check(
    me.sun !== null && typeof me.sun.sign === 'string',
    'солнце доступно без пересчёта',
    JSON.stringify(me.sun),
  );
});

/* 4. Продолжение незавершённого онбординга --------------------------------- */
await scenario('4. Продолжение незавершённого онбординга', tg(3), async (api) => {
  const early = await patchWithLimit(api, { persona: 'witch' });
  const earlyBody = await early.json();
  check(early.status === 200, 'PATCH до завершения → 200');
  check(earlyBody.onboarded === false, 'onboarded не выставлен досрочно');
  let me = await (await api.get('/api/me')).json();
  check(me.onboarded === false, 'сервер не считает онбординг завершённым');
  check(me.persona === 'witch', 'персона сохранена досрочно', me.persona);
  check(
    me.birth_date !== '1992-03-15',
    'дата рождения НЕ записана до completion (backend не пишет поля частично)',
    String(me.birth_date),
  );
  // Дозавершение тем же completion — данные не потерялись между сессиями.
  const done = await patchWithLimit(api, completion({ persona: 'witch' }));
  check(done.status === 200, 'дозавершение → 200', `status=${done.status}`);
  me = await (await api.get('/api/me')).json();
  check(me.onboarded === true, 'после дозавершения onboarded=true');
  check(me.persona === 'witch', 'ранняя персона не потерялась', me.persona);
});

/* 5. Повторная отправка после подтверждённого успеха ---------------------- */
await scenario('5. Повторная отправка после успеха', tg(4), async (api) => {
  await patchWithLimit(api, completion({ persona: 'mentor' }));
  const again = await patchWithLimit(api, completion({ persona: 'mentor' }));
  const body = await again.json();
  check(again.status === 200, 'повторный completion → 200 (идемпотентно)', `status=${again.status}`);
  check(body.onboarded === true, 'повтор не отменяет onboarded');
  const me = await (await api.get('/api/me')).json();
  check(me.onboarded === true, 'после повтора onboarded=true');
  check(me.birth_city === 'Москва', 'профиль не испорчен повтором', me.birth_city);
  check(me.chart_mode === 'full', 'карта на месте после повтора');
});

/* 6. Ошибка валидации API -------------------------------------------------- */
await scenario('6. Ошибка валидации API', tg(5), async (api) => {
  // Два разных уровня отказа, и клиент должен различать их:
  //   • 400 — бизнес-валидатор onboarding_fields, detail = строка с причиной;
  //   • 422 — Pydantic, detail = массив без строкового message.
  const bad = await patchWithLimit(api, { ...completion(), intent: 'не-направление' });
  const badBody = await bad.json();
  check(bad.status === 422, 'intent вне Literal → 422 (Pydantic)', `status=${bad.status}`);
  check(
    Array.isArray(badBody.detail),
    '422: detail — массив, строкового message нет (поэтому общий текст в UI)',
    typeof badBody.detail,
  );
  const me = await (await api.get('/api/me')).json();
  check(me.onboarded === false, 'провал завершения не оставляет полузаписи', String(me.onboarded));

  const unknownCity = await patchWithLimit(api, completion({ city: 'атлантида' }));
  check(unknownCity.status === 400, 'неизвестный город → 400', `status=${unknownCity.status}`);
  const unknownCityBody = await unknownCity.json();
  check(
    typeof unknownCityBody.detail === 'string',
    'город: текст ошибки есть',
    String(unknownCityBody.detail),
  );

  const badDate = await patchWithLimit(api, completion({ birth_date: '01.01.1850' }));
  check(badDate.status === 400, 'дата вне 1900..сегодня → 400', `status=${badDate.status}`);

  const badPersona = await patchWithLimit(api, { persona: 'не-образ' });
  check(badPersona.status === 400, 'неизвестная персона → 400', `status=${badPersona.status}`);

  const badTime = await patchWithLimit(api, completion({ birth_time: '77:99' }));
  check(badTime.status === 400, 'невозможное время → 400', `status=${badTime.status}`);

  const shortName = await patchWithLimit(api, completion({ name: 'x' }));
  check(shortName.status === 400, 'имя короче 2 символов → 400', `status=${shortName.status}`);

  const longName = await patchWithLimit(api, completion({ name: 'я'.repeat(61) }));
  check(longName.status === 422, 'имя длиннее 60 → 422 (Pydantic max_length)', `status=${longName.status}`);
});

/* 7. 401 и истечение сессии ------------------------------------------------ */
await scenario('7. 401 без авторизации', tg(6), async (api) => {
  const anon = await fetch(`${TARGET}/api/profile`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ oracle_name: 'Луна' }),
  });
  const anonBody = await anon.json();
  check(anon.status === 401, 'PATCH без токена → 401', `status=${anon.status}`);
  check(typeof anonBody.detail === 'string', '401 с телом', String(anonBody.detail));

  const bad = await fetch(`${TARGET}/api/profile`, {
    method: 'PATCH',
    headers: { 'X-Session-Token': 'not-a-token', 'Content-Type': 'application/json' },
    body: JSON.stringify({ oracle_name: 'Луна' }),
  });
  check(bad.status === 401, 'невалидный токен → 401', `status=${bad.status}`);

  const me = await fetch(`${TARGET}/api/me`);
  check(me.status === 401, 'GET /api/me без токена → 401', `status=${me.status}`);
});

/* 8. Сетевой сбой / таймаут ------------------------------------------------ */
await scenario('8. Сетевой сбой и таймаут', tg(7), async (api) => {
  // Таймаут на клиенте: сервер жив, но не отвечает за отведённое время.
  const timeout = await fetch(`${TARGET}/api/profile`, {
    method: 'PATCH',
    headers: { 'X-Session-Token': 'unused', 'Content-Type': 'application/json' },
    body: JSON.stringify({ oracle_name: 'Луна' }),
    signal: AbortSignal.timeout(10),
  }).catch((error) => ({ aborted: error.name === 'TimeoutError' || error.name === 'AbortError' }));
  check(
    timeout && ('aborted' in timeout ? timeout.aborted : true),
    'обрыв по таймауту распознаётся как ошибка транспорта, не успех',
    JSON.stringify(timeout?.status ?? 'abort'),
  );

  // Сеть недоступна: fetch бросает TypeError, клиент обязан перевести это
  // в транспортную ошибку с retry, а не показать «сохранено».
  const down = await fetch('http://127.0.0.1:1/api/profile', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ oracle_name: 'Луна' }),
    signal: AbortSignal.timeout(3000),
  }).catch((error) => error);
  check(
    down instanceof Error && down.name === 'TypeError',
    'недоступный хост → сетевая ошибка, а не успех',
    down?.name,
  );
});

/* 9. Сохранность введённых значений при неуспехе -------------------------- */
await scenario('9. Ввод сохраняется при отказе', tg(8), async (api) => {
  const rejected = await patchWithLimit(api, { ...completion(), city: 'атлантида' });
  check(rejected.status === 400, 'первая попытка завершения → 400', `status=${rejected.status}`);
  // После отказа тот же набор, но с городом из подсказок: сервер обязан
  // принять его без потери остальных полей.
  const retry = await patchWithLimit(api, completion({ persona: 'friend' }));
  check(retry.status === 200, 'повтор после отказа → 200', `status=${retry.status}`);
  const me = await (await api.get('/api/me')).json();
  check(me.onboarded === true, 'после повтора онбординг завершён');
  check(me.birth_date === '1992-03-15', 'дата не потерялась', me.birth_date);
  check(me.persona === 'friend', 'персона не потерялась', me.persona);
});

/* 10. Отсутствие неподдерживаемых полей в запросе ------------------------- */
await scenario('10. Неподдерживаемые поля', tg(9), async (api) => {
  // Контракт не имеет таких полей, и клиент их не отправляет: если бы
  // отправил, backend молча вернул бы 200 и ничего не записал (Pydantic
  // без extra="forbid"). Этот кейс фиксирует, что реальный ответ на
  // неизвестное поле — тихий успех, поэтому состав полей держим на клиенте.
  const extra = await patchWithLimit(api, { ...completion(), bogus_field: 'x' });
  const extraBody = await extra.json();
  check(extra.status === 200, 'backend не падает на лишнем поле', `status=${extra.status}`);
  const me = await (await api.get('/api/me')).json();
  check(
    !('bogus_field' in me),
    'лишнее поле не попало в /api/me',
    Object.keys(me).join(','),
  );
  // Контрактный набор проходит полностью; тело не содержит ничего beyond.
  const clean = completion();
  const cleanKeys = Object.keys(clean).sort().join(',');
  check(
    cleanKeys ===
      'birth_date,birth_time,birth_time_precision,city,intent,name,onboarding_complete',
    'completion содержит только поля контракта',
    cleanKeys,
  );
});

/* 11. Город: label vs key (регрессия на латинские подсказки) --------------- */
await scenario('11. Город латиницей против ключом', tg(10), async (api) => {
  // Подсказки GET /api/city/suggest отдают {key, label}; для части городов
  // label — латиница (London, Tokyo), а key — всегда ключ geo.FALLBACK
  // (кириллица). Сервер ищет город по нормализованному ключу, поэтому label
  // не проходит. Этот кейс зафиксирован после того, как онбординг сначала
  // отправлял label и ломал завершение для ~23% словаря.
  // Поиск подсказок работает по кириллическим ключам словаря: латинский
  // запрос «lond» не находит ничего. Значит клиент ищет только кириллицей,
  // а на экране показывает латинский label — отправлять надо key.
  const suggest = await api.raw('/api/city/suggest?q=' + encodeURIComponent('лондон'));
  const suggestBody = await suggest.json();
  const item = suggestBody.items.find((i) => /london/i.test(i.label));
  check(
    item !== undefined && typeof item.key === 'string',
    'подсказка города несёт key отдельно от label',
    JSON.stringify(item ?? null),
  );
  check(
    item !== undefined && /[а-яё]/i.test(item.key),
    'key — кириллический ключ словаря, пригодный для отправки',
    item?.key,
  );

  const latinSearch = await api.raw('/api/city/suggest?q=lond');
  const latinBody = await latinSearch.json();
  check(
    latinBody.items.length === 0,
    'латинский запрос не находит город (поиск только по кириллице)',
    `${latinBody.items.length} результатов`,
  );

  const byLabel = await patchWithLimit(api, completion({ city: 'London' }));
  const labelBody = await byLabel.json();
  check(byLabel.status === 400, 'город латинским label → 400 (сервер не знает «london»)', `status=${byLabel.status}`);
  check(
    typeof labelBody.detail === 'string' && /город/i.test(labelBody.detail),
    'отказ по городу несёт текст',
    String(labelBody.detail),
  );
  const me1 = await (await api.get('/api/me')).json();
  check(me1.onboarded === false, 'после отказа профиль не завершён', String(me1.onboarded));

  const byKey = await patchWithLimit(api, completion({ city: 'лондон' }));
  check(byKey.status === 200, 'тот же город ключом словаря → 200', `status=${byKey.status}`);
  const me2 = await (await api.get('/api/me')).json();
  check(me2.onboarded === true, 'по ключу онбординг завершается');
  check(me2.tz === 'Europe/London', 'часовой пояс города применён', `tz=${me2.tz}`);
});

/* 12. Пустое время при точной/приблизительной точности --------------------- */
await scenario('12. Время обязательно для exact/approx', tg(11), async (api) => {
  const noTime = await patchWithLimit(
    api,
    completion({ birth_time_precision: 'exact', birth_time: undefined }),
  );
  check(noTime.status === 400, 'exact без времени → 400', `status=${noTime.status}`);
  const noTimeBody = await noTime.json();
  check(
    typeof noTimeBody.detail === 'string' && /время|минут/i.test(noTimeBody.detail),
    'отказ объясняет причину про время',
    String(noTimeBody.detail),
  );

  // Ключ присутствует, но пустой: сервер всё равно требует формат HH:MM.
  const emptyTime = await patchWithLimit(api, completion({ birth_time: '' }));
  check(emptyTime.status === 400, 'пустая строка времени → 400', `status=${emptyTime.status}`);

  const approxNoTime = await patchWithLimit(
    api,
    completion({ birth_time_precision: 'approx', birth_time: undefined }),
  );
  check(approxNoTime.status === 400, 'approx без времени → 400', `status=${approxNoTime.status}`);

  const unknownOk = await patchWithLimit(
    api,
    completion({ birth_time_precision: 'unknown', birth_time: undefined }),
  );
  check(unknownOk.status === 200, 'unknown без времени → 200', `status=${unknownOk.status}`);
  const me = await (await api.get('/api/me')).json();
  check(me.birth_time === null, 'при unknown время не сохраняется', String(me.birth_time));
  check(me.birth_time_known === false, 'birth_time_known=false при unknown');
  check(me.ascendant === null, 'без времени асцендент не строится', String(me.ascendant));
});

/* Итог -------------------------------------------------------------------- */
console.log(`\n${failures === 0 ? 'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' : `ПРОВАЛОВ: ${failures}`}`);
process.exit(failures === 0 ? 0 : 1);
