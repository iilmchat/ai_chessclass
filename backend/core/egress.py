"""Egress allowlist (S-61): контроль исходящих HTTP-звонков приложения.

Все исходящие httpx-клиенты доменов (LLM / voice / Telegram / LRS) подключают
`make_egress_hook` — request-hook, проверяющий хост назначения по политике:

* всегда разрешён loopback (`localhost`, `127.0.0.1`, `::1`) — dev-стек:
  LM Studio, pytest-транспорт, локальные сценарии;
* разрешены хосты из `ALLOWED_EGRESS_HOSTS` (env, comma/JSON — как
  `CORS_ORIGINS`); запись вида `example.com` или `*.example.com` разрешает
  хост и его поддомены (запись с точкой-звёздочкой — только поддомены);
* разрешены хосты, явно сконфигурированные в базовых URL сервисов
  (`LLM_BASE_URL`, `LLM_LOCAL_BASE_URL`, `VOICE_BASE_URL`,
  `TELEGRAM_API_BASE`, `LRS_ENDPOINT`) — их задаёт администратор;
* `extra`-паттерны конкретного клиента (например, хост его собственного
  `base_url` при кастомном конструировании в тестах).

Нарушение → `AppError("egress_blocked", …, 502)` — запрос не уходит:
компрометированный зависимый вызов не доберётся до произвольного хоста
(security-review §4, детский prod). Нужный провайдер добавляется в
`ALLOWED_EGRESS_HOSTS` или конфигурится как базовый URL.

Политика — host-based (по имени из URL request'а httpx); DNS-resolve
не обходит проверку, потому что соединение открывается по тому же имени,
по которому прошла проверка.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urlparse

import httpx

from core.config import settings
from core.errors import AppError

logger = logging.getLogger(__name__)

#: Хосты, разрешённые всегда (dev/MockTransport/локальный LM Studio).
ALWAYS_ALLOWED_HOSTS: frozenset[str] = frozenset(
    {"localhost", "127.0.0.1", "::1"}
)

#: Код ошибки AppError при блокировке egress.
EGRESS_BLOCKED_CODE = "egress_blocked"


def _normalize_pattern(pattern: str) -> str:
    """Нормализовать запись: срезом URL-обвязки; «*/поддомены» сохраняется."""
    raw = pattern.strip().lower()
    if "//" in raw:
        parsed = urlparse(raw)
        raw = parsed.hostname or parsed.netloc or raw
    raw = raw.strip(".")
    # сохраняем ведущую `*.` — семантику «только поддомены» решает host_allowed
    if not raw.startswith("*"):
        return raw.lstrip(".")
    suffix = raw.lstrip("*").lstrip(".")
    return f"*.{suffix}" if suffix else "*"


def configured_egress_patterns() -> list[str]:
    """Паттерны политики: ALLOWED_EGRESS_HOSTS + хосты настроенных баз URL."""
    patterns = [
        _normalize_pattern(item) for item in settings.allowed_egress_hosts if item.strip()
    ]
    for base in (
        settings.llm_base_url,
        settings.llm_local_base_url,
        settings.voice_base_url,
        settings.telegram_api_base,
        settings.lrs_endpoint,
    ):
        host = hostname_of(base)
        if host:
            patterns.append(host.lower())
    return patterns


def hostname_of(url: str) -> str | None:
    """Hostname из URL (без порта); None для пустого/некорректного значения."""
    if not url:
        return None
    try:
        return urlparse(url).hostname
    except ValueError:
        return None


def host_allowed(
    host: str | None, patterns: Iterable[str], extra: Iterable[str] = ()
) -> bool:
    """Хост разрешён? Точное имя или поддомен записи (normalized).

    Семантика записи: `example.com` — хост и его поддомены; `*.example.com`
    — только поддомены (сам `example.com` не совпадает); `*` — всё.
    """
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host in ALWAYS_ALLOWED_HOSTS:
        return True
    for raw in (*patterns, *extra):
        entry = _normalize_pattern(raw or "")
        if not entry or entry == "*":
            if entry == "*":
                return True
            continue
        if entry.startswith("*."):
            base = entry[2:]
            if base and host.endswith(f".{base}"):
                return True
        elif host == entry or host.endswith(f".{entry}"):
            return True
    return False


def ensure_egress_allowed(url: str, *, extra: Iterable[str] = ()) -> None:
    """Разрешён ли исходящий вызов на этот URL? Нет — AppError (502)."""
    host = hostname_of(url)
    if host is None:
        raise AppError(
            EGRESS_BLOCKED_CODE,
            "Не удалось определить хост назначения для egress-политики",
            502,
        )
    if host_allowed(host, configured_egress_patterns(), extra):
        return
    logger.warning("egress: блокирован вызов на %s (host=%s)", url, host)
    raise AppError(
        EGRESS_BLOCKED_CODE,
        f"Хост {host} не разрешён политикой ALLOWED_EGRESS_HOSTS",
        502,
    )


def make_egress_hook(
    *extra: str,
) -> Callable[[httpx.Request], Awaitable[None]]:
    """httpx request-hooks (event_hooks={"request": [...]}) — guard egress."""

    async def _egress_hook(request: httpx.Request) -> None:
        ensure_egress_allowed(str(request.url), extra=extra)

    return _egress_hook
