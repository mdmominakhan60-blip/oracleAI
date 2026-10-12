import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { useI18n } from '../i18n/I18nProvider';

/* Неизвестный маршрут: объяснение и путь домой, а не пустой экран. */

export interface NotFoundScreenProps {
  onNavigate: (path: string) => void;
}

export function NotFoundScreen({ onNavigate }: NotFoundScreenProps) {
  const { t } = useI18n();

  return (
    <section className="screen notfound">
      <Card raised>
        <h1 className="screen__title">{t('notfound.title')}</h1>
        <p className="hint-text">{t('notfound.hint')}</p>
        <Button variant="primary" size="lg" fullWidth onClick={() => onNavigate('/')}>
          {t('action.back_home')}
        </Button>
      </Card>
    </section>
  );
}
