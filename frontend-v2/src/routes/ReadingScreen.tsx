import { useEffect, useRef, useState } from 'react';
import { Button } from '../components/Button';
import { Card, CardHeader, Chip } from '../components/Card';
import { ErrorState, Skeleton } from '../components/States';
import { Screen } from '../components/Screen';
import { fetchReading, interpretReading, type StoredReading } from '../api/client';
import { ApiDomainError } from '../api/transport';
import { withSessionRetry } from '../api/session';
import { useResource, errorKeyFrom, READ_ERRORS } from '../hooks/useResource';
import { useI18n } from '../i18n/I18nProvider';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   Reading — сохранённый расклад Таро.

   Подключено к реальному GET /api/tarot/history/{id}: карты, позиции, колода,
   наличие трактовки. Карты берутся из cards_json сервера (immutable — повтор
   никогда не пересдаёт), поэтому переворот не «украшение», а доказательство.

   Трактовка — POST /api/tarot/interpret/{id}; повторный вызов возвращает
   сохранённый текст, а не генерирует новый.
   ============================================================================ */

export interface ReadingScreenProps {
  readingId: string;
  onNavigate: (path: string) => void;
}

export function ReadingScreen({ readingId, onNavigate }: ReadingScreenProps) {
  const { t } = useI18n();
  const [revealed, setRevealed] = useState<boolean[]>([]);
  const [hint, setHint] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [interpreting, setInterpreting] = useState(false);
  const [interpretError, setInterpretError] = useState<TranslationKey | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const id = Number(readingId);
  const validId = Number.isInteger(id) && id > 0;

  // Карты и позиции приходят одним ответом; ответ проставляем сразу, чтобы
  // переворот не сбрасывался при ререндере.
  const { status, data: reading, errorKey, canRetry, reload } = useResource<StoredReading>({
    load: (signal) => fetchReading(id, signal),
    errorKeyFor: errorKeyFrom(READ_ERRORS),
    enabled: validId,
  });

  useEffect(() => {
    if (!reading) return;
    setRevealed(reading.cards.map(() => false));
    setAnswer(reading.answer);
  }, [reading]);

  if (status === 'loading') {
    return (
      <Screen title={t('reading.title')}>
        <Skeleton shape="card" count={2} />
      </Screen>
    );
  }

  if (status === 'error' || !reading) {
    return (
      <Screen title={t('reading.title')}>
        <ErrorState
          title={errorKey ? t(errorKey) : t('reading.not_found')}
          hint={t('reading.not_found_hint')}
          retryLabel={canRetry ? t('action.retry') : undefined}
          onRetry={canRetry ? () => void reload() : undefined}
        />
        <Button variant="secondary" size="md" onClick={() => onNavigate('/oracle')}>
          {t('action.back_home')}
        </Button>
      </Screen>
    );
  }

  const revealedCount = revealed.filter(Boolean).length;
  const allRevealed = revealedCount === reading.cards.length;
  const positions = reading.ledger.entries.length === reading.cards.length
    ? reading.ledger.entries.map((entry) => entry.position)
    : reading.cards.map((_, index) => String(index + 1));

  const revealAt = (index: number) => {
    if (revealed[index]) return;
    const nextExpected = revealed.findIndex((value) => !value);
    if (index !== nextExpected) {
      // Мягкая подсказка, не блокировка: карту открыть можно, но порядок советуется.
      setHint(t('reading.reveal_next'));
      return;
    }
    setHint(null);
    setRevealed((prev) => prev.map((value, position) => (position === index ? true : value)));
  };

  const interpret = async () => {
    if (interpreting) return;
    setInterpreting(true);
    setInterpretError(null);
    try {
      const result = await withSessionRetry(() => interpretReading(reading.id), 'POST');
      if (!alive.current) return;
      setAnswer(result.answer);
    } catch (error) {
      if (!alive.current) return;
      setInterpretError(interpretKeyFor(error));
    } finally {
      if (alive.current) setInterpreting(false);
    }
  };

  return (
    <Screen
      title={reading.spread || t('reading.title')}
      kicker={t('reading.positions')}
      action={
        <button type="button" className="link-btn" onClick={() => onNavigate('/oracle')}>
          {t('oracle.title')}
        </button>
      }
    >
      <Card raised>
        <CardHeader
          title={t('reading.progress', { n: revealedCount, total: reading.cards.length })}
          action={
            allRevealed && answer ? undefined : (
              <Chip tone={allRevealed ? 'accent' : 'neutral'}>
                {allRevealed ? t('reading.interpret') : t('reading.reveal_hint')}
              </Chip>
            )
          }
        />

        <ol className="tcard-grid">
          {reading.cards.map((card, index) => {
            const isOpen = revealed[index];
            const isNext = !isOpen && index === revealed.findIndex((value) => !value);
            return (
              <li key={`${card.img}-${index}`} className="tcard-slot">
                <span className="tcard-slot__position">{positions[index] ?? ''}</span>
                <button
                  type="button"
                  className={`tcard${isOpen ? ' open' : ''}${isNext ? ' is-next' : ''}`}
                  onClick={() => revealAt(index)}
                  aria-pressed={isOpen}
                  aria-label={`${positions[index] ?? ''}: ${isOpen ? card.name : t('reading.reveal_hint')}`}
                >
                  <span className="tcard-inner">
                    <img
                      className="tcard-face tcard-back"
                      src="/static/img/card-back.jpg"
                      alt=""
                      width={132}
                      height={198}
                    />
                    <img
                      className="tcard-face tcard-front"
                      src={`/static/img/${reading.deck}/${card.img}.jpg`}
                      alt={card.name}
                      width={132}
                      height={198}
                      // Нет картинки (старый слаг, битая сборка) — показываем
                      // рубашку, а не сломанный значок браузера.
                      onError={(event) => {
                        event.currentTarget.src = '/static/img/card-back.jpg';
                      }}
                    />
                  </span>
                </button>
                {isOpen ? (
                  <span className="tcard-slot__caption">
                    {card.name}
                    {card.reversed ? <Chip tone="info">{t('reading.reversed')}</Chip> : null}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ol>

        <div className="reading-progress" aria-hidden="true">
          <span
            className="reading-progress__bar"
            style={{ transform: `scaleX(${revealedCount / Math.max(1, reading.cards.length)})` }}
          />
        </div>

        {hint ? (
          <p className="hint-text hint-text--warn" role="status">
            {hint}
          </p>
        ) : null}
      </Card>

      <Card>
        <CardHeader title={t('reading.interpret')} />
        {answer ? (
          <p className="prose-answer">{answer}</p>
        ) : (
          <>
            <p className="hint-text">
              {allRevealed ? t('reading.interpret_hint') : t('reading.reveal_hint')}
            </p>
            <Button
              variant="primary"
              size="lg"
              fullWidth
              disabled={!allRevealed || interpreting}
              onClick={() => void interpret()}
            >
              {interpreting ? t('reading.interpreting') : t('reading.interpret')}
            </Button>
            {interpretError ? <p className="hint-text hint-text--warn">{t(interpretError)}</p> : null}
          </>
        )}
      </Card>

      {reading.question ? (
        <Card>
          <CardHeader title={t('reading.question_label')} />
          <p className="hint-text">{reading.question}</p>
        </Card>
      ) : null}
    </Screen>
  );
}

function interpretKeyFor(error: unknown): TranslationKey {
  if (error instanceof ApiDomainError) {
    if (error.status === 429) return 'oracle.limit_title';
    if (error.status === 402) return 'oracle.access_ended';
    return 'state.error';
  }
  return 'network.error';
}
