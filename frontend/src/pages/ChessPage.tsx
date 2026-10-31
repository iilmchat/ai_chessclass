import { StubPage } from '../shared/StubPage';

export function ChessPage() {
  return (
    <StubPage
      title="Шахматная лаборатория (chess_lab)"
      subtitle="Разбор партий, домашние задания, аннотации"
      notes={
        <p className="link-hint">
          Контент: Design §7 (chess_lab), перенос — §20.2; разбор партий — этапы
          E-03…E-04 в TODO V0.1.
        </p>
      }
    />
  );
}
