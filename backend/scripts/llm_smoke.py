"""S-59: двурежимный smoke LLM-шлюза (echo-базлайн → live) + FinOps.

Проверяет 4 маршрута шлюза, health провайдера, FinOps-строки `llm_calls`,
опционально озвучку (S-44) и PDF-отчёт (S-25). В echo-режиме ключи не нужны:
провайдер принудительно гасится, все маршруты идут через заглушку
(`status=echo`), расход = 0 — это baseline для сравнения с живым прогоном.

Запуск (staging, без ключей — echo-базлайн):
    docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T api \
        python scripts/llm_smoke.py --mode echo --with-voice --with-pdf \
        --out /srv/reports/llm-smoke-echo.json

Живой прогон (LLM_BASE_URL/LLM_API_KEY заданы в env, нужна сеть):
    docker compose --env-file .env.staging -f docker-compose.staging.yml exec -T api \
        python scripts/llm_smoke.py --mode live --out /srv/reports/llm-smoke-live.json

Сравнение baseline → live (--compare читает предыдущий артефакт и печатает
per-route diff; при расхождении схемы деградирует до generic-сравнения):
    python scripts/llm_smoke.py --mode echo \
        --compare /srv/reports/llm-smoke-echo.json

Без аргументов — auto: live, если провайдер настроен, иначе echo.
Коды возврата: 0 — ожидания выполнены; 2 — расхождение (route/health/voice/pdf);
3 — ошибка конфигурации (live без провайдера, БД/Redis недоступны, запись
артефакта). Скрипт пишет строки в `llm_calls` (FinOps) и не трогает квоты
пользователей (user_id=None); артефакт --out — JSON-базлайн schema v1.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SCHEMA = "chessclass.llm_smoke/1"

#: 4 маршрута Design §8.1: L1 / L2 / L3 / judge.
CASES: tuple[tuple[str, str, str], ...] = (
    (
        "python_teacher.comment",
        "novice",
        "Ученик написал: print('Привет'). Что здесь хорошо и что улучшить?",
    ),
    (
        "python_teacher.explain_code",
        "intermediate",
        "Объясни, что делает код и где он может пригодиться:\n"
        "for i in range(3):\n    print(i)",
    ),
    (
        "chess_lab.insight",
        "advanced",
        "Стартовая позиция. Назови один ключевой принцип развития фигур.",
    ),
    (
        "anticheat.judge_explain",
        "novice",
        "Ученик утверждает, что написал цикл for самостоятельно. "
        "Задай один уточняющий вопрос по его коду.",
    ),
)

SEED_STUDENT_EMAIL = "student1@chessclass.dev"
VOICE_TEXT = "ChessClass: проверка озвучки."


# --- чистые хелперы (тестируются без БД/сети: tests/test_llm_smoke.py)


def _expected_case_status(mode: str) -> str:
    """Ожидаемый status маршрута: echo-режим — заглушка, live — ok."""
    return "echo" if mode == "echo" else "ok"


def _expected_health_status(mode: str) -> str:
    """Ожидаемый health провайдера: в echo его нет, в live — ok."""
    return "echo" if mode == "echo" else "ok"


def _value(row: Any, key: str, default: Any = None) -> Any:
    """Поле ORM-строки `llm_calls` или dict с безопасным default."""
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _as_decimal(value: Any) -> Decimal:
    """Decimal из значения БД/JSON (None и мусор → 0)."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return Decimal("0")


def _summarize_calls(rows: Iterable[Any]) -> dict[str, Any]:
    """Свернуть новые строки `llm_calls` в FinOps-сводку (JSON-safe)."""
    calls: list[dict[str, Any]] = []
    tokens_in = 0
    tokens_out = 0
    cost_total = Decimal("0")
    for row in rows:
        cost = _as_decimal(_value(row, "cost_in")) + _as_decimal(
            _value(row, "cost_out")
        )
        row_in = int(_value(row, "tokens_in", 0) or 0)
        row_out = int(_value(row, "tokens_out", 0) or 0)
        tokens_in += row_in
        tokens_out += row_out
        cost_total += cost
        calls.append(
            {
                "route": _value(row, "route"),
                "status": _value(row, "status"),
                "modelUsed": _value(row, "model_used"),
                "tokensIn": row_in,
                "tokensOut": row_out,
                "cost": f"{cost:.4f}",
                "latencyMs": int(_value(row, "latency_ms", 0) or 0),
            }
        )
    return {
        "calls": calls,
        "tokensIn": tokens_in,
        "tokensOut": tokens_out,
        "costTotal": f"{cost_total:.4f}",
    }


