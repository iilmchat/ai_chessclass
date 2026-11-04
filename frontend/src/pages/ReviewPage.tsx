import { useCallback, useEffect, useState } from 'react';
import type { ReviewQueueDto, ReviewStatsDto } from '../shared/api';
import {
  ApiError,
  answerReview,
  fetchReviewQueue,
  fetchReviewStats,
  getToken,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

const RATINGS: Array<{
  value: 'again' | 'hard' | 'good' | 'easy';
  label: string;
}> = [
  { value: 'again', label: 'Забыл' },
  { value: 'hard', label: 'Сложно' },
  { value: 'good', label: 'Нормально' },
  { value: 'easy', label: 'Легко' },
];

/** S-52: очередь SM-2 и ответы по карточкам. */
export function ReviewPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [queue, setQueue] = useState<ReviewQueueDto | null>(null);
  const [stats, setStats] = useState<ReviewStatsDto | null>(null);
  const [showBack, setShowBack] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [next, summary] = await Promise.all([
        fetchReviewQueue(),
        fetchReviewStats(),
      ]);
      setQueue(next);
      setStats(summary);
      setShowBack(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки');
    }
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  const answer = useCallback(
    async (rating: 'again' | 'hard' | 'good' | 'easy') => {
      const card = queue?.cards[0];
      if (!card) return;
      setBusy(true);
      setError('');
      try {
        await answerReview(card.id, rating);
        await load();
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Ошибка ответа');
      } finally {
        setBusy(false);
      }
    },
    [queue, load],
  );

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Повторение</h1>
        <p className="page-subtitle">Карточки ошибок и интервальные повторения</p>
        <LoginGate
          hint="Demo: student1@chessclass.dev / dev-student-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  const card = queue?.cards[0];

  return (
    <section>
      <h1 className="page-title">Повторение</h1>
      <p className="page-subtitle">
        SM-2: карточки ошибок Python и шахмат, дневной лимит{' '}
        {queue?.dailyLimit ?? stats?.dailyLimit ?? 20}
      </p>
      {error && <p role="status" aria-live="assertive" className="verdict failed-note">{error}</p>}

      {stats && (
        <div className="panel">
          <h2>Статистика</h2>
          <div className="streak-row">
            <div>
              <span className="streak-value">{stats.due}</span>
              <span className="class-meta">к повторению</span>
            </div>
            <div>
              <span className="streak-value">{stats.reviewsToday}</span>
              <span className="class-meta">сегодня</span>
            </div>
            <div>
              <span className="streak-value">{stats.total}</span>
              <span className="class-meta">всего карточек</span>
            </div>
            <div>
              <span className="streak-value">
                {stats.retention === null
                  ? '—'
                  : `${Math.round(stats.retention * 100)}%`}
              </span>
              <span className="class-meta">удержание</span>
            </div>
          </div>
        </div>
      )}

      {card ? (
        <div className="panel">
          <h2>Карточка · {card.sourceType}</h2>
          <p className="card-front">{card.front}</p>
          {showBack ? (
            <p className="link-hint">{card.back}</p>
          ) : (
            <button
              className="retry-button"
              type="button"
              onClick={() => setShowBack(true)}
            >
              Показать ответ
            </button>
          )}
          {showBack && (
            <div className="class-actions">
              {RATINGS.map((rating) => (
                <button
                  key={rating.value}
                  className="retry-button"
                  type="button"
                  disabled={busy}
                  onClick={() => answer(rating.value)}
                >
                  {rating.label}
                </button>
              ))}
            </div>
          )}
          <p className="link-hint">
            Интервал: {card.intervalDays} дн. · повторений: {card.repetitions} ·
            забываний: {card.lapses}
          </p>
        </div>
      ) : (
        <div className="panel">
          <h2>На сегодня всё</h2>
          <p className="link-hint">
            Ошибки Python и шахматные зевки добавляются автоматически. Загляните
            позже — карточки появятся по интервалу SM-2.
          </p>
        </div>
      )}
    </section>
  );
}
