import logging
import time
from datetime import datetime, timezone

import numpy as np
import redis

from app.celery_app import celery_app
from app.config import REDIS_URL, TASK_TIME_LIMIT
from app.database import SessionLocal
from app.models import Task
from app.solver import SingularMatrix, SolverCancelled, solve_gauss

log = logging.getLogger(__name__)

CANCEL_CHECK_EVERY = 20  # перевіряти прапорець скасування раз на N рядків


def _now():
    return datetime.now(timezone.utc)


def generate_system(task_id, n):
    """Випадкова система. Seed = id задачі, тож результат відтворюваний."""
    rng = np.random.default_rng(task_id)
    return rng.random((n, n)), rng.random(n)


def _finish(db, task, status, error=None, progress=None):
    db.rollback()  # на випадок, якщо виняток перервав попередній commit
    task.status = status
    task.error = error
    task.finished_at = _now()
    if progress is not None:
        task.progress = progress
    db.commit()


@celery_app.task(name="ping")
def ping(x):
    return f"pong {x}"


@celery_app.task(name="solve_task")
def solve_task(task_id):
    r = redis.Redis.from_url(REDIS_URL)
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        if task is None or task.status != "QUEUED":
            return  # задачі немає, або її вже скасовано/виконано

        task.status = "RUNNING"
        task.started_at = _now()
        db.commit()

        try:
            A, b = generate_system(task_id, task.n)

            # Ліміт часу перевіряємо тут, а не через Celery soft_time_limit:
            # Celery бере ліміт з боку відправника задачі, і він міг би
            # перекрити налаштування воркера.
            deadline = time.monotonic() + TASK_TIME_LIMIT
            state = {"calls": 0, "timed_out": False}

            def should_cancel():
                if time.monotonic() > deadline:
                    state["timed_out"] = True
                    return True
                state["calls"] += 1
                if state["calls"] % CANCEL_CHECK_EVERY != 1:
                    return False
                return bool(r.exists(f"cancel:{task_id}"))

            def on_progress(row, n):
                task.current_row = row
                task.progress = round(100.0 * row / n, 1)
                db.commit()

            solve_gauss(A, b, on_progress=on_progress, should_cancel=should_cancel)
            _finish(db, task, "DONE", progress=100.0)

        except SolverCancelled:
            if state["timed_out"]:
                _finish(db, task, "FAILED", f"Time limit exceeded ({TASK_TIME_LIMIT} s)")
            else:
                _finish(db, task, "CANCELLED")
        except SingularMatrix:
            _finish(db, task, "FAILED", "Matrix is singular: no unique solution")
        except Exception as exc:
            log.exception("solve_task %s failed", task_id)
            _finish(db, task, "FAILED", f"{type(exc).__name__}: {exc}")
        finally:
            r.delete(f"cancel:{task_id}")
    finally:
        db.close()
        r.close()