from celery import Celery

from app.config import REDIS_URL

celery_app = Celery("slae", broker=REDIS_URL, include=["app.tasks"])

celery_app.conf.update(
    task_ignore_result=True,          # результати не зберігаємо: статус живе в Postgres
    worker_prefetch_multiplier=1,     # воркер бере одну задачу, а не набирає чергу наперед
)