def _cases_by_route(cases: Any) -> dict[str, Any]:
    """Индекс `cases` по route; чужая схема → пустой индекс (generic compare)."""
    index: dict[str, Any] = {}
    if isinstance(cases, Mapping):
        for route, case in cases.items():
            if isinstance(case, Mapping):
                index[str(route)] = case
        return index
    if not isinstance(cases, list):
        return index
    for case in cases:
        if isinstance(case, Mapping) and isinstance(case.get("route"), str):
            index[case["route"]] = case
    return index


def _case_model(case: Any) -> Any:
    return _value(case, "modelUsed", _value(case, "model"))


def _case_cost(case: Any) -> Decimal:
    return _as_decimal(_value(case, "cost"))


def _same_case(prev: Any, cur: Any) -> bool:
    if prev is None or cur is None:
        return False
    return (
        _value(prev, "status") == _value(cur, "status")
        and _case_model(prev) == _case_model(cur)
        and _case_cost(prev) == _case_cost(cur)
    )


def _artifact_cost(artifact: Mapping[str, Any]) -> Decimal:
    finops = artifact.get("finops")
    if isinstance(finops, Mapping):
        cost = finops.get("costTotal")
        if cost is not None:
            return _as_decimal(cost)
    total = Decimal("0")
    cases = artifact.get("cases")
    if isinstance(cases, list):
        for case in cases:
            total += _case_cost(case)
    return total


def _generic_compare(
    prev: Mapping[str, Any], cur: Mapping[str, Any]
) -> dict[str, Any]:
    """Сравнение артефактов чужой/будущей схемы: наличие и изменение ключей."""
    prev_keys = {str(key) for key in prev}
    cur_keys = {str(key) for key in cur}
    common = prev_keys & cur_keys
    changed = sorted(key for key in common if prev.get(key) != cur.get(key))
    added = sorted(cur_keys - prev_keys)
    removed = sorted(prev_keys - cur_keys)
    return {
        "comparable": False,
        "summary": (
            f"generic: schema differs; keys +{len(added)}/-{len(removed)}"
            f"/~{len(changed)}"
        ),
        "routes": [],
        "addedKeys": added,
        "removedKeys": removed,
        "changedKeys": changed,
    }


def _compare_artifacts(prev: Any, cur: Any) -> dict[str, Any]:
    """Diff артефактов schema v1: per-route status/model/cost.

    При несовпадении схемы уходит в generic-сравнение; исключений не бросает.
    """
    prev_map: Mapping[str, Any] = prev if isinstance(prev, Mapping) else {}
    cur_map: Mapping[str, Any] = cur if isinstance(cur, Mapping) else {}
    prev_cases = _cases_by_route(prev_map.get("cases"))
    cur_cases = _cases_by_route(cur_map.get("cases"))
    if not prev_cases and not cur_cases:
        return _generic_compare(prev_map, cur_map)

    routes = list(dict.fromkeys([*prev_cases, *cur_cases]))
    rows: list[dict[str, Any]] = []
    changed_routes = 0
    changed_models = 0
    for route in routes:
        prev_case = prev_cases.get(route)
        cur_case = cur_cases.get(route)
        prev_model = _case_model(prev_case) if prev_case is not None else None
        cur_model = _case_model(cur_case) if cur_case is not None else None
        changed = not _same_case(prev_case, cur_case)
        changed_routes += int(changed)
        if prev_model != cur_model:
            changed_models += 1
        rows.append(
            {
                "route": route,
                "prevStatus": (
                    _value(prev_case, "status") if prev_case is not None else None
                ),
                "prevModel": prev_model,
                "prevCost": (
                    f"{_case_cost(prev_case):.4f}" if prev_case is not None else None
                ),
                "curStatus": (
                    _value(cur_case, "status") if cur_case is not None else None
                ),
                "curModel": cur_model,
                "curCost": (
                    f"{_case_cost(cur_case):.4f}" if cur_case is not None else None
                ),
                "changed": changed,
            }
        )
    prev_cost = _artifact_cost(prev_map)
    cur_cost = _artifact_cost(cur_map)
    return {
        "comparable": True,
        "summary": (
            f"{prev_map.get('mode', '?')} -> {cur_map.get('mode', '?')}: "
            f"{changed_models}/{len(routes)} routes changed model; "
            f"cost {prev_cost:.4f} -> {cur_cost:.4f}"
        ),
        "routes": rows,
        "routesChanged": changed_routes,
        "routesChangedModels": changed_models,
        "totalRoutes": len(routes),
        "prevCost": f"{prev_cost:.4f}",
        "curCost": f"{cur_cost:.4f}",
    }


