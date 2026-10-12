import { useEffect, useRef, useState } from 'react';
import { Button } from '../components/Button';
import { Card, CardHeader, Chip } from '../components/Card';
import { Screen } from '../components/Screen';
import { EmptyState, ErrorState, Skeleton } from '../components/States';
import { useI18n } from '../i18n/I18nProvider';
import { useMe } from '../hooks/useMe';
import { FACT_MAX, useMemories } from '../hooks/useMemories';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   Память: реальный backend, а не демо-данные.

   Что честно показано, а что нет:
   - список фактов, создание и удаление — настоящие вызовы /api/memories;
   - «Что я замечаю» (паттерны) остаётся демо: API для вывода backend не даёт,
     поэтому блок подписан как демонстрация и не смешивается с фактами;
   - правки факта нет: GET|PATCH /api/memories/{id} отвечают 405. Экран не
     имитирует редактирование, а объясняет, что можно удалить и записать заново.
   ============================================================================ */

const DRAFT_KEY = 'oracle.memory.draft';

/**
 * Черновик неотправленного текста: хранится в sessionStorage, а не localStorage.
 *
 * Причины изоляции (аудит приватности 4.3):
 * - sessionStorage изолирован между вкладками и сессиями пользователей;
 * - при смене аккаунта или закрытии окна браузера черновик не утекает другому
 *   пользователю того же устройства;
 * - sessionStorage сохраняется при обновлении страницы (F5/reload) в рамках той же сессии;
 * - устаревший глобальный ключ из localStorage зачищается при первом чтении.
 */
function readDraft(): string {
  try {
    // Зачистка устаревшего ключа из localStorage, если остался от старой версии
    window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    /* ignore */
  }
  try {
    return window.sessionStorage.getItem(DRAFT_KEY) ?? '';
  } catch {
    return '';
  }
}

function writeDraft(value: string) {
  try {
    if (value.trim()) window.sessionStorage.setItem(DRAFT_KEY, value);
    else window.sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    // Приватный режим браузера: черновик не сохранится, ввод это не ломает.
  }
}

function formatDate(iso: string, lang: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString(lang === 'ru' ? 'ru-RU' : 'en-US', {
    day: 'numeric',
    month: 'short',
  });
}

export interface MemoryScreenProps {
  onNavigate: (path: string) => void;
}

