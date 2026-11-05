import { Chess } from 'chess.js';
import type { Square } from 'chess.js';

const PIECE_NAMES: Record<string, string> = {
  p: 'пешка',
  n: 'конь',
  b: 'слон',
  r: 'ладья',
  q: 'ферзь',
  k: 'король',
};

/** S-79: понятная aria-label для клетки react-chessboard v5. */
export function squareAriaLabel(fen: string, square: string): string {
  const game = new Chess(fen);
  const piece = game.get(square as Square);
  if (!piece) return `Пустая клетка ${square}`;
  const color = piece.color === 'w' ? 'Белая' : 'Чёрная';
  return `${color} ${PIECE_NAMES[piece.type] ?? piece.type} на ${square}`;
}

/** Добавить aria-label каждой клетке доски (DOM-патч v5). */
export function applyBoardA11y(root: HTMLElement | null, fen: string): void {
  if (!root) return;
  for (const square of root.querySelectorAll<HTMLElement>('[data-square]')) {
    const name = square.dataset.square;
    if (!name) continue;
    square.setAttribute('aria-label', squareAriaLabel(fen, name));
  }
}
