import json
from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения. Контракт переменных — Design.md §15.2."""

    model_config = SettingsConfigDict(
        env_file=[".env", "../.env"],  # локально из backend/ или из корня
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        # S-61: пустая env-переменная = «не задано» (дефолт из кода), иначе
        # `LLM_COST_JUDGE_OUT=` в локальном .env роняет Decimal-поле.
        env_ignore_empty=True,
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
    jwt_private_key: str = ""
    jwt_public_key: str = ""
    jwt_private_key_path: str = ""
    jwt_public_key_path: str = ""
    jwt_kid: str = "v1"
    jwt_legacy_hs256: bool = True
    jwt_ttl: str = "15m"
    refresh_ttl: str = "30d"
    refresh_cookie_name: str = "cc_refresh"
    argon2_time_cost: int = 3
    argon2_memory_cost: int = 65536  # 64 MiB
    argon2_parallelism: int = 2
    # ссылки из писем; dev — консольный SMTP-бэкенд (Design §13.1)
    web_base_url: str = "http://localhost:3200"
    # S-58: CORS allowlist; env CORS_ORIGINS — список через запятую или JSON.
    # NoDecode: pydantic-settings иначе требует JSON для list-поля из env.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3200",
        "http://web:3200",
        "http://localhost:3201",
    ]
    # S-61: egress allowlist (`ALLOWED_EGRESS_HOSTS`, comma/JSON) — записи
    # вида `host` или `*.host`; базовые URL провайдеров разрешены сами;
    # loopback разрешён всегда. См. core/egress.py.
    allowed_egress_hosts: Annotated[list[str], NoDecode] = []

    # --- rag (E-05)
    embedding_dim: int = 768

    # --- llm gateway (S-04+); слаги моделей — ожидаемые имена (R-01),
    # сверяются с провайдером на бутстрапе; несоответствие → warning + env
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_l1: str = "minimax/minimax-m3.1-flash"
    llm_model_l2: str = "deepseek/deepseek-v4.1-flash"
    llm_model_l3: str = "reflection/beam-1.0-501b-a23b"
    llm_model_l3_alt: str = "anthropic/claude-sonnet-5.5"
    # RouterAI Decider — decisions-API, не OpenAI chat; judge-route вызывается
    # через chat-completions, поэтому S-31 использует chat-совместимый Gemini.
    llm_model_judge: str = "google/gemini-3.1-flash-lite"
    llm_timeout_s: float = 40.0  # §8.4: максимум на клиентский запрос
    llm_retry_delay_s: float = 2.0  # §8.4: 1 retry через 2 с
    llm_local_fallback: bool = False
    llm_local_base_url: str = "http://localhost:1234/v1"
    # S-78: отдельный ключ LM Studio (Require Auth); облачный ключ не переиспользуем
    llm_local_api_key: str = ""
    llm_cost_currency: str = "RUB"
    # цены ₽/1M (Numeric(12,4)); взяты из каталога RouterAI на 2026-11-01
    llm_cost_l1_in: Decimal = Decimal("5.2362")
    llm_cost_l1_out: Decimal = Decimal("20.9449")
    llm_cost_l2_in: Decimal = Decimal("5.7598")
    llm_cost_l2_out: Decimal = Decimal("22.1178")
    llm_cost_l3_in: Decimal = Decimal("26.1811")
    llm_cost_l3_out: Decimal = Decimal("104.7245")
    llm_cost_l3_alt_in: Decimal = Decimal("209.4490")
    llm_cost_l3_alt_out: Decimal = Decimal("1047.2449")
    llm_cost_judge_in: Decimal = Decimal("26.1811")
    llm_cost_judge_out: Decimal = Decimal("157.0867")
    budget_free_tokens_day: int = 50_000
    budget_pro_tokens_day: int = 500_000

    # --- engine / sandbox (E-03+, E-04+)
    stockfish_path: str = "/usr/local/bin/stockfish"
    sf_threads: int = 1
    sf_hash_mb: int = 16
    sf_interactive_movetime_ms: int = 1000  # интерактивные вызовы ≤ 1.0 c (S-10)
    max_plies: int = 60
    bot_match_budget_s: int = 120
    bot_permove_timeout_s: float = 1.0
    bot_match_concurrency: int = 2
    # роль процесса: api | worker — Stockfish разрешён только воркеру (§15.3)
    app_role: str = "api"
    # --- песочница (S-07; Design §13.2)
    sandbox_memory_limit_mb: int = 256
    sandbox_max_output_chars: int = 65_536  # 64 КБ на stdout/stderr
    sandbox_timeout_s: float = 5.0  # per-run для заданий; боты — bot_permove_timeout_s
    # --- chess_lab (E-04)
    chess_blunder_cp: int = 300  # Δeval ≥ порога → blunder (§6.2, config не hardcoded)
    chess_pgn_max_bytes: int = 2_000_000  # §13.4
    study_daily_limit: int = 10  # S-43: генераций этюдов на пользователя/сутки
    tournament_max_plies: int = 40  # S-45: партия турнира без LLM
    # --- rag (S-13; §10.6, ADR-006: 768; модель — открытый вопрос §18.2)
    llm_embed_model: str = ""
    rag_chunk_chars: int = 800
    rag_chunk_overlap: int = 100
    rag_top_k: int = 5

    # --- cognitive (S-16; §10.3 EMA)
    skill_ema_alpha: float = 0.3
    # --- anticheat (S-21/S-22; §9.2 пороги — config)
    bot_trivial_min_lines: int = 5
    engine_likeliness_top1_threshold: float = 0.9
    # --- reports (S-25; §20.2 порт: системный TTF с кириллицей)
    reports_font_path: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    reports_dir: str = "/srv/reports"
    # --- voice (S-44; ElevenLabs; без ключа — graceful text fallback)
    voice_api_key: str = ""
    voice_base_url: str = "https://api.elevenlabs.io"
    voice_model_id: str = "eleven_multilingual_v2"
    voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    voice_daily_chars: int = 20_000
    voice_cost_per_1k_rub: float = 0.0
    voice_timeout_s: float = 30.0
    voice_cache_dir: str = "/srv/voice_cache"
    # --- retention / observability (S-46)
    audit_retention_days: int = 365
    llm_calls_retention_days: int = 180
    voice_retention_days: int = 30
    studies_retention_days: int = 90
    failed_jobs_retention_days: int = 90
    retention_archive_dir: str = "/srv/archive"
    retention_batch_size: int = 10_000
    metrics_token: str = ""
    obs_disk_min_free_gb: float = 5.0
    obs_queue_alert_depth: int = 50
    obs_llm_cost_alert_rub: float = 1000.0
    obs_failed_jobs_alert_threshold: int = 10
    obs_tls_cert_path: str = ""
    # --- compliance / parental consent (S-74, ADR-019)
    parental_consent_ttl_days: int = 7
    parental_consent_policy_version: str = "1.0"
    # --- SMTP (S-75): пусто → dev-консольный транспорт
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "noreply@chessclass.dev"
    smtp_starttls: bool = True
    smtp_ssl: bool = False
    smtp_timeout_s: float = 15.0
    # --- email outbox (S-83): очередь писем с retry/backoff
    email_outbox_batch: int = 50
    email_outbox_max_attempts: int = 8
    #: S-86: sent/failed старше N дней архивируются (gzip) и удаляются
    email_outbox_retention_days: int = 30
    # --- tracing (S-73, ADR-017)
    otel_enabled: bool = False
    otel_service_name: str = "chessclass-api"
    otel_exporter_otlp_endpoint: str = ""
    # --- LMS LRS (S-49)
    lrs_enabled: bool = False
    lrs_endpoint: str = ""
    lrs_key: str = ""
    lrs_secret: str = ""
    lrs_timeout_s: float = 15.0
    lms_sync_batch: int = 50
    # --- LMS LRS OAuth2 (S-67): client_credentials поверх Basic-хвоста.
    # Пустой client_id → Basic Auth fallback (S-49, как было).
    lrs_oauth_token_url: str = ""
    lrs_oauth_client_id: str = ""
    lrs_oauth_client_secret: str = ""
    lrs_oauth_scope: str = ""
    # --- Telegram (S-50)
    telegram_bot_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    telegram_link_ttl_s: int = 600
    telegram_batch: int = 50
    # S-68: webhook (секрет из X-Telegram-Bot-Api-Secret-Token; пусто →
    # webhook отключён) и long-poll fallback (worker-cron).
    telegram_webhook_secret: str = ""
    telegram_poll_enabled: bool = False
    telegram_poll_limit: int = 10
    # --- spaced repetition (S-52)
    review_daily_limit: int = 20

    # --- seeds (S-03)
    seed_admin_email: str = "admin@chessclass.dev"
    seed_admin_password: str = "dev-admin-2026"
    seed_teacher_password: str = "dev-teacher-2026"
    seed_auditor_password: str = "dev-auditor-2026"
    seed_student_password: str = "dev-student-2026"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        """S-58: CORS_ORIGINS — JSON-массив или список через запятую."""
        return _parse_string_list(value)

    @field_validator("allowed_egress_hosts", mode="before")
    @classmethod
    def _parse_allowed_egress_hosts(cls, value: object) -> object:
        """S-61: ALLOWED_EGRESS_HOSTS — JSON-массив или список через запятую."""
        return _parse_string_list(value)

def _parse_string_list(value: object) -> object:
    """Comma/JSON — общий формат строковых списков env (CORS, egress)."""
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            return json.loads(raw)
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return list(value)
    return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
