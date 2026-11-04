import { useCallback, useEffect, useState } from 'react';
import type {
  CostRowDto,
  ObsAlertDto,
  ObsSummaryDto,
  RetentionResultDto,
  RetentionStatusDto,
} from '../shared/api';
import {
  ApiError,
  apiFetch,
  downloadFile,
  fetchCosts,
  fetchObsAlerts,
  fetchObsSummary,
  fetchRetentionStatus,
  getToken,
  logout,
  runRetention,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

/** S-46: наблюдаемость, стоимость на ученика и retention. */
export function ObservabilityPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [role, setRole] = useState('');
  const [summary, setSummary] = useState<ObsSummaryDto | null>(null);
  const [alerts, setAlerts] = useState<ObsAlertDto[]>([]);
  const [costs, setCosts] = useState<CostRowDto[]>([]);
  const [retention, setRetention] = useState<RetentionStatusDto | null>(null);
  const [lastRun, setLastRun] = useState<RetentionResultDto[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const isAdmin = role === 'admin';

  const load = useCallback(async () => {
    setError('');
    try {
      const profile = await apiFetch<{ role: string }>('/profile/me');
      setRole(profile.role);
      const [snapshot, alertRows, retentionRows] = await Promise.all([
        fetchObsSummary(),
        fetchObsAlerts(),
        fetchRetentionStatus(),
      ]);
      setSummary(snapshot);
      setAlerts(alertRows);
      setRetention(retentionRows);
      if (profile.role === 'admin') {
        setCosts((await fetchCosts(30)).items);
      } else {
        setCosts([]);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка наблюдаемости');
    }
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  const act = useCallback(async (fn: () => Promise<void>, message = '') => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await fn();
      if (message) setNotice(message);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  }, []);

  const onRetention = (dryRun: boolean) =>
    act(async () => {
      const result = await runRetention(dryRun);
      setLastRun(result);
      await load();
    }, dryRun ? 'Dry-run выполнен' : 'Retention выполнен');

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Наблюдаемость</h1>
        <p className="page-subtitle">Метрики, стоимость и retention</p>
        <LoginGate
          hint="Demo: admin@chessclass.dev / dev-admin-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Наблюдаемость</h1>
      <p className="page-subtitle">
        Очереди, LLM/voice-стоимость, алерты и retention (S-46)
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
            setSummary(null);
            setCosts([]);
          }}
        >
          Выйти
        </button>
      </p>
      {error && <p role="status" aria-live="assertive" className="verdict failed-note">{error}</p>}
      {notice && <p className="link-hint">{notice}</p>}

      {summary && (
        <div className="panel stats-grid">
          <div>
            <h2>Инфраструктура</h2>
            <p className="health-label">
              DB: {summary.db ? 'ok' : 'down'} · Redis:{' '}
              {summary.redis ? 'ok' : 'down'} · диск: {summary.diskFreeGb} GB
            </p>
          </div>
          <div>
            <h2>LLM сегодня</h2>
            <p className="health-label">
              {summary.llmCostTodayRub.toFixed(2)} ₽ ·{' '}
              {summary.llmTokensToday} токенов
            </p>
          </div>
          <div>
            <h2>Voice сегодня</h2>
            <p className="health-label">
              {summary.voiceCharsToday} симв. ·{' '}
              {summary.voiceCostTodayRub.toFixed(2)} ₽
            </p>
          </div>
          <div>
            <h2>Retention</h2>
            <p className="health-label">
              последний запуск: {summary.retentionLastRun ?? '—'}
            </p>
          </div>
        </div>
      )}

      {alerts.length > 0 && (
        <div className="panel">
          <h2>Алерты</h2>
          <ul className="facts-list">
            {alerts.map((alert) => (
              <li key={alert.code}>
                <strong>[{alert.severity}]</strong> {alert.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary && (
        <div className="panel">
          <h2>Очереди</h2>
          <ul className="facts-list">
            {Object.entries(summary.queues).map(([queue, depth]) => (
              <li key={queue}>
                {queue}: {depth}
              </li>
            ))}
            {Object.entries(summary.activeMatches).map(([kind, active]) => (
              <li key={`active-${kind}`}>
                active {kind}: {active}
              </li>
            ))}
          </ul>
        </div>
      )}

      {isAdmin && (
        <div className="panel">
          <h2>Retention</h2>
          <div className="class-actions">
            <button
              className="retry-button"
              type="button"
              disabled={busy}
              onClick={() => onRetention(true)}
            >
              Dry-run
            </button>
            <button
              className="retry-button"
              type="button"
              disabled={busy}
              onClick={() => onRetention(false)}
            >
              Запустить retention
            </button>
            <button
              className="retry-button"
              type="button"
              disabled={busy}
              onClick={() =>
                act(
                  () => downloadFile('/admin/observability/costs.csv', 'costs.csv'),
                  'CSV стоимости скачан',
                )
              }
            >
              costs.csv
            </button>
          </div>
          {retention && (
            <ul className="facts-list">
              {retention.policies.map((policy) => (
                <li key={policy.policy}>
                  {policy.policy}: {policy.rows} строк старше{' '}
                  {policy.retentionDays} дн.
                </li>
              ))}
            </ul>
          )}
          {lastRun.length > 0 && (
            <ul className="facts-list">
              {lastRun.map((item) => (
                <li key={item.policy}>
                  {item.policy}: rows={item.rows}, deleted={item.deleted}
                  {item.archivePath ? `, archive=${item.archivePath}` : ''}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {isAdmin && (
        <div className="panel">
          <h2>Стоимость на ученика (30 дней)</h2>
          <div className="class-table-wrap">
            <table className="class-table">
              <thead>
                <tr>
                  <th>Ученик</th>
                  <th>LLM, ₽</th>
                  <th>Voice, ₽</th>
                  <th>Итого, ₽</th>
                  <th>Токены</th>
                </tr>
              </thead>
              <tbody>
                {costs.map((row) => (
                  <tr key={row.userId}>
                    <td>{row.email ?? row.userId}</td>
                    <td>{row.llmCostRub.toFixed(2)}</td>
                    <td>{row.voiceCostRub.toFixed(2)}</td>
                    <td>{row.totalCostRub.toFixed(2)}</td>
                    <td>
                      {row.tokensIn}/{row.tokensOut}
                    </td>
                  </tr>
                ))}
                {costs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="link-hint">
                      Нет данных за период.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
