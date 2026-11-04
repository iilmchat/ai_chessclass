# Accessibility-аудит (S-55)

**Дата:** 2026-11-03 · frontend (React + Vite), ручной + code review.

## 1. Чеклист

| # Критерий | Статус | Комментарий |
|---|---|---|
| Клавиатурная навигация | ✅ | nav/кнопки/поля — нативные; skip-link добавлен |
| Skip-link к контенту | ✅ | `a.skip-link` → `#main` |
| Видимый focus | ✅ | `:focus-visible` 3px accent + offset |
| Заголовки страниц | ✅ | `h1.page-title` на страницах |
| ARIA для навигации | ✅ | `nav aria-label="Основная навигация"` |
| Формы/поля | ✅ | `aria-label` у полей и select (S-66: добавлен на ChessPage) |
| Ошибки/уведомления | ✅ S-66 | `role="status"` + `aria-live` на error/notice в 6 страницах |
| Контраст текста | ✅ S-66 | `.achievement.locked` убрана opacity (мутант #9fa3ac→2.4), мутед на panel 4.63:1; axe-гейт 0 critical/serious |
| Мобильный UX | ✅ S-66 | топбар column, nav wrap, grids → 1 колонка, submit-стек при ≤720px |
| Изображения/иконки | ✅ | декоративные `aria-hidden`; file-input получил aria-label |
| prefers-reduced-motion | ✅ | анимаций нет; факт — CSS не зависит от motion |
| Масштаб 200% | ✅ S-66 | `overflow-wrap: anywhere` для facts/verdict/label, 320px-безопасно |
| Модальные окна | — | модалок в SPA нет (об окна выводят panels); focus-trap неприменим |

## 2. Автоматический гейт (S-66)

- `a11y-axe.spec.ts`: **гость** — 6 публичных маршрутов + **admin** — все 14
  маршрутов (wcag2a+2aa, критические/serious → 0).
- Исключено из сканера: контейнеры досок react-chessboard v5 (`.board-wrap`,
  `.pvp-board-wrap`) — third-party library gap (клетки = role/button без
  имён); апгрейд библиотеки — backlog v0.5.
- Прогон: **6 passed (19.5 с)** изолированный `scripts/e2e-targeted.ps1`;
  полный набор — 14 Playwright-сценариев.

## 3. Что исправлено (S-66)

- `role="status"` + `aria-live` на error/notice (Profile/Review/Observability/
  Pvp/Complaints/RagEditor).
- `aria-label="Уровень объяснения"` на select ChessPage (axe select-name critical).
- `aria-label="Файл для импорта"` на file-input (axe label critical).
- Контраст: `.achievement.locked` — без opacity, текст `--muted` на
  `--panel` (4.63:1 ≥ 4.5:1), кнопки/иконка — `--muted`/`--accent`.
- Мобильная адаптация ≤720px: topbar column, nav wrap, 1-колоночные
  grids, submit/toolbar стек; `overflow-wrap: anywhere` на текстовых
  блоках (320px/200% не рвут макет).

## 4. Известные ограничения

- Модалок (focus-trap) в v0.4 нет.
- react-chessboard v5: клетки не получают имена — третьесторонний
  backlog (upgrade contributing fix).
- Контраст dark-темы — по тем же переменным (color-scheme dark) —
  вручную не проверялся глубоко; axe-гейт гоняет light (Chrome default).
