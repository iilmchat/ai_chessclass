"""S-49: xAPI-коннектор LRS с идемпотентной очередью и retry.

S-67: OAuth2 client_credentials (Bearer) с токен-кэшем; Basic — fallback,
когда `lrs_oauth_client_id`/`lrs_oauth_token_url` не заданы. Mapping
классов на курсы LMS (`lms_class_map`) меняет activity id skill-объекта.
"""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from domains.auth.models import User, UserRole
from domains.bot_lab.models import BotStats
from domains.classes.models import ClassMember, Classroom
from domains.cognitive import service as cognitive_svc
from domains.lms.models import LmsClassMap, LmsCourse, LrsDelivery
from domains.profile.models import UserProfile

logger = logging.getLogger(__name__)

STATUSES = ("pending", "sent", "failed")
SenderFn = Callable[[dict], Awaitable[int]]

#: Локальный корень activity id (маппинг не задан) — источник S-49.
DEFAULT_ACTIVITY_ROOT = "https://chessclass.local"

#: Обновлять токен за N секунд до expiry (S-67).
OAUTH_REFRESH_MARGIN_S = 60
#: S-79: общий Redis-кэш токена между API/воркерами.
OAUTH_CACHE_KEY = "lrs:oauth:token"


class _OauthTokenState:
    """Модульный кэш токена (in-memory, один воркер — ок для S-67)."""

    def __init__(self) -> None:
        self.value: str = ""
        self.expires_at: float = 0.0


_oauth_token = _OauthTokenState()


def lms_auth_mode() -> str:
    """Режим авторизации к LRS: oauth2 | basic | none."""
    if settings.lrs_oauth_client_id and settings.lrs_oauth_token_url:
        return "oauth2"
    if settings.lrs_key:
        return "basic"
    return "none"


async def fetch_oauth_token(client: httpx.AsyncClient) -> str:
    """Выдать токен по client_credentials и обновить кэш (S-67)."""
    data: dict[str, str] = {
        "grant_type": "client_credentials",
        "client_id": settings.lrs_oauth_client_id,
        "client_secret": settings.lrs_oauth_client_secret,
    }
    if settings.lrs_oauth_scope:
        data["scope"] = settings.lrs_oauth_scope
    response = await client.post(settings.lrs_oauth_token_url, data=data)
    response.raise_for_status()
    payload = response.json()
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("LRS OAuth: access_token отсутствует в ответе")
    _oauth_token.value = token
    _oauth_token.expires_at = time.monotonic() + float(
        payload.get("expires_in") or 3600
    )
    return token


def _oauth_token_expired() -> bool:
    return (
        not _oauth_token.value
        or time.monotonic()
        > _oauth_token.expires_at - OAUTH_REFRESH_MARGIN_S
    )


def _http_client(base_url: str) -> httpx.AsyncClient:
    """httpx-клиент с egress-hook (S-61); точка инъекции транспорта в тестах."""
    from core.egress import hostname_of, make_egress_hook

    return httpx.AsyncClient(
        timeout=settings.lrs_timeout_s,
        event_hooks={
            "request": [make_egress_hook(hostname_of(base_url) or "")]
        },
    )


async def auth_headers(redis: Any | None = None) -> dict[str, str]:
    """Bearer из Redis/памяти (OAuth2) или пусто (Basic-fallback)."""
    if lms_auth_mode() != "oauth2":
        return {}
    if redis is not None:
        cached = await redis.get(OAUTH_CACHE_KEY)
        if cached:
            token = cached.decode() if isinstance(cached, bytes) else str(cached)
            return {"Authorization": f"Bearer {token}"}
    if _oauth_token_expired():
        async with _http_client(settings.lrs_oauth_token_url) as token_client:
            await fetch_oauth_token(token_client)
    if redis is not None:
        ttl = max(
            1,
            int(_oauth_token.expires_at - time.monotonic())
            - OAUTH_REFRESH_MARGIN_S,
        )
        await redis.set(OAUTH_CACHE_KEY, _oauth_token.value, ex=ttl)
    return {"Authorization": f"Bearer {_oauth_token.value}"}


async def invalidate_oauth_async(redis: Any | None = None) -> None:
    """Сбросить in-memory и Redis-кэш при 401."""
    _oauth_token.value = ""
    _oauth_token.expires_at = 0.0
    if redis is not None:
        await redis.delete(OAUTH_CACHE_KEY)


