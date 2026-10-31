"""Pydantic-модели результатов движка (порт models.py из annotator).

Соглашения:

* `score_cp` — сантипешки с точки зрения стороны, которая делает ход;
* мат кодируется в сантипешках `±(10000 − 100·N)` (мат в 1 → 9900).
"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = ["MATE_CP_BASE", "EngineLine"]

#: База для перевода мата в сантипешки (мат в 1 → 9900, в 5 → 9500).
MATE_CP_BASE: int = 10_000

_FROZEN = ConfigDict(frozen=True, extra="forbid")

_UCI_MOVE_PATTERN = r"^[a-h][1-8][a-h][1-8][qrbn]?$"


class EngineLine(BaseModel):
    """Одна линия MultiPV из ответа Stockfish."""

    model_config = _FROZEN

    multipv: int = Field(ge=1, description="Ранг линии в MultiPV (1 — лучшая)")
    depth: int = Field(ge=0, description="Глубина, на которой получена линия")
    score_cp: int | None = Field(default=None, description="Оценка в сантипешках")
    mate: int | None = Field(default=None, description="Мат в N; знак — за кого")
    move_uci: str = Field(pattern=_UCI_MOVE_PATTERN, description="Первый ход линии")
    pv: list[str] = Field(default_factory=list, description="PV в UCI")

    @model_validator(mode="after")
    def _exactly_one_score(self) -> "EngineLine":
        """В линии ровно одна форма оценки: cp или мат."""
        if (self.score_cp is None) == (self.mate is None):
            raise ValueError("нужна ровно одна оценка: score_cp или mate")
        return self
