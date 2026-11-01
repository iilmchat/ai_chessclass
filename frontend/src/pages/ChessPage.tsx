import { useCallback, useEffect, useRef, useState } from 'react';
import { Chessboard } from 'react-chessboard';
import type { BlunderDto, GameStatusOut, InsightOut } from '../shared/api';
import {
  API_BASE,
  ApiError,
  explainBlunder,
  fetchBlunders,
  fetchGameStatus,
  fetchPositions,
  getToken,
  insightPosition,
  logout,
  uploadGame,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';
import type { EventStreamEvent } from '../shared/useEventStream';
import { useEventStream } from '../shared/useEventStream';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const LEVELS = [
  { value: '', label: 'Уровень профиля' },
  { value: 'novice', label: 'Novice (новичок)' },
  { value: 'intermediate', label: 'Intermediate' },
  { value: 'advanced', label: 'Advanced (продвинутый)' },
];

const ANALYSIS_LABELS: Record<string, string> = {
  pending: 'в очереди',
  running: 'идёт',
  done: 'готово',
  failed: 'ошибка',
};

/** S-11/S-33: шахматная лаборатория — инсайт позиции и PGN-анализ с SSE. */
export function ChessPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [fen, setFen] = useState(START_FEN);
  const [boardFen, setBoardFen] = useState(START_FEN);
  const [level, setLevel] = useState('');
  const [insight, setInsight] = useState<InsightOut | null>(null);
  const [positions, setPositions] = useState<{ id: string; fen: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [pgn, setPgn] = useState('');
  const [gameId, setGameId] = useState<string | null>(null);
  const [gameStatus, setGameStatus] = useState<GameStatusOut | null>(null);
  const [progress, setProgress] = useState<{ ply: number; total: number } | null>(
    null,
  );
  const [blunders, setBlunders] = useState<BlunderDto[]>([]);
  const [explanations, setExplanations] = useState<Record<number, string>>({});
  const [explaining, setExplaining] = useState<number | null>(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const finishedGameRef = useRef<string | null>(null);

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

  const finishGame = useCallback(async (id: string) => {
    if (finishedGameRef.current === id) {
      return;
    }
    finishedGameRef.current = id;
    try {
      const status = await fetchGameStatus(id);
      setGameStatus(status);
      if (status.status === 'done') {
        const data = await fetchBlunders(id);
        setBlunders(data.blunders);
        const initial: Record<number, string> = {};
        for (const blunder of data.blunders) {
          if (blunder.explanation) {
            initial[blunder.ply] = blunder.explanation;
          }
        }
        setExplanations(initial);
      } else if (status.status === 'failed') {
        setAnalysisError('Анализ завершился ошибкой');
      }
    } catch (err) {
      finishedGameRef.current = null;
      setAnalysisError(
        err instanceof ApiError ? err.message : 'Ошибка получения результата',
      );
    }
  }, []);

  const handleStreamEvent = useCallback(
    (event: EventStreamEvent) => {
      try {
        const data = JSON.parse(event.data) as {
          status?: string;
          ply?: number;
          total?: number;
        };
        if (event.event === 'status' && data.status) {
          setGameStatus((prev) =>
            prev ? { ...prev, status: data.status! } : prev,
          );
          if (data.status === 'done' && gameId) {
            void finishGame(gameId);
          }
          if (data.status === 'failed') {
            setAnalysisError('Анализ завершился ошибкой');
          }
        }
        if (event.event === 'progress') {
          if (data.status === 'running') {
            setProgress({
              ply: typeof data.ply === 'number' ? data.ply : 0,
              total: typeof data.total === 'number' ? data.total : 0,
            });
          } else if (data.status === 'done') {
            setProgress(null);
            if (gameId) {
              void finishGame(gameId);
            }
          } else if (data.status === 'failed') {
            setProgress(null);
            setAnalysisError('Анализ завершился ошибкой');
          }
        }
      } catch {
        // Некорректный SSE-payload игнорируем; polling остаётся страховкой.
      }
    },
    [finishGame, gameId],
  );

  const stream = useEventStream({
    url: gameId ? `${API_BASE}/chess/games/${gameId}/events` : null,
    enabled:
      Boolean(gameId) &&
      gameStatus?.status !== 'done' &&
      gameStatus?.status !== 'failed',
    onEvent: handleStreamEvent,
  });

  // Fallback: SSE мог не подключиться/оборваться; polling добирает статус.
  useEffect(() => {
    if (!gameId) {
      return;
    }
    if (gameStatus?.status === 'done' || gameStatus?.status === 'failed') {
      return;
    }
    const timer = window.setInterval(() => {
      fetchGameStatus(gameId)
        .then((status) => {
          setGameStatus(status);
          if (status.status === 'done') {
            void finishGame(gameId);
          }
          if (status.status === 'failed') {
            setAnalysisError('Анализ завершился ошибкой');
          }
        })
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [finishGame, gameId, gameStatus?.status]);

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
      setError(err instanceof ApiError ? err.message : 'Ошибка запроса');
    } finally {
      setBusy(false);
    }
  }, [fen, level, loadPositions]);

  const analyzePgn = useCallback(async () => {
    const text = pgn.trim();
    if (!text) {
      setAnalysisError('Вставьте PGN');
      return;
    }
    setAnalysisBusy(true);
    setAnalysisError('');
    setBlunders([]);
    setExplanations({});
    setProgress(null);
    setGameId(null);
    setGameStatus(null);
    finishedGameRef.current = null;
    try {
      const uploaded = await uploadGame(text);
      setGameId(uploaded.gameId);
      setGameStatus({
        gameId: uploaded.gameId,
        status: uploaded.status,
        blunderCount: 0,
        summary: {},
      });
    } catch (err) {
      setAnalysisError(
        err instanceof ApiError ? err.message : 'Ошибка загрузки PGN',
      );
    } finally {
      setAnalysisBusy(false);
    }
  }, [pgn]);

  const explain = useCallback(
    async (ply: number) => {
      if (!gameId) {
        return;
      }
      setExplaining(ply);
      setAnalysisError('');
      try {
        const result = await explainBlunder(gameId, ply);
        setExplanations((prev) => ({ ...prev, [ply]: result.explanation }));
      } catch (err) {
        setAnalysisError(
          err instanceof ApiError ? err.message : 'Ошибка объяснения',
        );
      } finally {
        setExplaining(null);
      }
    },
    [gameId],
  );

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Шахматная лаборатория (chess_lab)</h1>
        <p className="page-subtitle">Лаборатория доступна после входа</p>
        <LoginGate
          hint="Demo: student1@chessclass.dev / dev-student-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  const streamLabel =
    stream.status === 'open'
      ? 'live'
      : stream.status === 'connecting'
        ? 'подключение'
        : stream.status === 'reconnecting'
          ? 'переподключение'
          : stream.status === 'error'
            ? 'polling'
            : stream.status === 'closed'
              ? 'завершён'
              : '—';
  const progressPercent =
    progress && progress.total > 0
      ? Math.round((progress.ply / progress.total) * 100)
      : null;

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
            setGameId(null);
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
            <button
              className="retry-button"
              type="button"
              disabled={busy}
              onClick={ask}
            >
              {busy ? 'Запрашиваем…' : 'Получить инсайт'}
            </button>
          </div>
          {error && <p className="verdict failed-note">{error}</p>}

          {insight && (
            <>
              <h3>Факты Stockfish (не выдуманы)</h3>
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

      <div className="panel">
        <h2>Анализ PGN</h2>
        <textarea
          className="editor"
          spellCheck={false}
          rows={6}
          value={pgn}
          onChange={(event) => setPgn(event.target.value)}
          placeholder={'[Event "..."] 1. e4 e5 2. Nf3 ...'}
        />
        <div className="submit-row">
          <button
            className="retry-button"
            type="button"
            disabled={analysisBusy}
            onClick={analyzePgn}
          >
            {analysisBusy ? 'Загружаем…' : 'Загрузить и разобрать'}
          </button>
          {gameId && (
            <span className="link-hint">
              Игра #{gameId} ·{' '}
              {ANALYSIS_LABELS[gameStatus?.status ?? ''] ?? gameStatus?.status} ·
              поток: {streamLabel}
            </span>
          )}
        </div>

        {progress && (
          <p className="link-hint">
            Прогресс: {progress.ply}/{progress.total}
            {progressPercent !== null && ` (${progressPercent}%)`}
          </p>
        )}
        {analysisError && <p className="verdict failed-note">{analysisError}</p>}

        {gameStatus?.status === 'done' && blunders.length === 0 && (
          <p className="link-hint">Блюндеров не найдено.</p>
        )}

        {blunders.length > 0 && (
          <>
            <h3>Блюндеры ({blunders.length})</h3>
            <ul className="facts-list">
              {blunders.map((blunder) => {
                const explanation =
                  explanations[blunder.ply] ?? blunder.explanation;
                return (
                  <li key={blunder.ply}>
                    <strong>ход {blunder.ply}</strong>: {blunder.playedSan} → лучше{' '}
                    {blunder.bestSan} (Δ {blunder.deltaCp} cp){' '}
                    <button
                      className="link-button"
                      type="button"
                      disabled={explaining === blunder.ply}
                      onClick={() => explain(blunder.ply)}
                    >
                      {explaining === blunder.ply
                        ? 'Объясняем…'
                        : explanation
                          ? 'Обновить объяснение'
                          : 'Объяснить'}
                    </button>
                    {explanation && (
                      <p className="statement">{explanation}</p>
                    )}
                  </li>
                );
              })}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