def _statement_id(actor_mbox: str, object_id: str, day: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{actor_mbox}|{object_id}|{day}",
        )
    )


def skill_activity_id(activity_ref: str | None, slug: str) -> str:
    """Activity id skill-объекта: через маппинг курса (S-67) или дефолт."""
    if activity_ref:
        return f"{activity_ref.rstrip('/')}/skills/{slug}"
    return f"{DEFAULT_ACTIVITY_ROOT}/skills/{slug}"


async def class_activity_refs(session: AsyncSession) -> dict[int, str]:
    """user_id → activity_ref класса с маппингом на курс LMS (S-67).

    У класса — не более одного маппинга, поэтому setdefault достаточно.
    """
    rows = (
        await session.execute(
            select(ClassMember.user_id, LmsClassMap.activity_ref).join(
                LmsClassMap, LmsClassMap.class_id == ClassMember.class_id
            )
        )
    ).all()
    refs: dict[int, str] = {}
    for user_id, ref in rows:
        refs.setdefault(user_id, ref)
    return refs


async def build_statements(session: AsyncSession) -> list[dict]:
    """Собрать xAPI statements по всем ученикам (идемпотентно за день)."""
    rows = (
        await session.execute(
            select(User, UserProfile)
            .outerjoin(UserProfile, UserProfile.user_id == User.id)
            .where(User.role == UserRole.STUDENT)
            .order_by(User.id)
        )
    ).all()
    stats = {
        s.user_id: s for s in (await session.execute(select(BotStats))).scalars()
    }
    day = datetime.now(UTC).date().isoformat()
    now = datetime.now(UTC).isoformat()
    refs = await class_activity_refs(session)
    statements: list[dict] = []
    for user, profile in rows:
        actor = {
            "mbox": f"mailto:{user.email}",
            "name": (
                profile.display_name
                if profile is not None and profile.display_name
                else user.email
            ),
        }
        activity_ref = refs.get(user.id)
        for skill in await cognitive_svc.scores_snapshot(session, user.id):
            object_id = skill_activity_id(activity_ref, skill["slug"])
            statements.append(
                {
                    "id": _statement_id(actor["mbox"], object_id, day),
                    "actor": actor,
                    "verb": {
                        "id": "http://adlnet.gov/expapi/verbs/experienced",
                        "display": {"ru-RU": "изучил"},
                    },
                    "object": {
                        "id": object_id,
                        "definition": {
                            "name": {"ru-RU": skill["titleRu"]},
                            "type": "https://chessclass.local/activity/skill",
                        },
                    },
                    "result": {
                        "score": {"scaled": round(float(skill["score"]) / 100, 4)},
                        "completion": True,
                    },
                    "timestamp": now,
                }
            )
        stat = stats.get(user.id)
        if stat is not None:
            object_id = f"https://chessclass.local/bots/{user.id}"
            statements.append(
                {
                    "id": _statement_id(actor["mbox"], object_id, day),
                    "actor": actor,
                    "verb": {
                        "id": "http://adlnet.gov/expapi/verbs/achieved",
                        "display": {"ru-RU": "достиг"},
                    },
                    "object": {
                        "id": object_id,
                        "definition": {
                            "name": {"ru-RU": "Рейтинг бота"},
                            "type": "https://chessclass.local/activity/bot-elo",
                        },
                    },
                    "result": {
                        "score": {
                            "raw": float(stat.elo),
                            "min": 0,
                            "max": 3000,
                        },
                        "completion": True,
                    },
                    "timestamp": now,
                }
            )
    return statements


async def enqueue_statements(session: AsyncSession) -> int:
    statements = await build_statements(session)
    if not statements:
        return 0
    existing = set(
        (
            await session.execute(
                select(LrsDelivery.statement_id).where(
                    LrsDelivery.statement_id.in_(
                        [statement["id"] for statement in statements]
                    )
                )
            )
        ).scalars()
    )
    new = [statement for statement in statements if statement["id"] not in existing]
    if new:
        await session.execute(
            pg_insert(LrsDelivery).values(
                [
                    {
                        "statement_id": statement["id"],
                        "payload": statement,
                        "status": "pending",
                        "attempts": 0,
                        "next_attempt_at": datetime.now(UTC),
                    }
                    for statement in new
                ]
            )
        )
        await session.flush()
    return len(new)


