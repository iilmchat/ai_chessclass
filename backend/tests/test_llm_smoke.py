"""S-59: чистые хелперы scripts/llm_smoke.py (без БД, Redis и сети).

Скрипт не является пакетом — импортируем его по пути через importlib.
Тяжёлые зависимости (core.db/llm) скрипт импортирует внутри main(), поэтому
этот импорт не создаёт соединений и не требует env провайдера.
"""

import importlib.util
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "llm_smoke.py"


def _load_smoke():
    spec = importlib.util.spec_from_file_location("llm_smoke_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


smoke = _load_smoke()


def test_expected_case_status_by_mode() -> None:
    assert smoke._expected_case_status("echo") == "echo"
    assert smoke._expected_case_status("live") == "ok"
    assert smoke._expected_health_status("echo") == "echo"
    assert smoke._expected_health_status("live") == "ok"


def test_summarize_calls_aggregates_finops() -> None:
    rows = [
        SimpleNamespace(
            route="python_teacher.comment",
            status="echo",
            model_used="echo",
            tokens_in=0,
            tokens_out=0,
            cost_in=Decimal("0"),
            cost_out=None,
            latency_ms=5,
        ),
        SimpleNamespace(
            route="chess_lab.insight",
            status="ok",
            model_used="minimax/minimax-m3.1-flash",
            tokens_in=10,
            tokens_out=4,
            cost_in=Decimal("0.0100"),
            cost_out=Decimal("0.0025"),
            latency_ms=1200,
        ),
        {
            "route": "anticheat.judge_explain",
            "status": "ok",
            "model_used": "judge-model",
            "tokens_in": 1,
            "tokens_out": 1,
            "cost_in": "0.0010",
            "cost_out": None,
            "latency_ms": 9,
        },
    ]

    summary = smoke._summarize_calls(rows)

    assert summary["tokensIn"] == 11
    assert summary["tokensOut"] == 5
    assert summary["costTotal"] == "0.0135"
    assert len(summary["calls"]) == 3
    assert summary["calls"][0]["modelUsed"] == "echo"
    assert summary["calls"][0]["cost"] == "0.0000"
    assert summary["calls"][1]["cost"] == "0.0125"
    assert summary["calls"][2]["cost"] == "0.0010"


def test_compare_artifacts_echo_to_live() -> None:
    prev = {
        "schema": "chessclass.llm_smoke/1",
        "mode": "echo",
        "cases": [
            {"route": "a", "status": "echo", "modelUsed": "echo", "cost": "0.0000"},
            {"route": "b", "status": "echo", "modelUsed": "echo", "cost": "0.0000"},
        ],
        "finops": {"costTotal": "0.0000"},
    }
    cur = {
        "schema": "chessclass.llm_smoke/1",
        "mode": "live",
        "cases": [
            {"route": "a", "status": "ok", "modelUsed": "model-a", "cost": "0.0400"},
            {"route": "b", "status": "ok", "modelUsed": "model-b", "cost": "0.0600"},
        ],
        "finops": {"costTotal": "0.1000"},
    }

    diff = smoke._compare_artifacts(prev, cur)

    assert diff["comparable"] is True
    assert diff["totalRoutes"] == 2
    assert diff["routesChanged"] == 2
    assert diff["routesChangedModels"] == 2
    assert diff["prevCost"] == "0.0000"
    assert diff["curCost"] == "0.1000"
    assert "echo -> live" in diff["summary"]
    assert all(row["changed"] for row in diff["routes"])

    # Чужая/будущая схема: generic-сравнение без исключений.
    generic = smoke._compare_artifacts({"schema": "other", "foo": 1}, {"bar": 2})
    assert generic["comparable"] is False
    assert "generic" in generic["summary"]
    assert generic["addedKeys"] == ["bar"]
    assert generic["removedKeys"] == ["foo", "schema"]
