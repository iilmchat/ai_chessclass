import { useCallback, useEffect, useState } from 'react';
import type {
  CostRowDto,
  FailedJobDto,
  LmsClassMapDto,
  LmsCourseDto,
  LmsOauthStatusDto,
  LmsStatusDto,
  ObsAlertDto,
  ObsSummaryDto,
  RetentionResultDto,
  RetentionStatusDto,
} from '../shared/api';
import {
  ApiError,
  apiFetch,
  createLmsClassMap,
  createLmsCourse,
  deleteLmsClassMap,
  deleteLmsCourse,
  downloadFile,
  fetchCosts,
  fetchFailedJobs,
  fetchLmsClassMap,
  fetchLmsCourses,
  fetchLmsOauthStatus,
  fetchLmsStatus,
  fetchObsAlerts,
  fetchObsSummary,
  fetchRetentionStatus,
  getToken,
  logout,
  retryFailedJob,
  runRetention,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

/** S-46: наблюдаемость, стоимость на ученика и retention. S-67: LMS LRS. */
export function ObservabilityPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [role, setRole] = useState('');
  const [summary, setSummary] = useState<ObsSummaryDto | null>(null);
  const [alerts, setAlerts] = useState<ObsAlertDto[]>([]);
  const [costs, setCosts] = useState<CostRowDto[]>([]);
  const [failedJobs, setFailedJobs] = useState<FailedJobDto[]>([]);
  const [retention, setRetention] = useState<RetentionStatusDto | null>(null);
  const [lastRun, setLastRun] = useState<RetentionResultDto[]>([]);
  const [lmsStatus, setLmsStatus] = useState<LmsStatusDto | null>(null);
  const [lmsOauth, setLmsOauth] = useState<LmsOauthStatusDto | null>(null);
  const [lmsCourses, setLmsCourses] = useState<LmsCourseDto[]>([]);
  const [lmsMaps, setLmsMaps] = useState<LmsClassMapDto[]>([]);
  const [courseExternalId, setCourseExternalId] = useState('');
  const [courseTitle, setCourseTitle] = useState('');
  const [mapClassId, setMapClassId] = useState('');
  const [mapCourseId, setMapCourseId] = useState('');
  const [mapActivityRef, setMapActivityRef] = useState('');
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
        setFailedJobs(await fetchFailedJobs());
        const [status, oauth] = await Promise.all([
          fetchLmsStatus(),
          fetchLmsOauthStatus(),
        ]);
        setLmsStatus(status);
        setLmsOauth(oauth);
      } else {
        setCosts([]);
        setFailedJobs([]);
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

  const onRetryFailedJob = (rowId: string) =>
    act(async () => {
      await retryFailedJob(rowId);
      await load();
    }, 'Задача поставлена в очередь');

  // --- S-67: LMS admin ---
  const loadLmsLists = useCallback(async () => {
    const [courses, maps] = await Promise.all([
      fetchLmsCourses(),
      fetchLmsClassMap(),
    ]);
    setLmsCourses(courses);
    setLmsMaps(maps);
  }, []);

  useEffect(() => {
    if (authed && isAdmin) loadLmsLists().catch(() => undefined);
  }, [authed, isAdmin, loadLmsLists]);

  const onAddCourse = () =>
    act(async () => {
      if (!courseExternalId.trim() || !courseTitle.trim()) {
        throw new Error('external_id и название обязательны');
      }
      await createLmsCourse({
        externalId: courseExternalId.trim(),
        titleRu: courseTitle.trim(),
      });
      setCourseExternalId('');
      setCourseTitle('');
      await loadLmsLists();
    }, 'Курс LMS создан');

  const onDeleteCourse = (courseId: number) =>
    act(async () => {
      await deleteLmsCourse(courseId);
      await loadLmsLists();
    }, 'Курс удалён');

  const onAddClassMap = () =>
    act(async () => {
      const classId = Number(mapClassId);
      const courseId = Number(mapCourseId);
      if (!classId || !courseId || !mapActivityRef.trim()) {
        throw new Error('ID класса, курса и activity_ref обязательны');
      }
      await createLmsClassMap({
        classId,
        courseId,
        activityRef: mapActivityRef.trim(),
      });
      setMapClassId('');
      setMapCourseId('');
      setMapActivityRef('');
      await loadLmsLists();
    }, 'Маппинг создан');

  const onDeleteClassMap = (mapId: number) =>
    act(async () => {
      await deleteLmsClassMap(mapId);
      await loadLmsLists();
    }, 'Маппинг удалён');

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
          <h2>DLQ: упавшие задачи</h2>
          <p className="health-label">
            failed: {summary?.failedJobs ?? failedJobs.length}
          </p>
          <p className="link-hint">
            Повторная постановка в arq; строка остаётся в журнале со статусом
            retried. Retention удаляет старые записи.
          </p>
          <div className="class-table-wrap">
            <table className="class-table">
              <thead>
                <tr>
                  <th>Задача</th>
                  <th>Ошибка</th>
                  <th>Попытки</th>
                  <th>trace_id</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {failedJobs.map((job) => (
                  <tr key={job.id}>
                    <td>{job.task}</td>
                    <td>
                      {job.errorType}: {job.error.slice(0, 160)}
                    </td>
                    <td>{job.attempts}</td>
                    <td>{job.traceId ?? '—'}</td>
                    <td>
                      <button
                        className="retry-button"
                        type="button"
                        disabled={busy || job.status !== 'failed'}
                        onClick={() => onRetryFailedJob(job.id)}
                      >
                        Retry
                      </button>
                    </td>
                  </tr>
                ))}
                {failedJobs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="link-hint">
                      DLQ пуст.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
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

      {isAdmin && lmsStatus && (
        <div className="panel">
          <h2>LMS LRS (S-67)</h2>
          <p className="health-label">
            {lmsStatus.configured
              ? `${lmsStatus.endpoint} · auth: ${lmsStatus.authMode}`
              : 'LRS не настроен'}
            {lmsOauth ? ` · token-url: ${lmsOauth.tokenUrl ?? '—'}` : ''}
          </p>
          <p className="health-label">
            deliveries: sent {lmsStatus.counts.sent ?? 0} · pending{' '}
            {lmsStatus.counts.pending ?? 0} · failed {lmsStatus.counts.failed ?? 0}
          </p>
          <p className="link-hint">
            Курсы LMS и привязку классов ведите здесь: statement skill-объекта
            строится как activity_ref/skills/&lt;slug&gt;.
          </p>
          <div className="rag-toolbar">
            <input
              className="field"
              aria-label="external_id курса LMS"
              placeholder="external_id курса (в LMS)"
              value={courseExternalId}
              onChange={(e) => setCourseExternalId(e.target.value)}
            />
            <input
              className="field"
              aria-label="Название курса"
              placeholder="Название курса"
              value={courseTitle}
              onChange={(e) => setCourseTitle(e.target.value)}
            />
            <button
              className="retry-button"
              type="button"
              disabled={busy}
              onClick={onAddCourse}
            >
              Добавить курс
            </button>
          </div>
          <div className="rag-toolbar">
            <input
              className="field"
              aria-label="ID класса для маппинга"
              placeholder="ID класса"
              inputMode="numeric"
              value={mapClassId}
              onChange={(e) => setMapClassId(e.target.value.replace(/\D/g, ''))}
            />
            <input
              className="field"
              aria-label="ID курса LMS"
              placeholder="ID курса LMS"
              inputMode="numeric"
              value={mapCourseId}
              onChange={(e) => setMapCourseId(e.target.value.replace(/\D/g, ''))}
            />
            <input
              className="field"
              aria-label="activity_ref курса"
              placeholder="https://lms.example/courses/42"
              value={mapActivityRef}
              onChange={(e) => setMapActivityRef(e.target.value)}
            />
            <button
              className="retry-button"
              type="button"
              disabled={busy}
              onClick={onAddClassMap}
            >
              Привязать класс
            </button>
          </div>
          <div className="class-table-wrap">
            <table className="class-table">
              <thead>
                <tr>
                  <th>Курс</th>
                  <th>external_id</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lmsCourses.map((course) => (
                  <tr key={course.id}>
                    <td>{course.titleRu}</td>
                    <td>{course.externalId}</td>
                    <td>
                      <button
                        className="retry-button"
                        type="button"
                        disabled={busy}
                        onClick={() => onDeleteCourse(course.id)}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
                {lmsCourses.length === 0 && (
                  <tr>
                    <td colSpan={3} className="link-hint">
                      Курсов нет.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="class-table-wrap">
            <table className="class-table">
              <thead>
                <tr>
                  <th>Класс</th>
                  <th>Курс</th>
                  <th>activity_ref</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {lmsMaps.map((map) => (
                  <tr key={map.id}>
                    <td>
                      {map.className} (#{map.classId})
                    </td>
                    <td>
                      {map.courseTitle} (#{map.courseId})
                    </td>
                    <td className="link-hint">{map.activityRef}</td>
                    <td>
                      <button
                        className="retry-button"
                        type="button"
                        disabled={busy}
                        onClick={() => onDeleteClassMap(map.id)}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                ))}
                {lmsMaps.length === 0 && (
                  <tr>
                    <td colSpan={4} className="link-hint">
                      Маппингов нет.
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
