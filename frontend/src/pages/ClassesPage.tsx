import { useCallback, useEffect, useState } from 'react';
import type {
  AgeGroup,
  ClassDashboardDto,
  ClassDetailDto,
  ClassDto,
} from '../shared/api';
import {
  ApiError,
  addClassMember,
  apiFetch,
  confirmStudentAgeGroup,
  createClass,
  fetchClassDashboard,
  fetchClassDetail,
  fetchClasses,
  getToken,
  joinClass,
  logout,
  removeClassMember,
  rotateClassInvite,
} from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

const AGE_GROUP_OPTIONS: { value: AgeGroup; label: string }[] = [
  { value: 'child', label: 'ребёнок' },
  { value: 'teen', label: 'подросток' },
  { value: 'adult', label: 'взрослый' },
  { value: 'unknown', label: 'не указан' },
];

const AGE_GROUP_LABELS: Record<AgeGroup, string> = {
  child: 'ребёнок',
  teen: 'подросток',
  adult: 'взрослый',
  unknown: 'не указан',
};

function weakestSkills(member: ClassDashboardDto['members'][number]): string {
  return [...member.skills]
    .sort((a, b) => a.score - b.score)
    .slice(0, 3)
    .map((s) => `${s.titleRu}: ${s.score}`)
    .join(' · ');
}

