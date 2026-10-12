import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';
import { DEFAULT_LANG, translate, type Lang, type TranslationKey } from './index';

export type { TranslationKey };

interface I18nContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: (key: TranslationKey, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export interface I18nProviderProps {
  initialLang?: Lang;
  children: ReactNode;
}

/**
 * Провайдер языка. UI не содержит тернарников `lang === 'en'` —
 * всё переводится через словарь (требование приёмки A1-6).
 */
export function I18nProvider({ initialLang = DEFAULT_LANG, children }: I18nProviderProps) {
  const [lang, setLang] = useState<Lang>(initialLang);

  const t = useCallback(
    (key: TranslationKey, vars?: Record<string, string | number>) => translate(lang, key, vars),
    [lang],
  );

  const value = useMemo<I18nContextValue>(() => ({ lang, setLang, t }), [lang, t]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used inside I18nProvider');
  }
  return context;
}

export { dictionaryParity } from './index';
