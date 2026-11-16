import asyncio
import contextlib
import json
import logging

import redis
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool

from app.config import REDIS_URL
from app.database import SessionLocal
from app.models import Task, User
from app.security import decode_access_token

log = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

AUTH_TIMEOUT = 5  # с на те, щоб клієнт надіслав токен
HEARTBEAT = 10  # с без подій: перечитуємо стан із БД і шлемо його клієнтові
FINAL_STATUSES = ("DONE", "FAILED", "CANCELLED")

WS_UNAUTHORIZED = 4401
WS_NOT_FOUND = 4404


def _event(task: Task) -> dict:
    # Той самий формат, що публікує воркер (app.tasks._publish)
    return {
        "status": task.status,
        "progress": task.progress,
        "current_row": task.current_row,
        "n": task.n,
        "error": task.error,
    }


def _load(task_id: int, user_id: int):
    """(код_закриття, подія). Код не None — клієнта треба відхилити."""
    with SessionLocal() as db:
        if db.get(User, user_id) is None:
            return WS_UNAUTHORIZED, None
        task = db.get(Task, task_id)
        if task is None or task.user_id != user_id:
            return WS_NOT_FOUND, None
        return None, _event(task)


async def _close(ws: WebSocket, code: int) -> None:
    with contextlib.suppress(RuntimeError, WebSocketDisconnect):
        await ws.close(code)


@router.websocket("/ws/tasks/{task_id}")
async def task_progress(ws: WebSocket, task_id: int):
    await ws.accept()

    # Браузерний WebSocket не вміє слати заголовок Authorization, а токен у URL
    # потрапляє в логи nginx. Тому перше повідомлення від клієнта: {"token": "..."}.
    try:
        msg = await asyncio.wait_for(ws.receive_json(), AUTH_TIMEOUT)
        token = msg.get("token") if isinstance(msg, dict) else None
    except (asyncio.TimeoutError, ValueError, KeyError):
        await _close(ws, WS_UNAUTHORIZED)
        return
    except WebSocketDisconnect:
        return

    user_id = decode_access_token(token) if isinstance(token, str) else None
    if user_id is None:
        await _close(ws, WS_UNAUTHORIZED)
        return

    r = aioredis.Redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    try:
        # Спершу підписка, потім знімок з БД: подія, що прилетить між ними,
        # не загубиться (у гіршому разі прийде дубль, що не шкодить).
        await pubsub.subscribe(f"task:{task_id}")
        code, event = await run_in_threadpool(_load, task_id, user_id)
        if code:
            await _close(ws, code)
            return
        await ws.send_json(event)

        while event["status"] not in FINAL_STATUSES:
            message = await pubsub.get_message(timeout=HEARTBEAT)
            if message is None:
                # Справжня тиша (таймаут): страхуємось від втраченої події
                # (Redis моргнув) і заодно тримаємо з'єднання живим для nginx.
                code, event = await run_in_threadpool(_load, task_id, user_id)
                if code:
                    await _close(ws, code)
                    return
            elif message["type"] == "message":
                event = json.loads(message["data"])
            else:
                continue  # службове підтвердження підписки, не подія
            await ws.send_json(event)

        await _close(ws, 1000)
    except WebSocketDisconnect:
        pass
    except redis.RedisError:
        log.warning("redis error in websocket of task %s", task_id, exc_info=True)
        await _close(ws, 1011)
    finally:
        for obj in (pubsub, r):
            closer = getattr(obj, "aclose", None) or obj.close
            with contextlib.suppress(Exception):
                await closer()