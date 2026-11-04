import { useCallback, useEffect, useRef, useState } from 'react';
import { Chessboard } from 'react-chessboard';
import type { PvpLeaderRowDto, PvpRoomDto } from '../shared/api';
import {
  ApiError,
  apiFetch,
  cancelPvpRoom,
  createPvpComplaint,
  createPvpRoom,
  fetchMyPvpRoom,
  fetchPvpLeaderboard,
  fetchPvpRoom,
  fetchTournament,
  getToken,
  joinPvpRoom,
  logout,
  pvpQuickMatch,
  startPvpRoom,
  type PvpReplayDto,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';
import { useEventStream } from '../shared/useEventStream';

interface BotDto {
  id: string;
  versionNo: number;
}

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

/** S-65: PvP — комнаты, quick-match, SSE-статус, replay, лидерборд, жалобы. */
export function PvpPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [bots, setBots] = useState<BotDto[]>([]);
  const [botId, setBotId] = useState('');
  const [room, setRoom] = useState<PvpRoomDto | null>(null);
  const [joinCode, setJoinCode] = useState('');
  const [rated, setRated] = useState(true);
  const [leaders, setLeaders] = useState<PvpLeaderRowDto[]>([]);
  const [replay, setReplay] = useState<PvpReplayDto | null>(null);
  const [replayPly, setReplayPly] = useState(0);
  const [events, setEvents] = useState<string[]>([]);
  const [complaintText, setComplaintText] = useState('');
  const [myUserId, setMyUserId] = useState('');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const loadTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const act = useCallback(
    async (fn: () => Promise<void>, message: string) => {
      setBusy(message);
      setNotice('');
      setError('');
      try {
        await fn();
        setNotice(`Готово: ${message}`);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Ошибка операции');
      } finally {
        setBusy('');
      }
    },
    [],
  );

  const refreshLeaders = useCallback(() => {
    fetchPvpLeaderboard().then(setLeaders).catch(() => setLeaders([]));
  }, []);

  const loadBots = useCallback(() => {
    apiFetch<BotDto[]>('/bots').then(setBots).catch(() => setBots([]));
  }, []);

  const openReplay = useCallback(async (current: PvpRoomDto) => {
    if (!current.tournamentId) {
      return;
    }
    const detail = await fetchTournament(current.tournamentId);
    const match = detail.matches[0];
    if (!match) {
      return;
    }
    const response = await apiFetch<PvpReplayDto>(
      `/pvp/rooms/${current.id}/replay?match_id=${match.id}`,
    );
    setReplay(response);
    setReplayPly(response.moves.length);
  }, []);

  // Поллинг статуса комнаты: waiting/ready/running → done/cancelled/failed.
  useEffect(() => {
    if (!room) {
      return;
    }
    if (!['waiting', 'ready', 'running'].includes(room.status)) {
      if (room.status === 'done' && !replay) {
        void openReplay(room);
      }
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const fresh = await fetchPvpRoom(room.id);
        setRoom(fresh);
      } catch {
        /* сетевой шум: на следующем тике */
      }
    }, 3000);
    loadTimer.current = timer;
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room, replay, openReplay]);

  // SSE прогресс турнира, пока партия running.
  const sseEnabled = Boolean(room?.tournamentId && room.status === 'running');
  useEventStream({
    url: room?.tournamentId ? `/tournaments/${room.tournamentId}/events` : null,
    enabled: sseEnabled,
    onEvent: (event) => {
      setEvents((prev) => [...prev.slice(-40), `${event.event}: ${event.data}`]);
    },
  });

  const load = useCallback(() => {
    loadBots();
    refreshLeaders();
    apiFetch<{ role: string; id: string }>('/profile/me')
      .then((profile) => setMyUserId(profile.id))
      .catch(() => setMyUserId(''));
    // S-65: возврат активной комнаты после F5 (waiting/ready/running)
    fetchMyPvpRoom()
      .then(setRoom)
      .catch(() => setRoom(null));
  }, [loadBots, refreshLeaders]);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  const pickBot = () => {
    const value = botId === '' ? bots[0]?.id ?? '' : botId;
    if (!value) {
      throw new Error('Сначала создайте бота в разделе Боты');
    }
    return Number(value);
  };

  const onCreate = () =>
    act(async () => {
      setReplay(null);
      setRoom(await createPvpRoom(pickBot(), rated));
      refreshLeaders();
    }, 'комната создана (ожидание гостя)');

  const onQuick = () =>
    act(async () => {
      setReplay(null);
      const result = await pvpQuickMatch(pickBot());
      setRoom(result.room);
      setNotice(result.matched ? 'Found opponent' : 'Комната создана, ожидаем соперника');
      refreshLeaders();
    }, 'поиск соперника');

  const onJoin = () =>
    act(async () => {
      setReplay(null);
      const joined = await joinPvpRoom(joinCode, pickBot());
      setRoom(joined);
      setJoinCode('');
    }, 'вы вошли в комнату');

  const onStart = () =>
    act(async () => {
      if (!room) return;
      setRoom(await startPvpRoom(room.id));
      setEvents([]);
    }, 'матч запущен (турнир в очереди)');

  const onCancel = () =>
    act(async () => {
      if (!room) return;
      setRoom(await cancelPvpRoom(room.id));
    }, 'комната отменена');

  const onComplaint = () =>
    act(async () => {
      if (!room) return;
      const text = complaintText.trim();
      if (text.length < 5) {
        setError('Опишите причину (≥ 5 символов)');
        return;
      }
      await createPvpComplaint(room.id, text);
      setComplaintText('');
    }, 'жалоба отправлена на разбор');

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">PvP-матчи ботов</h1>
        <p className="page-subtitle" role="status" aria-live="polite">Арена доступна после входа</p>
        <LoginGate hint="Demo: student1@chessclass.dev / dev-student-2026" onReady={() => setAuthed(true)} />
      </section>
    );
  }

  const statusLine = room
    ? `Комната #${room.id} · код ${room.code} · статус ${room.status}${room.rated ? ' · rated' : ''}`
    : 'Нет активной комнаты';

  const amHost = Boolean(room && room.hostUserId === myUserId);
  const amParticipant = Boolean(
    room && (room.hostUserId === myUserId || room.guestUserId === myUserId),
  );

  return (
    <section>
      <h1 className="page-title">PvP-матчи ботов</h1>
      <p className="page-subtitle" role="status" aria-live="polite">
        Комнаты · quick-match · SSE · replay · Elo (S-65) · {busy || notice || '—'}
        <button className="retry-button logout" type="button" onClick={() => { logout(); setAuthed(false); }}>
          Выйти
        </button>
      </p>
      {error && <p role="status" aria-live="assertive" className="verdict failed-note">{error}</p>}

      <div className="panel pvp-room">
        <h2>Мой бот</h2>
        {bots.length === 0 ? (
          <p className="link-hint">Ботов нет — создайте версию в разделе «Боты»</p>
        ) : (
          <select className="field" value={botId} onChange={(e) => setBotId(e.target.value)} aria-label="Бот">
            {bots.map((b) => (
              <option key={b.id} value={b.id}>
                версия №{b.versionNo}
              </option>
            ))}
          </select>
        )}
        <label className="pvp-rated">
          <input type="checkbox" checked={rated} onChange={(e) => setRated(e.target.checked)} />
          рейтинговый матч (Elo)
        </label>
        <div className="submit-row">
          <button className="retry-button" type="button" disabled={busy !== '' || !myUserId} onClick={onCreate}>
            Создать комнату
          </button>
          <button className="retry-button" type="button" disabled={busy !== '' || !myUserId} onClick={onQuick}>
            Quick-match
          </button>
        </div>
        <div className="rag-toolbar">
          <input
            className="field"
            value={joinCode}
            placeholder="код комнаты гостя"
            onChange={(e) => setJoinCode(e.target.value)}
          />
          <button className="retry-button" type="button" disabled={busy !== '' || joinCode.trim().length < 4} onClick={onJoin}>
            Войти по коду
          </button>
        </div>
      </div>

      {room && (
        <div className="panel">
          <h2>Статус</h2>
          <p className="health-label">{statusLine}</p>
          {room.status === 'ready' && amHost && (
            <button className="retry-button" type="button" disabled={busy !== ''} onClick={onStart}>
              Запустить матч (host)
            </button>
          )}
          {amHost && room.status !== 'done' && room.status !== 'cancelled' && (
            <button className="retry-button" type="button" disabled={busy !== ''} onClick={onCancel}>
              Отменить
            </button>
          )}
          {room.status === 'running' && (
            <p className="link-hint">
              Матч идёт: {events.length > 0 ? events[events.length - 1] : 'SSE подключен'}
            </p>
          )}
          {room.status === 'done' && (
            <p className="verdict">
              Матч завершён. Реплей и Elo обновлены.
            </p>
          )}
          {amParticipant && (
            <div className="pvp-complaint">
              <h3>Жалоба на матч (разбор учителем)</h3>
              <textarea
                className="field"
                rows={2}
                value={complaintText}
                placeholder="причина (≥ 5 символов)"
                onChange={(e) => setComplaintText(e.target.value)}
              />
              <button className="retry-button" type="button" disabled={busy !== ''} onClick={onComplaint}>
                Отправить жалобу
              </button>
            </div>
          )}
        </div>
      )}

      {replay && (
        <div className="panel pvp-replay">
          <h2>
            Реплей · {replay.match.result} · {replay.match.movesCount} ходов
          </h2>
          <div className="pvp-board-wrap">
            <Chessboard
              options={{
                position: replay.moves[replayPly - 1]?.fen ?? START_FEN,
              }}
            />
          </div>
          <div className="rag-toolbar">
            <button className="retry-button" type="button" onClick={() => setReplayPly((v) => Math.max(1, v - 1))}>
              ◀ Шаг назад
            </button>
            <span className="health-label">
              полуход {replayPly}/{replay.moves.length}
            </span>
            <button
              className="retry-button"
              type="button"
              onClick={() => setReplayPly((v) => Math.min(replay.moves.length, v + 1))}
            >
              Шаг вперёд ▶
            </button>
          </div>
          <ul className="facts-list pvp-moves">
            {replay.moves.slice(Math.max(0, replayPly - 8), replayPly).map((mv) => (
              <li key={mv.ply}>
                №{mv.ply} {mv.agent}: {mv.uci} ({mv.thinkMs} мс)
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <h2>Лидерборд (PvP Elo)</h2>
        <ul className="facts-list">
          {leaders.map((row) => (
            <li key={row.userId}>
              {row.displayName ?? row.email}: <strong>{row.elo}</strong> ({row.wins}/{row.losses}/{row.draws})
            </li>
          ))}
          {leaders.length === 0 && <li className="link-hint">Пока пусто</li>}
        </ul>
        <button className="retry-button" type="button" onClick={refreshLeaders}>
          Обновить
        </button>
      </div>
    </section>
  );
}
