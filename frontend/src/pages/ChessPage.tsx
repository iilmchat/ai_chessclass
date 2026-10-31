import { useCallback, useEffect, useState } from 'react';
import { Chessboard } from 'react-chessboard';
import type { InsightOut } from '../shared/api';
import {
  ApiError,
  fetchPositions,
  getToken,
  insightPosition,
  logout,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const LEVELS = [
  { value: '', label: 'Уровень профиля' },
  { value: 'novice', label: 'Novice (просто)' },
  { value: 'intermediate', label: 'Intermediate' },
  { value: 'advanced', label: 'Advanced (глубоко)' },
];

/** S-11: инсайт позиции — доска + факты SF + объяснение по уровню. */
export function ChessPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [fen, setFen] = useState(START_FEN);
  const [boardFen, setBoardFen] = useState(START_FEN);
  const [level, setLevel] = useState('');
  const [insight, setInsight] = useState<InsightOut | null>(null);
  const [positions, setPositions] = useState<{ id: string; fen: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const loadPositions = useCallback(() => {
    fetchPositions()
      .then((page) => setPositions(page.items))
      .catch(() => setPositions([]));
  }, []);

  useEffect(() => {
    if (authed) {
      loadPositions();
    }
  }, [authed, loadPositions]);

  const ask = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      setBoardFen(fen.trim());
      const data = await insightPosition(fen.trim(), level || undefined);
      setInsight(data);
      loadPositions();
    } catch (err) {
      setInsight(null);
      setError(err instanceof ApiError ? err.message : 'Ошибка анализа');
    } finally {
      setBusy(false);
    }
  }, [fen, level, loadPositions]);

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Шахматная лаборатория (chess_lab)</h1>
        <p className="page-subtitle">Инсайт позиции доступен после входа</p>
        <LoginGate hint="Demo: student1@chessclass.dev / dev-student-2026" onReady={() => setAuthed(true)} />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Шахматная лаборатория (chess_lab)</h1>
      <p className="page-subtitle">
        Инсайт позиции — факты Stockfish + объяснение по уровню (S-11)
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
            setInsight(null);
          }}
        >
          Выйти
        </button>
      </p>

      <div className="panel chess-grid">
        <div>
          <div className="board-wrap">
            <Chessboard options={{ position: boardFen }} />
          </div>
          <input
            className="field fen-input"
            value={fen}
            onChange={(e) => setFen(e.target.value)}
            placeholder="FEN"
          />
        </div>

        <div className="chess-panel">
          <h2>Инсайт</h2>
          <select
            className="field"
            value={level}
            onChange={(e) => setLevel(e.target.value)}
          >
            {LEVELS.map((l) => (
              <option key={l.value} value={l.value}>
                {l.label}
              </option>
            ))}
          </select>
          <div className="submit-row">
            <button className="retry-button" type="button" disabled={busy} onClick={ask}>
              {busy ? 'Анализируем…' : 'Получить инсайт'}
            </button>
          </div>
          {error && <p className="verdict failed-note">{error}</p>}

          {insight && (
            <>
              <h3>Факты Stockfish (не меняются)</h3>
              <ul className="facts-list">
                {insight.factsText.map((f) => (
                  <li key={f}>{f}</li>
                ))}
              </ul>
              <h3>
                Объяснение <span className="level-tag">{insight.level}</span>{' '}
                <span className="level-tag">{insight.modelUsed}</span>
              </h3>
              <p className="statement">{insight.explanation}</p>
            </>
          )}

          {positions.length > 0 && (
            <>
              <h3>Последние позиции</h3>
              <ul className="facts-list">
                {positions.slice(0, 6).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => {
                        setFen(p.fen);
                        setBoardFen(p.fen);
                      }}
                    >
                      {p.fen.length > 42 ? `${p.fen.slice(0, 42)}…` : p.fen}
                    </button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
