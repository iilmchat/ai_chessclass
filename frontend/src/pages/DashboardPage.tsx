import { useCallback, useEffect, useState } from 'react';
import type { InsightOut } from '../shared/api';
import { ApiError, apiFetch, fetchHealth, getToken, logout } from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

interface Snapshot {
  skills: { slug: string; titleRu: string; score: number }[];
  recommendations: { hint: string }[];
}

interface StatsDto {
  elo: number;
  wins: number;
  losses: number;
  draws: number;
}

/** S-26: dashboard — сводка всех доменов с состояниями загрузки. */
export function DashboardPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [health, setHealth] = useState<{ status: string; db: boolean; redis: boolean } | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [stats, setStats] = useState<StatsDto | null>(null);
  const [insight, setInsight] = useState<InsightOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const refresh = useCallback(() => {
    setLoading(true);
    setError('');
    fetchHealth()
      .then(setHealth)
      .catch((err: unknown) => setError(err instanceof ApiError ? err.message : 'Ошибка'));
    if (getToken()) {
      apiFetch<Snapshot>('/skills/me').then(setSnapshot).catch(() => setSnapshot(null));
      apiFetch<StatsDto>('/bots/stats').then(setStats).catch(() => setStats(null));
      apiFetch<InsightOut>('/chess/insight', {
        method: 'POST',
        body: JSON.stringify({
          fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
        }),
      })
        .then(setInsight)
        .catch(() => setInsight(null));
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Дашборд</h1>
        <p className="page-subtitle">Единая экосистема «Шахматно-программистский класс»</p>
        <div className="panel">
          <div className="health-card">
            <span className={`health-dot ${health ? (health.status === 'ok' ? 'ok' : 'down') : 'down'}`} />
            <span className="health-label">
              {health ? `Инфраструктура: ${health.status}` : `Инфраструктура недоступна: ${error}`}
            </span>
            <button className="retry-button" type="button" onClick={refresh}>Обновить</button>
          </div>
        </div>
        <LoginGate hint="Demo: student1@chessclass.dev / dev-student-2026" onReady={() => setAuthed(true)} />
      </section>
    );
  }

  const weakest = [...(snapshot?.skills ?? [])].sort((a, b) => a.score - b.score).slice(0, 3);

  return (
    <section>
      <h1 className="page-title">Дашборд</h1>
      <p className="page-subtitle">
        Сводка всех доменов (S-26)
        <button className="retry-button logout" type="button" onClick={() => { logout(); setAuthed(false); }}>Выйти</button>
      </p>

      <div className="panel stats-grid">
        <div>
          <h2>Инфраструктура</h2>
          <p className="health-label">
            {health ? (health.status === 'ok' ? '✓ API/БД/Redis — ок' : 'Деградация') : 'Недоступно'}
          </p>
        </div>
        <div>
          <h2>Шахматный бот</h2>
          <p className="health-label">
            {stats ? <>Elo <strong>{stats.elo}</strong> ({stats.wins}/{stats.losses}/{stats.draws})</> : '—'}
          </p>
        </div>
        <div>
          <h2>Слабые навыки</h2>
          <p className="health-label">
            {weakest.length > 0
              ? weakest.map((s) => `${s.titleRu}: ${s.score}`).join(' · ')
              : '—'}
          </p>
        </div>
      </div>

      {snapshot && snapshot.recommendations.length > 0 && (
        <div className="panel">
          <h2>Рекомендации</h2>
          <ul className="facts-list">
            {snapshot.recommendations.map((r) => (
              <li key={r.hint}>{r.hint}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="panel">
        <h2>Инсайт дня (стартовая позиция)</h2>
        {insight ? (
          <>
            <ul className="facts-list">
              {insight.factsText.map((f) => <li key={f}>{f}</li>)}
            </ul>
            <p className="statement">{insight.explanation}</p>
            <p className="link-hint">модель: {insight.modelUsed} · уровень: {insight.level}</p>
          </>
        ) : (
          <p className="link-hint">{loading ? 'Загрузка…' : 'Откройте /chess для анализа'}</p>
        )}
      </div>
    </section>
  );
}
