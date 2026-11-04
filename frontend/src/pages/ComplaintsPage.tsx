import { useCallback, useEffect, useState } from 'react';
import type { PvpComplaintDto } from '../shared/api';
import {
  ApiError,
  apiFetch,
  getToken,
  logout,
  reviewPvpComplaint,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

const FILTERS = ['', 'open', 'reviewed', 'rejected'] as const;

/** S-65: очередь жалоб PvP (teacher/admin) — open → reviewed/rejected. */
export function ComplaintsPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [role, setRole] = useState('');
  const [rows, setRows] = useState<PvpComplaintDto[]>([]);
  const [filter, setFilter] = useState<'' | 'open' | 'reviewed' | 'rejected'>('open');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

  const isGuard = role === 'teacher' || role === 'admin';

  const refresh = useCallback(
    (status: string) => {
      const suffix = status ? `?status=${encodeURIComponent(status)}` : '';
      apiFetch<PvpComplaintDto[]>(`/admin/pvp/complaints${suffix}`)
        .then(setRows)
        .catch(() => setRows([]));
    },
    [],
  );

  const load = useCallback(async () => {
    setError('');
    try {
      const profile = await apiFetch<{ role: string }>('/profile/me');
      setRole(profile.role);
      if (profile.role === 'teacher' || profile.role === 'admin') {
        refresh('open');
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка очереди жалоб');
    }
  }, [refresh]);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  const act = useCallback(
    async (fn: () => Promise<void>, message: string) => {
      setBusy(message);
      setNotice('');
      setError('');
      try {
        await fn();
        setNotice(`Готово: ${message}`);
        refresh(filter);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Ошибка операции');
      } finally {
        setBusy('');
      }
    },
    [refresh, filter],
  );

  const onReview = (complaint: PvpComplaintDto, status: 'reviewed' | 'rejected') =>
    act(
      async () => {
        await reviewPvpComplaint(complaint.id, status, notes[complaint.id] || undefined);
      },
      `${status} жалобу #${complaint.id}`,
    );

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Очередь жалоб PvP</h1>
        <p className="page-subtitle" role="status" aria-live="polite">Разбор доступен после входа</p>
        <LoginGate hint="Разбор жалоб — учитель/админ" onReady={() => setAuthed(true)} />
      </section>
    );
  }
  if (!isGuard) {
    return (
      <section>
        <h1 className="page-title">Очередь жалоб PvP</h1>
        <p className="verdict failed-note">Доступно учителю/админу (роль: {role || '—'})</p>
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Очередь жалоб PvP</h1>
      <p className="page-subtitle" role="status" aria-live="polite">
        open → reviewed / rejected (S-65, вердикт за учителем) · {busy || notice || '—'}
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
          }}
        >
          Выйти
        </button>
      </p>
      {error && <p role="status" aria-live="assertive" className="verdict failed-note">{error}</p>}

      <div className="panel">
        <div className="rag-toolbar">
          <h2>Жалобы ({rows.length})</h2>
          <select
            className="field"
            value={filter}
            onChange={(e) => {
              const value = e.target.value as '' | 'open' | 'reviewed' | 'rejected';
              setFilter(value);
              refresh(value);
            }}
            aria-label="Фильтр статуса"
          >
            {FILTERS.map((value) => (
              <option key={value || 'all'} value={value}>
                {value === '' ? 'все статусы' : value}
              </option>
            ))}
          </select>
          <button className="retry-button" type="button" onClick={() => refresh(filter)}>
            Обновить
          </button>
        </div>

        <ul className="facts-list">
          {rows.map((complaint) => (
            <li
              key={complaint.id}
              className={complaint.status === 'open' ? 'pvp-complaint-row' : undefined}
            >
              <strong>#{complaint.id}</strong> · комната {complaint.roomId} · reporter{' '}
              {complaint.reporterId} · <span className="level-tag">{complaint.status}</span>
              <div className="pvp-complaint-reason">{complaint.reason}</div>
              {complaint.note && (
                <div className="pvp-complaint-reason">
                  вердикт: {complaint.note} (by {complaint.reviewedBy ?? '—'})
                </div>
              )}
              {complaint.status === 'open' && (
                <>
                  <input
                    className="field"
                    value={notes[complaint.id] ?? ''}
                    placeholder="вердикт / комментарий (необязательный)"
                    onChange={(e) =>
                      setNotes((prev) => ({ ...prev, [complaint.id]: e.target.value }))
                    }
                  />
                  <div className="submit-row">
                    <button
                      className="retry-button"
                      type="button"
                      disabled={busy !== ''}
                      onClick={() => onReview(complaint, 'reviewed')}
                    >
                      подтверждено (reviewed)
                    </button>
                    <button
                      className="retry-button"
                      type="button"
                      disabled={busy !== ''}
                      onClick={() => onReview(complaint, 'rejected')}
                    >
                      отклонено (rejected)
                    </button>
                  </div>
                </>
              )}
            </li>
          ))}
          {rows.length === 0 && <li className="link-hint">Очередь пуста</li>}
        </ul>
      </div>
    </section>
  );
}
