"""Правила уровней ассистента (порт levels.py + §5.5 Comment policy).

Тон/объём: novice — короче, проще, больше конкретики; intermediate —
объяснение причин; advanced — терминология, сложность, альтернативы.
"""

from dataclasses import dataclass

from core.levels import Level


@dataclass(frozen=True, slots=True)
class LevelRules:
    level: Level
    title: str
    rules: str              # блок «Правила уровня» в системном промпте
    gives_ready_code: bool  # полное решение разрешено?


LEVEL_RULES: dict[Level, LevelRules] = {
    Level.NOVICE: LevelRules(
        level=Level.NOVICE,
        title="Начинающий",
        gives_ready_code=False,
        rules=(
            "Короче, проще, больше конкретики. Готовое решение не давать:\n"
            "— указывай, где ошибка (строка, оператор), но не исправляй её сам;\n"
            "— задавай наводящие вопросы («что произойдёт, если…», «как ты думал,\n"
            "  когда отвечал…»);\n"
            "— подсказывай синтаксис на отвлечённом примере, а не на решении;\n"
            "— план действий: шаги (псевдокод), а не код;\n"
            "— 1–2 коротких абзаца + следующий конкретный шаг."
        ),
    ),
    Level.INTERMEDIATE: LevelRules(
        level=Level.INTERMEDIATE,
        title="Средний",
        gives_ready_code=False,
        rules=(
            "Объясняй причины, а не только факты. Правильный синтаксис —\n"
            "на коротких примерах. Готовое решение целиком не давать:\n"
            "— разбор ошибки: почему возникла, как её увидеть самому;\n"
            "— фрагменты кода допустимы, целое решение — нет;\n"
            "— добавляй мини-упражнение для закрепления."
        ),
    ),
    Level.ADVANCED: LevelRules(
        level=Level.ADVANCED,
        title="Продвинутый",
        gives_ready_code=True,
        rules=(
            "Терминология, оценка сложности, альтернативные решения,\n"
            "рекомендации по стилю. Полное решение с комментариями допустимо.\n"
            "Если есть более эффективный подход — покажи разницу (время/память)."
        ),
    ),
}


def get_level_rules(level: Level) -> LevelRules:
    return LEVEL_RULES[level]
