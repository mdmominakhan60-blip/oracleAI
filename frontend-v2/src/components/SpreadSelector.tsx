import { useEffect, useRef, useState } from 'react';
import { Button } from '../components/Button';
import { Chip } from '../components/Card';
import { ErrorState, Skeleton } from '../components/States';
import { fetchSpreadCatalog, drawTarot, type SpreadCatalogItem } from '../api/client';
import { ApiDomainError, ApiTransportError } from '../api/transport';
import { withSessionRetry } from '../api/session';
import { useI18n } from '../i18n/I18nProvider';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   SpreadSelector — витрина раскладов (bottom sheet над чатом, SCREEN_SPEC §10).

   Подключено к реальному GET /api/tarot/spreads/full: code, title, positions,
   tier, emoji, hint, guide. Цены и owned приходят из /api/tarot/spreads —
   этот endpoint в объём следующего среза, поэтому признак премиума пока
   текстовый, без цены.
   ============================================================================ */

export interface SpreadSelectorProps {
  open: boolean;
  onClose: () => void;
  onDrawn: (readingId: number) => void;
}

type Status = 'loading' | 'ready' | 'error';

export function SpreadSelector({ open, onClose, onDrawn }: SpreadSelectorProps) {
  const { t } = useI18n();
  const [status, setStatus] = useState<Status>('loading');
  const [spreads, setSpreads] = useState<SpreadCatalogItem[]>([]);
  const [errorKey, setErrorKey] = useState<TranslationKey | null>(null);
  const [canRetry, setCanRetry] = useState(false);
  const [question, setQuestion] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [drawing, setDrawing] = useState(false);
  const [drawError, setDrawError] = useState<TranslationKey | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = async () => {
    if (!open) return;
    setStatus('loading');
    try {
      const data = await withSessionRetry(() => fetchSpreadCatalog(), 'GET');
      if (!alive.current) return;
      setSpreads(data);
      setStatus('ready');
    } catch (error) {
      if (!alive.current) return;
      setErrorKey(keyFor(error));
      setCanRetry(error instanceof ApiTransportError);
      setStatus('error');
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const draw = async () => {
    const q = question.trim();
    if (!q || !selected || drawing) return;
    setDrawing(true);
    setDrawError(null);
    try {
      const result = await withSessionRetry(
        () => drawTarot(selected, { question: q, deck: 'tarot' }),
        'POST',
      );
      if (!alive.current) return;
      onDrawn(result.reading_id);
    } catch (error) {
      if (!alive.current) return;
      setDrawError(keyFor(error));
    } finally {
      if (alive.current) setDrawing(false);
    }
  };

  return (
    <div className="sheet" role="dialog" aria-modal="true" aria-label={t('reading.title')}>
      <div className="sheet__backdrop" onClick={onClose} />
      <div className="sheet__panel">
        <header className="sheet__head">
          <h2 className="sheet__title">{t('reading.choose_spread')}</h2>
          <button type="button" className="sheet__close" onClick={onClose} aria-label={t('action.close')}>
            ✕
          </button>
        </header>

        {status === 'loading' ? (
          <Skeleton shape="list" count={4} />
        ) : status === 'error' ? (
          <ErrorState
            title={errorKey ?? t('state.error')}
            hint={t('network.error_hint')}
            retryLabel={canRetry ? t('action.retry') : undefined}
            onRetry={canRetry ? () => void load() : undefined}
          />
        ) : (
          <>
            <ul className="spread-list">
              {spreads.map((spread) => (
                <li key={spread.code}>
                  <button
                    type="button"
                    className={`spread-row${selected === spread.code ? ' is-active' : ''}`}
                    onClick={() => setSelected(spread.code)}
                    aria-pressed={selected === spread.code}
                  >
                    <span className="spread-row__emoji" aria-hidden="true">
                      {spread.emoji}
                    </span>
                    <span className="spread-row__body">
                      <span className="spread-row__title">{spread.title}</span>
                      <span className="spread-row__meta">
                        {spread.positions.length} · {spread.hint}
                      </span>
                    </span>
                    <Chip tone={spread.tier === 'premium' ? 'accent' : 'neutral'}>
                      {spread.tier === 'premium' ? t('reading.tier_premium') : t('reading.tier_included')}
                    </Chip>
                  </button>
                </li>
              ))}
            </ul>

            <label className="field-label" htmlFor="spread-question">
              {t('reading.question_label')}
            </label>
            <textarea
              id="spread-question"
              className="field field--area"
              rows={2}
              value={question}
              placeholder={t('reading.question_placeholder')}
              onChange={(event) => setQuestion(event.target.value)}
            />

            {drawError ? <p className="hint-text hint-text--warn">{t(drawError)}</p> : null}

            <Button
              variant="primary"
              size="lg"
              fullWidth
              disabled={!selected || question.trim().length === 0 || drawing}
              onClick={() => void draw()}
            >
              {drawing ? t('reading.drawing') : t('reading.draw_action')}
            </Button>
          </>
        )}
      </div>
    </div>
  );
}

function keyFor(error: unknown): TranslationKey {
  if (error instanceof ApiDomainError) {
    if (error.status === 429) return 'oracle.limit_title';
    if (error.status === 402) return 'oracle.access_ended';
    return 'state.error';
  }
  return 'network.error';
}
