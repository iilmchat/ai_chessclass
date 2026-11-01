"""Elo (Design §7.4, ADR-008): старт 1000, K=32, clamp ±40 за матч."""

from decimal import Decimal

ELO_START = Decimal("1000")
K_FACTOR = Decimal("32")
CLAMP = Decimal("40")


def expected_score(elo: Decimal, opponent_elo: Decimal) -> Decimal:
    """Ожидаемый результат (0..1) по классической формуле Эло."""
    diff = opponent_elo - elo
    return Decimal(1) / (Decimal(1) + Decimal(10) ** (diff / Decimal(400)))


def elo_delta(elo: Decimal, opponent_elo: Decimal, result: str) -> Decimal:
    """Изменение Elo за матч: win=1, draw=0.5, loss=0; clamp ±40."""
    actual = {"win": Decimal(1), "draw": Decimal("0.5"), "loss": Decimal(0)}.get(
        result, Decimal(0)
    )
    raw = K_FACTOR * (actual - expected_score(elo, opponent_elo))
    return max(-CLAMP, min(CLAMP, raw)).quantize(Decimal("0.1"))
