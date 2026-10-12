import { useEffect, useMemo } from 'react';
import { AppShell, type TabId } from './components/TabBar';
import { useHashRoute } from './routes/router';
import { HomeScreen } from './routes/HomeScreen';
import { OracleScreen } from './routes/OracleScreen';
import { PeopleScreen } from './routes/PeopleScreen';
import { PersonScreen } from './routes/PersonScreen';
import { TimelineScreen } from './routes/TimelineScreen';
import { SettingsScreen } from './routes/SettingsScreen';
import { MemoryScreen } from './routes/MemoryScreen';
import { ChartScreen } from './routes/ChartScreen';
import { ReadingScreen } from './routes/ReadingScreen';
import { WelcomeScreen } from './routes/WelcomeScreen';
import { OnboardingScreen } from './routes/OnboardingScreen';
import { FirstInsightScreen } from './routes/FirstInsightScreen';
import { NotFoundScreen } from './routes/NotFoundScreen';
import { useMe } from './hooks/useMe';

/** Маршруты без нижней навигации: Welcome и онбординг занимают весь экран. */
const FULLSCREEN_ROUTES = new Set(['welcome', 'onboarding', 'first-insight']);

/** Маршруты первого запуска: закрыты тому, кто уже прошёл знакомство. */
const FIRST_RUN_ROUTES = new Set(['welcome', 'onboarding']);

export function App() {
  const { route, navigate } = useHashRoute();
  // Пустой хеш означает новый пользователя: сначала Welcome.
  const hasEnteredHash = typeof window !== 'undefined' && window.location.hash.length > 0;
  // Профиль отличает новый запуск от возврата: `onboarded` — серверный
  // признак (GET /api/me), локального флага завершения нет. Пока ответа нет,
  // Welcome не показываем, иначе вернувшийся пользователь мигнул бы экраном
  // первого запуска. Поэтому null — «ещё не знаем, что рисовать».
  const { status: meStatus, data: me, reload: reloadMe } = useMe();
  const profileKnown = meStatus === 'ready' || meStatus === 'error';
  const onboarded = me?.onboarded === true;
  // Переход внутри SPA (hash) не перемонтирует App, а экраны редактируют
  // профиль сами: после записи в онбординге/настройках копия в App остаётся
  // прежней, и закрытый маршрут первого запуска снова открылся бы. Перечитываем
  // профиль при каждой смене маршрута — дешевле и честнее, чем общий стор.
  useEffect(() => {
    void reloadMe();
  }, [route.name, reloadMe]);

  const effectiveName = !hasEnteredHash
    ? profileKnown
      ? onboarded
        ? 'home'
        : 'welcome'
      : null
    : FIRST_RUN_ROUTES.has(route.name) && onboarded
      ? 'home'
      : route.name;

  const activeTab = useMemo<TabId | null>(() => {
    if (effectiveName === 'home') return 'home';
    if (effectiveName === 'oracle') return 'oracle';
    if (effectiveName === 'people' || effectiveName === 'person') return 'people';
    if (effectiveName === 'settings') return 'settings';
    return null;
  }, [effectiveName]);

  // Без useMemo: switch по 13 веткам дешевле мемо, а зависимость от объекта
  // params была источником бага (view менялся, мемо оставался валидным).
  const renderScreen = () => {
    switch (effectiveName) {
      case 'welcome':
        return <WelcomeScreen onNavigate={navigate} />;
      case 'onboarding':
        return <OnboardingScreen onNavigate={navigate} />;
      case 'first-insight':
        return <FirstInsightScreen onNavigate={navigate} />;
      case 'home':
        return <HomeScreen onNavigate={navigate} />;
      case 'oracle':
        return <OracleScreen />;
      case 'people':
        return <PeopleScreen onNavigate={navigate} />;
      case 'person':
        return route.params.view === 'timeline' ? (
          <TimelineScreen
            key={`timeline-${route.params.personId ?? ''}`}
            personId={route.params.personId ?? ''}
            onNavigate={navigate}
          />
        ) : (
          <PersonScreen
            key={`person-${route.params.personId ?? ''}`}
            personId={route.params.personId ?? ''}
            onNavigate={navigate}
          />
        );
      case 'settings':
        return <SettingsScreen onNavigate={navigate} />;
      case 'memory':
        return <MemoryScreen onNavigate={navigate} />;
      case 'chart':
        return <ChartScreen onNavigate={navigate} />;
      case 'reading':
        return (
          <ReadingScreen
            key={`reading-${route.params.readingId ?? ''}`}
            readingId={route.params.readingId ?? ''}
            onNavigate={navigate}
          />
        );
      default:
        return <NotFoundScreen onNavigate={navigate} />;
    }
  };

  const isFullscreen = effectiveName !== null && FULLSCREEN_ROUTES.has(effectiveName);
  // Профиль ещё не ответил и маршрут не выбран: рисуем пустую оболочку, а не
  // угадываем экран. Welcome/Home сами покажут состояние загрузки.
  const screen = effectiveName === null ? null : renderScreen();

  if (isFullscreen) {
    return (
      <div className="app-shell app-shell--fullscreen">
        <main className="app-shell__main" id="main">
          {screen}
        </main>
      </div>
    );
  }

  return (
    <AppShell activeTab={activeTab} lang="ru" onNavigate={navigate}>
      {screen}
    </AppShell>
  );
}
