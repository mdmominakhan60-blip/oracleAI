import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { DemoBadge } from '../components/Screen';
import { useI18n } from '../i18n/I18nProvider';

/* First Insight: первый настоящий результат после онбординга.
   Показывается один раз; завершается переходом на Home, не на чат. */

export interface FirstInsightScreenProps {
  onNavigate: (path: string) => void;
}

export function FirstInsightScreen({ onNavigate }: FirstInsightScreenProps) {
  const { t } = useI18n();

  return (
    <section className="screen first-insight">
      <h1 className="screen__title">{t('first_insight.title')}</h1>
      <DemoBadge label={t('demo.badge')} hint={t('demo.badge_hint')} />

      <Card raised>
        <p className="insight-lead">{t('demo.insight_lead')}</p>
        <ul className="section-list">
          <li className="section-row">
            <span className="section-row__label">{t('chart.section_identity')}</span>
            <span className="section-row__text">{t('demo.insight_identity')}</span>
          </li>
          <li className="section-row">
            <span className="section-row__label">{t('chart.section_love')}</span>
            <span className="section-row__text">{t('demo.insight_love')}</span>
          </li>
        </ul>
      </Card>

      <Card>
        <p className="insight-question">{t('demo.insight_question')}</p>
      </Card>

      <Button variant="primary" size="lg" fullWidth onClick={() => onNavigate('/')}>
        {t('first_insight.ask')}
      </Button>
      <p className="hint-text">{t('first_insight.stage_note')}</p>
    </section>
  );
}