# --- CLI / вывод


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Двурежимный smoke LLM-шлюза (echo-базлайн / live) + FinOps.",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "echo", "live"),
        default="auto",
        help="auto — live при настроенном провайдере, иначе echo (default)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="записать JSON-артефакт (baseline для --compare)",
    )
    parser.add_argument(
        "--compare",
        type=Path,
        default=None,
        dest="compare_path",
        help="сравнить текущий прогон с предыдущим JSON-артефактом",
    )
    parser.add_argument(
        "--with-voice",
        action="store_true",
        help="проверить озвучку (S-44; без ключа ожидается graceful disabled)",
    )
    parser.add_argument(
        "--with-pdf",
        action="store_true",
        help="проверить PDF-отчёт (S-25; локальный fpdf2 + DejaVu)",
    )
    return parser


def _print_case(case: Mapping[str, Any]) -> None:
    marker = "ok" if case.get("ok") else "FAIL"
    print(
        f"[{marker}] {case.get('route')} ({case.get('level')}/{case.get('tier')}): "
        f"status={case.get('status')} model={case.get('modelUsed')} "
        f"latency={case.get('latencyMs')}ms "
        f"tokens={case.get('tokensIn')}/{case.get('tokensOut')} "
        f"cost={case.get('cost')}"
    )
    print(f"       {case.get('textPreview')}")


def _print_compare(prev_path: Path, current: Mapping[str, Any]) -> None:
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(
            f"compare: пропуск — не удалось прочитать {prev_path}: {exc}",
            file=sys.stderr,
        )
        return
    diff = _compare_artifacts(prev, current)
    print(f"compare: {prev_path} -> текущий прогон")
    for row in diff.get("routes", []):
        mark = "changed" if row.get("changed") else "same"
        print(
            f"  {row.get('route')}: "
            f"{row.get('prevStatus')}/{row.get('prevModel')}/{row.get('prevCost')} -> "
            f"{row.get('curStatus')}/{row.get('curModel')}/{row.get('curCost')} "
            f"[{mark}]"
        )
    print(f"compare summary: {diff.get('summary')}")


# --- health и опциональные проверки


async def _check_health() -> dict[str, Any]:
    """In-process health провайдера (аналог /admin/llm/health, S-31)."""
    from llm.gateway import get_cloud_provider
    from llm.models_registry import MODELS

    provider = get_cloud_provider()
    configured = provider.is_configured()
    available: set[str] | None = None
    latency_ms: int | None = None
    error: str | None = None
    if configured:
        started = time.monotonic()
        try:
            available = set(await asyncio.wait_for(provider.list_models(), timeout=5.0))
        except Exception as exc:  # noqa: BLE001 — health не должен падать
            error = f"{type(exc).__name__}: {exc}"
        latency_ms = int((time.monotonic() - started) * 1000)
    missing = sorted(
        {
            spec.slug
            for spec in MODELS.values()
            if available is not None and spec.slug not in available
        }
    )
    if not configured:
        status = "echo"
    elif available is None or missing:
        status = "degraded"
    else:
        status = "ok"
    return {
        "status": status,
        "providerConfigured": configured,
        "baseUrl": provider.base_url,
        "missingModels": missing,
        "availableModels": sorted(available)[:50] if available is not None else [],
        "latencyMs": latency_ms,
        "error": error,
    }