export function MemoryScreen({ onNavigate }: MemoryScreenProps) {
  const { t, lang } = useI18n();
  const me = useMe();
  const memoryEnabled = me.data?.memory_enabled ?? false;
  // Список грузим всегда, даже при выключенной памяти: backend и в этом
  // случае отдаёт сохранённое (флаг проверяется только в POST), а значит
  // посмотреть и удалить свои факты можно — и данные не должны «исчезать»
  // из интерфейса только потому, что флаг снят.
  const {
    items,
    status,
    errorKey,
    canRetry,
    reload,
    add,
    remove,
    mutation,
    pendingDeleteId,
    askDelete,
    resetMutation,
  } = useMemories();

  const [draft, setDraft] = useState(readDraft);
  const [touched, setTouched] = useState(false);
  const formRef = useRef<HTMLInputElement>(null);

  // Черновик — только для восстановления ввода. Ответ сервера о состоянии
  // памяти он не означает и не заменяет.
  useEffect(() => {
    writeDraft(draft);
  }, [draft]);

  // Успешная запись очищает черновик: он своё отработал.
  useEffect(() => {
    if (mutation.status === 'saved') {
      setDraft('');
      setTouched(false);
    }
  }, [mutation.status]);

  const saving = mutation.status === 'saving';
  const draftInvalid: TranslationKey | null = (() => {
    const trimmed = draft.trim();
    if (trimmed.length === 0) return 'memory.form_empty';
    if (trimmed.length < 3) return 'memory.form_too_short';
    if (trimmed.length > FACT_MAX) return 'memory.form_too_long';
    return null;
  })();
  const submitDisabled = saving || draftInvalid !== null;

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (submitDisabled) return;
    await add(draft);
  };

  if (status === 'loading') {
    return (
      <Screen title={t('memory.title')} kicker={t('nav.me')}>
        <Skeleton shape="card" count={3} />
      </Screen>
    );
  }

  if (status === 'error') {
    return (
      <Screen title={t('memory.title')} kicker={t('nav.me')}>
        <ErrorState
          title={t('state.error')}
          hint={errorKey ? t(errorKey) : undefined}
          retryLabel={canRetry ? t('action.retry') : undefined}
          onRetry={canRetry ? reload : undefined}
        />
      </Screen>
    );
  }

  return (
    <Screen
      title={t('memory.title')}
      kicker={t('nav.me')}
      action={
        <button type="button" className="link-btn" onClick={() => onNavigate('/settings')}>
          {t('nav.me')}
        </button>
      }
    >
      <Card raised>
        <CardHeader title={t('memory.toggle')} />
        <div className="memory-switch">
          <Chip tone={memoryEnabled ? 'success' : 'error'}>
            {memoryEnabled ? t('oracle.memory_on') : t('oracle.memory_off')}
          </Chip>
          <p className="hint-text">
            {memoryEnabled ? t('memory.toggle_on_hint') : t('memory.toggle_off_hint')}
          </p>
          {!memoryEnabled ? (
            <>
              <p className="hint-text">{t('memory.readonly_note')}</p>
              <Button
                variant="primary"
                size="md"
                onClick={() => onNavigate('/settings')}
              >
                {t('memory.toggle')}
              </Button>
            </>
          ) : null}
        </div>
      </Card>

      <Card>
        <CardHeader title={t('memory.add_title')} />
        <p className="hint-text">{t('memory.add_hint')}</p>
        <form className="memory-form" onSubmit={onSubmit} noValidate>
          <label className="sr-only" htmlFor="memory-fact">
            {t('memory.add_title')}
          </label>
          <input
            id="memory-fact"
            ref={formRef}
            className="field"
            type="text"
            maxLength={FACT_MAX}
            value={draft}
            placeholder={t('memory.add_placeholder')}
            disabled={saving}
            aria-invalid={touched && draftInvalid !== null}
            aria-describedby="memory-form-status"
            onChange={(event) => {
              setDraft(event.target.value);
              if (event.target.value.trim()) setTouched(false);
            }}
          />
          <div className="memory-form__row">
            <Button
              variant="primary"
              size="md"
              type="submit"
              disabled={submitDisabled}
            >
              {saving ? t('memory.saving') : t('memory.add_submit')}
            </Button>
            <span className="memory-form__count">
              {draft.trim().length}/{FACT_MAX}
            </span>
          </div>

          <p
            id="memory-form-status"
            className={mutation.status === 'error' || (touched && draftInvalid) ? 'form-error' : 'hint-text'}
            role={mutation.status === 'error' ? 'alert' : 'status'}
          >
            {mutation.status === 'saved'
              ? t('memory.saved')
              : mutation.status === 'error'
                ? `${t(mutation.errorKey ?? 'state.error')}${mutation.detail ? ` — ${mutation.detail}` : ''}`
                : touched && draftInvalid
                  ? t(draftInvalid)
                  : ''}
          </p>
        </form>
      </Card>

      <Card>
        <CardHeader title={t('memory.section_saved')} />
        {items.length === 0 ? (
          <EmptyState
            title={t('memory.empty_title')}
            hint={memoryEnabled ? t('memory.empty_hint') : t('memory.readonly_note')}
            action={
              <Button variant="secondary" size="md" onClick={() => formRef.current?.focus()}>
                {t('memory.add_submit')}
              </Button>
            }
          />
        ) : (
          <ul className="fact-list">
            {items.map((item) => (
              <li key={item.id} className="fact-list__item">
                <span className="fact-list__text">{item.fact}</span>
                <span className="fact-list__meta">
                  <Chip tone="neutral">{t('memory.kind_label')}: {item.kind}</Chip>
                  {item.created_at ? (
                    <span className="fact-list__date">
                      {t('memory.saved_at')} {formatDate(item.created_at, lang)}
                    </span>
                  ) : null}
                </span>
                <span className="fact-list__actions">
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={saving}
                    onClick={() => askDelete(item.id)}
                  >
                    {t('action.delete')}
                  </Button>
                </span>
              </li>
            ))}
          </ul>
        )}
        {items.length > 0 ? (
          <p className="hint-text">{t('memory.no_edit')}</p>
        ) : null}
      </Card>

      {pendingDeleteId !== null ? (
        <Card raised>
          <CardHeader title={t('memory.delete_confirm_title')} />
          <p className="hint-text">{t('memory.delete_confirm_hint')}</p>
          {mutation.status === 'error' ? (
            <p className="form-error" role="alert">
              {t('memory.delete_failed_hint')}
              {mutation.detail ? ` (${mutation.detail})` : ''}
            </p>
          ) : null}
          <div className="memory-form__row">
            <Button
              variant="primary"
              size="md"
              disabled={saving}
              onClick={async () => {
                await remove(pendingDeleteId);
              }}
            >
              {t('memory.delete_confirm_yes')}
            </Button>
            <Button
              variant="ghost"
              size="md"
              disabled={saving}
              onClick={() => {
                askDelete(null);
                resetMutation();
              }}
            >
              {t('memory.delete_confirm_no')}
            </Button>
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHeader title={t('memory.patterns_title')} />
        <p className="hint-text">{t('memory.patterns_hint')}</p>
        <p className="pattern-text">{t('demo.memory_pattern')}</p>
        <Chip tone="info">{t('demo.badge')}</Chip>
      </Card>
    </Screen>
  );
}
