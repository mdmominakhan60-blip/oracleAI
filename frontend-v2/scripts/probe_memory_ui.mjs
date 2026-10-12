import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
const EXE = execFileSync('sh',['-c','echo "$HOME/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome"']).toString().trim();
let pass=0, fail=0;
const check=(ok,label,extra='')=>{ if(ok){pass++;console.log('PASS '+label);} else {fail++;console.log('FAIL '+label+' '+extra);} };
const b = await chromium.launch({executablePath:EXE, headless:true, args:['--no-sandbox']});
const p = await b.newPage({viewport:{width:420,height:900}});
const errs=[];
p.on('pageerror', e=>errs.push(String(e)));
p.on('console', m=>{ if(m.type()==='error' && !/Failed to load resource/.test(m.text())) errs.push(m.text()); });
await p.addInitScript((d)=>{Object.defineProperty(window,'Telegram',{configurable:true,value:{WebApp:{initData:d}}});}, process.env.INIT_DATA);
await p.goto('http://127.0.0.1:5180/#/memory',{waitUntil:'networkidle'});
// Состояние чипа зависит от флага: проверяем то, что задано предусловием.
const chip = await p.$eval('.memory-switch .chip', el=>el.textContent.trim());
const expectOn = process.env.TG_MEM_ON === '1';
check(expectOn ? /включена/i.test(chip) : /выключена/i.test(chip),
  expectOn ? 'чип «память включена» при memory_enabled=true' : 'чип «память выключена» при memory_enabled=false', chip);
const items0 = await p.$$('.fact-list__item');
check(items0.length===0, 'нет фиктивных фактов при пустом списке', `items=${items0.length}`);
const demoBadges = await p.$$eval('.fact-list .chip', els=>els.length);
check(demoBadges===0, 'в списке фактов нет демо-плашек', `chips=${demoBadges}`);
// валидация: пустая форма не отправляется
await p.fill('#memory-fact','');
const disabledEmpty = await p.$eval('#memory-fact + .memory-form__row button', el=>el.disabled).catch(()=>null);
check(disabledEmpty===true, 'кнопка сохранения заблокирована при пустом поле', `disabled=${disabledEmpty}`);
// короткий факт (<3): кнопка заблокирована клиентской валидацией — клик невозможен
await p.fill('#memory-fact','ab');
const disabledShort = await p.$eval('#memory-fact + .memory-form__row button', el=>el.disabled);
check(disabledShort===true, 'короткий факт (<3) блокирует отправку клиентской валидацией', `disabled=${disabledShort}`);
// Отказ сервера при выключенной памяти: проверяется только когда флаг выключен
// (иначе 200 — и это не отказ). Черновик при отказе проверяется там же.
if (process.env.TG_MEM_ON !== '1') {
  await p.fill('#memory-fact','Тестовый факт для экрана памяти');
  await p.click('#memory-fact + .memory-form__row button');
  await p.waitForTimeout(2500);
  const status2 = await p.$eval('#memory-form-status', el=>el.textContent.trim()).catch(()=>'');
  check(/выключена/i.test(status2), 'при выключенной памяти показан отказ сервера (409), не ложный успех', status2);
  const stillEmpty = (await p.$$('.fact-list__item')).length;
  check(stillEmpty===0, 'после 409 список остался пустым (нет ложной вставки)', `items=${stillEmpty}`);
  const draftVal = await p.$eval('#memory-fact', el=>el.value);
  check(draftVal==='Тестовый факт для экрана памяти', 'введённый текст сохранён после отказа сервера', draftVal);
  // Проверка изоляции черновика (US-001): черновик живёт в sessionStorage, не в localStorage
  const storages = await p.evaluate(() => ({
    session: window.sessionStorage.getItem('oracle.memory.draft'),
    local: window.localStorage.getItem('oracle.memory.draft'),
  }));
  check(storages.session === 'Тестовый факт для экрана памяти', 'черновик сохранён в sessionStorage', storages.session);
  check(storages.local === null, 'черновик отсутствует в localStorage (изолирован от других пользователей)', String(storages.local));
}
check(errs.length===0, 'нет JS-ошибок в консоли', errs.join(' | ').slice(0,300));

