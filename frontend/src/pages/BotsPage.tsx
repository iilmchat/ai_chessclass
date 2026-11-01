import { useCallback, useEffect, useState } from 'react';
import {
  API_BASE,
  ApiError,
  apiFetch,
  getToken,
  logout,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';
import { LazyCodeEditor } from '../shared/LazyCodeEditor';
import { draftKey, readDraft, writeDraft } from '../shared/draft';
import { useEventStream } from '../shared/useEventStream';

interface BotDto {
  id: string;
  versionNo: number;
  entry: string;
  isActive: boolean;
  createdAt: string;
}

interface MatchDto {
  id: string;
  opponent: string;
  result: string;
  movesCount: number;
  durationMs: number;
  eloDelta: number;
}

interface MatchRunOut {
  matchId: number;
  status: string;
}

interface ActiveMatch {
  botId: string;
  matchId: number;
  ply: number;
}

interface ReplayDto {
  match: MatchDto;
  moves: { ply: number; uci: string; agent: string; thinkMs: number }[];
}

interface LeaderRow {
  userId: string;
  email: string;
  elo: number;
  wins: number;
  losses: number;
  draws: number;
}

const DEFAULT_BOT_CODE = `import random

def choose_move(position):
    return random.choice(position.legal_moves)
`;

/** S-20: арена ботов — редактор, тест-прогон, матч, лидерборд. */
export function BotsPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [bots, setBots] = useState<BotDto[]>([]);
  const [stats, setStats] = useState<{ elo: number; wins: number; losses: number; draws: number } | null>(null);
  const [code, setCode] = useState(() => readDraft(draftKey('bots')) ?? DEFAULT_BOT_CODE);
  const [testInfo, setTestInfo] = useState('');
  const [matches, setMatches] = useState<MatchDto[]>([]);
  const [activeMatch, setActiveMatch] = useState<ActiveMatch | null>(null);
  const [replay, setReplay] = useState<ReplayDto | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderRow[]>([]);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const loadAll = useCallback(() => {
    apiFetch<BotDto[]>('/bots').then(setBots).catch(() => setBots([]));
    apiFetch<{ elo: number; wins: number; losses: number; draws: number }>('/bots/stats').then(setStats).catch(() => setStats(null));
    apiFetch<LeaderRow[]>('/bots/leaderboard').then(setLeaderboard).catch(() => setLeaderboard([]));
  }, []);

  const finishMatch = useCallback(
    (botId: string, result?: string, eloDelta?: number) => {
      setActiveMatch(null);
      if (result) {
        const delta = eloDelta !== undefined ? ` (Δelo ${eloDelta})` : '';
        setTestInfo(`Матч завершён: ${result}${delta}`);
      }
      loadAll();
      if (botId) {
        apiFetch<MatchDto[]>(`/bots/${botId}/matches`)
          .then(setMatches)
          .catch(() => undefined);
      }
    },
    [loadAll],
  );

  useEffect(() => {
    if (authed) loadAll();
  }, [authed, loadAll]);

  useEffect(() => {
    writeDraft(draftKey('bots'), code);
  }, [code]);

  const matchStream = useEventStream({
    url: activeMatch
      ? `${API_BASE}/bots/${activeMatch.botId}/matches/${activeMatch.matchId}/events`
      : null,
    enabled: activeMatch !== null,
    onEvent: (event) => {
      if (event.event !== 'progress') {
        return;
      }
      try {
        const data = JSON.parse(event.data) as {
          status?: string;
          ply?: number;
          result?: string;
          eloDelta?: number;
        };
        if (data.status === 'running') {
          setActiveMatch((prev) =>
            prev && typeof data.ply === 'number'
              ? { ...prev, ply: data.ply }
              : prev,
          );
        } else if (data.status === 'done') {
          finishMatch(activeMatch?.botId ?? '', data.result, data.eloDelta);
        } else if (data.status === 'failed') {
          setActiveMatch(null);
          setTestInfo('Матч завершился ошибкой');
          loadAll();
        }
      } catch {
        // Некорректный JSON не должен ломать UI; polling остаётся страховкой.
      }
    },
  });

  useEffect(() => {
    if (!activeMatch) {
      return;
    }
    const timer = window.setInterval(() => {
      apiFetch<MatchDto[]>(`/bots/${activeMatch.botId}/matches`)
        .then((list) => {
          setMatches(list);
          const finished = list.find(
            (match) => match.id === String(activeMatch.matchId),
          );
          if (finished) {
            finishMatch(activeMatch.botId, finished.result, finished.eloDelta);
          }
        })
        .catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [activeMatch, finishMatch]);

  const streamLabel =
    matchStream.status === 'open'
      ? 'live'
      : matchStream.status === 'connecting'
        ? 'подключение'
        : matchStream.status === 'reconnecting'
          ? 'переподключение'
          : matchStream.status === 'error'
            ? 'polling'
            : matchStream.status === 'closed'
              ? 'завершён'
              : '—';

  const act = useCallback(
    async (fn: () => Promise<void>) => {
      setBusy('…');
      setError('');
      try {
        await fn();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Ошибка');
      } finally {
        setBusy('');
      }
    },
    []
  );

  const create = () =>
    act(async () => {
      await apiFetch('/bots', { method: 'POST', body: JSON.stringify({ code }) });
      setCode(DEFAULT_BOT_CODE);
      loadAll();
    });

  const test = (botId: string) =>
    act(async () => {
      setTestInfo('Ходим в стартовой позиции…');
      const result = await apiFetch<Record<string, unknown>>(
        `/bots/${botId}/test`,
        { method: 'POST', body: JSON.stringify({ fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' }) }
      );
      setTestInfo(
        result['ok'] ? `Ход: ${result['moveUci']} (${result['timeMs']} мс)` : `Ошибка: ${result['error']}`
      );
    });

  const runMatch = (botId: string, opponent = 'random') =>
    act(async () => {
      setTestInfo('Матч поставлен в очередь…');
      const started = await apiFetch<MatchRunOut>(
        `/bots/${botId}/match/run`,
        {
          method: 'POST',
          body: JSON.stringify({ opponent }),
        },
      );
      if (started.matchId > 0) {
        setActiveMatch({ botId, matchId: started.matchId, ply: 0 });
        setTestInfo(`Матч #${started.matchId} идёт…`);
        return;
      }
      // Совместимость со старым API (matchId=-1): polling через 20 с.
      window.setTimeout(() => {
        apiFetch<MatchDto[]>(`/bots/${botId}/matches`)
          .then(setMatches)
          .catch(() => undefined);
        loadAll();
      }, 20000);
    });

  const showReplay = (botId: string, matchId: string) =>
    act(async () => {
      const data = await apiFetch<ReplayDto>(`/bots/${botId}/matches/${matchId}/replay`);
      setReplay(data);
    });

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Конструктор ботов (bot_lab)</h1>
        <p className="page-subtitle">Арена доступна после входа</p>
        <LoginGate hint="Demo: student1@chessclass.dev / dev-student-2026" onReady={() => setAuthed(true)} />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Конструктор ботов (bot_lab)</h1>
      <p className="page-subtitle">
        Контракт choose_move(position) → UCI; лестница random/greedy/minimax2/SF (S-17…S-19)
        <button className="retry-button logout" type="button" onClick={() => { logout(); setAuthed(false); }}>
          Выйти
        </button>
      </p>
      {error && <p className="verdict failed-note">{error}</p>}

      {activeMatch && (
        <p className="link-hint">
          Матч #{activeMatch.matchId}: ход {activeMatch.ply} · поток: {streamLabel}
        </p>
      )}

      {stats && (
        <div className="panel">
          <h2>Мой рейтинг</h2>
          <p>
            Elo <strong>{stats.elo}</strong> · победы {stats.wins} · поражения{' '}
            {stats.losses} · ничьи {stats.draws}
          </p>
        </div>
      )}

      <div className="panel">
        <h2>Код бота (версия {bots[0]?.versionNo !== undefined ? `след. №${bots[0].versionNo + 1}` : '№1'})</h2>
        <LazyCodeEditor
          value={code}
          onChange={setCode}
          minHeight={220}
          ariaLabel="Код бота на Python"
        />
        <div className="submit-row">
          <button className="retry-button" type="button" disabled={busy !== ''} onClick={create}>
            Сохранить версию
          </button>
          <span className="link-hint">версий: {bots.length}</span>
        </div>
        {testInfo && <p className="link-hint">{testInfo}</p>}
      </div>

      <div className="panel">
        <h2>Мои боты</h2>
        <ul className="facts-list">
          {bots.map((b) => (
            <li key={b.id}>
              версия №{b.versionNo} · entry {b.entry}
              <button className="retry-button" type="button" onClick={() => test(b.id)}>Тест-ход</button>{' '}
              <button className="retry-button" type="button" onClick={() => runMatch(b.id)}>Матч vs random</button>{' '}
              {matches.some((m) => m.id) && (
                <button className="link-button" type="button" onClick={() => showReplay(b.id, matches[0].id)}>
                  реплей
                </button>
              )}
            </li>
          ))}
          {bots.length === 0 && <li className="link-hint">Ботов нет — сохраните версию выше</li>}
        </ul>
        {replay && (
          <div className="verdict">
            <strong>Реплей:</strong> {replay.match.result} vs {replay.match.opponent} (
            {replay.match.movesCount} ходов, Δelo {replay.match.eloDelta})
            <ul className="facts-list">
              {replay.moves.map((m) => (
                <li key={m.ply}>
                  №{m.ply} {m.agent}: {m.uci} ({m.thinkMs} мс)
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="panel">
        <h2>Лидерборд</h2>
        <ul className="facts-list">
          {leaderboard.map((row, i) => (
            <li key={row.userId}>
              {i + 1}. {row.email} — Elo {row.elo} ({row.wins}/{row.losses}/{row.draws})
            </li>
          ))}
          {leaderboard.length === 0 && <li className="link-hint">Пока пусто</li>}
        </ul>
      </div>
    </section>
  );
}
