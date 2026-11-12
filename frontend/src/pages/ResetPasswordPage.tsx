import { useState } from 'react';
import type { FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ApiError, resetPassword } from '../shared/api';

/** Публичная страница установки нового пароля по ссылке из письма. */
export function ResetPasswordPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState(
    token ? '' : 'Ссылка недействительна или истекла.',
  );

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');
    if (!token) {
      setError('Ссылка недействительна или истекла.');
      return;
    }
    if (password.length < 8) {
      setError('Пароль должен содержать минимум 8 символов.');
      return;
    }
    if (password !== confirmation) {
      setError('Пароли не совпадают.');
      return;
    }
    setBusy(true);
    try {
      await resetPassword(token, password);
      setSuccess(true);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Не удалось изменить пароль.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <section>
      <h1 className="page-title">Сброс пароля</h1>
      <p className="page-subtitle">Ссылка из письма ChessClass</p>
      <div className="panel">
        {success ? (
          <>
            <h2>Пароль изменён</h2>
            <p>Пароль изменён, можно войти с новым паролем.</p>
            <div className="auth-actions">
              <button
                className="retry-button auth-button"
                type="button"
                onClick={() => navigate('/login')}
              >
                Перейти к входу
              </button>
            </div>
          </>
        ) : (
          <form className="login-form" onSubmit={submit} noValidate>
            <h2>Новый пароль</h2>
            <input
              className="field"
              type="password"
              placeholder="новый пароль"
              autoComplete="new-password"
              value={password}
              disabled={!token || busy}
              onChange={(e) => setPassword(e.target.value)}
            />
            <input
              className="field"
              type="password"
              placeholder="повторите пароль"
              autoComplete="new-password"
              value={confirmation}
              disabled={!token || busy}
              onChange={(e) => setConfirmation(e.target.value)}
            />
            <p className="link-hint">Минимум 8 символов.</p>
            {error && (
              <p role="status" aria-live="assertive" className="verdict failed-note">
                {error}
              </p>
            )}
            <div className="auth-actions">
              <button
                className="retry-button auth-button"
                type="submit"
                disabled={!token || busy}
              >
                {busy ? 'Сохраняем…' : 'Изменить пароль'}
              </button>
            </div>
            {busy && (
              <p className="link-hint" role="status">
                Сохраняем новый пароль…
              </p>
            )}
          </form>
        )}
      </div>
    </section>
  );
}