// ── Память включена: создание → перезагрузка → удаление → отмена ──
// ── Включённая память: создание → перезагрузка → отмена удаления → удаление ──
// Предусловие задаёт вызывающая сторона (TG_MEM_ON=1): initData того, чья
// память уже включена через PATCH /api/profile. Браузер не делает этого сам,
// чтобы не смешивать предустановку состояния с проверками интерфейса.
if (process.env.TG_MEM_ON === '1') {
  const chipOn = await p.$eval('.memory-switch .chip', el=>el.textContent.trim());
  check(/включена/i.test(chipOn), 'чип «память включена» при memory_enabled=true', chipOn);

  const countBefore = (await p.$$('.fact-list__item')).length;
  const fact = 'Факт для проверки удаления ' + Date.now();
  await p.fill('#memory-fact', fact);
  const btn = '#memory-fact + .memory-form__row button';
  await p.waitForFunction(()=>{const el=document.querySelector('#memory-fact + .memory-form__row button'); return el && !el.disabled;});
  await p.click(btn);
  await p.waitForTimeout(2500);
  const created = (await p.$$('.fact-list__item')).length;
  const savedMsg = await p.$eval('#memory-form-status', el=>el.textContent.trim()).catch(()=>'');
  check(created === countBefore + 1, 'создание добавляет ровно одну запись с сервера', `${countBefore} → ${created}, msg="${savedMsg}"`);
  check(/Факт сохранён/i.test(savedMsg), '«сохранён» показывается только после 200 сервера', savedMsg);
  check((await p.$eval('#memory-fact', el=>el.value))==='', 'после успеха черновик очищен');

  // перезагрузка: список приходит с сервера, а не из localStorage
  await p.reload({waitUntil:'networkidle'});
  const afterReload = await p.$$eval('.fact-list__item', els=>els.length);
  check(afterReload === created, 'после перезагрузки столько же фактов (данные с сервера)', `${created} → ${afterReload}`);
  const factVisible = await p.$$eval('.fact-list__text', (els,f)=>els.some(e=>e.textContent.trim()===f), fact);
  check(factVisible, 'созданный факт виден после перезагрузки');

  // подтверждение удаления обязательно
  await p.click('.fact-list__item button');
  await p.waitForTimeout(400);
  const confirmShown = await p.$$eval('.card', els=>els.some(e=>/Удалить факт\?/.test(e.textContent)));
  check(confirmShown, 'удаление требует подтверждения');

  // отмена: данные на месте
  const keepBtn = await p.$('.card .btn--ghost:has-text("Оставить")');
  if (keepBtn) await keepBtn.click();
  await p.waitForTimeout(800);
  const afterCancel = await p.$$eval('.fact-list__item', els=>els.length);
  check(afterCancel === afterReload, 'отмена удаления сохраняет данные', `${afterReload} → ${afterCancel}`);

  // подтверждение: запись исчезает
  await p.click('.fact-list__item button');
  await p.waitForTimeout(400);
  const delBtn = await p.$('.card .btn--primary:has-text("Удалить")');
  if (delBtn) await delBtn.click();
  await p.waitForTimeout(2500);
  const afterDelete = await p.$$eval('.fact-list__item', els=>els.length);
  check(afterDelete === afterCancel - 1, 'удаление убирает факт из списка', `${afterCancel} → ${afterDelete}`);
  const stillThere = await p.$$eval('.fact-list__text', (els,f)=>els.some(e=>e.textContent.trim()===f), fact);
  check(!stillThere, 'удалённый факт не виден (после перечитывания)');
}

console.log(`\nИТОГ: ${pass} PASS, ${fail} FAIL`);
await b.close();
process.exit(fail>0?1:0);
