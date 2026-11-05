import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { ConsentStatusDto } from '../shared/api';
import {
  ApiError,
  confirmParentalConsent,
  fetchConsentStatus,
  getToken,
  requestParentalConsent,
  revokeParentalConsent,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

const STATUS_LABELS: Record<string, string> = {
  not_required: 'Согласие не требуется (взрослый аккаунт)',
  none: 'Согласие ещё не запрошено',
  pending: 'Ожидает подтверждения родителя',
  granted: 'Согласие получено',
  revoked: 'Согласие отозвано',
  expired: 'Срок ссылки истёк',
};

/** S-74: COPPA/GDPR-K — запрос, подтверждение по ссылке и отзыв согласия. */
export function ConsentPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [status, setStatus] = useState<ConsentStatusDto | null>(null);
  const [parentEmail, setParentEmail] = useState('');
  const [devLink, setDevLink] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const confirmedRef = useRef(false);

  const load = useCallback(async () => {
    setError('');
    try {
      setStatus(await fetchConsentStatus());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки');
    }
  }, []);

  useEffect(() => {
    if (!token) return;
    if (confirmedRef.current) return;
    confirmedRef.current = true;
    setBusy(true);
    confirmParentalConsent(token)
      .then((result) => {
        setStatus(result);
        setNotice('Согласие родителя подтверждено');
      })
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Ссылка недействительна');
      })
      .finally(() => setBusy(false));
  }, [token]);

  useEffect(() => {
    if (authed && !token) load();
  }, [authed, token, load]);

  const request = useCallback(async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await requestParentalConsent(parentEmail);
      setStatus(result);
      setDevLink(result.confirmUrl ?? '');
      setNotice(
        'Запрос создан. В dev-режиме ссылка для родителя показана ниже.',
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка запроса');
    } finally {
      setBusy(false);
    }
  }, [parentEmail]);

  const revoke = useCallback(async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      setStatus(await revokeParentalConsent());
      setDevLink('');
      setNotice('Согласие отозвано');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка отзыва');
    } finally {
      setBusy(false);
    }
  }, []);

  if (!authed && !token) {
    return (
      <section>
        <h1 className="page-title">Согласие родителя</h1>
        <p className="page-subtitle">COPPA/GDPR-K: подтверждение для учеников до 18 лет</p>
        <LoginGate
          hint="Demo: student1@chessclass.dev / dev-student-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Согласие родителя</h1>
      <p className="page-subtitle">
        Для учеников младше 18 лет нужно подтверждение родителя или опекуна.
        Согласие можно отозвать в любой момент.
      </p>
      {error && (
        <p role="status" aria-live="assertive" className="verdict failed-note">
          {error}
        </p>
      )}
      {notice && <p className="link-hint">{notice}</p>}

      {token && (
        <div className="panel">
          <h2>Подтверждение по ссылке</h2>
          <p className="class-meta">
            {busy ? 'Проверяем ссылку…' : STATUS_LABELS[status?.status ?? 'none']}
          </p>
        </div>
      )}

      {!token && status && (
        <div className="profile-grid">
          <div className="panel">
            <h2>Статус</h2>
            <p>
              <strong>{STATUS_LABELS[status.status] ?? status.status}</strong>
            </p>
            <p className="class-meta">Версия политики: {status.policyVersion}</p>
            {status.parentEmail && (
              <p className="class-meta">Родитель: {status.parentEmail}</p>
            )}
            {status.confirmedAt && (
              <p className="class-meta">
                Подтверждено: {new Date(status.confirmedAt).toLocaleString('ru-RU')}
              </p>
            )}
            {status.expiresAt && status.status === 'pending' && (
              <p className="class-meta">
                Ссылка действует до:{' '}
                {new Date(status.expiresAt).toLocaleString('ru-RU')}
              </p>
            )}
            {status.status === 'not_required' && (
              <p className="link-hint">
                Возрастная группа «взрослый» не требует родительского согласия.
              </p>
            )}
          </div>

          {status.required && status.status !== 'granted' && (
            <div className="panel">
              <h2>Запросить согласие</h2>
              <div className="class-actions">
                <input
                  className="field"
                  type="email"
                  value={parentEmail}
                  onChange={(e) => setParentEmail(e.target.value)}
                  placeholder="email родителя"
                  aria-label="Email родителя"
                />
                <button
                  className="retry-button"
                  type="button"
                  disabled={busy || !parentEmail}
                  onClick={request}
                >
                  Отправить ссылку
                </button>
              </div>
              {devLink && (
                <p className="link-hint">
                  Dev-ссылка для проверки:{' '}
                  <a href={devLink}>{devLink}</a>
                </p>
              )}
            </div>
          )}

          {(status.status === 'granted' || status.status === 'pending') && (
            <div className="panel">
              <h2>Отзыв</h2>
              <p className="class-meta">
                Отзыв прекращает обработку данных, требующую согласия.
              </p>
              <button
                className="retry-button"
                type="button"
                disabled={busy}
                onClick={revoke}
              >
                Отозвать согласие
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
