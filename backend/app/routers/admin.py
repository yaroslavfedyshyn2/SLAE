import json
import redis
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import REDIS_URL
from app.database import get_db
from app.deps import get_current_admin
from app.models import Task, User

router = APIRouter(prefix="/admin", tags=["admin"])

redis_client = redis.Redis.from_url(REDIS_URL)

STATUSES = ("QUEUED", "RUNNING", "DONE", "FAILED", "CANCELLED")


@router.get("/overview")
def overview(
    admin: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    # 1. Скільки задач у кожному статусі (за всіма користувачами)
    rows = db.execute(select(Task.status, func.count()).group_by(Task.status)).all()
    counts = {s: 0 for s in STATUSES}
    counts.update({status: n for status, n in rows})

    # 2. Задачі, що рахуються зараз
    running = db.execute(
        select(Task, User.username)
        .join(User, User.id == Task.user_id)
        .where(Task.status == "RUNNING")
        .order_by(Task.id)
    ).all()

    # 3. Довжина черги Celery в Redis (повідомлення, які ще ніхто не взяв)
    try:
        queue_length = redis_client.llen("celery")
    except redis.RedisError:
        queue_length = None

    # 4. Живі воркери (ping чекає відповіді до 1 с)
    try:
        pong = celery_app.control.inspect(timeout=1).ping() or {}
        workers = sorted(pong.keys())
    except Exception:
        workers = None
        # 5. Навантаження контейнерів (його кладе автоскейлер)
    try:
        raw = redis_client.get("admin:containers")
        containers = json.loads(raw) if raw else []
    except redis.RedisError:
        containers = None
    return {
        "tasks": counts,
        "queue_length": queue_length,
        "workers": workers,
        "containers": containers,
        "running": [
            {
                "task_id": t.id,
                "username": username,
                "n": t.n,
                "progress": t.progress,
                "started_at": t.started_at,
            }
            for t, username in running
        ],
    }