import { Button } from '../components/Button';
import { EmptyState, Skeleton } from '../components/States';
import { Screen } from '../components/Screen';
import { useI18n } from '../i18n/I18nProvider';
import { usePartners } from '../hooks/usePartners';

/* ============================================================================
   Relationship Timeline: хроника отношений с человеком.

   Контракт:
   В существующем backend и БД таблицы связей (memory_links) и личных событий
   (personal_events) отсутствуют (запланированы на Этап 6 в MIGRATION_PLAN.md).
   Поэтому фиктивные данные удалены: если связанных событий нет, экран
   честно показывает пустое состояние с предложением обсудить человека в чате.
   ============================================================================ */

export interface TimelineScreenProps {
  onNavigate: (path: string) => void;
  personId?: string;
}

export function TimelineScreen({ onNavigate, personId }: TimelineScreenProps) {
  const { t } = useI18n();
  const { getPartner, status } = usePartners();

  const partner = getPartner(personId);

  if (status === 'loading') {
    return (
      <Screen title={t('timeline.title')} kicker={t('people.title')}>
        <Skeleton shape="card" count={2} />
      </Screen>
    );
  }

  if (!partner) {
    return (
      <Screen
        title={t('timeline.title')}
        kicker={t('people.title')}
        action={
          <button
            type="button"
            className="link-btn"
            onClick={() => onNavigate('/people')}
          >
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

  return (
    <Screen
      title={t('timeline.title')}
      kicker={partner.name}
      action={
        <button
          type="button"
          className="link-btn"
          onClick={() => onNavigate(`/people/${personId}`)}
        >
          {partner.name}
        </button>
      }
    >
      <div className="timeline">
        <EmptyState
          title={t('timeline.empty_title')}
          hint={t('timeline.empty_state')}
          action={
            <Button
              variant="secondary"
              size="md"
              onClick={() => onNavigate('/oracle')}
            >
              {t('person.ask_about')}
            </Button>
          }
        />
      </div>
    </Screen>
  );
}
