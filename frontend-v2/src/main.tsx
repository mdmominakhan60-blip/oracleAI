import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { DEFAULT_LANG } from './i18n';
import { I18nProvider } from './i18n/I18nProvider';
import { initializeApi } from './api/configure';
import './styles/tokens.css';
import './styles/base.css';
import './styles/components.css';

const container = document.getElementById('root');
if (!container) {
  throw new Error('Root container #root is missing from index.html');
}

// Сессия: обмен initData на токен. Вне Telegram приложение работает в
// неавторизованном режиме — сервер сам ответит 401 на защищённых ручках.
void initializeApi();

createRoot(container).render(
  <StrictMode>
    <I18nProvider initialLang={DEFAULT_LANG}>
      <App />
    </I18nProvider>
  </StrictMode>,
);
