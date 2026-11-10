"""S-92: Sentry включается только при DSN и не ломает старт."""

from core.config import settings
from core.error_tracking import init_sentry, reset_error_tracking


def test_sentry_disabled_without_dsn(monkeypatch):
    monkeypatch.setattr(settings, "sentry_dsn", "")
    reset_error_tracking()
    try:
        assert init_sentry("test-api") is False
    finally:
        reset_error_tracking()


def test_sentry_fake_dsn_does_not_break_start(monkeypatch):
    # Фиктивный DSN: SDK не должен падать и не делает сетевой запрос.
    monkeypatch.setattr(
        settings, "sentry_dsn", "https://public@example.invalid/1"
    )
    monkeypatch.setattr(settings, "sentry_environment", "test")
    reset_error_tracking()
    try:
        assert init_sentry("test-api") is True
    finally:
        reset_error_tracking()
