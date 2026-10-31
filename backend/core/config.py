from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения. Контракт переменных — Design.md §15.2."""

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],  # локально из backend/ или из корня
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app
    app_name: str = "chessclass-api"
    app_env: str = "dev"
    api_port: int = 8020
    log_level: str = "INFO"

    # --- infra
    database_url: str = "postgresql+asyncpg://chess:chess_dev_2026@localhost:5438/chessclass"
    db_pool_size: int = 10
    db_echo: bool = False
    redis_url: str = "redis://localhost:6384/0"

    # --- auth (S-02)
    jwt_secret: str = "dev-secret-change-me-please-0123456789abcdef"
    jwt_algorithm: str = "HS256"
    jwt_ttl: str = "15m"
    refresh_ttl: str = "30d"
    refresh_cookie_name: str = "cc_refresh"
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536  # 64 MiB
    argon2_parallelism: int = 2
    # ссылки из писем; dev — консольный SMTP-бэкенд (Design §13.1)
    web_base_url: str = "http://localhost:3200"

    # --- rag (E-05)
    embedding_dim: int = 768

    # --- llm gateway (S-04+); слаги моделей — ожидаемые имена (R-01),
    # сверяются с провайдером на бутстрапе; несоответствие → warning + env
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_l1: str = "minimax-m3.1"
    llm_model_l2: str = "deepseek-v4.1"
    llm_model_l3: str = "beam-1.0-501b"
    llm_model_l3_alt: str = "claude-sonnet-5.5"
    llm_model_judge: str = "decider-flash-v1.2"
    llm_timeout_s: float = 40.0  # §8.4: максимум на клиентский запрос
    llm_retry_delay_s: float = 2.0  # §8.4: 1 retry через 2 с
    llm_local_fallback: bool = False
    llm_local_base_url: str = "http://localhost:1234/v1"
    llm_cost_currency: str = "RUB"
    # цены ₽/1M (Numeric(12,4)); judge/L3-alt Design не фиксирует — задать env'ом
    llm_cost_l1_in: Decimal = Decimal("7.0")
    llm_cost_l1_out: Decimal = Decimal("25.0")
    llm_cost_l2_in: Decimal = Decimal("26.0")
    llm_cost_l2_out: Decimal = Decimal("100.0")
    llm_cost_l3_in: Decimal = Decimal("26.0")
    llm_cost_l3_out: Decimal = Decimal("104.0")
    llm_cost_l3_alt_in: Decimal | None = None
    llm_cost_l3_alt_out: Decimal | None = None
    llm_cost_judge_in: Decimal | None = None
    llm_cost_judge_out: Decimal | None = None
    budget_free_tokens_day: int = 50_000
    budget_pro_tokens_day: int = 500_000

    # --- engine / sandbox (E-03+, E-07+)
    stockfish_path: str = "/usr/games/stockfish"
    max_plies: int = 60
    bot_match_budget_s: int = 120
    bot_permove_timeout_s: float = 1.0
    bot_match_concurrency: int = 2

    # --- seeds (S-03)
    seed_admin_email: str = "admin@chessclass.dev"
    seed_admin_password: str = "dev-admin-2026"
    seed_student_password: str = "dev-student-2026"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
