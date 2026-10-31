import { StubPage } from '../shared/StubPage';

export function BotsPage() {
  return (
    <StubPage
      title="Конструктор ботов (bot_lab)"
      subtitle="Свой бот → лестница Elo (random→greedy→minimax2→Stockfish) → надёжность"
      notes={
        <p className="link-hint">
          Контент: Design §8 (bot_lab, ADR-007/008); матчи без LLM — ADR-012; этапы
          E-05…E-07 в TODO V0.1.
        </p>
      }
    />
  );
}
