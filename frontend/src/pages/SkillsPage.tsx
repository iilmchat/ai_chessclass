import { useCallback, useEffect, useState } from 'react';
import { ApiError, apiFetch, getToken, logout } from '../shared/api';
import { LoginGate } from '../shared/LoginGate';

interface SkillScore {
  slug: string;
  titleRu: string;
  domain: string;
  score: number;
  week: string | null;
}

interface Recommendation {
  fromTitle: string;
  toTitle: string;
  hint: string;
}

interface Snapshot {
  userId: string;
  skills: SkillScore[];
  recommendations: Recommendation[];
}

/** Spider-график (SVG): 11 навыков, срез 0..100. */
function SpiderChart({ skills }: { skills: SkillScore[] }) {
  const size = 320;
  const center = size / 2;
  const radius = 120;
  const n = Math.max(skills.length, 3);
  const point = (i: number, r: number) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2;
    return [center + r * Math.cos(angle), center + r * Math.sin(angle)];
  };
  const polygon = skills
    .map((s, i) => point(i, (Math.max(0, Math.min(100, s.score)) / 100) * radius).map((v) => v.toFixed(1)).join(','))
    .map((xy) => xy)
    .map((coords, i) => (i === 0 ? `M${coords}` : `L${coords}`))
    .join(' ') + ' Z';

  return (
    <svg width={size} height={size} role="img" aria-label="Spider-график навыков">
      {[0.25, 0.5, 0.75, 1].map((frac) => (
        <polygon
          key={frac}
          points={
            Array.from({ length: n }, (_, i) =>
              point(i, radius * frac)
                .map((v) => v.toFixed(1))
                .join(',')
            )
              .map((xy, i) => (i === 0 ? `M${xy}` : `L${xy}`))
              .join(' ') + ' Z'
          }
          fill="none"
          stroke="var(--line)"
          strokeWidth="1"
        />
      ))}
      {skills.map((s, i) => {
        const [x, y] = point(i, radius + 16);
        return (
          <text
            key={s.slug}
            x={x}
            y={y}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="9"
            fill="var(--muted)"
          >
            {s.titleRu.length > 14 ? `${s.titleRu.slice(0, 13)}…` : s.titleRu}
          </text>
        );
      })}
      <path d={polygon} fill="rgba(47,111,79,0.25)" stroke="var(--accent)" strokeWidth="2" />
      {skills.map((s, i) => {
        const [x, y] = point(i, (Math.max(0, Math.min(100, s.score)) / 100) * radius);
        return <circle key={s.slug} cx={x} cy={y} r="3" fill="var(--accent)" />;
      })}
    </svg>
  );
}

/** S-16: дашборд навыков — spider + тренд + рекомендации по skill_links. */
export function SkillsPage() {
  const [authed, setAuthed] = useState<boolean>(Boolean(getToken()));
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    apiFetch<Snapshot>('/skills/me')
      .then(setSnapshot)
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Ошибка загрузки'));
  }, []);

  useEffect(() => {
    if (authed) {
      load();
    }
  }, [authed, load]);

  if (!authed) {
    return (
      <section>
        <h1 className="page-title">Навыки (cognitive_skills)</h1>
        <p className="page-subtitle">Дашборд доступен после входа</p>
        <LoginGate hint="Demo: student1@chessclass.dev / dev-student-2026" onReady={() => setAuthed(true)} />
      </section>
    );
  }

  return (
    <section>
      <h1 className="page-title">Навыки (cognitive_skills)</h1>
      <p className="page-subtitle">
        Недельные EMA по 11 навыкам (S-16)
        <button
          className="retry-button logout"
          type="button"
          onClick={() => {
            logout();
            setAuthed(false);
            setSnapshot(null);
          }}
        >
          Выйти
        </button>
      </p>
      {error && <p className="verdict failed-note">{error}</p>}
      {snapshot && (
        <>
          <div className="panel skills-grid">
            <SpiderChart skills={snapshot.skills} />
            <div>
              <h2>Срез навыков</h2>
              <ul className="facts-list">
                {snapshot.skills.map((s) => (
                  <li key={s.slug}>
                    {s.titleRu}: <strong>{s.score}</strong> ({s.domain})
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {snapshot.recommendations.length > 0 && (
            <div className="panel">
              <h2>Рекомендации (skill_links)</h2>
              <ul className="facts-list">
                {snapshot.recommendations.map((r) => (
                  <li key={r.fromTitle + r.toTitle}>{r.hint}</li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
