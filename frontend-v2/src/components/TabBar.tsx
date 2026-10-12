import type { ReactNode } from 'react';
import { translate, type Lang } from '../i18n';

export type TabId = 'home' | 'oracle' | 'people' | 'settings';

export interface TabDef {
  id: TabId;
  labelKey: 'nav.home' | 'nav.oracle' | 'nav.people' | 'nav.me';
  path: string;
}

/** Четыре нижние вкладки — весь способ перемещения по продукту. */
export const TABS: readonly TabDef[] = [
  { id: 'home', labelKey: 'nav.home', path: '/' },
  { id: 'oracle', labelKey: 'nav.oracle', path: '/oracle' },
  { id: 'people', labelKey: 'nav.people', path: '/people' },
  { id: 'settings', labelKey: 'nav.me', path: '/settings' },
];

export interface TabBarProps {
  active: TabId | null;
  lang: Lang;
  onNavigate: (path: string) => void;
}

export function TabBar({ active, lang, onNavigate }: TabBarProps) {
  return (
    <nav className="tabbar" aria-label={translate(lang, 'app.title')}>
      <ul className="tabbar__list">
        {TABS.map((tab) => {
          const isActive = tab.id === active;
          return (
            <li key={tab.id} className="tabbar__item">
              <button
                type="button"
                className={`tabbar__btn${isActive ? ' is-active' : ''}`}
                aria-current={isActive ? 'page' : undefined}
                onClick={() => onNavigate(tab.path)}
              >
                <span className="tabbar__label">{translate(lang, tab.labelKey)}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export interface AppShellProps {
  activeTab: TabId | null;
  lang: Lang;
  onNavigate: (path: string) => void;
  children: ReactNode;
}

/** Каркас приложения: контент + нижняя навигация. */
export function AppShell({ activeTab, lang, onNavigate, children }: AppShellProps) {
  return (
    <div className="app-shell">
      <main className="app-shell__main" id="main">
        {children}
      </main>
      <TabBar active={activeTab} lang={lang} onNavigate={onNavigate} />
    </div>
  );
}
