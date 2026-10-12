import { Button } from '../components/Button';
import { useI18n } from '../i18n/I18nProvider';

/* Welcome: один заголовок, одна фраза, одна кнопка. Не загрузка, не карусель. */

export interface WelcomeScreenProps {
  onNavigate: (path: string) => void;
}

export function WelcomeScreen({ onNavigate }: WelcomeScreenProps) {
  const { t } = useI18n();

  return (
    <section className="welcome">
      <div className="welcome__sky" aria-hidden="true">
        {Array.from({ length: 24 }, (_, index) => (
          <i key={index} className={`welcome__star welcome__star--${index % 6}`} />
        ))}
      </div>

      <div className="welcome__content">
        <h1 className="welcome__title">{t('welcome.title')}</h1>
        <p className="welcome__body">{t('welcome.body')}</p>
        <Button variant="primary" size="lg" fullWidth onClick={() => onNavigate('/onboarding')}>
          {t('welcome.cta')}
        </Button>
        <p className="welcome__age">{t('welcome.age')}</p>
      </div>
    </section>
  );
}
