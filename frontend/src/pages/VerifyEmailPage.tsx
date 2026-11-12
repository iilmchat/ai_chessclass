import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, verifyEmail } from '../shared/api';

type Status = 'loading' | 'success' | 'error';

/** Публичная страница подтверждения email по ссылке из письма. */
export function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const navigate = useNavigate();
  const [status, setStatus] = useState<Status>('loading');
  const [error, setError] = useState('');
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    if (!token) {
      setStatus('error');
      setError('Токен недействителен или истёк.');
      return;
    }
    verifyEmail(token)
      .then(() => setStatus('success'))
      .catch((err: unknown) => {
        setStatus('error');
        // 422 — токен не прошёл валидацию; показываем общий текст, без деталей.
        setError(
          err instanceof ApiError && err.status !== 422
            ? err.message
            : 'Токен недействителен или истёк.',
        );
      });
  }, [token]);

  return (
    <section>
      <h1 className="page-title">Подтверждение email</h1>
      <p className="page-subtitle">Ссылка из письма ChessClass</p>
      <div className="panel" role="status" aria-live="polite">
        {status === 'loading' && (
          <div className="status-row">
            <span className="spinner" aria-hidden="true" />
            <p>Проверяем токен…</p>
          </div>
        )}
        {status === 'success' && (
          <>
            <h2>Email подтверждён</h2>
            <p>Email подтверждён, можно войти.</p>
          </>
        )}
        {status === 'error' && (
          <>
            <h2>Не удалось подтвердить email</h2>
            <p className="verdict failed-note">{error}</p>
          </>
        )}
        {status !== 'loading' && (
          <div className="auth-actions">
            <button
              className="retry-button auth-button"
              type="button"
              onClick={() => navigate('/login')}
            >
              Перейти к входу
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
