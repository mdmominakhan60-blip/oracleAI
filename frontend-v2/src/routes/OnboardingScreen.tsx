import { useEffect, useState } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { useI18n } from '../i18n/I18nProvider';
import { fetchCitySuggestions, type CitySuggestion } from '../api/client';
import { useMe } from '../hooks/useMe';
import { useProfileSave } from '../hooks/useProfileSave';

/* ============================================================================
   Onboarding: тема → дата → время/город → тон → 16+.

   ЗАПИСЬ НА СЕРВЕР. Финальный шаг отправляет PATCH /api/profile с
   `onboarding_complete: true` — сервер валидирует набор полей целиком и
   атомарно пишет профиль, считает карту и выставляет `onboarded=1`
   (app/api/common/onboarding.py). До этого ни одно поле рождения не уходит:
   backend не поддерживает частичное сохранение — проверено живой пробой,
   `birth_date`/`city` без completion не записываются.

   Черновик в localStorage остаётся: он единственный носитель ответов между
   шагами, потому что сервер частичного прогресса не принимает. Но он НЕ
   источник истины о завершении — только ответ сервера и последующий
   GET /api/me. Локальный флаг не заменяет серверный.

   При отказе (сеть, 401, 400, таймаут) ответы остаются в форме, отправку
   можно повторить той же кнопкой. Мутация не повторяется автоматически:
   сервер мог применить её частично, и слепой дубль опаснее ошибки.
   ============================================================================ */

type Step = 'topic' | 'birth' | 'time' | 'tone' | 'age';

const STEPS: Step[] = ['topic', 'birth', 'time', 'tone', 'age'];

const STORAGE_KEY = 'oracleai.onboarding.v1';

interface OnboardingState {
  step: Step;
  topic: string;
  birth_date: string;
  birth_precision: 'exact' | 'approx' | 'unknown';
  birth_time: string;
  birth_city: string;
  tone: 'friend' | 'witch' | 'mentor';
  age_confirmed: boolean;
}

const INITIAL: OnboardingState = {
  step: 'topic',
  topic: '',
  birth_date: '',
  birth_precision: 'exact',
  birth_time: '',
  birth_city: '',
  tone: 'friend',
  age_confirmed: false,
};

function loadState(): OnboardingState {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return INITIAL;
    const parsed = JSON.parse(raw) as Partial<OnboardingState>;
    const step = STEPS.includes(parsed.step as Step) ? (parsed.step as Step) : 'topic';
    return { ...INITIAL, ...parsed, step };
  } catch {
    return INITIAL;
  }
}

/** ДД.ММ.ГГГГ, как принимает parse_birth_date на сервере. */
function toApiDate(value: string): string {
  return value.trim();
}

export interface OnboardingScreenProps {
  onNavigate: (path: string) => void;
}