async def _send(payload: dict, redis: Any | None = None) -> int:
    if not settings.lrs_enabled or not settings.lrs_endpoint:
        raise RuntimeError("LRS не настроен")
    url = f"{settings.lrs_endpoint.rstrip('/')}/statements"

    use_oauth = lms_auth_mode() == "oauth2"
    auth: tuple[str, str] | None = None
    headers: dict[str, str] = {}
    if use_oauth:
        # S-67/S-79: Bearer из Redis/in-memory; Basic — только fallback.
        headers = await auth_headers(redis)
    else:
        auth = (settings.lrs_key, settings.lrs_secret)

    async def put(client: httpx.AsyncClient) -> httpx.Response:
        return await client.put(
            url,
            params={"statementId": payload["id"]},
            json=payload,
            headers=headers,
            auth=auth if auth is not None else httpx.USE_CLIENT_DEFAULT,
        )

    async with _http_client(settings.lrs_endpoint) as client:
        response = await put(client)
        if use_oauth and response.status_code == 401:
            # Токен мог быть отозван/истёк на стороне IdP — обновляем и
            # повторяем ровно один раз.
            await invalidate_oauth_async(redis)
            headers = await auth_headers(redis)
            response = await put(client)
    return response.status_code


async def deliver_pending(
    session: AsyncSession,
    *,
    sender: SenderFn | None = None,
    limit: int | None = None,
    redis: Any | None = None,
) -> dict[str, int]:
    if sender is None and not settings.lrs_enabled:
        return {"sent": 0, "failed": 0, "pending": 0, "disabled": 1}
    if sender is not None:
        fetch = sender
    else:
        async def fetch(payload: dict) -> int:
            return await _send(payload, redis=redis)
    now = datetime.now(UTC)
    rows = list(
        (
            await session.execute(
                select(LrsDelivery)
                .where(
                    LrsDelivery.status.in_(("pending", "failed")),
                    LrsDelivery.next_attempt_at <= now,
                )
                .order_by(LrsDelivery.id)
                .limit(limit or settings.lms_sync_batch)
            )
        ).scalars()
    )
    sent = failed = 0
    for row in rows:
        row.attempts += 1
        try:
            status = await fetch(row.payload)
            row.response_status = int(status)
            if 200 <= status < 300:
                row.status = "sent"
                row.sent_at = datetime.now(UTC)
                row.last_error = None
                sent += 1
            else:
                row.status = "failed"
                row.last_error = f"HTTP {status}"
                row.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 2 ** min(row.attempts, 10))
                )
                failed += 1
        except Exception as exc:  # noqa: BLE001 - retry позже
            row.status = "failed"
            row.last_error = str(exc)[:1000]
            row.next_attempt_at = datetime.now(UTC) + timedelta(
                seconds=min(3600, 2 ** min(row.attempts, 10))
            )
            failed += 1
            logger.warning("lms: delivery %s failed: %s", row.id, exc)
    await session.flush()
    pending = int(
        await session.scalar(
            select(func.count())
            .select_from(LrsDelivery)
            .where(LrsDelivery.status == "pending")
        )
        or 0
    )
    return {"sent": sent, "failed": failed, "pending": pending, "disabled": 0}


async def status(session: AsyncSession) -> dict:
    counts = {
        status_name: int(count)
        for status_name, count in (
            await session.execute(
                select(LrsDelivery.status, func.count()).group_by(
                    LrsDelivery.status
                )
            )
        ).all()
    }
    last = (
        await session.execute(
            select(LrsDelivery).order_by(LrsDelivery.id.desc()).limit(1)
        )
    ).scalar_one_or_none()
    return {
        "configured": bool(settings.lrs_enabled and settings.lrs_endpoint),
        "endpoint": settings.lrs_endpoint or None,
        "authMode": lms_auth_mode(),
        "counts": {name: counts.get(name, 0) for name in STATUSES},
        "lastDelivery": (
            {
                "id": str(last.id),
                "status": last.status,
                "attempts": last.attempts,
                "responseStatus": last.response_status,
                "sentAt": last.sent_at,
            }
            if last is not None
            else None
        ),
    }


async def list_deliveries(
    session: AsyncSession, *, status_filter: str | None = None, limit: int = 100
) -> list[LrsDelivery]:
    stmt = select(LrsDelivery)
    if status_filter:
        stmt = stmt.where(LrsDelivery.status == status_filter)
    stmt = stmt.order_by(LrsDelivery.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars())


