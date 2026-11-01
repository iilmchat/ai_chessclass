"""SafePosition — read-only прокси над chess.Board для ботов (Design bot_lab).

Бот видит только безопасные методы; прямого доступа к доске/python-chess нет
(RestrictedPython-гварды не пропускают dunders). Материал — пешечные единицы.
"""

import chess


class SafePosition:
    """Read-only фасад позиции. Все методы возвращают простые типы."""

    def __init__(self, board: chess.Board) -> None:
        self._board = board

    @property
    def fen(self) -> str:
        return self._board.fen()

    @property
    def turn(self) -> str:
        return "white" if self._board.turn == chess.WHITE else "black"

    @property
    def legal_moves(self) -> list[str]:
        return [m.uci() for m in self._board.legal_moves]

    @property
    def is_check(self) -> bool:
        return self._board.is_check()

    def piece_at(self, square: str) -> dict | None:
        """Фигура на поле (например 'e4'): {'type': 'p', 'color': 'white'}."""
        square_obj = chess.parse_square(square)
        piece = self._board.piece_at(square_obj)
        if piece is None:
            return None
        return {
            "type": piece.symbol().lower(),
            "color": "white" if piece.color == chess.WHITE else "black",
        }

    def is_attacked(self, square: str) -> bool:
        """Атаковано ли поле кем-либо из соперника."""
        square_obj = chess.parse_square(square)
        attacker = not self._board.turn
        return self._board.is_attacked_by(attacker, square_obj)

    def material(self, color: str) -> int:
        """Материал стороны (пешечные единицы: п=1, к/с=3, л=5, ф=9)."""
        values = {"p": 1, "n": 3, "b": 3, "r": 5, "q": 9}
        want_white = color == "white"
        total = 0
        for piece in self._board.piece_map().values():
            if piece.color == chess.WHITE == want_white:
                total += values.get(piece.symbol().lower(), 0)
        return total

    def king_square(self, color: str) -> str | None:
        """Поле короля стороны ('e1'-стиль) или None."""
        want_white = color == "white"
        king = self._board.king(chess.WHITE if want_white else chess.BLACK)
        return chess.square_name(king) if king is not None else None
