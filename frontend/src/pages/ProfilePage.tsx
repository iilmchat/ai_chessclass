import { useCallback, useEffect, useState } from 'react';
import type { ProgressDto, ProfileDto } from '../shared/api';
import {
  ApiError,
  fetchMyProfile,
  fetchMyProgress,
  getToken,
  logout,
  updateMyProfile,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

const AGE_LABELS: Record<string, string> = {
  unknown: 'Не указан',
  child: 'Ребёнок (6–12)',
  teen: 'Подросток (13–17)',
  adult: 'Взрослый (18+)',
};

const ROLE_LABELS: Record<string, string> = {
  student: 'ученик',
  teacher: 'учитель',
  admin: 'админ',
  auditor: 'аудитор',
};

/** S-42: профиль — age_group, стрики, прогресс и бейджи. */
export function ProfilePage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [profile, setProfile] = useState<ProfileDto | null>(null);
  const [progress, setProgress] = useState<ProgressDto | null>(null);
  const [ageGroup, setAgeGroup] = useState('unknown');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [me, snapshot] = await Promise.all([
        fetchMyProfile(),
        fetchMyProgress(),
      ]);
      setProfile(me);
      setAgeGroup(me.ageGroup);
      setProgress(snapshot);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки');
    }
  }, []);

  useEffect(() => {
    if (authed) load();
  }, [authed, load]);

  const saveAge = useCallback(async () => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const me = await updateMyProfile({ ageGroup });
      setProfile(me);
      setAgeGroup(me.ageGroup);
      setNotice('Возрастная группа сохранена');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка сохранения');
    } finally {
      setBusy(false);
    }
  }, [ageGroup]);

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Профиль</h1>
        <p className="page-subtitle">Профиль, стрики и достижения</p>
        <LoginGate
          hint="Demo: student1@chessclass.dev / dev-student-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Профиль</h1>
      <p className="page-subtitle">
        Возрастная группа, прогресс и бейджи (S-42)
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
            setProfile(null);
            setProgress(null);
          }}
        >
          Выйти
        </button>
      </p>
      {error && <p className="verdict failed-note">{error}</p>}
      {notice && <p className="link-hint">{notice}</p>}

      {profile && (
        <div className="profile-grid">
          <div className="panel">
            <h2>Аккаунт</h2>
            <p>
              <strong>{profile.displayName ?? profile.email}</strong>
            </p>
            <p className="class-meta">
              {profile.email} · {ROLE_LABELS[profile.role] ?? profile.role} ·
              уровень {profile.level ?? '—'}
            </p>
            <p className="class-meta">
              Возрастная группа:{' '}
              <strong>{AGE_LABELS[profile.ageGroup] ?? profile.ageGroup}</strong>
            </p>
            <div className="class-actions">
              <select
                className="field"
                value={ageGroup}
                onChange={(e) => setAgeGroup(e.target.value)}
                aria-label="Возрастная группа"
              >
                {Object.entries(AGE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <button
                className="retry-button"
                type="button"
                disabled={busy || ageGroup === profile.ageGroup}
                onClick={saveAge}
              >
                Сохранить
              </button>
            </div>
            <p className="link-hint">
              По умолчанию — «не указан»; данные видны только вам и учителю.
            </p>
          </div>

          <div className="panel">
            <h2>Прогресс Python</h2>
            <div className="streak-row">
              <div>
                <span className="streak-value">
                  {progress?.solvedCount ?? 0}
                </span>
                <span className="class-meta">решено</span>
              </div>
              <div>
                <span className="streak-value">
                  {progress?.currentStreak ?? 0}
                </span>
                <span className="class-meta">текущий стрик</span>
              </div>
              <div>
                <span className="streak-value">
                  {progress?.longestStreak ?? 0}
                </span>
                <span className="class-meta">лучший стрик</span>
              </div>
            </div>
            <h3>Темы</h3>
            <ul className="facts-list">
              {Object.entries(progress?.topics ?? {}).map(([topic, count]) => (
                <li key={topic}>
                  {topic}: <strong>{count}</strong>
                </li>
              ))}
              {Object.keys(progress?.topics ?? {}).length === 0 && (
                <li className="link-hint">Пока нет решённых заданий.</li>
              )}
            </ul>
          </div>
        </div>
      )}

      {progress && (
        <div className="panel">
          <h2>Достижения</h2>
          <div className="achievement-grid">
            {progress.achievements.map((achievement) => (
              <div
                key={achievement.code}
                className={
                  achievement.awarded
                    ? 'achievement earned'
                    : 'achievement locked'
                }
              >
                <span className="achievement-icon" aria-hidden="true">
                  {achievement.awarded ? '★' : '☆'}
                </span>
                <strong>{achievement.titleRu}</strong>
                <span className="class-meta">{achievement.description}</span>
                {achievement.awarded && achievement.awardedAt && (
                  <span className="link-hint">
                    получен {new Date(achievement.awardedAt).toLocaleDateString()}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
