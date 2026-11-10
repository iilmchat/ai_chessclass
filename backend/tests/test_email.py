"""S-75: SMTP-транспорт и dev-консольный fallback."""

import logging

import pytest

from core import email as email_mod
from core.config import settings
from core.email import EmailDeliveryError, send_email


async def test_dev_email_falls_back_to_console(monkeypatch, caplog):
    monkeypatch.setattr(settings, "smtp_host", "")
    with caplog.at_level(logging.INFO, logger="core.email"):
        delivered = await send_email("user@example.com", "Тема", "Текст")
    assert delivered is False
    assert "dev-email" in caplog.text


async def test_smtp_delivery_starttls_and_auth(monkeypatch):
    captured: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            captured.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            captured["ehlo"] = captured.get("ehlo", 0) + 1

        def starttls(self):
            captured["starttls"] = True

        def login(self, user, password):
            captured.update(user=user, password=password)

        def send_message(self, message):
            captured["message"] = message

    monkeypatch.setattr(email_mod.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_user", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_ssl", False)

    delivered = await send_email("parent@example.com", "Согласие", "Ссылка")
    assert delivered is True
    assert captured["host"] == "smtp.test" and captured["starttls"] is True
    assert captured["user"] == "mailer"
    msg = captured["message"]
    assert msg["To"] == "parent@example.com"
    assert msg["Subject"] == "Согласие"


async def test_smtp_ssl_mode_uses_smtp_ssl(monkeypatch):
    captured: dict = {}

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout):
            captured.update(host=host, port=port, timeout=timeout)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            captured["ehlo"] = True

        def login(self, user, password):
            captured.update(user=user, password=password)

        def send_message(self, message):
            captured["message"] = message

    monkeypatch.setattr(email_mod.smtplib, "SMTP_SSL", FakeSMTPSSL)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_port", 465)
    monkeypatch.setattr(settings, "smtp_user", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "secret")
    monkeypatch.setattr(settings, "smtp_starttls", True)
    monkeypatch.setattr(settings, "smtp_ssl", True)

    delivered = await send_email("parent@example.com", "Сброс", "Ссылка")
    assert delivered is True
    assert captured["host"] == "smtp.test" and captured["port"] == 465
    assert "starttls" not in captured  # SMTP_SSL не делает STARTTLS
    assert captured["message"]["To"] == "parent@example.com"


async def test_smtp_failure_raises(monkeypatch):
    class BrokenSMTP:
        def __init__(self, *args, **kwargs):
            raise OSError("smtp down")

    monkeypatch.setattr(email_mod.smtplib, "SMTP", BrokenSMTP)
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_ssl", False)
    with pytest.raises(EmailDeliveryError):
        await send_email("parent@example.com", "Тема", "Текст")
