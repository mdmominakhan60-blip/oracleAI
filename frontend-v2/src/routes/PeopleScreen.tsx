import { useEffect, useState } from 'react';
import { Card, CardHeader, Chip } from '../components/Card';
import { Button } from '../components/Button';
import { EmptyState, ErrorState, Skeleton } from '../components/States';
import { Screen } from '../components/Screen';
import { useI18n, type TranslationKey } from '../i18n/I18nProvider';
import { usePartners } from '../hooks/usePartners';
import { fetchCitySuggestions, type CitySuggestion } from '../api/client';

/* ============================================================================
   People — вкладка 3. Список реальных людей из окружения пользователя.

   Сущность подключена к реальному backend `GET|POST|DELETE /api/partners`
   (app/api/routers/chart.py:463).
   Все демо-данные удалены: список пуст, пока пользователь не добавит
   партнера или не назовет его в диалоге с Оракулом.
   ============================================================================ */

const RELATIONS = ['partner', 'friend', 'family', 'colleague', 'crush'] as const;
type RelationType = (typeof RELATIONS)[number];

const RELATION_LABEL_KEYS: Record<RelationType, TranslationKey> = {
  partner: 'people.relation_partner',
  friend: 'people.relation_friend',
  family: 'people.relation_family',
  colleague: 'people.relation_colleague',
  crush: 'people.relation_crush',
};

export interface PeopleScreenProps {
  onNavigate: (path: string) => void;
}

export function PeopleScreen({ onNavigate }: PeopleScreenProps) {
  const { t } = useI18n();
  const {
    items: people,
    status,
    errorKey,
    canRetry,
    reload,
    add,
    mutation,
    resetMutation,
  } = usePartners();

  const [showAddForm, setShowAddForm] = useState(false);
  const [name, setName] = useState('');
  const [relation, setRelation] = useState<RelationType>('partner');
  const [birthDate, setBirthDate] = useState('');
  const [birthCity, setBirthCity] = useState('');

  const [cities, setCities] = useState<CitySuggestion[]>([]);
  const [citiesOpen, setCitiesOpen] = useState(false);

  // Подсказки городов при добавлении человека
  useEffect(() => {
    const query = birthCity.trim();
    if (!showAddForm || query.length < 2) {
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
          /* ignore */
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [birthCity, showAddForm]);

  const saving = mutation.status === 'saving';

  const handleAddSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (saving) return;
    const ok = await add({
      name: name.trim(),
      relation,
      birth_date: birthDate.trim(),
      birth_city: birthCity.trim() || undefined,
    });
    if (ok) {
      setName('');
      setBirthDate('');
      setBirthCity('');
      setShowAddForm(false);
      resetMutation();
    }
  };

  const handleCancelAdd = () => {
    setShowAddForm(false);
    setName('');
    setBirthDate('');
    setBirthCity('');
    resetMutation();
  };

  if (status === 'loading') {
    return (
      <Screen title={t('people.title')} kicker={t('nav.people')}>
        <Skeleton shape="card" count={2} />
      </Screen>
    );
  }

  if (status === 'error') {
    return (
      <Screen title={t('people.title')} kicker={t('nav.people')}>
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
      title={t('people.title')}
      kicker={t('nav.people')}
      action={
        !showAddForm ? (
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setShowAddForm(true);
              resetMutation();
            }}
          >
            {t('people.add')}
          </Button>
        ) : undefined
      }
    >
      {showAddForm ? (
        <Card raised>
          <CardHeader title={t('people.add')} />
          <form className="memory-form" onSubmit={handleAddSubmit}>
            <div>
              <label className="field-label" htmlFor="person-name">
                {t('people.name_placeholder')}
              </label>
              <input
                id="person-name"
                className="field"
                type="text"
                value={name}
                placeholder={t('people.name_placeholder')}
                disabled={saving}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="field-label" htmlFor="person-birth-date">
                {t('onboarding.date_format')}
              </label>
              <input
                id="person-birth-date"
                className="field"
                type="text"
                inputMode="numeric"
                value={birthDate}
                placeholder={t('onboarding.date_format')}
                disabled={saving}
                onChange={(e) => setBirthDate(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="field-label" htmlFor="person-city">
                {t('city.suggest_label')}
              </label>
              <input
                id="person-city"
                className="field"
                type="text"
                value={birthCity}
                placeholder={t('city.suggest_label')}
                disabled={saving}
                onChange={(e) => {
                  setBirthCity(e.target.value);
                  setCitiesOpen(true);
                }}
              />
              {citiesOpen && cities.length > 0 ? (
                <ul className="city-list">
                  {cities.map((city) => (
                    <li key={city.key}>
                      <button
                        type="button"
                        className="city-row"
                        onClick={() => {
                          setBirthCity(city.key);
                          setCitiesOpen(false);
                        }}
                      >
                        {city.label}
                        {city.detail ? (
                          <span className="city-row__detail">{city.detail}</span>
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>

            <div>
              <span className="field-label">{t('person.relation_label')}</span>
              <div className="chip-row" role="radiogroup" aria-label={t('person.relation_label')}>
                {RELATIONS.map((rel) => (
                  <button
                    key={rel}
                    type="button"
                    role="radio"
                    aria-checked={relation === rel}
                    className={`chip ${relation === rel ? 'chip--accent' : 'chip--neutral'}`}
                    disabled={saving}
                    onClick={() => setRelation(rel)}
                  >
                    {t(RELATION_LABEL_KEYS[rel])}
                  </button>
                ))}
              </div>
            </div>

            {mutation.status === 'error' ? (
              <p className="form-error" role="alert">
                {mutation.errorKey ? t(mutation.errorKey) : t('state.error')}
                {mutation.detail ? ` (${mutation.detail})` : ''}
              </p>
            ) : null}

            <div className="memory-form__row">
              <Button variant="primary" size="md" type="submit" disabled={saving}>
                {saving ? t('people.saving') : t('people.add_submit')}
              </Button>
              <Button
                variant="ghost"
                size="md"
                type="button"
                disabled={saving}
                onClick={handleCancelAdd}
              >
                {t('people.cancel')}
              </Button>
            </div>
          </form>
        </Card>
      ) : null}

      {people.length === 0 && !showAddForm ? (
        <EmptyState
          title={t('people.empty_title')}
          hint={t('people.empty_hint')}
          action={
            <Button
              variant="primary"
              size="md"
              onClick={() => {
                setShowAddForm(true);
                resetMutation();
              }}
            >
              {t('people.add')}
            </Button>
          }
        />
      ) : (
        <ul className="person-list">
          {people.map((person) => {
            const relationKey =
              RELATIONS.includes(person.relation as RelationType)
                ? RELATION_LABEL_KEYS[person.relation as RelationType]
                : undefined;
            const displayRelation = relationKey ? t(relationKey) : person.relation;

            return (
              <li key={person.id}>
                <button
                  type="button"
                  className="person-row"
                  onClick={() => onNavigate(`/people/${person.id}`)}
                >
                  <span className="person-row__avatar" aria-hidden="true">
                    {person.name?.slice(0, 1).toUpperCase()}
                  </span>
                  <span className="person-row__body">
                    <span className="person-row__name">{person.name}</span>
                    <span className="person-row__meta">
                      {person.birth_date}
                      {person.birth_city ? ` · ${person.birth_city}` : ''}
                    </span>
                  </span>
                  <Chip tone="neutral">{displayRelation}</Chip>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Screen>
  );
}
