import { useCallback, useEffect, useState } from 'react';
import { ApiError, fetchHealth, type HealthDto } from '../shared/api';

/** S-01: дашборд — каркас on healthz. Живые виджеты приходят позже (TODO V0.1). */
export function DashboardPage() {
  const [health, setHealth] = useState<HealthDto | null>(null);
  const [error, setError] = useState<string>('');

  const refresh = useCallback(() => {
    setError('');
    fetchHealth()
      .then(setHealth)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Неизвестная ошибка');
        setHealth(null);
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const allOk = health?.status === 'ok';

  return (
    <section>
      <h1 className="page-title">Дашборд</h1>
      <p className="page-subtitle">
        Единая экосистема «Шахматно-программистский класс» — каркас v0.1 (S-01)
      </p>

      <div className="panel">
        <h2>Состояние инфраструктуры</h2>
        <div className="health-card">
          <span
            className={health ? `health-dot ${allOk ? 'ok' : 'down'}` : 'health-dot down'}
            aria-hidden="true"
          />
          <span className="health-label">
            {health
              ? allOk
                ? 'API/БД/Redis — ок'
                : `Деградация: ${health.db ? 'db ok' : 'db down'}, ${health.redis ? 'redis ok' : 'redis down'}`
              : `Healthz недоступен: ${error}`}
          </span>
          <button className="retry-button" type="button" onClick={refresh}>
            Обновить
          </button>
        </div>
        {health && <p className="health-detail">Посредник: GET /api/v1/healthz через proxy Vite</p>}
      </div>

      <div className="panel">
        <h2>Домены (роуты-заглушки)</h2>
        <p>
          python_teacher · chess_lab · bot_lab · cognitive_skills — каркасы страниц уже
          есть в навигации; функциональность подключается по спринтам (TODO V0.1, этапы
          E-01…E-10 — см. Design §17).
        </p>
        <p className="link-hint">
          Контракты API — <code>docs/SPEC.md</code>, процесс — <code>docs/RULES.md</code>.
        </p>
      </div>
    </section>
  );
}
