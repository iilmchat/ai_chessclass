import { useCallback, useState } from 'react';
import { ApiError, login } from './api';

/** Вход для доменных экранов (S-08 python / S-11 chess). */
export function LoginGate({ hint, onReady }: { hint?: string; onReady: () => void }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      await login(email.trim(), password);
      onReady();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка входа');
    } finally {
      setBusy(false);
    }
  }, [email, password, onReady]);

  return (
    <div className="panel">
      <h2>Вход</h2>
      {hint && <p className="link-hint">{hint}</p>}
      <div className="login-form">
        <input
          className="field"
          placeholder="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className="field"
          type="password"
          placeholder="пароль"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="retry-button" type="button" disabled={busy} onClick={submit}>
          {busy ? 'Входим…' : 'Войти'}
        </button>
      </div>
      {error && <p className="verdict failed-note">{error}</p>}
    </div>
  );
}
