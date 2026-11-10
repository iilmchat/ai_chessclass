"""S-92: optional Sentry error-tracking.

DSN берётся только из env (`SENTRY_DSN`); пусто → Sentry не инициализируется.
PII не отправляем: `send_default_pii=False`, тела запросов отключены. DSN не
логируется. Ошибка инициализации не роняет приложение/воркер.
"""

import logging
from typing import Any

from core.config import settings

logger = logging.getLogger(__name__)
_initialized = False


def init_sentry(service_name: str) -> bool:
    """Инициализировать Sentry один раз; вернуть True, если включён."""
    global _initialized
    if _initialized or not settings.sentry_dsn.strip():
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration

        integrations: list[Any] = [
            StarletteIntegration(),
            FastApiIntegration(),
        ]
        try:
            from sentry_sdk.integrations.arq import ArqIntegration

            integrations.append(ArqIntegration())
        except ImportError:  # pragma: no cover — зависит от версии SDK
            pass
        sentry_sdk.init(
            dsn=settings.sentry_dsn.strip(),
            environment=settings.sentry_environment or settings.app_env,
            release=f"{settings.app_name}@{service_name}",
            traces_sample_rate=settings.sentry_traces_sample_rate,
            # S-92: PII/тела/заголовки/query не отправляем (Sentry >=2.74).
            data_collection={
                "user_info": False,
                "cookies": {"mode": "off"},
                "http_headers": {"request": {"mode": "off"}},
                "http_bodies": [],
                "url_query_params": {"mode": "off"},
                "graphql": {"document": False, "variables": False},
                "gen_ai": {"inputs": False, "outputs": False},
                "database_query_data": False,
                "queues": False,
                "stack_frame_variables": False,
                "frame_context_lines": 0,
            },
            integrations=integrations,
        )
        _initialized = True
        logger.info(
            "sentry: enabled service=%s env=%s",
            service_name,
            settings.sentry_environment or settings.app_env,
        )
        return True
    except Exception:  # noqa: BLE001 — телеметрия не должна ронять старт
        logger.warning("sentry: init failed — работаем без error-tracking")
        return False


def reset_error_tracking() -> None:
    """Для тестов: сбросить флаг инициализации и закрыть клиент."""
    global _initialized
    _initialized = False
    try:
        import sentry_sdk

        sentry_sdk.init(dsn="")
    except Exception:  # noqa: BLE001
        pass
