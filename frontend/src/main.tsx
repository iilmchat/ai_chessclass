import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import * as Sentry from '@sentry/react';
import { App } from './app/App';
import './app/app.css';

// S-92: error-tracking включается только при заданном DSN (build-time env).
const sentryDsn = import.meta.env.VITE_SENTRY_DSN;
if (sentryDsn) {
  Sentry.init({
    dsn: sentryDsn,
    environment: __APP_STAGE__,
    tracesSampleRate: 0.1,
  });
}

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('#root не найден в index.html');
}

createRoot(rootElement).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