async def sync(
    session: AsyncSession,
    *,
    sender: SenderFn | None = None,
    redis: Any | None = None,
) -> dict:
    queued = await enqueue_statements(session)
    result = await deliver_pending(session, sender=sender, redis=redis)
    return {"queued": queued, **result}


# --- S-67: CRUD курсов LMS и маппинга классов ---


async def list_courses(session: AsyncSession) -> list[LmsCourse]:
    rows = await session.execute(select(LmsCourse).order_by(LmsCourse.id))
    return list(rows.scalars())


async def create_course(
    session: AsyncSession, *, external_id: str, title_ru: str
) -> LmsCourse:
    """Создать курс; duplicate external_id — ошибка (HTTP 409 в router)."""
    exists = (
        await session.scalar(
            select(func.count())
            .select_from(LmsCourse)
            .where(LmsCourse.external_id == external_id)
        )
        or 0
    )
    if exists:
        raise RuntimeError(f"LMS-курс с external_id={external_id} уже существует")
    course = LmsCourse(external_id=external_id, title_ru=title_ru)
    session.add(course)
    await session.flush()
    return course


async def delete_course(session: AsyncSession, course_id: int) -> bool:
    course = (
        await session.execute(select(LmsCourse).where(LmsCourse.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        return False
    await session.delete(course)
    await session.flush()
    return True


class ClassMapRow:
    """DTO маппинга с названиями класса/курса (для админ-UI)."""

    def __init__(
        self,
        *,
        map_id: int,
        class_id: int,
        course_id: int,
        activity_ref: str,
        class_name: str,
        course_title: str,
    ) -> None:
        self.map_id = map_id
        self.class_id = class_id
        self.course_id = course_id
        self.activity_ref = activity_ref
        self.class_name = class_name
        self.course_title = course_title


async def list_class_maps(session: AsyncSession) -> list[ClassMapRow]:
    rows = (
        await session.execute(
            select(
                LmsClassMap.id,
                LmsClassMap.class_id,
                LmsClassMap.course_id,
                LmsClassMap.activity_ref,
            ).order_by(LmsClassMap.id)
        )
    ).all()
    course_ids = {row[2] for row in rows}
    titles: dict[int, str] = {}
    if course_ids:
        titles = {
            course.id: course.title_ru
            for course in (
                await session.scalars(
                    select(LmsCourse).where(LmsCourse.id.in_(course_ids))
                )
            )
        }
    class_names = await _class_names(session, {row[1] for row in rows})
    return [
        ClassMapRow(
            map_id=row[0],
            class_id=row[1],
            course_id=row[2],
            activity_ref=row[3],
            class_name=class_names.get(row[1], f"#{row[1]}"),
            course_title=titles.get(row[2], f"#{row[2]}"),
        )
        for row in rows
    ]


async def _class_names(
    session: AsyncSession, class_ids: set[int]
) -> dict[int, str]:
    if not class_ids:
        return {}
    rows = (
        await session.execute(
            select(Classroom.id, Classroom.name).where(
                Classroom.id.in_(class_ids)
            )
        )
    ).all()
    return {row[0]: row[1] for row in rows}


async def create_class_map(
    session: AsyncSession,
    *,
    class_id: int,
    course_id: int,
    activity_ref: str,
) -> LmsClassMap:
    """Привязать класс к курсу; существующий маппинг класса — ошибка (409)."""
    classroom = (
        await session.execute(select(Classroom).where(Classroom.id == class_id))
    ).scalar_one_or_none()
    if classroom is None:
        raise LookupError(f"class {class_id} не найден")
    course = (
        await session.execute(select(LmsCourse).where(LmsCourse.id == course_id))
    ).scalar_one_or_none()
    if course is None:
        raise KeyError(f"course {course_id} не найден")
    existing = (
        await session.execute(
            select(LmsClassMap).where(LmsClassMap.class_id == class_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise RuntimeError(
            f"маппинг класса class_id={class_id} уже существует"
        )
    mapping = LmsClassMap(
        class_id=class_id, course_id=course_id, activity_ref=activity_ref
    )
    session.add(mapping)
    await session.flush()
    return mapping


async def delete_class_map(session: AsyncSession, map_id: int) -> bool:
    mapping = (
        await session.execute(select(LmsClassMap).where(LmsClassMap.id == map_id))
    ).scalar_one_or_none()
    if mapping is None:
        return False
    await session.delete(mapping)
    await session.flush()
    return True
