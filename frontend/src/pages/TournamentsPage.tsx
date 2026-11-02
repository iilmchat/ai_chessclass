import { useCallback, useEffect, useState } from 'react';
import type {
  TournamentDetailDto,
  TournamentDto,
  TournamentReplayDto,
} from '../shared/api';
import {
  ApiError,
  apiFetch,
  cancelTournament,
  createTournament,
  downloadFile,
  fetchTournament,
  fetchTournamentReplay,
  fetchTournaments,
  getToken,
  logout,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

/** S-45: турниры ботов — bracket/round-robin, лидерборд, экспорт. */
export function TournamentsPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [role, setRole] = useState('');
  const [items, setItems] = useState<TournamentDto[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<TournamentDetailDto | null>(null);
  const [replay, setReplay] = useState<TournamentReplayDto | null>(null);
  const [name, setName] = useState('');
  const [format, setFormat] = useState('bracket');
  const [botIds, setBotIds] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const canManage = role === 'teacher' || role === 'admin';

  const loadList = useCallback(async () => {
    const list = await fetchTournaments();
    setItems(list);
    setSelectedId((prev) =>
      prev && list.some((item) => item.id === prev)
        ? prev
        : (list[0]?.id ?? null),
    );
  }, []);

  const load = useCallback(async () => {
    try {
      const profile = await apiFetch<{ role: string }>('/profile/me');
      setRole(profile.role);
      await loadList();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки');
    }
  }, [loadList]);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    fetchTournament(selectedId)
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof ApiError ? err.message : 'Ошибка турнира'),
      );
  }, [selectedId]);

  useEffect(() => {
    if (
      !selectedId ||
      !detail ||
      !['queued', 'running'].includes(detail.status)
    ) {
      return;
    }
    const timer = window.setInterval(() => {
      fetchTournament(selectedId)
        .then(setDetail)
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [selectedId, detail?.status]);

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

  const onCreate = () =>
    act(async () => {
      const ids = botIds
        .split(/[,\s]+/)
        .map((value) => Number(value))
        .filter((value) => Number.isInteger(value) && value > 0);
      const created = await createTournament({
        name: name.trim(),
        format,
        botVersionIds: ids,
      });
      setName('');
      setBotIds('');
      await loadList();
      setSelectedId(created.id);
    }, 'Турнир проведён');

  const onExport = (id: string) =>
    act(async () => {
      await downloadFile(
        `/admin/tournaments/${id}/export.csv`,
        `tournament-${id}.csv`,
      );
    }, 'Экспорт скачан');

  const onCancel = (id: string) =>
    act(async () => {
      await cancelTournament(id);
      setDetail(await fetchTournament(id));
    }, 'Турнир отменён');

  const onReplay = (tournamentId: string, matchId: string) =>
    act(async () => {
      setReplay(await fetchTournamentReplay(tournamentId, matchId));
    });

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Турниры ботов</h1>
        <p className="page-subtitle">Турниры без LLM и экспорт результатов</p>
        <LoginGate
          hint="Demo: teacher@chessclass.dev / dev-teacher-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Турниры ботов</h1>
      <p className="page-subtitle">
        Bracket/round-robin, лидерборд, античит-флаги (S-45)
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
            setItems([]);
            setDetail(null);
          }}
        >
          Выйти
        </button>
      </p>
      {error && <p className="verdict failed-note">{error}</p>}
      {notice && <p className="link-hint">{notice}</p>}

      {canManage && (
        <div className="panel">
          <h2>Новый турнир</h2>
          <div className="class-actions">
            <input
              className="field"
              placeholder="Название турнира"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            <select
              className="field"
              value={format}
              onChange={(e) => setFormat(e.target.value)}
              aria-label="Формат турнира"
            >
              <option value="bracket">Плей-офф (bracket)</option>
              <option value="round_robin">Круговая (round-robin)</option>
            </select>
            <input
              className="field"
              placeholder="ID ботов через запятую (2–16)"
              value={botIds}
              onChange={(e) => setBotIds(e.target.value)}
            />
            <button
              className="retry-button"
              type="button"
              disabled={busy || name.trim().length < 2 || !botIds.trim()}
              onClick={onCreate}
            >
              Провести турнир
            </button>
          </div>
          <p className="link-hint">
            ID ботов видны в конструкторе ботов; турнир считается без LLM.
          </p>
        </div>
      )}

      <div className="classes-layout">
        <div className="panel class-list">
          <h2>Турниры</h2>
          {items.length === 0 && (
            <p className="link-hint">Турниров пока нет.</p>
          )}
          {items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={
                item.id === selectedId ? 'class-item active' : 'class-item'
              }
              onClick={() => setSelectedId(item.id)}
            >
              <strong>{item.name}</strong>
              <span>
                {item.format} · {item.status}
              </span>
            </button>
          ))}
        </div>

        <div className="panel class-detail">
          {!detail && <p className="link-hint">Выберите турнир слева.</p>}
          {detail && (
            <>
              <h2>{detail.name}</h2>
              <p className="class-meta">
                {detail.format} · {detail.status} · участников:{' '}
                {detail.participants.length} · матчей: {detail.matches.length}
              </p>
              <p className="link-hint">
                прогресс: {detail.progress}/{detail.totalMatches}
                {detail.error ? ` · ошибка: ${detail.error}` : ''}
              </p>
              {canManage && ['queued', 'running'].includes(detail.status) && (
                <button
                  className="retry-button"
                  type="button"
                  disabled={busy}
                  onClick={() => onCancel(detail.id)}
                >
                  Отменить турнир
                </button>
              )}
              {canManage && (
                <button
                  className="retry-button"
                  type="button"
                  disabled={busy}
                  onClick={() => onExport(detail.id)}
                >
                  Экспорт CSV
                </button>
              )}
              <h3>Лидерборд</h3>
              <div className="class-table-wrap">
                <table className="class-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Бот</th>
                      <th>Ученик</th>
                      <th>W/L/D</th>
                      <th>Очки</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.participants.map((participant) => (
                      <tr key={participant.botVersionId}>
                        <td>{participant.rank ?? '—'}</td>
                        <td>{participant.botVersionId}</td>
                        <td>
                          {participant.displayName ??
                            participant.email ??
                            participant.userId}
                        </td>
                        <td>
                          {participant.wins}/{participant.losses}/
                          {participant.draws}
                        </td>
                        <td>{participant.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <h3>Матчи</h3>
              <ul className="facts-list">
                {detail.matches.map((match) => (
                  <li key={`${match.roundNo}-${match.matchNo}`}>
                    раунд {match.roundNo}.{match.matchNo}: {match.botAId} vs{' '}
                    {match.botBId} → {match.result} ({match.movesCount} ходов){' '}
                    <button
                      className="link-button"
                      type="button"
                      onClick={() => onReplay(detail.id, match.id)}
                    >
                      replay
                    </button>
                  </li>
                ))}
              </ul>
              {replay && (
                <div className="verdict">
                  <strong>Реплей:</strong> {replay.match.botAId} vs{' '}
                  {replay.match.botBId} · {replay.match.result}
                  <ul className="facts-list">
                    {replay.moves.map((move) => (
                      <li key={move.ply}>
                        {move.ply}. {move.agent}: {move.uci}
                        {move.sfSample ? ' · SF-семпл' : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
