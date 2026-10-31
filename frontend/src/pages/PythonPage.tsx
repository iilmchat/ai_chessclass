import { useCallback, useEffect, useState } from 'react';
import type { AssignmentDetailDto, AssignmentDto, SubmissionDto } from '../shared/api';
import {
  ApiError,
  fetchAssignmentDetail,
  fetchAssignments,
  getToken,
  logout,
  submitSolution,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

const VERDICT_LABELS: Record<SubmissionDto['verdict'], string> = {
  passed: 'Пройдено',
  failed: 'Провалено',
  timeout: 'Превышен лимит времени',
  restricted: 'Запрещённый код',
  error: 'Ошибка выполнения',
};

/** S-08: экран задания — условие + редактор + тесты → вердикт. */
export function PythonPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [assignments, setAssignments] = useState<AssignmentDto[]>([]);
  const [selected, setSelected] = useState<AssignmentDetailDto | null>(null);
  const [code, setCode] = useState('');
  const [result, setResult] = useState<SubmissionDto | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const loadList = useCallback(() => {
    fetchAssignments()
      .then((page) => setAssignments(page.items))
      .catch(() => setAssignments([]));
  }, []);

  useEffect(() => {
    if (authed) {
      loadList();
    }
  }, [authed, loadList]);

  const open = useCallback(async (id: string) => {
    setError('');
    setResult(null);
    try {
      const detail = await fetchAssignmentDetail(id);
      setSelected(detail);
      setCode(detail.starterCode);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки');
    }
  }, []);

  const submit = useCallback(async () => {
    if (!selected) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      setResult(await submitSolution(selected.id, code));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка сдачи');
    } finally {
      setBusy(false);
    }
  }, [selected, code]);

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Python-курс (python_teacher)</h1>
        <p className="page-subtitle">Задания доступны после входа</p>
        <LoginGate onReady={() => setAuthed(true)} />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Python-курс (python_teacher)</h1>
      <p className="page-subtitle">
        Задания и сдача — S-08; проверка в песочнице (assert-тесты)
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
            setSelected(null);
          }}
        >
          Выйти
        </button>
      </p>

      <div className="panel">
        <h2>Задания ({assignments.length})</h2>
        <ul className="assignment-list">
          {assignments.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                className={`assignment-item ${selected?.id === a.id ? 'active' : ''}`}
                onClick={() => open(a.id)}
              >
                <span>{a.title}</span>
                <span className="level-tag">{a.level}</span>
              </button>
            </li>
          ))}
          {assignments.length === 0 && (
            <li className="link-hint">Заданий нет — прогони seed (docker compose run --rm seed)</li>
          )}
        </ul>
      </div>

      {selected && (
        <div className="panel">
          <h2>{selected.title}</h2>
          <p className="statement">{selected.statement}</p>
          <textarea
            className="editor"
            spellCheck={false}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            rows={12}
          />
          <div className="submit-row">
            <button className="retry-button" type="button" disabled={busy} onClick={submit}>
              {busy ? 'Проверяем…' : 'Проверить'}
            </button>
            <span className="link-hint">Тестов: {selected.testsCount}</span>
          </div>
          {error && <p className="verdict verdict-error">{error}</p>}
          {result && (
            <div className={`verdict verdict-${result.verdict}`}>
              <strong>{VERDICT_LABELS[result.verdict]}</strong> — тесты{' '}
              {result.passedTests}/{result.totalTests}
              {result.failedTest !== null && <>; провален №{result.failedTest}</>}
              {result.durationMs !== null && <>; {result.durationMs} мс</>}
              {result.stdoutDigest && (
                <pre className="stdout">{result.stdoutDigest}</pre>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
