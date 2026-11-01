"""Очереди матчей ботов (S-37): per-queue лимиты и fairness.

Каждый тип соперника имеет отдельную arq-очередь и отдельный worker:
random — 2 слота, greedy/minimax/SF — по 1. Суммарно 5 матчей одновременно;
очереди не блокируют друг друга (нет глобального FIFO-голодания).
"""

MATCH_QUEUE_PREFIX = "arq:matches"

#: kind -> (queue_name, max_jobs)
MATCH_QUEUES: dict[str, tuple[str, int]] = {
    "random": (f"{MATCH_QUEUE_PREFIX}:random", 2),
    "greedy": (f"{MATCH_QUEUE_PREFIX}:greedy", 1),
    "minimax": (f"{MATCH_QUEUE_PREFIX}:minimax", 1),
    "sf": (f"{MATCH_QUEUE_PREFIX}:sf", 1),
}

MATCH_QUEUE_LIMITS: dict[str, int] = {
    kind: limit for kind, (_queue, limit) in MATCH_QUEUES.items()
}

MAX_ACTIVE_MATCHES = 5
ACTIVE_MATCH_TTL_S = 10 * 60  # pending-матч старше 10 мин не считаем активным


def queue_kind(opponent: str) -> str:
    """Вернуть категорию очереди для соперника."""
    if opponent.startswith("stockfish-"):
        return "sf"
    if opponent in ("random", "greedy", "minimax2"):
        return "minimax" if opponent == "minimax2" else opponent
    raise ValueError(f"unknown opponent {opponent!r}")


def queue_for_opponent(opponent: str) -> str:
    return MATCH_QUEUES[queue_kind(opponent)][0]


def active_key(kind: str) -> str:
    return f"matchq:active:{kind}"


def refused_key(kind: str) -> str:
    return f"matchq:refused:{kind}"
