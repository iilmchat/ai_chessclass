import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import { Chess } from 'chess.js';
import type { Move, Square } from 'chess.js';
import { Chessboard } from 'react-chessboard';
import type {
  PieceDropHandlerArgs,
  PieceHandlerArgs,
  SquareHandlerArgs,
} from 'react-chessboard';
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
import { applyBoardA11y } from '../shared/chessA11y';
import { LoginGate } from '../shared/LoginGate';
import { VoicePlayer } from '../shared/VoicePlayer';
import type { EventStreamEvent } from '../shared/useEventStream';
import { useEventStream } from '../shared/useEventStream';
import { usePrefersDark } from '../shared/usePrefersDark';

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
  const [blunderKnowledge, setBlunderKnowledge] = useState<
    Record<number, string[]>
  >({});
  const [explaining, setExplaining] = useState<number | null>(null);
  const [analysisBusy, setAnalysisBusy] = useState(false);
  const [analysisError, setAnalysisError] = useState('');
  const finishedGameRef = useRef<string | null>(null);

  // S-34: локальная партия для drag-and-drop, undo/redo и подсветки.
  const gameRef = useRef<Chess | null>(null);
  if (gameRef.current === null) {
    gameRef.current = new Chess(START_FEN);
  }
  const redoRef = useRef<Move[]>([]);
  const [selectedSquare, setSelectedSquare] = useState<Square | null>(null);
  const [legalMoves, setLegalMoves] = useState<string[]>([]);
  const [lastMove, setLastMove] = useState<{ from: string; to: string } | null>(
    null,
  );
  const [moveInput, setMoveInput] = useState('');
  const [boardError, setBoardError] = useState('');
  const boardRef = useRef<HTMLDivElement | null>(null);
  const [history, setHistory] = useState<string[]>([]);
  const [canRedo, setCanRedo] = useState(false);
  const [orientation, setOrientation] = useState<'white' | 'black'>('white');
  const prefersDark = usePrefersDark();

  useEffect(() => {
    applyBoardA11y(boardRef.current, boardFen);
  }, [boardFen, orientation]);

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

  const syncBoard = useCallback(
    (game: Chess, move?: { from: string; to: string }) => {
      setBoardFen(game.fen());
      setFen(game.fen());
      setHistory(game.history());
      setSelectedSquare(null);
      setLegalMoves([]);
      setLastMove(move ?? null);
      setBoardError('');
    },
    [],
  );

  const applyFen = useCallback((value: string): boolean => {
    try {
      const next = new Chess(value.trim());
      gameRef.current = next;
      redoRef.current = [];
      setCanRedo(false);
      setBoardFen(next.fen());
      setFen(next.fen());
      setHistory([]);
      setSelectedSquare(null);
      setLegalMoves([]);
      setLastMove(null);
      setBoardError('');
      return true;
    } catch {
      setBoardError('Некорректный FEN');
      return false;
    }
  }, []);

  const applyMove = useCallback(
    (from: string, to: string): boolean => {
      const game = gameRef.current;
      if (!game) {
        return false;
      }
      try {
        const piece = game.get(from as Square);
        const promotion =
          piece?.type === 'p' && (to[1] === '8' || to[1] === '1')
            ? 'q'
            : undefined;
        const move = game.move({
          from,
          to,
          ...(promotion ? { promotion } : {}),
        });
        redoRef.current = [];
        setCanRedo(false);
        syncBoard(game, { from: move.from, to: move.to });
        setMoveInput('');
        return true;
      } catch {
        setBoardError('Недопустимый ход');
        return false;
      }
    },
    [syncBoard],
  );

  const undoMove = useCallback(() => {
    const game = gameRef.current;
    if (!game) {
      return;
    }
    const move = game.undo();
    if (!move) {
      return;
    }
    redoRef.current.push(move);
    setCanRedo(true);
    syncBoard(game);
  }, [syncBoard]);

  const redoMove = useCallback(() => {
    const game = gameRef.current;
    if (!game) {
      return;
    }
    const move = redoRef.current.pop();
    if (!move) {
      return;
    }
    try {
      const result = game.move(move.san);
      setCanRedo(redoRef.current.length > 0);
      syncBoard(game, { from: result.from, to: result.to });
    } catch {
      setBoardError('Не удалось повторить ход');
    }
  }, [syncBoard]);

  const resetBoard = useCallback(() => {
    applyFen(START_FEN);
    setMoveInput('');
  }, [applyFen]);

  const submitMove = useCallback(() => {
    const text = moveInput.trim();
    const game = gameRef.current;
    if (!text || !game) {
      return;
    }
    try {
      const uci = text.match(/^([a-h][1-8])([a-h][1-8])([qrbn])?$/i);
      let move: Move;
      if (uci) {
        const from = uci[1].toLowerCase();
        const to = uci[2].toLowerCase();
        const piece = game.get(from as Square);
        const promotion =
          piece?.type === 'p' && (to[1] === '8' || to[1] === '1')
            ? (uci[3]?.toLowerCase() ?? 'q')
            : undefined;
        move = game.move({
          from,
          to,
          ...(promotion ? { promotion } : {}),
        });
      } else {
        move = game.move(text);
      }
      redoRef.current = [];
      setCanRedo(false);
      syncBoard(game, { from: move.from, to: move.to });
      setMoveInput('');
    } catch {
      setBoardError('Ход не распознан: нужен SAN (e4) или UCI (e2e4)');
    }
  }, [moveInput, syncBoard]);

  const handleSquareClick = useCallback(
    ({ piece, square }: SquareHandlerArgs) => {
      const game = gameRef.current;
      if (!game) {
        return;
      }
      if (selectedSquare) {
        if (selectedSquare === square) {
          setSelectedSquare(null);
          setLegalMoves([]);
          return;
        }
        if (applyMove(selectedSquare, square)) {
          return;
        }
        if (piece && piece.pieceType.startsWith(game.turn())) {
          const moves = game.moves({
            square: square as Square,
            verbose: true,
          });
          setSelectedSquare(square as Square);
          setLegalMoves(moves.map((move) => move.to));
          setBoardError('');
          return;
        }
        setSelectedSquare(null);
        setLegalMoves([]);
        return;
      }
      if (piece && piece.pieceType.startsWith(game.turn())) {
        const moves = game.moves({ square: square as Square, verbose: true });
        setSelectedSquare(square as Square);
        setLegalMoves(moves.map((move) => move.to));
        setBoardError('');
      }
    },
    [applyMove, selectedSquare],
  );

  const handlePieceDrop = useCallback(
    ({ sourceSquare, targetSquare }: PieceDropHandlerArgs) => {
      if (!targetSquare) {
        return false;
      }
      return applyMove(sourceSquare, targetSquare);
    },
    [applyMove],
  );

  const canDragPiece = useCallback(({ piece }: PieceHandlerArgs) => {
    const game = gameRef.current;
    return Boolean(
      game && !game.isGameOver() && piece.pieceType.startsWith(game.turn()),
    );
  }, []);

  const squareStyles = useMemo(() => {
    const styles: Record<string, CSSProperties> = {};
    if (selectedSquare) {
      styles[selectedSquare] = { backgroundColor: 'rgba(99, 184, 146, 0.35)' };
    }
    for (const target of legalMoves) {
      const occupied = gameRef.current?.get(target as Square);
      styles[target] = occupied
        ? { boxShadow: 'inset 0 0 0 3px rgba(99, 184, 146, 0.7)' }
        : {
            background:
              'radial-gradient(circle, rgba(99, 184, 146, 0.55) 0 18%, transparent 19%)',
          };
    }
    if (lastMove) {
      for (const square of [lastMove.from, lastMove.to]) {
        styles[square] = {
          ...(styles[square] ?? {}),
          backgroundColor: 'rgba(255, 193, 7, 0.25)',
        };
      }
    }
    const game = gameRef.current;
    if (game?.isCheck()) {
      const king = game.findPiece({ type: 'k', color: game.turn() })[0];
      if (king) {
        styles[king] = {
          ...(styles[king] ?? {}),
          backgroundColor: 'rgba(220, 53, 69, 0.35)',
        };
      }
    }
    return styles;
  }, [selectedSquare, legalMoves, lastMove, boardFen]);

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
    const currentFen = fen.trim();
    if (!applyFen(currentFen)) {
      return;
    }
    setBusy(true);
    setError('');
    try {
      const data = await insightPosition(currentFen, level || undefined);
      setInsight(data);
      loadPositions();
    } catch (err) {
      setInsight(null);
      setError(err instanceof ApiError ? err.message : 'Ошибка запроса');
    } finally {
      setBusy(false);
    }
  }, [applyFen, fen, level, loadPositions]);

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
    setBlunderKnowledge({});
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
        setBlunderKnowledge((prev) => ({
          ...prev,
          [ply]: result.knowledge ?? [],
        }));
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
          <div className="board-wrap" ref={boardRef}>
            <Chessboard
              options={{
                position: boardFen,
                boardOrientation: orientation,
                boardStyle: { borderRadius: '10px', overflow: 'hidden' },
                darkSquareStyle: {
                  backgroundColor: prefersDark ? '#2f3542' : '#b8c2cf',
                },
                lightSquareStyle: {
                  backgroundColor: prefersDark ? '#465064' : '#eef2f7',
                },
                squareStyles,
                dropSquareStyle: {
                  boxShadow: 'inset 0 0 0 3px rgba(99, 184, 146, 0.8)',
                },
                canDragPiece,
                onPieceDrop: handlePieceDrop,
                onSquareClick: handleSquareClick,
                showNotation: true,
                animationDurationInMs: 150,
              }}
            />
          </div>

          <div className="board-controls">
            <input
              className="field fen-input"
              value={fen}
              onChange={(event) => setFen(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  applyFen(fen);
                }
              }}
              placeholder="FEN"
              aria-label="FEN позиции"
            />
            <button
              className="retry-button"
              type="button"
              onClick={() => applyFen(fen)}
            >
              Применить FEN
            </button>
          </div>

          <div className="board-controls">
            <input
              className="field"
              value={moveInput}
              onChange={(event) => setMoveInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  submitMove();
                }
              }}
              placeholder="Ход: e4 или e2e4"
              aria-label="Ход в SAN или UCI"
            />
            <button
              className="retry-button"
              type="button"
              onClick={submitMove}
            >
              Сделать ход
            </button>
          </div>

          <div className="board-controls">
            <button
              className="retry-button"
              type="button"
              onClick={undoMove}
              disabled={history.length === 0}
            >
              ← Отменить
            </button>
            <button
              className="retry-button"
              type="button"
              onClick={redoMove}
              disabled={!canRedo}
            >
              Повторить →
            </button>
            <button className="retry-button" type="button" onClick={resetBoard}>
              Сброс
            </button>
            <button
              className="retry-button"
              type="button"
              onClick={() =>
                setOrientation((current) =>
                  current === 'white' ? 'black' : 'white',
                )
              }
            >
              Перевернуть
            </button>
          </div>

          {boardError && <p className="verdict failed-note">{boardError}</p>}
          {history.length > 0 && (
            <p className="link-hint">
              Ходы: {history.slice(-12).join(' ')}
            </p>
          )}
          <p className="link-hint">
            Перетащите фигуру или выберите её кликом; превращение — ферзь.
          </p>
        </div>

        <div className="chess-panel">
          <h2>Инсайт</h2>
          <select
            className="field"
            aria-label="Уровень объяснения"
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
              <VoicePlayer text={insight.explanation} />
              {(insight.knowledge?.length ?? 0) > 0 && (
                <>
                  <h3>Полезные знания</h3>
                  <ul className="facts-list">
                    {insight.knowledge.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </>
              )}
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
                      onClick={() => applyFen(p.fen)}
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
                    {explanation && <VoicePlayer text={explanation} />}
                    {(blunderKnowledge[blunder.ply]?.length ?? 0) > 0 && (
                      <ul className="facts-list">
                        {blunderKnowledge[blunder.ply].map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
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
