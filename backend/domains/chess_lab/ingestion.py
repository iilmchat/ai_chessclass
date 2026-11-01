"""Ingestion: парсинг PGN/FEN (упрощённый порт app/ingestion/parser.py).

Читается первая партия, mainline; ошибки — InvalidPgnError/InvalidFenError
(порт контракта teacher-annotator). ECO/фазы/повторы — за пределами v0.1.
"""

import io

import chess
import chess.pgn

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


class InvalidPgnError(ValueError):
    """PGN не читается / партия пустая."""


class InvalidFenError(ValueError):
    """FEN некорректен или позиция невозможна."""


def parse_fen(fen_string: str) -> chess.Board:
    """Проверить FEN и вернуть доску (порт teacher)."""
    candidate = (fen_string or "").strip()
    if not candidate:
        raise InvalidFenError("FEN пуст")
    try:
        board = chess.Board(candidate)
    except ValueError as exc:
        raise InvalidFenError(f"Некорректный FEN: {exc}") from exc
    if not board.is_valid():
        status = board.status()
        reasons = ", ".join(str(flag.name) for flag in type(status) if flag & status)
        raise InvalidFenError(f"Невозможная позиция в FEN: {reasons}")
    return board


class ParsedMove:
    """Один полуход: SAN, UCI, FEN после хода."""

    __slots__ = ("ply", "san", "uci", "fen")

    def __init__(self, ply: int, san: str, uci: str, fen: str) -> None:
        self.ply = ply
        self.san = san
        self.uci = uci
        self.fen = fen


class ParsedGame:
    """Нормализованная партия (упрощённый порт ParsedGame)."""

    __slots__ = ("white", "black", "initial_fen", "moves")

    def __init__(
        self,
        white: str | None,
        black: str | None,
        initial_fen: str,
        moves: list[ParsedMove],
    ) -> None:
        self.white = white
        self.black = black
        self.initial_fen = initial_fen
        self.moves = moves

    @property
    def ply_count(self) -> int:
        return len(self.moves)


def parse_pgn(pgn_string: str) -> ParsedGame:
    """PGN → партия (первая, mainline). Пустая партия → InvalidPgnError."""
    game = chess.pgn.read_game(io.StringIO(pgn_string or ""))
    if game is None:
        raise InvalidPgnError("PGN не распознан: нет партии")
    if game.errors:
        # python-chess молча останавливается на невалидных токенах — предупреждаем
        first = game.errors[0]
        raise InvalidPgnError(f"PGN содержит ошибки: {first}")

    board = game.board()
    initial_fen = board.fen()
    moves: list[ParsedMove] = []
    for ply, move in enumerate(game.mainline_moves(), start=1):
        san = board.san(move)
        board.push(move)
        moves.append(ParsedMove(ply=ply, san=san, uci=move.uci(), fen=board.fen()))

    if not moves:
        raise InvalidPgnError("В PGN нет ходов")

    headers = game.headers
    return ParsedGame(
        white=headers.get("White") or None,
        black=headers.get("Black") or None,
        initial_fen=initial_fen,
        moves=moves,
    )
