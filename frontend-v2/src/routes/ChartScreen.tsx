import { Button } from '../components/Button';
import { Card, CardHeader } from '../components/Card';
import { ErrorState, Skeleton } from '../components/States';
import { Screen } from '../components/Screen';
import { fetchChart, type ChartPayload } from '../api/client';
import { useResource, errorKeyFrom, READ_ERRORS } from '../hooks/useResource';
import { useI18n } from '../i18n/I18nProvider';
import type { TranslationKey } from '../i18n/I18nProvider';

/* ============================================================================
   My Chart — натальная карта как визуализация, не таблица.

   Подключено к реальному GET /api/chart: планеты, дома, precision, секции.
   Расчёт остаётся на сервере (kerykeion + pyswisseph) — клиент только рисует.

   Правило честности UI: при precision != exact дома и углы не рисуются,
   и причина называется словами (см. UX_FLOWS §6).
   ============================================================================ */

const SECTION_KEY: Record<string, TranslationKey> = {
  identity: 'chart.section_identity',
  mind_career: 'chart.section_mind',
  relationships: 'chart.section_love',
  nodes: 'chart.section_nodes',
};

export interface ChartScreenProps {
  onNavigate: (path: string) => void;
}

export function ChartScreen({ onNavigate }: ChartScreenProps) {
  const { t } = useI18n();
  const { status, data: chart, errorKey, canRetry, reload } = useResource<ChartPayload>({
    load: (signal) => fetchChart(signal),
    errorKeyFor: errorKeyFrom(READ_ERRORS),
  });

  if (status === 'loading') {
    return (
      <Screen title={t('chart.title')} kicker={t('home.quick_chart')}>
        <Skeleton shape="wheel" count={1} />
        <Skeleton shape="card" count={2} />
      </Screen>
    );
  }

  if (status === 'error' || !chart) {
    return (
      <Screen title={t('chart.title')} kicker={t('home.quick_chart')}>
        <ErrorState
          title={errorKey ? t(errorKey) : t('state.error')}
          hint={t('chart.error_hint')}
          retryLabel={canRetry ? t('action.retry') : undefined}
          onRetry={canRetry ? () => void reload() : undefined}
        />
      </Screen>
    );
  }

  const hasExactAngles = chart.precision === 'exact';
  const sections = chart.sections?.sections ?? {};

  return (
    <Screen
      title={t('chart.title')}
      kicker={t('home.quick_chart')}
      action={
        <button type="button" className="link-btn" onClick={() => onNavigate('/')}>
          {t('action.back_home')}
        </button>
      }
    >
      <Card raised>
        <ChartWheel
          hasAngles={hasExactAngles}
          caption={t(hasExactAngles ? 'chart.horizon_shown' : 'chart.no_horizon')}
        />
        <p className="precision-note">
          {t(hasExactAngles ? 'chart.precision_exact' : 'chart.houses_hidden')}
        </p>
      </Card>

      {chart.sun ? (
        <Card>
          <CardHeader title={t('chart.accents')} />
          <p className="chart-state">
            <span aria-hidden="true">{chart.sun.symbol} </span>
            {t('home.sun_line', { sign: chart.sun.sign, element: chart.sun.element })}
          </p>
        </Card>
      ) : null}

      <Card>
        <CardHeader title={t('chart.planets')} />
        <ul className="planet-list">
          {chart.planets.map((planet) => (
            <li key={planet.name} className="planet-row">
              <span className="planet-row__name">{planet.name}</span>
              <span className="planet-row__sign">{planet.sign}</span>
              <span className="planet-row__deg">
                {planet.deg.toFixed(1)}°
                {planet.retro ? ' ℞' : ''}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      {Object.keys(sections).length > 0 ? (
        <Card>
          <CardHeader title={t('chart.sections_title')} />
          <ul className="section-list">
            {Object.entries(sections).map(([key, section]) => (
              <li key={key} className="section-row">
                <span className="section-row__label">
                  {t(SECTION_KEY[key] ?? 'chart.sections_title')}
                </span>
                {section.items?.slice(0, 3).map((item) => (
                  <span key={item.key} className="section-row__text">
                    {item.label}: {item.value}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      <Button variant="primary" size="lg" fullWidth onClick={() => onNavigate('/oracle')}>
        {t('chart.interpret')}
      </Button>
    </Screen>
  );
}

/** SVG-колесо: inline, без растровых картинок (REUSE_MAP §5). */
function ChartWheel({ hasAngles, caption }: { hasAngles: boolean; caption: string }) {
  const size = 260;
  const center = size / 2;
  const radius = size / 2 - 16;
  const segments = 12;

  return (
    <div className="chart-wheel">
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={caption}>
        <circle cx={center} cy={center} r={radius} className="chart-wheel__rim" />
        <circle cx={center} cy={center} r={radius * 0.62} className="chart-wheel__inner" />
        <circle cx={center} cy={center} r={radius * 0.28} className="chart-wheel__inner" />
        {Array.from({ length: segments }, (_, index) => {
          const angle = (index * 360) / segments - 90;
          const radians = (angle * Math.PI) / 180;
          return (
            <line
              key={index}
              x1={center + Math.cos(radians) * (radius * 0.28)}
              y1={center + Math.sin(radians) * (radius * 0.28)}
              x2={center + Math.cos(radians) * radius}
              y2={center + Math.sin(radians) * radius}
              className="chart-wheel__spoke"
            />
          );
        })}
        {hasAngles ? (
          <line
            x1={center}
            y1={center}
            x2={center}
            y2={center - radius}
            className="chart-wheel__angle"
          />
        ) : null}
      </svg>
      <p className="chart-wheel__caption">{caption}</p>
    </div>
  );
}
