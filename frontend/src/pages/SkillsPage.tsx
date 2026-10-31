import { StubPage } from '../shared/StubPage';

export function SkillsPage() {
  return (
    <StubPage
      title="Навыки (cognitive_skills)"
      subtitle="11 когнитивных навыков, недельные EMA-скоры, PDF-отчёты родителям"
      notes={
        <p className="link-hint">
          Контент: Design §9 (skill_events → user_skill_scores, ADR-005/006); этапы
          E-08…E-09 в TODO V0.1.
        </p>
      }
    />
  );
}
