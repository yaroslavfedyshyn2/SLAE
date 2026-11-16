import contextlib
import logging
import os
import time
from datetime import datetime, timezone

import numpy as np
import redis

from app.celery_app import celery_app
from app.config import REDIS_URL, TASK_TIME_LIMIT, UPLOAD_DIR
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


def upload_path(task_id):
    return os.path.join(UPLOAD_DIR, f"{task_id}.txt")


def load_uploaded_system(task_id, n):
    """Читає розширену матрицю [A | b] із текстового файлу (пробіли або коми)."""
    path = upload_path(task_id)
    with open(path, "rb") as f:
        first = f.readline()
    delimiter = "," if b"," in first else None
    data = np.loadtxt(path, delimiter=delimiter, dtype=np.float64, ndmin=2)
    if data.shape != (n, n + 1):
        raise ValueError(f"Expected {n}x{n + 1} values (matrix A and column b), got {data.shape}")
    return data[:, :-1], data[:, -1]


def load_system(task):
    if task.source == "upload":
        return load_uploaded_system(task.id, task.n)
    return generate_system(task.id, task.n)


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

        is_upload = task.source == "upload"
        task.status = "RUNNING"
        task.started_at = _now()
        db.commit()

        try:
            A, b = load_system(task)

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
            if is_upload:
                with contextlib.suppress(FileNotFoundError):
                    os.remove(upload_path(task_id))
    finally:
        db.close()
        r.close()