import { useMe } from '../hooks/useMe';
import { useToday } from '../hooks/useToday';
import { Card, CardHeader, Chip } from '../components/Card';
import { Button } from '../components/Button';
import { ErrorState, Skeleton } from '../components/States';
import { ActionTile, Screen } from '../components/Screen';
import { useI18n } from '../i18n/I18nProvider';
import type { BirthPrecision } from '../api/client';

/* ============================================================================
   Home — персональная сводка (вкладка 1).

   Подключено к реальному GET /api/me (имя, план, лимиты, память, точность
   карты) и GET /api/today (карта дня, лунный ориентир, сезон Солнца,
   сфера дня, следующий шаг). /api/today требует активной подписки:
   при 402 экран честно показывает тарифное ограничение, не имитируя прогноз.
   ============================================================================ */

const PRECISION_LABEL: Record<BirthPrecision, 'chart.precision_exact' | 'chart.precision_approx' | 'chart.precision_date_only'> = {
  exact: 'chart.precision_exact',
  approx: 'chart.precision_approx',
  unknown: 'chart.precision_date_only',
};

export interface HomeScreenProps {
  onNavigate: (path: string) => void;
}

export function HomeScreen({ onNavigate }: HomeScreenProps) {
  const { t } = useI18n();
  const { status, data: me, errorKey, canRetry, reload } = useMe();

  if (status === 'loading') {
    return (
      <Screen title={t('app.title')} kicker={t('nav.home')}>
        <Skeleton shape="card" count={1} />
        <Skeleton shape="card" count={2} />
      </Screen>
    );
  }

  if (status === 'error' || !me) {
    // Заголовок экрана = сам отказ: иначе под «OracleAI» висит ошибка,
    // и пользователь не понимает, что экран не загрузился именно поэтому.
    return (
      <Screen title={errorKey ? t(errorKey) : t('app.title')} kicker={t('nav.home')}>
        <ErrorState
          title={errorKey ? t(errorKey) : t('state.error')}
          hint={t('network.error_hint')}
          retryLabel={canRetry ? t('action.retry') : undefined}
          onRetry={canRetry ? () => void reload() : undefined}
        />
      </Screen>
    );
  }

  const displayName = me.name?.trim() || me.oracle_name?.trim() || t('oracle.title');
  const greeting = me.onboarded ? t('home.greeting', { name: displayName }) : t('home.greeting_new', { name: displayName });
  const precision = me.birth_time_precision;
  const allowance = me.allowance;

  return (
    <Screen
      title={greeting}
      kicker={t('nav.home')}
    >
      {/* Реальные данные: лимиты и тариф */}
      <Card>
        <CardHeader
          title={me.plan?.title ?? t('home.plan_free')}
          kicker={t('home.allowance_kicker')}
          action={
            <Chip tone={allowance.can_ask ? 'success' : 'error'}>
              {t('home.questions_left', { n: allowance.left })}
            </Chip>
          }
        />
        <p className="allowance-line">
          {allowance.period === 'day'
            ? t('home.allowance_day', { used: allowance.used, limit: allowance.limit })
            : t('home.allowance_week', { used: allowance.used, limit: allowance.limit })}
        </p>
      </Card>

      {/* Реальные данные: память, которую Oracle сохранил */}
      <Card>
        <CardHeader
          title={t('home.memory_block')}
          kicker={t(me.memory_enabled ? 'oracle.memory_on' : 'oracle.memory_off')}
          action={
            <Button variant="ghost" size="sm" onClick={() => onNavigate('/memory')}>
              {t('home.memory_more')}
            </Button>
          }
        />
        {me.memory_enabled && me.memories.length > 0 ? (
          <ul className="memory-strip">
            {me.memories.slice(0, 3).map((fact: string, index: number) => (
              <li key={`${index}-${fact}`} className="memory-strip__item">
                <Chip tone="neutral">{t('person.fact_saved')}</Chip>
                <span className="memory-strip__text">{fact}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint-text">
            {me.memory_enabled ? t('memory.empty_hint') : t('memory.toggle_off_hint')}
          </p>
        )}
      </Card>

      {/* Реальные данные: точность натальной карты */}
      <Card>
        <CardHeader title={t('home.chart_state')} kicker={t('home.quick_chart')} />
        {me.sun ? (
          <p className="chart-state">
            <span aria-hidden="true">{me.sun.symbol} </span>
            {t('home.sun_line', { sign: me.sun.sign, element: me.sun.element })}
          </p>
        ) : (
          <p className="hint-text">{t('chart.empty_hint')}</p>
        )}
        <p className="hint-text">{t(PRECISION_LABEL[precision])}</p>
        <Button variant="secondary" size="md" onClick={() => onNavigate('/chart')}>
          {t('home.quick_chart')}
        </Button>
      </Card>

      {/* Реальные данные: прогноз дня (карта, луна, сезон, следующий шаг) */}
      <TodaySection />

      {/* Быстрые действия */}
      <div className="quick-grid">
        <ActionTile
          title={t('home.quick_ask')}
          hint={t('home.quick_ask_hint')}
          onClick={() => onNavigate('/oracle')}
        />
        <ActionTile
          title={t('home.quick_tarot')}
          hint={t('home.quick_tarot_hint')}
          onClick={() => onNavigate('/oracle')}
        />
        <ActionTile
          title={t('home.quick_people')}
          hint={t('home.quick_people_hint')}
          onClick={() => onNavigate('/people')}
        />
        <ActionTile
          title={t('nav.me')}
          hint={t('me.tone_hint')}
          onClick={() => onNavigate('/settings')}
        />
      </div>
    </Screen>
  );
}

/* ============================================================================
   Прогноз дня — GET /api/today.

   Отдельный компонент со своими состояниями, чтобы отказ прогноза
   (подписка/лимит/сеть) не ронял остальную сводку Home: подписка и лимиты
   продолжают показываться.
   ============================================================================ */

function TodaySection() {
  const { t } = useI18n();
  const { status, today, errorKey, canRetry, reload } = useToday();

  if (status === 'loading') {
    return (
      <Card>
        <CardHeader title={t('today.title')} kicker={t('app.tagline')} />
        <Skeleton shape="card" count={1} />
      </Card>
    );
  }

  // Тарифное ограничение: честное состояние, без имитации прогноза.
  if (status === 'locked') {
    return (
      <Card raised>
        <CardHeader title={t('today.locked_title')} kicker={t('today.title')} />
        <p className="insight-question">{t('today.locked_hint')}</p>
        <p className="hint-text">{t('today.locked_cta')} — в боте, раздел «Подписка».</p>
      </Card>
    );
  }

  if (status === 'error' || !today) {
    return (
      <Card>
        <CardHeader title={t('today.title')} kicker={t('app.tagline')} />
        <ErrorState
          title={errorKey ? t(errorKey) : t('state.error')}
          hint={t('network.error_hint')}
          retryLabel={canRetry ? t('action.retry') : undefined}
          onRetry={canRetry ? () => void reload() : undefined}
        />
      </Card>
    );
  }

  return (
    <>
      <Card raised>
        <CardHeader title={t('home.card_of_day')} kicker={t('today.title')} />
        <div className="day-card is-revealed">
          <img
            className="day-card__img"
            src={`/static/img/tarot/${today.card.img}.jpg`}
            alt={today.card.name}
            width={132}
            height={198}
            onError={(event) => {
              event.currentTarget.src = '/static/img/card-back.jpg';
            }}
          />
          <span className="day-card__name">
            {today.card.emoji} {today.card.name}
          </span>
          <p className="day-card__meaning">
            {t('home.card_meaning')}: {today.card.meaning}
          </p>
        </div>
      </Card>

      <Card>
        <CardHeader title={t('today.forecast')} />
        <p className="prose-answer">{today.forecast}</p>
      </Card>

      <Card>
        <CardHeader title={t('today.moon')} />
        <p className="moon-line">
          <span className="moon-line__emoji" aria-hidden="true">
            {today.moon.emoji}
          </span>
          {today.moon.name}, {today.moon.day}-й лунный день. {today.moon.advice}
        </p>
        <p className="hint-text">
          <span aria-hidden="true">{today.sun_season.symbol} </span>
          {t('today.sun_season')}: {today.sun_season.sign}
        </p>
        <p className="hint-text">{t('today.sphere')}: {today.sphere}</p>
      </Card>

      {today.next_action?.title ? (
        <Card>
          <CardHeader
            title={t('today.next_step')}
            action={
              <span aria-hidden="true" className="next-step__emoji">
                {today.next_action.emoji}
              </span>
            }
          />
          <p className="next-step__title">{today.next_action.title}</p>
          <p className="hint-text">{today.next_action.text}</p>
        </Card>
      ) : null}
    </>
  );
}
