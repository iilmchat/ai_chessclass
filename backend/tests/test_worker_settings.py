"""Регресс S-30: worker-настройки должны импортироваться без ошибок.

До фикса cron-путь был ``"scores_recalc"`` — arq пытался импортировать его
как модуль и worker падал в рестарт-луп, оставляя analyze/matches/PDF без
исполнителя. Тест импортирует WorkerSettings (побочный эффект — проверка
cron-пути) и сверяет имена зарегистрированных задач.
"""

from app.worker import WorkerSettings


def test_worker_settings_import_and_cron() -> None:
    names = {fn.__name__ for fn in WorkerSettings.functions}
    assert {"heartbeat", "analyze_position", "analyze_game", "scores_recalc", "run_match"} <= names

    cron_names = {
        getattr(job.coroutine, "__name__", str(job.coroutine))
        for job in WorkerSettings.cron_jobs
    }
    assert "scores_recalc" in cron_names
