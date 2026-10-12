import { useState } from 'react';
import { IconButton } from '../components/Button';
import { Chip } from '../components/Card';
import { EmptyState, ErrorState, Skeleton } from '../components/States';
import { useOracleChat } from '../hooks/useOracleChat';
import { SpreadSelector } from '../components/SpreadSelector';
import { useHashRoute } from '../routes/router';
import { useI18n } from '../i18n/I18nProvider';

/* ============================================================================
   Oracle — единый чат (вкладка 2).

   Один собеседник: домен выбирает backend, клиент не маршрутизирует сам.
   Пометка «Демо-данные» снята: экран работает на реальных
   POST /api/chat/oracle и GET /api/chat/oracle.
   ============================================================================ */

export function OracleScreen() {
  const { t } = useI18n();
  const { navigate } = useHashRoute();
  const { status, messages, sending, errorKey, send, reload } = useOracleChat();
  const [draft, setDraft] = useState('');
  const [spreadOpen, setSpreadOpen] = useState(false);

  // Черновик очищаем только после успешного ответа: при отказе (429, сеть)
  // текст остаётся в поле, чтобы не набирать вопрос заново.
  const submit = async () => {
    const text = draft.trim();
    if (!text || sending) return;
    const sent = await send(text);
    if (sent) setDraft('');
  };

  return (
    <section className="screen screen--chat">
      <header className="chat-head">
        <div>
          <h1 className="screen__title">{t('oracle.title')}</h1>
          <span className="chat-head__meta">
            <Chip tone="success">{t('oracle.memory_on')}</Chip>
          </span>
        </div>
        <IconButton label={t('oracle.sessions')}>☰</IconButton>
      </header>

      <button type="button" className="chat-action" onClick={() => setSpreadOpen(true)}>
        🎴 {t('reading.choose_spread')}
      </button>

      <div className="chat-thread" aria-live="polite">
        {status === 'loading' ? (
          <Skeleton shape="list" count={3} />
        ) : status === 'error' ? (
          <ErrorState
            title={t('state.error')}
            hint={t('network.error_hint')}
            retryLabel={t('action.retry')}
            onRetry={() => void reload()}
          />
        ) : messages.length === 0 ? (
          <EmptyState title={t('oracle.empty_title')} hint={t('oracle.empty_hint')} />
        ) : (
          <ul className="chat-list">
            {messages.map((message) => (
              <li key={message.id} className={`bubble bubble--${message.role}`}>
                <span className="bubble__author">
                  {message.role === 'user' ? t('oracle.you') : t('oracle.title')}
                </span>
                <p className="bubble__text prose-answer">{message.text}</p>
                {message.role === 'assistant' && message.agent ? (
                  <span className="message-proof">
                    <Chip tone="info">{t('oracle.answered_via')}: {message.agent}</Chip>
                  </span>
                ) : null}
                {message.role === 'assistant' && message.charge === 'followup' ? (
                  <span className="message-note">{t('oracle.followup_note')}</span>
                ) : null}
              </li>
            ))}
            {sending ? <li className="chat-thinking">{t('oracle.thinking')}</li> : null}
          </ul>
        )}

        {errorKey ? (
          <ErrorState title={t(errorKey)} hint={undefined} />
        ) : null}
      </div>

      {messages.length === 0 && status === 'ready' ? (
        <ul className="chat-starters">
          {t('oracle.starters').split('|').map((starter) => (
              <li key={starter}>
                <button type="button" className="chat-starter" onClick={() => setDraft(starter)}>
                  {starter}
                </button>
              </li>
          ))}
        </ul>
      ) : null}

      <form
        className="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label className="visually-hidden" htmlFor="composer-input">
          {t('oracle.title')}
        </label>
        <textarea
          id="composer-input"
          className="composer__input"
          rows={1}
          value={draft}
          placeholder={t('oracle.composer_placeholder')}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
        />
        <button type="submit" className="composer__send" disabled={draft.trim().length === 0 || sending}>
          {sending ? t('oracle.sending') : t('action.send')}
        </button>
      </form>

      <p className="composer__hint">{t('oracle.composer_hint')}</p>

      <SpreadSelector
        open={spreadOpen}
        onClose={() => setSpreadOpen(false)}
        onDrawn={(readingId) => {
          setSpreadOpen(false);
          navigate(`/reading/${readingId}`);
        }}
      />
    </section>
  );
}
