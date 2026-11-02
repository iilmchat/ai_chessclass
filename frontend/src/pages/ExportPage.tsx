import { useCallback, useState } from 'react';
import { ApiError, downloadFile, getToken, logout } from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

/** S-45: экспорт навыков/результатов для LMS (CSV, xAPI). */
export function ExportPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const download = useCallback(
    async (path: string, filename: string) => {
      setBusy(path);
      setError('');
      setNotice('');
      try {
        await downloadFile(path, filename);
        setNotice(`Файл ${filename} скачан`);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Ошибка экспорта');
      } finally {
        setBusy('');
      }
    },
    [],
  );

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Экспорт для LMS</h1>
        <p className="page-subtitle">CSV навыков и xAPI-совместимый payload</p>
        <LoginGate
          hint="Demo: teacher@chessclass.dev / dev-teacher-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Экспорт для LMS</h1>
      <p className="page-subtitle">
        Результаты и навыки учеников (S-45)
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
      {error && <p className="verdict failed-note">{error}</p>}
      {notice && <p className="link-hint">{notice}</p>}
      <div className="panel">
        <h2>Форматы</h2>
        <p className="class-meta">
          CSV — строки «ученик × навык» с EMA, стриками и Elo. xAPI —
          statements (actor/verb/object/result) для LMS.
        </p>
        <div className="class-actions">
          <button
            className="retry-button"
            type="button"
            disabled={busy !== ''}
            onClick={() => download('/admin/export/skills.csv', 'skills.csv')}
          >
            Скачать skills.csv
          </button>
          <button
            className="retry-button"
            type="button"
            disabled={busy !== ''}
            onClick={() => download('/admin/export/xapi', 'xapi.json')}
          >
            Скачать xapi.json
          </button>
        </div>
      </div>
    </section>
  );
}
