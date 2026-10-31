import { StubPage } from '../shared/StubPage';

export function PythonPage() {
  return (
    <StubPage
      title="Python-курс (python_teacher)"
      subtitle="Песочница, уроки, уровни novice / intermediate / advanced"
      notes={
        <p className="link-hint">
          Контент: Design §6 (python_teacher), перенос — §20.1; API-контракты появятся
          в <code>docs/SPEC.md</code> по мере спринтов.
        </p>
      }
    />
  );
}