export function OnboardingScreen({ onNavigate }: OnboardingScreenProps) {
  const { t } = useI18n();
  const { status: meStatus, data: me } = useMe();
  const [state, setState] = useState<OnboardingState>(loadState);
  const { state: save, save: saveProfile } = useProfileSave();

  // Имя приходит из Telegram и уже известно серверу. Пока профиль не
  // загрузился, отправка отключена — не ждём, не подставляем заглушку.
  const serverName = me?.name ?? '';

  const [cities, setCities] = useState<CitySuggestion[]>([]);
  const [citiesOpen, setCitiesOpen] = useState(false);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Приватный режим: онбординг работает в рамках сессии.
    }
  }, [state]);

  // Подсказки городов: запрос уходит с задержкой, чтобы не бить по API на
  // каждую нажатую клавишу. Прежний запрос отменяется — ответ уже не нужен.
  useEffect(() => {
    const query = state.birth_city.trim();
    if (state.step !== 'time' || query.length < 2) {
      setCities([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void fetchCitySuggestions(query, controller.signal)
        .then((res) => {
          if (controller.signal.aborted) return;
          setCities(res.items);
          setCitiesOpen(true);
        })
        .catch(() => {
          // Подсказки — не критичны: сервер всё равно проверит город при
          // завершении, поэтому молча оставляем поле редактируемым.
        });
    }, 250);
    // Уход с экрана или новый ввод гасят и таймер, и сам запрос.
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [state.birth_city, state.step]);

  const stepIndex = STEPS.indexOf(state.step);
  const canSkip = state.step !== 'age';

  const goNext = () => {
    const next = STEPS[stepIndex + 1];
    if (next) {
      setState((prev) => ({ ...prev, step: next }));
      return;
    }
    void complete();
  };

  const goBack = () => {
    const prev = STEPS[stepIndex - 1];
    if (prev) setState((current) => ({ ...current, step: prev }));
    else onNavigate('/');
  };

  /**
   * Завершение: один PATCH со всем набором обязательных полей.
   * Backend требует, чтобы `name`, `birth_date`, `birth_time_precision`,
   * `city` и `intent` пришли ВМЕСТЕ (проверка `required.issubset(
   * item.model_fields_set)`) — проверено живой пробой: тот же набор без
   * `name` в теле даёт 400 «Проверь имя, дату, время и город».
   *
   * `name` отправляем серверным значением из GET /api/me, а не тем, что
   * ввёл пользователь: имя приходит из Telegram (`users.ensure`) и серверу
   * уже известно. Тема первого шага (`topic`) — это запрос, а не имя, и в
   * поле `name` она не попадает.
   */
  const complete = async () => {
    const result = await saveProfile({
      name: serverName,
      birth_date: toApiDate(state.birth_date) || undefined,
      birth_time_precision: state.birth_precision,
      birth_time: state.birth_precision === 'unknown' ? undefined : state.birth_time || undefined,
      city: state.birth_city.trim() || undefined,
      intent: 'oracle',
      persona: state.tone,
      onboarding_complete: true,
    });
    if (!result) return;
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* ignore */
    }
    onNavigate('/first-insight');
  };

  return (
    <section className="onboarding">
      <header className="onboarding__head">
        <button type="button" className="link-btn" onClick={goBack}>
          ←
        </button>
        <div
          className="seg-progress"
          aria-label={t('onboarding.step_counter', { n: stepIndex + 1, total: STEPS.length })}
        >
          {STEPS.map((step, index) => (
            <span key={step} className={index <= stepIndex ? 'is-on' : ''} />
          ))}
        </div>
        <span className="onboarding__count">
          {stepIndex + 1}/{STEPS.length}
        </span>
      </header>

      <div className="onboarding__body">
        {state.step === 'topic' ? (
          <>
            <h1 className="onboarding__title">{t('onboarding.step_topic')}</h1>
            <p className="hint-text">{t('onboarding.topic_hint')}</p>
            <textarea
              className="field field--area"
              rows={4}
              value={state.topic}
              onChange={(event) => setState((prev) => ({ ...prev, topic: event.target.value }))}
            />
            <div className="chip-row">
              {(['relations', 'decision', 'tired', 'anxiety'] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  className="chip chip--neutral"
                  onClick={() =>
                    setState((prev) => ({ ...prev, topic: t(`onboarding.option_${option}`) }))
                  }
                >
                  {t(`onboarding.option_${option}`)}
                </button>
              ))}
            </div>
          </>
        ) : null}

        {state.step === 'birth' ? (
          <>
            <h1 className="onboarding__title">{t('onboarding.step_birth')}</h1>
            <div className="chip-row" role="radiogroup" aria-label={t('onboarding.step_birth')}>
              {(['exact', 'approx', 'unknown'] as const).map((precision) => (
                <button
                  key={precision}
                  type="button"
                  role="radio"
                  aria-checked={state.birth_precision === precision}
                  className={`chip ${state.birth_precision === precision ? 'chip--accent' : 'chip--neutral'}`}
                  onClick={() => setState((prev) => ({ ...prev, birth_precision: precision }))}
                >
                  {t(`onboarding.birth_${precision}`)}
                </button>
              ))}
            </div>
            <label className="field-label" htmlFor="birth-date">
              {t('onboarding.date_format')}
            </label>
            <input
              id="birth-date"
              className="field"
              value={state.birth_date}
              inputMode="numeric"
              onChange={(event) => setState((prev) => ({ ...prev, birth_date: event.target.value }))}
            />
            {state.birth_precision === 'unknown' ? (
              <p className="hint-text">{t('onboarding.birth_note_unknown')}</p>
            ) : null}
          </>
        ) : null}

        {state.step === 'time' ? (
          <>
            <h1 className="onboarding__title">{t('onboarding.step_time')}</h1>
            {state.birth_precision !== 'unknown' ? (
              <>
                <label className="field-label" htmlFor="birth-time">
                  {t('onboarding.time_label')}
                </label>
                <input
                  id="birth-time"
                  className="field"
                  value={state.birth_time}
                  onChange={(event) => setState((prev) => ({ ...prev, birth_time: event.target.value }))}
                />
              </>
            ) : null}
            <label className="field-label" htmlFor="birth-city">
              {t('city.suggest_label')}
            </label>
            <input
              id="birth-city"
              className="field"
              value={state.birth_city}
              onChange={(event) => {
                setState((prev) => ({ ...prev, birth_city: event.target.value }));
                setCitiesOpen(true);
              }}
            />
            <p className="hint-text">{t('city.suggest_hint')}</p>
            {citiesOpen && cities.length > 0 ? (
              <ul className="city-list">
                {cities.map((city) => (
                  <li key={city.key}>
                    <button
                      type="button"
                      className="city-row"
                      onClick={() => {
                        // Кладём `key`, а не `label`: сервер ищет город в
                        // geo.FALLBACK по нормализованному ключу, а часть
                        // подсказок имеет латинский label (London, Tokyo) —
                        // такой город завершение не прошло бы (400).
                        setState((prev) => ({ ...prev, birth_city: city.key }));
                        setCitiesOpen(false);
                      }}
                    >
                      {city.label}
                      {city.detail ? <span className="city-row__detail">{city.detail}</span> : null}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {state.birth_precision !== 'unknown' && !state.birth_time.trim() ? (
              <p className="hint-text hint-text--warn">{t('onboarding.time_required')}</p>
            ) : null}
          </>
        ) : null}

        {state.step === 'tone' ? (
          <>
            <h1 className="onboarding__title">{t('onboarding.step_tone')}</h1>
            <p className="hint-text">{t('me.tone_hint')}</p>
            <ul className="tone-list" role="radiogroup" aria-label={t('onboarding.step_tone')}>
              {(['friend', 'witch', 'mentor'] as const).map((tone) => (
                <li key={tone}>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={state.tone === tone}
                    className={`tone-row${state.tone === tone ? ' is-active' : ''}`}
                    onClick={() => setState((prev) => ({ ...prev, tone }))}
                  >
                    <span aria-hidden="true">{tone === 'friend' ? '🌸' : tone === 'witch' ? '🔮' : '🕉'}</span>
                    {t(`onboarding.tone_${tone}`)}
                  </button>
                </li>
              ))}
            </ul>
          </>
        ) : null}

        {state.step === 'age' ? (
          <>
            <h1 className="onboarding__title">{t('onboarding.step_age')}</h1>
            <Card>
              <label className="age-row">
                <input
                  type="checkbox"
                  checked={state.age_confirmed}
                  onChange={(event) =>
                    setState((prev) => ({ ...prev, age_confirmed: event.target.checked }))
                  }
                />
                <span>{t('onboarding.age_label')}</span>
              </label>
              <p className="hint-text">{t('onboarding.age_note')}</p>
              {!state.age_confirmed ? (
                <p className="hint-text hint-text--warn">{t('onboarding.age_required')}</p>
              ) : null}
              {meStatus === 'loading' ? (
                <p className="hint-text">{t('state.loading')}</p>
              ) : null}
              {meStatus === 'error' ? (
                <p className="hint-text hint-text--warn">{t('profile.need_profile')}</p>
              ) : null}
            </Card>
          </>
        ) : null}

        {state.step === 'age' && save.status === 'error' ? (
          <Card>
            <p className="hint-text hint-text--warn" role="alert">
              {/* Причина из валидатора onboarding_fields приходит строкой и
                  говорит, что именно исправить; общий ключ — только для
                  отказов без текста (422 Pydantic отдаёт массив). */}
              {save.detail ?? t(save.errorKey ?? 'state.error')}
            </p>
            <p className="hint-text">{t('profile.save_failed_hint')}</p>
            <Button variant="secondary" size="md" onClick={() => void complete()}>
              {t('profile.retry')}
            </Button>
          </Card>
        ) : null}
      </div>

      <footer className="onboarding__foot">
        {state.step === 'age' ? (
          <Button
            variant="primary"
            size="lg"
            fullWidth
            disabled={
              !state.age_confirmed || save.status === 'saving' || meStatus !== 'ready' || !serverName
            }
            onClick={goNext}
          >
            {save.status === 'saving' ? t('profile.saving') : t('onboarding.complete')}
          </Button>
        ) : (
          <>
            {/* На шаге времени без него не уйти: сервер отказал бы на
                завершении (400 «Укажи часы и минуты»), а причина была бы
                неочевидна на пятом шаге. */}
            <Button
              variant="primary"
              size="lg"
              fullWidth
              disabled={state.step === 'time' && state.birth_precision !== 'unknown' && !state.birth_time.trim()}
              onClick={goNext}
            >
              {t('action.continue')}
            </Button>
            {canSkip ? (
              <Button variant="ghost" size="md" fullWidth onClick={goNext}>
                {t('action.skip')}
              </Button>
            ) : null}
          </>
        )}
      </footer>
    </section>
  );
}
