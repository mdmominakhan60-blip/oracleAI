import { $, esc, num, get } from '../core/runtime.js';
import { setDq } from './analytics.js';
import { segmentLabel } from './users.js';

// Общий рендер churn-карточек R3 (BUS-168 §1.2) для экранов «Аудитория» и
// «Когорты»: expiring_3d/sleeping_14d со сплитом payer/free. Счётчик карточки
// идёт тем же предикатом SEGMENTS, что и таблица аудитории, — расхождение
// невозможно конструкцией (BUS-279). Клик — источник цифры: список сегмента.

export async function renderChurnCards(targetId, dqId) {
  try {
    const data = await get('/api/admin/audience/churn');
    const cards = data.cards || [];
    setDq(dqId, cards.length
      ? { status: 'full' }
      : { status: 'empty', note: 'карточки churn недоступны' });
    $(targetId).innerHTML = cards.length
      ? cards.map((card) => `<button type="button" class="churn-card" data-churn-segment="${esc(card.segment)}" aria-label="Сегмент ${esc(segmentLabel(card.segment))}: ${num(card.total)} клиенток, платящих ${num(card.payers)}. Открыть список сегмента"><span class="churn-value">${num(card.total)}</span><span class="churn-label">${esc(segmentLabel(card.segment))}</span><span class="churn-split">платящих: ${num(card.payers)} · бесплатных: ${num(card.free)}</span></button>`).join('')
      : '<div class="empty">Нет данных — сегменты churn недоступны</div>';
    return cards;
  } catch (error) {
    setDq(dqId, { status: 'empty', note: 'API churn недоступен' });
    $(targetId).innerHTML = '<div class="empty">Нет данных — API churn недоступен</div>';
    return [];
  }
}