/** S-40: кабинет учителя — классы, инвайты, участники, групповой дашборд. */
export function ClassesPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [role, setRole] = useState('');
  const [classes, setClasses] = useState<ClassDto[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<ClassDetailDto | null>(null);
  const [dashboard, setDashboard] = useState<ClassDashboardDto | null>(null);
  const [ageDrafts, setAgeDrafts] = useState<Record<string, AgeGroup>>({});
  const [newName, setNewName] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [memberEmail, setMemberEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const isTeacher = role === 'teacher' || role === 'admin';

  const loadList = useCallback(async () => {
    const list = await fetchClasses();
    setClasses(list);
    setSelectedId((prev) =>
      prev && list.some((item) => item.id === prev)
        ? prev
        : (list[0]?.id ?? null),
    );
  }, []);

  const load = useCallback(async () => {
    setError('');
    try {
      const profile = await apiFetch<{ role: string }>('/profile/me');
      setRole(profile.role);
      await loadList();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Ошибка загрузки');
    }
  }, [loadList]);

  useEffect(() => {
    if (authed) {
      load();
    }
  }, [authed, load]);

  const loadDetail = useCallback(
    async (classId: string) => {
      try {
        const detailData = await fetchClassDetail(classId);
        setDetail(detailData);
        setAgeDrafts(
          Object.fromEntries(
            detailData.members.map((member) => [member.userId, member.ageGroup]),
          ),
        );
        if (isTeacher) {
          setDashboard(await fetchClassDashboard(classId));
        } else {
          setDashboard(null);
        }
      } catch (err) {
        setError(err instanceof ApiError ? err.message : 'Ошибка класса');
      }
    },
    [isTeacher],
  );

  useEffect(() => {
    if (selectedId) {
      loadDetail(selectedId);
    } else {
      setDetail(null);
      setDashboard(null);
    }
  }, [selectedId, loadDetail]);

  const act = useCallback(
    async (fn: () => Promise<void>, message = '') => {
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
    },
    [],
  );

  const onCreate = () =>
    act(async () => {
      const created = await createClass(newName.trim());
      setNewName('');
      await loadList();
      setSelectedId(created.id);
    }, 'Класс создан');

  const onJoin = () =>
    act(async () => {
      const joined = await joinClass(joinCode.trim());
      setJoinCode('');
      await loadList();
      setSelectedId(joined.id);
    }, 'Вы присоединились к классу');

  const onAddMember = () =>
    act(async () => {
      if (!selectedId) return;
      await addClassMember(selectedId, memberEmail.trim());
      setMemberEmail('');
      await loadDetail(selectedId);
      await loadList();
    }, 'Ученик добавлен');

  const onRemoveMember = (userId: string) =>
    act(async () => {
      if (!selectedId) return;
      await removeClassMember(selectedId, userId);
      await loadDetail(selectedId);
      await loadList();
    }, 'Ученик удалён из класса');

  const onConfirmAge = (userId: string) =>
    act(async () => {
      if (!selectedId) return;
      const ageGroup = ageDrafts[userId];
      if (!ageGroup) return;
      await confirmStudentAgeGroup(selectedId, userId, ageGroup);
      await loadDetail(selectedId);
    }, 'Возраст ученика подтверждён');

  const onRotateInvite = () =>
    act(async () => {
      if (!selectedId) return;
      const updated = await rotateClassInvite(selectedId);
      setDetail((prev) =>
        prev ? { ...prev, inviteCode: updated.inviteCode } : prev,
      );
    }, 'Код класса обновлён');

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Классы (classes)</h1>
        <p className="page-subtitle">Кабинет учителя и классы учеников</p>
        <LoginGate
          hint="Demo: teacher@chessclass.dev / dev-teacher-2026"
          onReady={() => setAuthed(true)}
        />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Классы (classes)</h1>
      <p className="page-subtitle">
        Классы, инвайты и групповой дашборд (S-40)
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
            setClasses([]);
            setDetail(null);
            setDashboard(null);
          }}
        >
          Выйти
        </button>
      </p>
      {error && (
        <p className="verdict failed-note" role="status">
          {error}
        </p>
      )}
      {notice && (
        <p className="link-hint" role="status">
          {notice}
        </p>
      )}

      {isTeacher ? (
        <div className="panel">
          <h2>Новый класс</h2>
          <div className="login-form">
            <input
              className="field"
              placeholder="Название класса"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <button
              className="retry-button"
              type="button"
              disabled={busy || newName.trim().length < 2}
              onClick={onCreate}
            >
              Создать класс
            </button>
          </div>
        </div>
      ) : (
        <div className="panel">
          <h2>Присоединиться по коду</h2>
          <div className="login-form">
            <input
              className="field"
              placeholder="Инвайт-код"
              value={joinCode}
              onChange={(e) => setJoinCode(e.target.value)}
            />
            <button
              className="retry-button"
              type="button"
              disabled={busy || joinCode.trim().length < 4}
              onClick={onJoin}
            >
              Войти в класс
            </button>
          </div>
        </div>
      )}

      <div className="classes-layout">
        <div className="panel class-list">
          <h2>Мои классы</h2>
          {classes.length === 0 && (
            <p className="link-hint">
              {isTeacher
                ? 'Классов пока нет — создайте первый выше.'
                : 'Вы пока не в классе — попросите код у учителя.'}
            </p>
          )}
          {classes.map((item) => (
            <button
              key={item.id}
              type="button"
              className={
                item.id === selectedId ? 'class-item active' : 'class-item'
              }
              onClick={() => setSelectedId(item.id)}
            >
              <strong>{item.name}</strong>
              <span>{item.memberCount} уч.</span>
            </button>
          ))}
        </div>

        <div className="panel class-detail">
          {!detail && <p className="link-hint">Выберите класс слева.</p>}
          {detail && (
            <>
              <h2>{detail.name}</h2>
              <p className="class-meta">
                Участников: {detail.memberCount} · уровень доступа:{' '}
                {isTeacher ? 'учитель' : 'ученик'}
              </p>
              {isTeacher && detail.inviteCode && (
                <p className="class-meta">
                  Инвайт-код: <code>{detail.inviteCode}</code>{' '}
                  <button
                    className="retry-button"
                    type="button"
                    disabled={busy}
                    onClick={onRotateInvite}
                  >
                    Обновить код
                  </button>
                </p>
              )}

              {isTeacher && (
                <div className="class-actions">
                  <input
                    className="field"
                    placeholder="email ученика"
                    value={memberEmail}
                    onChange={(e) => setMemberEmail(e.target.value)}
                  />
                  <button
                    className="retry-button"
                    type="button"
                    disabled={busy || !memberEmail.trim()}
                    onClick={onAddMember}
                  >
                    Добавить ученика
                  </button>
                </div>
              )}

              {isTeacher && (
                <>
                  <h3>Участники</h3>
                  <ul className="facts-list">
                    {detail.members.map((member) => (
                      <li key={member.userId}>
                        <div>
                          {member.displayName ?? member.email} · {member.email} ·{' '}
                          {member.level}
                        </div>
                        <div className="class-meta">
                          возраст: {AGE_GROUP_LABELS[member.ageGroup]}
                          {member.ageGroupConfirmedAt
                            ? ` · подтверждён ${new Date(
                                member.ageGroupConfirmedAt,
                              ).toLocaleDateString('ru-RU')}`
                            : ' · не подтверждён учителем'}
                        </div>
                        <div className="age-confirm">
                          <select
                            className="field"
                            aria-label={`Возрастная группа для ${member.email}`}
                            value={ageDrafts[member.userId] ?? member.ageGroup}
                            disabled={busy}
                            onChange={(e) =>
                              setAgeDrafts((prev) => ({
                                ...prev,
                                [member.userId]: e.target.value as AgeGroup,
                              }))
                            }
                          >
                            {AGE_GROUP_OPTIONS.map((option) => (
                              <option key={option.value} value={option.value}>
                                {option.label}
                              </option>
                            ))}
                          </select>
                          <button
                            className="retry-button"
                            type="button"
                            disabled={busy}
                            onClick={() => onConfirmAge(member.userId)}
                          >
                            Подтвердить возраст
                          </button>
                          <button
                            className="link-button"
                            type="button"
                            disabled={busy}
                            onClick={() => onRemoveMember(member.userId)}
                          >
                            удалить
                          </button>
                        </div>
                      </li>
                    ))}
                    {detail.members.length === 0 && (
                      <li className="link-hint">В классе пока нет учеников.</li>
                    )}
                  </ul>
                </>
              )}

              {isTeacher && dashboard && (
                <>
                  <h3>Групповой дашборд</h3>
                  <div className="class-table-wrap">
                    <table className="class-table">
                      <thead>
                        <tr>
                          <th>Ученик</th>
                          <th>Уровень</th>
                          <th>Слабые навыки</th>
                          <th>Флаги</th>
                          <th>Матчи / Elo</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dashboard.members.map((member) => (
                          <tr key={member.userId}>
                            <td>
                              {member.displayName ?? member.email}
                              <br />
                              <span className="link-hint">{member.email}</span>
                            </td>
                            <td>{member.level}</td>
                            <td>{weakestSkills(member) || '—'}</td>
                            <td>
                              {member.flagsCount}
                              {member.newFlagsCount > 0
                                ? ` (новых: ${member.newFlagsCount})`
                                : ''}
                            </td>
                            <td>
                              {member.matchesCount} · Elo {member.elo}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}

              {!isTeacher && (
                <p className="link-hint">
                  Вы участник класса. Прогресс и задания доступны на дашборде
                  ученика.
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
