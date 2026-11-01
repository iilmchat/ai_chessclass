"""Оппоненты лестницы (Design §7.3): random / greedy / minimax2.

Все — trusted-модули на воркере (python-chess напрямую, без песочницы;
ученический бот играет через песочницу). Единый интерфейс:
`choose_move(board: chess.Board) -> chess.Move`.
"""

import random as random_module
from collections.abc import Callable

import chess


def _random(board: chess.Board) -> chess.Move:
    return random_module.choice(list(board.legal_moves))


def _material(board: chess.Board, color: chess.Color) -> int:
    values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
    total = 0
    for piece in board.piece_map().values():
        if piece.color == color:
            total += values.get(piece.piece_type, 0)
    return total


_CAPTURE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def _greedy(board: chess.Board) -> chess.Move:
    """max по материал-дельте (fallback evaluate): взятие с максимальной ценой."""
    best: chess.Move | None = None
    best_gain = -1
    for move in board.legal_moves:
        gain = 0
        captured = board.piece_type_at(move.to_square)
        if captured is not None:
            gain += _CAPTURE_VALUES.get(captured, 0)
        if board.is_castling(move):
            gain += 1
        if gain > best_gain:
            best_gain = gain
            best = move
    return best if best is not None else _random(board)


def _minimax2(board: chess.Board) -> chess.Move:
    """Negamax глубина 2 + alpha-beta; оценка — материал (со стороны ходящего)."""
    values = {
        chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
        chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0,
    }

    def material_for(color: chess.Color) -> int:
        total = 0
        for piece in board.piece_map().values():
            base = values.get(piece.piece_type, 0)
            total += base if piece.color == color else -base
        return total

    def evaluate() -> int:
        mover = board.turn
        return material_for(mover) - material_for(not mover)

    best: chess.Move | None = None
    best_score = -10_000
    alpha = -10_000
    moves = list(board.legal_moves)
    random_module.shuffle(moves)  # разнообразие среди равных
    for move in moves:
        board.push(move)
        score = -_negamax(board, depth=1, alpha=-10_000, beta=10_000, values=values)
        board.pop()
        if score > best_score:
            best_score = score
            best = move
        alpha = max(alpha, score)
        if alpha >= 10_000:
            break
    return best if best is not None else _random(board)


def _negamax(board: chess.Board, *, depth: int, alpha: int, beta: int, values: dict) -> int:
    if board.is_checkmate():
        return -9_900
    if board.is_stalemate() or board.is_insufficient_material():
        return 0
    if depth == 0:
        mover = board.turn
        return material_for_cached(board, mover, values)
    best = -10_000
    for move in board.legal_moves:
        board.push(move)
        score = -_negamax(board, depth=depth - 1, alpha=-beta, beta=-alpha, values=values)
        board.pop()
        best = max(best, score)
        alpha = max(alpha, score)
        if alpha >= beta:
            break
    return best


def material_for_cached(board: chess.Board, color: chess.Color, values: dict) -> int:
    total = 0
    for piece in board.piece_map().values():
        base = values.get(piece.piece_type, 0)
        total += base if piece.color == color else -base
    return total


OPPONENTS: dict[str, tuple[int, Callable[[chess.Board], chess.Move]]] = {
    "random": (400, _random),
    "greedy": (800, _greedy),
    "minimax2": (1100, _minimax2),
}
