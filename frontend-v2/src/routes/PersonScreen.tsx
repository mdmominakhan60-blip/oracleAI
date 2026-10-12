import { useState } from 'react';
import { Button } from '../components/Button';
import { Card, CardHeader, Chip } from '../components/Card';
import { EmptyState, Skeleton } from '../components/States';
import { Screen } from '../components/Screen';
import { useI18n, type TranslationKey } from '../i18n/I18nProvider';
import { usePartners } from '../hooks/usePartners';
import { useMemories } from '../hooks/useMemories';
import { calculateCompat, type CompatResult } from '../api/client';

/* ============================================================================
   PersonScreen — карточка человека на реальных данных.

   Данные загружаются через usePartners (GET /api/partners).
   Реальные возможности:
   - отображение имени, связи, даты рождения и города;
   - расчет астрологической совместимости через реальный POST /api/compat;
   - отображение связанных фактов из реального GET /api/memories;
   - удаление человека через DELETE /api/partners/{id} с подтверждением.

   Редактирование в backend отсутствует (PATCH не поддерживается), поэтому
   не имитируется на клиенте.
   Связей с раскладами и разговорами в БД нет, поэтому фиктивные списки удалены.
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

export interface PersonScreenProps {
  personId: string;
  onNavigate: (path: string) => void;
}

export function PersonScreen({ personId, onNavigate }: PersonScreenProps) {
  const { t } = useI18n();
  const { getPartner, status, remove } = usePartners();
  const { items: memories } = useMemories();

  const [compatLoading, setCompatLoading] = useState(false);
  const [compatResult, setCompatResult] = useState<CompatResult | null>(null);
  const [compatError, setCompatError] = useState<string | null>(null);

  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const partner = getPartner(personId);

  // Фильтруем факты, относящиеся к этому человеку (автоматические при создании или содержащие имя)
  const relatedMemories = partner
    ? memories.filter((m) => {
        const text = m.fact.toLowerCase();
        const partnerName = partner.name.toLowerCase();
        return text.includes(partnerName);
      })
    : [];

  const handleCalculateCompat = async () => {
    if (!partner || compatLoading) return;
    setCompatLoading(true);
    setCompatError(null);
    try {
      const rel = (
        RELATIONS.includes(partner.relation as RelationType) && partner.relation !== 'crush'
          ? partner.relation
          : 'love'
      ) as 'love' | 'friend' | 'work' | 'family';

      const res = await calculateCompat({
        partner_date: partner.birth_date,
        partner_name: partner.name,
        relation: rel,
      });
      setCompatResult(res);
    } catch {
      setCompatError(t('state.error'));
    } finally {
      setCompatLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!partner || deleting) return;
    setDeleting(true);
    try {
      const ok = await remove(partner.id);
      if (ok) {
        onNavigate('/people');
      }
    } finally {
      setDeleting(false);
    }
  };

  if (status === 'loading') {
    return (
      <Screen title={t('people.title')} kicker={t('nav.people')}>
        <Skeleton shape="card" count={2} />
      </Screen>
    );
  }

  if (!partner) {
    return (
      <Screen
        title={t('people.title')}
        kicker={t('nav.people')}
        action={
          <button type="button" className="link-btn" onClick={() => onNavigate('/people')}>
            {t('people.title')}
          </button>
        }
      >
        <EmptyState
          title={t('person.not_found_title')}
          hint={t('person.not_found_hint')}
          action={
            <Button variant="primary" size="md" onClick={() => onNavigate('/people')}>
              {t('people.title')}
            </Button>
          }
        />
      </Screen>
    );
  }

  const relationKey = RELATIONS.includes(partner.relation as RelationType)
    ? RELATION_LABEL_KEYS[partner.relation as RelationType]
    : undefined;
  const displayRelation = relationKey ? t(relationKey) : partner.relation;

  return (
    <Screen
      title={partner.name}
      kicker={displayRelation}
      action={
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onNavigate(`/people/${personId}/timeline`)}
        >
          {t('timeline.title')}
        </Button>
      }
    >
      <Card>
        <dl className="fact-grid">
          <div>
            <dt>{t('person.relation_label')}</dt>
            <dd>{displayRelation}</dd>
          </div>
          <div>
            <dt>{t('person.birth_label')}</dt>
            <dd>
              {partner.birth_date}
              {partner.birth_city ? ` · ${partner.birth_city}` : ''}
            </dd>
          </div>
        </dl>
        <div className="person-actions">
          <Button
            variant="primary"
            size="md"
            disabled={compatLoading}
            onClick={handleCalculateCompat}
          >
            {compatLoading ? t('person.compat_calculating') : t('person.compat')}
          </Button>
          <Button
            variant="secondary"
            size="md"
            onClick={() => onNavigate('/oracle')}
          >
            {t('person.ask_about')}
          </Button>
        </div>
      </Card>

      {/* Результат расчета совместимости POST /api/compat */}
      {compatResult ? (
        <Card raised>
          <CardHeader
            title={t('person.compat_score', { score: compatResult.total ?? compatResult.score })}
          />
          {compatResult.verdict ? (
            <p className="pattern-text">{compatResult.verdict}</p>
          ) : null}
          {compatResult.breakdown && compatResult.breakdown.length > 0 ? (
            <ul className="fact-list">
              {compatResult.breakdown.map((item, idx) => (
                <li key={idx} className="fact-list__item">
                  <Chip tone="neutral">{item.title}</Chip>
                  <span className="fact-list__text">{item.note}</span>
                  <span className="fact-list__date">{item.value}%</span>
                </li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : null}

      {compatError ? (
        <Card>
          <p className="form-error" role="alert">
            {compatError}
          </p>
        </Card>
      ) : null}

      {/* Что я знаю — реальные воспоминания из GET /api/memories */}
      <Card>
        <CardHeader title={t('person.what_i_know')} />
        {relatedMemories.length === 0 ? (
          <p className="hint-text">{t('person.no_memories')}</p>
        ) : (
          <ul className="fact-list">
            {relatedMemories.map((fact) => (
              <li key={fact.id} className="fact-list__item">
                <Chip tone="neutral">{t('person.fact_saved')}</Chip>
                <span className="fact-list__text">{fact.fact}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Удаление человека с подтверждением */}
      <Card>
        <CardHeader title={t('person.delete')} />
        <p className="hint-text">{t('person.delete_hint')}</p>
        {confirmDelete ? (
          <div>
            <p className="form-error" role="alert">
              {t('person.delete_confirm_title')}
            </p>
            <div className="memory-form__row">
              <Button
                variant="primary"
                size="md"
                disabled={deleting}
                onClick={handleDelete}
              >
                {t('person.delete_confirm_yes')}
              </Button>
              <Button
                variant="ghost"
                size="md"
                disabled={deleting}
                onClick={() => setConfirmDelete(false)}
              >
                {t('person.delete_confirm_no')}
              </Button>
            </div>
          </div>
        ) : (
          <Button
            variant="secondary"
            size="md"
            onClick={() => setConfirmDelete(true)}
          >
            {t('person.delete')}
          </Button>
        )}
      </Card>
    </Screen>
  );
}
