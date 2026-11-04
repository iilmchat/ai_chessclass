import { useCallback, useEffect, useState } from 'react';
import type {
  ProgressDto,
  ProfileDto,
  TelegramStatusDto,
} from '../shared/api';
import {
  ApiError,
  createTelegramCode,
  fetchMyProfile,
  fetchMyProgress,
  fetchTelegramStatus,
  getToken,
  linkTelegram,
  logout,
  unlinkTelegram,
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
  const [telegram, setTelegram] = useState<TelegramStatusDto | null>(null);
  const [ageGroup, setAgeGroup] = useState('unknown');
  const [chatId, setChatId] = useState('');
  const [consent, setConsent] = useState(false);
  const [telegramCode, setTelegramCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [telegramBusy, setTelegramBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [me, snapshot, tg] = await Promise.all([
        fetchMyProfile(),
        fetchMyProgress(),
        fetchTelegramStatus(),
      ]);
      setProfile(me);
      setAgeGroup(me.ageGroup);
      setProgress(snapshot);
      setTelegram(tg);
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

  const linkChat = useCallback(async () => {
    setTelegramBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await linkTelegram(chatId, consent);
      setTelegram((prev) => ({
        linked: result.linked,
        consent: result.consent,
        configured: result.configured,
        counts: prev?.counts ?? {},
      }));
      setNotice('Telegram привязан: уведомления включены');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка привязки');
    } finally {
      setTelegramBusy(false);
    }
  }, [chatId, consent]);

  const unlinkChat = useCallback(async () => {
    setTelegramBusy(true);
    setError('');
    setNotice('');
    try {
      await unlinkTelegram();
      setTelegram((prev) => ({
        linked: false,
        consent: false,
        configured: prev?.configured ?? false,
        counts: prev?.counts ?? {},
      }));
      setNotice('Telegram отвязан, уведомления отключены');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка отписки');
    } finally {
      setTelegramBusy(false);
    }
  }, []);

  const makeCode = useCallback(async () => {
    setTelegramBusy(true);
    setError('');
    try {
      const result = await createTelegramCode();
      setTelegramCode(result.code);
      setNotice(`Код: ${result.code} (действует ${result.expiresInS} с)`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка кода');
    } finally {
      setTelegramBusy(false);
    }
  }, []);

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
      {error && <p role="status" aria-live="assertive" className="verdict failed-note">{error}</p>}
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
            <h2>Telegram</h2>
            <p className="class-meta">
              {telegram?.linked
                ? 'Уведомления включены'
                : 'Уведомления не подключены'}
              {telegram && !telegram.configured
                ? ' · бот не настроен на сервере'
                : ''}
            </p>
            <div className="class-actions">
              <input
                className="field"
                value={chatId}
                onChange={(e) => setChatId(e.target.value)}
                placeholder="chat_id из Telegram"
                aria-label="Telegram chat_id"
              />
              <button
                className="retry-button"
                type="button"
                disabled={telegramBusy || !chatId || !consent}
                onClick={linkChat}
              >
                Привязать
              </button>
              {telegram?.linked && (
                <button
                  className="retry-button"
                  type="button"
                  disabled={telegramBusy}
                  onClick={unlinkChat}
                >
                  Отписаться
                </button>
              )}
            </div>
            <label className="class-meta">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
              />{' '}
              Согласен получать уведомления в Telegram
            </label>
            <p className="link-hint">
              Бейджи, стрики, проверка учителем и готовый PDF. Можно отписаться
              в любой момент.
            </p>
            {telegramCode && (
              <p className="link-hint">
                Код для бота: <code>{telegramCode}</code>
              </p>
            )}
            <button
              className="retry-button"
              type="button"
              disabled={telegramBusy}
              onClick={makeCode}
            >
              Получить код привязки
            </button>
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
