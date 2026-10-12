import { useMe } from '../hooks/useMe';
import { Button } from '../components/Button';
import { Card, CardHeader, Chip } from '../components/Card';
import { ErrorState, Skeleton } from '../components/States';
import { Screen } from '../components/Screen';
import { useI18n } from '../i18n/I18nProvider';
import type { BirthPrecision, Persona } from '../api/client';
import { useProfileSave } from '../hooks/useProfileSave';

/* ============================================================================
   Me / Settings — вкладка 4. Профиль, тон, память, приватность.

   Подключено к реальному GET /api/me: имя, город, рождение, точность,
   персона, тариф, состояние памяти. Запись идёт через PATCH /api/profile
   (useProfileSave): тон и память — существующие поля ProfileIn, поэтому
   пишутся сразу, без промежуточного состояния.

   Источник истины — сервер: после успешного PATCH перечитываем /api/me,
   а не подменяем значение локально. Провал показывает честную ошибку,
   а не «сохранено».
   ============================================================================ */

const PRECISION_LABEL: Record<
  BirthPrecision,
  'chart.precision_exact' | 'chart.precision_approx' | 'chart.precision_date_only'
> = {
  exact: 'chart.precision_exact',
  approx: 'chart.precision_approx',
  unknown: 'chart.precision_date_only',
};

type Tone = 'friend' | 'witch' | 'mentor';

const TONES: Array<{
  id: Tone;
  labelKey: 'onboarding.tone_friend' | 'onboarding.tone_witch' | 'onboarding.tone_mentor';
}> = [
  { id: 'friend', labelKey: 'onboarding.tone_friend' },
  { id: 'witch', labelKey: 'onboarding.tone_witch' },
  { id: 'mentor', labelKey: 'onboarding.tone_mentor' },
];

export interface SettingsScreenProps {
  onNavigate: (path: string) => void;
}

export function SettingsScreen({ onNavigate }: SettingsScreenProps) {
  const { t } = useI18n();
  const { status, data: me, errorKey, canRetry, reload } = useMe();
  const { state: save, save: saveProfile } = useProfileSave();

  const saving = save.status === 'saving';

  const choosePersona = (persona: Persona) => {
    if (saving || me?.persona === persona) return;
    void saveProfile({ persona }).then((result) => {
      // Перечитываем только при подтверждённой записи: при отказе
      // reload() стёр бы ошибку из состояния до того, как её увидят.
      if (result?.ok) void reload();
    });
  };

  const toggleMemory = () => {
    if (saving || !me) return;
    void saveProfile({ memory_enabled: !me.memory_enabled }).then((result) => {
      if (result?.ok) void reload();
    });
  };

  if (status === 'loading') {
    return (
      <Screen title={t('me.title')} kicker={t('nav.me')}>
        <Skeleton shape="card" count={3} />
      </Screen>
    );
  }

  if (status === 'error' || !me) {
    return (
      <Screen title={errorKey ? t(errorKey) : t('me.title')} kicker={t('nav.me')}>
        <ErrorState
          title={errorKey ? t(errorKey) : t('state.error')}
          hint={t('network.error_hint')}
          retryLabel={canRetry ? t('action.retry') : undefined}
          onRetry={canRetry ? () => void reload() : undefined}
        />
      </Screen>
    );
  }

  return (
    <Screen title={t('me.title')} kicker={t('nav.me')}>
      <Card>
        <CardHeader title={t('me.profile')} />
        <dl className="fact-grid">
          <div>
            <dt>{t('me.field_name')}</dt>
            <dd>{me.name?.trim() || '—'}</dd>
          </div>
          <div>
            <dt>{t('me.field_city')}</dt>
            <dd>{me.birth_city?.trim() || '—'}</dd>
          </div>
          <div>
            <dt>{t('me.field_birth')}</dt>
            <dd>
              {me.birth_date ?? '—'}
              {me.birth_time ? ` · ${me.birth_time}` : ''}
            </dd>
          </div>
          <div>
            <dt>{t('me.precision_label')}</dt>
            <dd>{t(PRECISION_LABEL[me.birth_time_precision])}</dd>
          </div>
          <div>
            {/* Сервер возраста не хранит: колонки удалены миграцией
                0006_drop_age_columns, `age_confirmed_at` в /api/me не
                приходит. Поэтому честно показываем серверный признак
                завершённого онбординга, а не красный «не подтверждён»
                каждому, включая прошедших знакомство. */}
            <dt>{t('me.field_onboarded')}</dt>
            <dd>
              <Chip tone={me.onboarded ? 'success' : 'error'}>
                {t(me.onboarded ? 'me.field_yes' : 'me.field_no')}
              </Chip>
            </dd>
          </div>
          <div>
            <dt>{t('me.plan_label')}</dt>
            <dd>{me.plan?.title ?? t('home.plan_free')}</dd>
          </div>
        </dl>
      </Card>

      <Card>
        <CardHeader title={t('me.tone')} />
        <p className="hint-text">{t('me.tone_hint')}</p>
        <ul className="tone-list" role="radiogroup" aria-label={t('me.tone')}>
          {TONES.map((tone) => (
            <li key={tone.id}>
              <button
                type="button"
                role="radio"
                aria-checked={me.persona === tone.id}
                disabled={saving}
                className={`tone-row${me.persona === tone.id ? ' is-active' : ''}`}
                onClick={() => choosePersona(tone.id)}
              >
                <span aria-hidden="true">
                  {tone.id === 'friend' ? '🌸' : tone.id === 'witch' ? '🔮' : '🕉'}
                </span>
                {t(tone.labelKey)}
              </button>
            </li>
          ))}
        </ul>
        <p className="hint-text" aria-live="polite">
          {save.status === 'saving'
            ? t('profile.saving')
            : save.status === 'saved'
              ? t('profile.saved')
              : save.status === 'error'
                ? (save.detail ?? t(save.errorKey ?? 'state.error'))
                : t('me.tone_hint')}
        </p>
      </Card>

      <Card>
        <CardHeader title={t('me.memory')} />
        <div className="memory-switch">
          <Chip tone={me.memory_enabled ? 'success' : 'error'}>
            {t(me.memory_enabled ? 'oracle.memory_on' : 'oracle.memory_off')}
          </Chip>
          <p className="hint-text">
            {t(me.memory_enabled ? 'memory.toggle_on_hint' : 'memory.toggle_off_hint')}
          </p>
          {/* memory_enabled — существующее поле ProfileIn: переключатель
              пишет на сервер сразу. Значение после записи берём из
              перечитанного /api/me, а не из ответа на PATCH. */}
          <Button variant="secondary" size="md" disabled={saving} onClick={toggleMemory}>
            {t(me.memory_enabled ? 'oracle.memory_off' : 'oracle.memory_on')}
          </Button>
          <Button variant="ghost" size="md" onClick={() => onNavigate('/memory')}>
            {t('memory.title')}
          </Button>
        </div>
      </Card>

      <Card>
        <CardHeader title={t('me.privacy')} />
        <div className="settings-actions">
          <Button variant="ghost" size="md">{t('me.privacy')}</Button>
          <Button variant="ghost" size="md">{t('me.export')}</Button>
          <Button variant="ghost" size="md">{t('me.notifications')}</Button>
          <Button variant="ghost" size="md">{t('me.subscription')}</Button>
        </div>
      </Card>

      <Card>
        <CardHeader title={t('me.delete_account')} />
        <p className="hint-text">{t('me.delete_account_hint')}</p>
        <Button variant="secondary" size="md">{t('me.delete_account')}</Button>
      </Card>
    </Screen>
  );
}
