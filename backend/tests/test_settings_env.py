"""S-61 (попутно): контракт env — пустая переменная = «не задано».

`env_ignore_empty=True` в Settings: переменная со значением «пусто»
(например `LLM_COST_JUDGE_OUT=` в локальном .env после cp из примера)
не роняет Decimal-поле — поле получает дефолт из кода.
"""

from decimal import Decimal

from core.config import Settings


def test_empty_decimal_env_falls_back_to_code_default(monkeypatch):
    monkeypatch.setenv("LLM_COST_JUDGE_OUT", "")
    fresh = Settings(_env_file=None)  # type: ignore[call-arg]
    assert fresh.llm_cost_judge_out == Decimal("157.0867")


def test_empty_string_list_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("ALLOWED_EGRESS_HOSTS", "")
    monkeypatch.setenv("CORS_ORIGINS", "")
    fresh = Settings(_env_file=None)  # type: ignore[call-arg]
    assert fresh.allowed_egress_hosts == []  # дефолт allowlist — пустой
    # CORS-дефолт — локальные origin'ы из кода (S-58), не ошибка валидации
    assert fresh.cors_origins == [
        "http://localhost:3200",
        "http://web:3200",
        "http://localhost:3201",
    ]
