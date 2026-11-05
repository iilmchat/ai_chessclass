"""Транспорт email (S-75): SMTP в prod, консольный fallback в dev.

Письма не должны блокировать event loop: SMTP-вызовы выполняются в
`asyncio.to_thread`. При пустом `SMTP_HOST` пишем письмо в лог (dev/CI) и
возвращаем False — это существующий контракт verify-email.
"""

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from core.config import settings

logger = logging.getLogger(__name__)


class EmailDeliveryError(RuntimeError):
    """SMTP настроен, но письмо не удалось отправить."""


def verification_email(link: str) -> tuple[str, str]:
    return (
        "Подтвердите email — ChessClass",
        "Здравствуйте!\n\n"
        f"Подтвердите email для ChessClass: {link}\n\n"
        "Если вы не регистрировались, проигнорируйте письмо.\n",
    )


def password_reset_email(link: str) -> tuple[str, str]:
    return (
        "Сброс пароля — ChessClass",
        "Здравствуйте!\n\n"
        f"Сбросить пароль ChessClass: {link}\n\n"
        "Ссылка одноразовая. Если вы не запрашивали сброс, проигнорируйте письмо.\n",
    )


def parental_consent_email(link: str, policy_version: str) -> tuple[str, str]:
    return (
        "Согласие родителя — ChessClass",
        "Здравствуйте!\n\n"
        "Ученик указал вас как родителя/опекуна в ChessClass. "
        "Подтвердите согласие на обработку данных ребёнка:\n"
        f"{link}\n\n"
        f"Версия политики: {policy_version}. Ссылка одноразовая, действует 7 дней. "
        "Согласие можно отозвать в любой момент в разделе «Согласие».\n",
    )


def _smtp_send(to: str, subject: str, text: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)

    smtp_cls = smtplib.SMTP_SSL if settings.smtp_ssl else smtplib.SMTP
    with smtp_cls(
        settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_s
    ) as client:
        client.ehlo()
        if settings.smtp_starttls and not settings.smtp_ssl:
            client.starttls()
            client.ehlo()
        if settings.smtp_user:
            client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(msg)


async def send_email(to: str, subject: str, text: str) -> bool:
    """Отправить письмо; False — dev-консоль (SMTP не настроен).

    При настроенном SMTP ошибка доставки поднимает `EmailDeliveryError`,
    чтобы вызывающий endpoint мог сообщить клиенту о сбое.
    """
    if not settings.smtp_host:
        logger.info("[dev-email] to=%s subject=%s body=%s", to, subject, text)
        return False
    try:
        await asyncio.to_thread(_smtp_send, to, subject, text)
    except (OSError, smtplib.SMTPException) as exc:
        logger.exception("email: SMTP delivery failed to=%s", to)
        raise EmailDeliveryError(str(exc)) from exc
    return True