async def _voice_check(redis: Any) -> dict[str, Any]:
    """Озвучка: без ключа ожидается graceful `disabled`, с ключом — аудио > 0."""
    from sqlalchemy import select

    from core.config import settings
    from core.db import session_factory
    from core.errors import AppError
    from domains.auth.models import User, UserRole
    from domains.voice import service as voice_svc

    async with session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.email == settings.seed_admin_email)
            )
        ).scalar_one_or_none()
        if user is None:
            user = (
                await session.execute(
                    select(User)
                    .where(User.role == UserRole.ADMIN)
                    .order_by(User.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
        if user is None:
            user = (
                await session.execute(select(User).order_by(User.id).limit(1))
            ).scalar_one_or_none()
        if user is None:
            return {"status": "skipped", "reason": "в БД нет пользователей"}
        configured = bool(settings.voice_api_key)
        try:
            audio, meta, cached = await voice_svc.synthesize(
                session, redis, user, VOICE_TEXT
            )
            await session.commit()
        except AppError as exc:
            await session.rollback()
            # Без ключа это ожидаемый graceful fallback, а не сбой прогона.
            if exc.code == "voice_unavailable" and not configured:
                return {"status": "disabled", "code": exc.code, "detail": exc.detail}
            return {"status": "failed", "code": exc.code, "detail": exc.detail}
        except Exception as exc:  # noqa: BLE001 — сбой провайдера в отчёт, не в трейс
            await session.rollback()
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    if not audio:
        return {"status": "failed", "reason": "пустой аудиобуфер"}
    return {
        "status": "ok",
        "bytes": len(audio),
        "cached": cached,
        "chars": len(VOICE_TEXT),
        "cost": f"{_as_decimal(meta.cost):.4f}",
        "voiceId": meta.voice_id,
        "path": meta.path,
    }


async def _pdf_check() -> dict[str, Any]:
    """PDF-отчёт: локальная генерация (fpdf2 + DejaVu), ключей не требует."""
    from sqlalchemy import select

    from core.db import session_factory
    from domains.auth.models import User, UserRole
    from domains.reports.pdf import generate_for_student

    async with session_factory() as session:
        requester = (
            await session.execute(
                select(User)
                .where(User.role.in_((UserRole.ADMIN, UserRole.TEACHER)))
                .order_by(User.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        student = (
            await session.execute(
                select(User).where(User.email == SEED_STUDENT_EMAIL)
            )
        ).scalar_one_or_none()
        if student is None:
            student = (
                await session.execute(
                    select(User)
                    .where(User.role == UserRole.STUDENT)
                    .order_by(User.id)
                    .limit(1)
                )
            ).scalar_one_or_none()
        if requester is None or student is None:
            return {"status": "skipped", "reason": "нет teacher/admin или student"}
        try:
            info = await generate_for_student(session, requester, student.id)
            await session.commit()
        except Exception as exc:  # noqa: BLE001 — сбой генерации в отчёт
            await session.rollback()
            return {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    path = Path(str(info["path"]))
    try:
        head = path.read_bytes()[:5]
    except OSError as exc:
        return {"status": "failed", "error": f"файл отчёта: {exc}", "path": str(path)}
    size_bytes = int(info["sizeBytes"])
    return {
        "status": (
            "ok" if size_bytes > 0 and head.startswith(b"%PDF") else "failed"
        ),
        "reportId": info["reportId"],
        "sizeBytes": size_bytes,
        "path": str(path),
        "magic": head.decode("latin-1"),
    }


# --- основной прогон


async def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    # Тяжёлые импорты внутри main(): импорт скрипта в тестах не открывает
    # соединений с БД/Redis (tests/test_llm_smoke.py).
    import redis.asyncio as redis_lib
    from sqlalchemy import func, select
    from sqlalchemy.exc import SQLAlchemyError

    import domains.auth.models  # noqa: F401 — регистрирует users для FK llm_calls
    from core.config import settings
    from core.db import engine, session_factory
    from core.levels import Level
    from llm import economy
    from llm.gateway import (
        LLMCallContext,
        close_llm_providers,
        get_cloud_provider,
        llm_generate,
    )
    from llm.models import LLMCall
    from llm.models_registry import MODELS
    from llm.prompts.builder import build_messages

    redis: Any | None = None
    try:
        provider = get_cloud_provider()
        configured = provider.is_configured()
        mode = args.mode
        if mode == "auto":
            mode = "live" if configured else "echo"
        if mode == "echo":
            # Детерминированный baseline: гасим провайдера ДО первого вызова.
            settings.llm_base_url = ""
            settings.llm_api_key = ""
            settings.llm_local_fallback = False
            await close_llm_providers()
            configured = False
        elif not configured:
            print(
                "llm smoke: live-режим, но LLM_BASE_URL не задан — "
                "заполните env провайдера",
                file=sys.stderr,
            )
            return 3
        label = "echo-заглушка" if mode == "echo" else "live-провайдер"
        print(f"llm smoke: mode={mode} ({label})")

        # exit 3: конфигурационные ошибки до содержательных проверок
        try:
            async with session_factory() as session:
                max_before = int(
                    (await session.execute(select(func.max(LLMCall.id)))).scalar() or 0
                )
        except (SQLAlchemyError, OSError) as exc:
            print(f"llm smoke: БД недоступна: {exc}", file=sys.stderr)
            return 3

        redis = redis_lib.from_url(settings.redis_url, decode_responses=True)
        try:
            await redis.ping()
        except Exception as exc:  # noqa: BLE001 — это конфигурационная ошибка
            print(f"llm smoke: Redis недоступен: {exc}", file=sys.stderr)
            return 3

        health = await _check_health()
        print(
            f"health: status={health['status']} "
            f"providerConfigured={health['providerConfigured']} "
            f"missingModels={health['missingModels']}"
        )

        expected_case = _expected_case_status(mode)
        cases: list[dict[str, Any]] = []
        for route, level_name, request in CASES:
            level = Level(level_name)
            started = time.monotonic()
            try:
                async with session_factory() as session:
                    result = await llm_generate(
                        session,
                        redis,
                        route=route,
                        level=level,
                        messages=build_messages(route, level, request=request),
                        ctx=LLMCallContext(
                            user_id=None, billing_tier="free", task_kind="sync"
                        ),
                    )
                    await session.commit()
            except Exception as exc:  # noqa: BLE001 — сбой фиксируем как FAIL
                case: dict[str, Any] = {
                    "route": route,
                    "level": level.value,
                    "tier": "-",
                    "status": "error",
                    "expectedStatus": expected_case,
                    "modelRequested": "-",
                    "modelUsed": "-",
                    "tokensIn": 0,
                    "tokensOut": 0,
                    "latencyMs": int((time.monotonic() - started) * 1000),
                    "cost": "0.0000",
                    "textPreview": "",
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                cases.append(case)
                _print_case(case)
                continue
            latency_ms = int((time.monotonic() - started) * 1000)
            spec = MODELS.get(result.tier)
            cost = Decimal("0")
            if spec is not None:
                cost = (
                    economy.compute_cost(result.usage.prompt_tokens, spec.price_in)
                    or Decimal("0")
                ) + (
                    economy.compute_cost(result.usage.completion_tokens, spec.price_out)
                    or Decimal("0")
                )
            case = {
                "route": route,
                "level": level.value,
                "tier": result.tier,
                "status": result.status,
                "expectedStatus": expected_case,
                "modelRequested": result.model_requested,
                "modelUsed": result.model_used,
                "tokensIn": result.usage.prompt_tokens,
                "tokensOut": result.usage.completion_tokens,
                "latencyMs": latency_ms,
                "cost": f"{cost:.4f}",
                "textPreview": result.text[:160].replace("\n", " "),
                "fallbackFrom": result.fallback_from,
                "ok": result.status == expected_case,
            }
            cases.append(case)
            _print_case(case)

        # FinOps: строки llm_calls, добавленные этим прогоном, и суммы за сутки.
        async with session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(LLMCall)
                        .where(LLMCall.id > max_before)
                        .order_by(LLMCall.id)
                    )
                )
                .scalars()
                .all()
            )
        finops: dict[str, Any] = _summarize_calls(rows)
        finops["budgetFree"] = settings.budget_free_tokens_day
        today_start = datetime.now(UTC).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        async with session_factory() as session:
            today_in, today_out, today_cost = (
                await session.execute(
                    select(
                        func.coalesce(func.sum(LLMCall.tokens_in), 0),
                        func.coalesce(func.sum(LLMCall.tokens_out), 0),
                        func.coalesce(
                            func.sum(
                                func.coalesce(LLMCall.cost_in, 0)
                                + func.coalesce(LLMCall.cost_out, 0)
                            ),
                            0,
                        ),
                    ).where(LLMCall.created_at >= today_start)
                )
            ).one()
        finops["today"] = {
            "tokensIn": int(today_in),
            "tokensOut": int(today_out),
            "costTotal": f"{_as_decimal(today_cost):.4f}",
        }
        print(
            f"finops: new calls={len(finops['calls'])} "
            f"tokensIn={finops['tokensIn']} tokensOut={finops['tokensOut']} "
            f"cost={finops['costTotal']} {settings.llm_cost_currency} "
            f"budgetFree={finops['budgetFree']}"
        )
        print(
            f"finops today: tokensIn={finops['today']['tokensIn']} "
            f"tokensOut={finops['today']['tokensOut']} "
            f"cost={finops['today']['costTotal']} {settings.llm_cost_currency}"
        )

        # Опциональные контуры: без ключей проверяем graceful-поведение.
        voice: dict[str, Any] | None = None
        pdf: dict[str, Any] | None = None
        expected: dict[str, Any] = {
            "cases": expected_case,
            "health": _expected_health_status(mode),
        }
        if args.with_voice:
            expected["voice"] = "ok" if settings.voice_api_key else "disabled"
            voice = await _voice_check(redis)
            print(
                f"voice: status={voice['status']} bytes={voice.get('bytes')} "
                f"cached={voice.get('cached')} cost={voice.get('cost')} "
                f"code={voice.get('code')}"
            )
        if args.with_pdf:
            expected["pdf"] = "ok"
            pdf = await _pdf_check()
            print(
                f"pdf: status={pdf['status']} reportId={pdf.get('reportId')} "
                f"size={pdf.get('sizeBytes')}b path={pdf.get('path')}"
            )

        problems: list[str] = []
        if health["status"] != expected["health"]:
            problems.append(
                f"health={health['status']} (ожидалось {expected['health']})"
            )
        failed_cases = [case["route"] for case in cases if not case["ok"]]
        if failed_cases:
            problems.append("cases FAIL: " + ", ".join(failed_cases))
        if voice is not None and voice["status"] != expected["voice"]:
            problems.append(f"voice={voice['status']} (ожидалось {expected['voice']})")
        if pdf is not None and pdf["status"] != "ok":
            problems.append(f"pdf={pdf['status']}")
        if mode == "echo" and _as_decimal(finops["costTotal"]) != 0:
            problems.append(f"echo cost={finops['costTotal']} (ожидалось 0)")
        exit_code = 0 if not problems else 2
        for problem in problems:
            print(f"llm smoke: FAIL — {problem}", file=sys.stderr)

        artifact: dict[str, Any] = {
            "schema": SCHEMA,
            "ts": datetime.now(UTC).isoformat(),
            "mode": mode,
            "provider": {"configured": configured, "baseUrl": health["baseUrl"]},
            "health": health,
            "cases": cases,
            "voice": voice,
            "pdf": pdf,
            "finops": finops,
            "expected": expected,
            "verdict": "ok" if not problems else "failed",
            "exitCode": exit_code,
        }

        if args.out is not None:
            try:
                out_path = Path(args.out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(
                    json.dumps(artifact, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"llm smoke: artifact -> {out_path}")
            except OSError as exc:
                print(
                    f"llm smoke: не удалось записать артефакт {args.out}: {exc}",
                    file=sys.stderr,
                )
                exit_code = 3

        if args.compare_path is not None:
            _print_compare(Path(args.compare_path), artifact)

        verdict = "OK" if not problems else "FAILED"
        print(
            f"llm smoke: {verdict} mode={mode} "
            f"({'echo' if mode == 'echo' else 'live'}) "
            f"cases={sum(1 for case in cases if case['ok'])}/{len(cases)} "
            f"exit={exit_code}",
            file=sys.stdout if not problems else sys.stderr,
        )
        return exit_code
    finally:
        await close_llm_providers()
        if redis is not None:
            await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
