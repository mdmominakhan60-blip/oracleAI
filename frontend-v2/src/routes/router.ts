import { useCallback, useEffect, useState } from 'react';

/* ============================================================================
   Минимальный hash-роутер.

   Почему hash, а не History API: SPA-fallback на сервере отсутствует —
   GET /{filename} (app/api/main.py:398) является catch-all'ом на один сегмент
   и защищает от path traversal. Прямой маршрут /chart вернул бы JSON 404,
   поэтому hash-режим выбран как решение (UX_FLOWS.md §0, ARCHITECTURE.md §3.1).

   Внешняя библиотека маршрутизации намеренно не добавлена: объём задач этапа 1
   покрывается этим хуком.
   ============================================================================ */

export interface ParsedRoute {
  /** Имя маршрута: 'home' | 'oracle' | 'people' | … | 'notfound' */
  name: string;
  path: string;
  params: Record<string, string>;
}

const KNOWN_ROOTS = new Set([
  'home',
  'welcome',
  'onboarding',
  'first-insight',
  'oracle',
  'people',
  'settings',
  'memory',
  'chart',
  'reading',
]);

function parseHash(hash: string): ParsedRoute {
  const cleaned = hash.replace(/^#\/?/, '').replace(/\/+$/, '');
  if (!cleaned) return { name: 'home', path: '/', params: {} };
  const segments = cleaned.split('/').filter(Boolean);
  const root = segments[0] ?? 'home';

  if (!KNOWN_ROOTS.has(root)) {
    return { name: 'notfound', path: `/${cleaned}`, params: {} };
  }

  const params: Record<string, string> = {};
  if (root === 'people') {
    if (segments[1]) params.personId = segments[1];
    if (segments[2] === 'timeline') params.view = 'timeline';
  }
  if (root === 'reading' && segments[1]) params.readingId = segments[1];

  const name = root === 'people' && segments[1] ? 'person' : root;
  return { name, path: `/${cleaned}`, params };
}

export function useHashRoute(): {
  route: ParsedRoute;
  navigate: (path: string) => void;
} {
  const [route, setRoute] = useState<ParsedRoute>(() =>
    parseHash(typeof window === 'undefined' ? '' : window.location.hash),
  );

  useEffect(() => {
    const onHashChange = () => {
      setRoute(parseHash(window.location.hash));
      // Экран не должен оставлять прежний заголовок документа.
      document.title = 'OracleAI';
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const navigate = useCallback((path: string) => {
    const next = path.startsWith('#') ? path : `#${path.startsWith('/') ? path : `/${path}`}`;
    if (window.location.hash === next) {
      setRoute(parseHash(next));
      return;
    }
    window.location.hash = next;
  }, []);

  return { route, navigate };
}
