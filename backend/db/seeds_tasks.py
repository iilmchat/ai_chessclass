"""Seed заданий (S-08): 16 заданий по темам Design §5.2, уровни §4.2.

Идемпотентно по slug. Тесты — assert-стиль (однострочные); темы —
slug навыков реестра (§10.1): variables→conditions→loops→…  Ступени
подсказок (concept→strategy) — задел лестницы S-09.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.python_teacher.models import AssignmentLevel, HintKind, PyAssignment, PyHint

logger = logging.getLogger(__name__)

#: (slug, title, level, topic, statement, starter_code, tests, hints)
ASSIGNMENTS: tuple[dict, ...] = (
    {
        "slug": "greet-function",
        "title": "Приветствие (переменные)",
        "level": AssignmentLevel.NOVICE,
        "topic": "data_structures",
        "statement": (
            "Напиши функцию `greet(name)`, которая возвращает строку\n"
            "«Привет, <name>!». Пример: `greet(\"Аня\")` → `Привет, Аня!`"
        ),
        "starter_code": "def greet(name):\n    # твой код\n    pass\n",
        "tests": [
            'assert greet("Аня") == "Привет, Аня!"',
            'assert greet("Petr") == "Привет, Petr!"',
            'assert greet("") == "Привет, !"',
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "f-строка: f\"Привет, {name}!\""},
            {"idx": 1, "kind": HintKind.STRATEGY.value, "content": "Верни строку через return, print не нужен."},
        ],
    },
    {
        "slug": "max-of-two",
        "title": "Максимум из двух (переменные)",
        "level": AssignmentLevel.NOVICE,
        "topic": "conditions",
        "statement": "Функция `max2(a, b)` возвращает большее из двух чисел.",
        "starter_code": "def max2(a, b):\n    pass\n",
        "tests": [
            "assert max2(3, 7) == 7",
            "assert max2(-1, -5) == -1",
            "assert max2(4, 4) == 4",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Сравни a и b через if."},
        ],
    },
    {
        "slug": "even-check",
        "title": "Чётное число (условия)",
        "level": AssignmentLevel.NOVICE,
        "topic": "conditions",
        "statement": "Функция `is_even(n)` возвращает True для чётных чисел, иначе False.",
        "starter_code": "def is_even(n):\n    pass\n",
        "tests": [
            "assert is_even(4) is True",
            "assert is_even(7) is False",
            "assert is_even(0) is True",
            "assert is_even(-2) is True",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Остаток от деления: n % 2."},
        ],
    },
    {
        "slug": "sum-to-n",
        "title": "Сумма от 1 до N (циклы)",
        "level": AssignmentLevel.NOVICE,
        "topic": "loops_basic",
        "statement": "Функция `sum_to(n)` возвращает сумму чисел от 1 до n включительно.",
        "starter_code": "def sum_to(n):\n    pass\n",
        "tests": [
            "assert sum_to(1) == 1",
            "assert sum_to(5) == 15",
            "assert sum_to(100) == 5050",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Цикл for i in range(1, n + 1) и аккумулятор."},
        ],
    },
    {
        "slug": "count-vowels",
        "title": "Гласные в строке (циклы)",
        "level": AssignmentLevel.INTERMEDIATE,
        "topic": "loops_basic",
        "statement": "Функция `count_vowels(text)` считает русские гласные (аеёиоуыэюя) в строке.",
        "starter_code": "def count_vowels(text):\n    pass\n",
        "tests": [
            'assert count_vowels("привет") == 2',
            'assert count_vowels("ЩУК") == 1',
            'assert count_vowels("вжух") == 0',
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Строку приводи к нижнему регистру, гласные — набором в строке."},
        ],
    },
    {
        "slug": "list-max-index",
        "title": "Индекс максимума (списки)",
        "level": AssignmentLevel.INTERMEDIATE,
        "topic": "data_structures",
        "statement": "Функция `max_index(nums)` возвращает индекс первого максимального элемента.",
        "starter_code": "def max_index(nums):\n    pass\n",
        "tests": [
            "assert max_index([1, 5, 3]) == 1",
            "assert max_index([7, 7, 1]) == 0",
            "assert max_index([-3]) == 0",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "max() и .index() или один цикл с аккумулятором."},
        ],
    },
    {
        "slug": "slice-reverse",
        "title": "Реверс строки (срезы)",
        "level": AssignmentLevel.INTERMEDIATE,
        "topic": "data_structures",
        "statement": "Функция `reverse(text)` возвращает перевёрнутую строку.",
        "starter_code": "def reverse(text):\n    pass\n",
        "tests": [
            'assert reverse("школа") == "алокш"',
            'assert reverse("") == ""',
            'assert reverse("a") == "a"',
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Срез с шагом -1: text[::-1]."},
        ],
    },
    {
        "slug": "fizzbuzz",
        "title": "Физкульт-крики (FIZZBUZZ, вложенные условия)",
        "level": AssignmentLevel.INTERMEDIATE,
        "topic": "conditions",
        "statement": (
            "Функция `fizzbuzz(n)` возвращает список строк от 1 до n:\n"
            "кратные 3 → \"Fizz\", кратные 5 → \"Buzz\", кратные 15 → \"FizzBuzz\", остальное — число строкой."
        ),
        "starter_code": "def fizzbuzz(n):\n    pass\n",
        "tests": [
            'assert fizzbuzz(5) == ["1", "2", "Fizz", "4", "Buzz"]',
            'assert fizzbuzz(15)[-1] == "FizzBuzz"',
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Сначала проверяй делимость на 15, потом на 3 и 5."},
        ],
    },
    {
        "slug": "multiplication-table",
        "title": "Таблица умножения (вложенные циклы)",
        "level": AssignmentLevel.INTERMEDIATE,
        "topic": "loops_nested",
        "statement": "Функция `mul_table(n)` возвращает список списков: строка i — произведения i×1…i×n.",
        "starter_code": "def mul_table(n):\n    pass\n",
        "tests": [
            "assert mul_table(2) == [[1, 2], [2, 4]]",
            "assert mul_table(3)[2] == [3, 6, 9]",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Цикл в цикле: внешний по строкам, внутренний собирает список."},
        ],
    },
    {
        "slug": "star-pyramid",
        "title": "Пирамида из звёзд (вложенные циклы)",
        "level": AssignmentLevel.INTERMEDIATE,
        "topic": "loops_nested",
        "statement": "Функция `pyramid(rows)` возвращает список строк: 1 звезда, 3, 5… (нечётное число звёзд).",
        "starter_code": "def pyramid(rows):\n    pass\n",
        "tests": [
            'assert pyramid(2) == ["*", "***"]',
            'assert pyramid(3)[2] == "*****"',
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "В строке i — 2*i + 1 звёзд."},
        ],
    },
    {
        "slug": "digits-sum",
        "title": "Сумма цифр числа (алгоритмы)",
        "level": AssignmentLevel.INTERMEDIATE,
        "topic": "loops_basic",
        "statement": "Функция `digits_sum(n)` возвращает сумму цифр целого числа (учитывай знак).",
        "starter_code": "def digits_sum(n):\n    pass\n",
        "tests": [
            "assert digits_sum(123) == 6",
            "assert digits_sum(-45) == 9",
            "assert digits_sum(0) == 0",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "abs(n), затем n % 10 и n // 10 в цикле."},
        ],
    },
    {
        "slug": "is-prime",
        "title": "Простое число (алгоритмы)",
        "level": AssignmentLevel.ADVANCED,
        "topic": "complexity",
        "statement": "Функция `is_prime(n)` проверяет простоту числа (n ≥ 0). 1 — не простое.",
        "starter_code": "def is_prime(n):\n    pass\n",
        "tests": [
            "assert is_prime(2) is True",
            "assert is_prime(9) is False",
            "assert is_prime(97) is True",
            "assert is_prime(1) is False",
            "assert is_prime(0) is False",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Проверяй делители до корня из n."},
            {"idx": 1, "kind": HintKind.STRATEGY.value, "content": "Шаг делителей — 2 (после проверки 2)."},
        ],
    },
    {
        "slug": "unique-words",
        "title": "Уникальные слова (множества/списки)",
        "level": AssignmentLevel.ADVANCED,
        "topic": "data_structures",
        "statement": "Функция `unique_words(text)` возвращает отсортированный список уникальных слов (нижний регистр, без пунктуации . , ! ?).",
        "starter_code": "def unique_words(text):\n    pass\n",
        "tests": [
            'assert unique_words("Аня и Петр. Аня!") == ["аня", "и", "петр"]',
            'assert unique_words("") == []',
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "strip пунктуации у слов, set() для уникальности, sorted()."},
        ],
    },
    {
        "slug": "word-frequencies",
        "title": "Частоты слов (словари)",
        "level": AssignmentLevel.ADVANCED,
        "topic": "data_structures",
        "statement": "Функция `word_counts(text)` возвращает словарь «слово → число вхождений» (нижний регистр).",
        "starter_code": "def word_counts(text):\n    pass\n",
        "tests": [
            'assert word_counts("а ба а") == {"а": 2, "ба": 1}',
            'assert word_counts("") == {}',
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "split() + dict с get(key, 0)."},
        ],
    },
    {
        "slug": "fibonacci-n",
        "title": "Фибоначчи (функции)",
        "level": AssignmentLevel.ADVANCED,
        "topic": "functions",
        "statement": "Функция `fib(n)` возвращает n-е число Фибоначчи (fib(0)=0, fib(1)=1).",
        "starter_code": "def fib(n):\n    pass\n",
        "tests": [
            "assert fib(0) == 0",
            "assert fib(1) == 1",
            "assert fib(10) == 55",
            "assert fib(20) == 6765",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Два аккумулятора a, b в цикле — без рекурсии."},
        ],
    },
    {
        "slug": "binary-search",
        "title": "Бинарный поиск (алгоритмы)",
        "level": AssignmentLevel.ADVANCED,
        "topic": "complexity",
        "statement": "Функция `binary_search(sorted_list, target)` возвращает индекс элемента или -1.",
        "starter_code": "def binary_search(sorted_list, target):\n    pass\n",
        "tests": [
            "assert binary_search([1, 3, 5, 7], 5) == 2",
            "assert binary_search([1, 3, 5], 4) == -1",
            "assert binary_search([], 1) == -1",
        ],
        "hints": [
            {"idx": 0, "kind": HintKind.CONCEPT.value, "content": "Границы lo/hi, середина, сравнение и сужение."},
        ],
    },
)


async def seed_tasks(session: AsyncSession) -> dict[str, int]:
    existing = set(
        (await session.execute(select(PyAssignment.slug))).scalars()
    )
    created = 0
    hints_created = 0
    for item in ASSIGNMENTS:
        if item["slug"] in existing:
            continue
        assignment = PyAssignment(
            slug=item["slug"],
            title=item["title"],
            level=item["level"],
            topic=item["topic"],
            statement=item["statement"],
            starter_code=item["starter_code"],
            tests=list(item["tests"]),
        )
        session.add(assignment)
        await session.flush()
        created += 1
        for hint in item.get("hints", ()):
            session.add(
                PyHint(
                    assignment_id=assignment.id,
                    idx=hint["idx"],
                    kind=HintKind(hint["kind"]),
                    content=hint["content"],
                )
            )
            hints_created += 1
    await session.flush()
    return {"assignments": created, "hints": hints_created}
