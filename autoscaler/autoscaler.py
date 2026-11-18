import logging
import os
import time

import docker
import redis
import uuid
import json
import threading
from concurrent.futures import ThreadPoolExecutor

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "3"))             # разом з базовим воркером
INTERVAL = int(os.getenv("SCALE_INTERVAL", "5"))             # с між перевірками
SCALE_DOWN_AFTER = int(os.getenv("SCALE_DOWN_AFTER", "60"))  # с порожньої черги до зупинки одного воркера
UP_COOLDOWN = int(os.getenv("SCALE_UP_COOLDOWN", "15"))      # с паузи після запуску, щоб нові воркери встигли взяти задачі

QUEUE_KEY = "celery"      # назва черги Celery в Redis (список)
LABEL = "slae.autoscaled"  # мітка на контейнерах, які створив автоскейлер
STATS_KEY = "admin:containers"  
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("autoscaler")

client = docker.from_env()
r = redis.Redis.from_url(REDIS_URL)

# Власний контейнер: hostname = короткий id. Звідси беремо назву compose-проєкту.
me = client.containers.get(os.environ["HOSTNAME"])
project = me.labels["com.docker.compose.project"]


def base_workers():
    """Воркери, якими керує docker compose (сервіс worker)."""
    return client.containers.list(filters={"label": [
        f"com.docker.compose.project={project}",
        "com.docker.compose.service=worker",
    ]})


def extra_workers(all_states=False):
    """Додаткові воркери, створені автоскейлером."""
    return client.containers.list(all=all_states, filters={"label": f"{LABEL}={project}"})


def start_extra(template):
    """Запускає ще один воркер за зразком базового."""
    attrs = template.attrs
    cfg = attrs["Config"]
    network = list(attrs["NetworkSettings"]["Networks"])[0]
    mounts = [
        docker.types.Mount(target=m["Destination"], source=m["Name"], type="volume")
        for m in attrs["Mounts"]
        if m["Type"] == "volume"
    ]
    name = f"{project}-worker-auto-{uuid.uuid4().hex[:8]}"
    client.containers.run(
        image=cfg["Image"],
        command=cfg["Cmd"],
        environment=cfg["Env"],
        network=network,
        mounts=mounts,
        labels={LABEL: project},
        name=name,
        detach=True,
    )
    log.info("started %s", name)

def container_stats(c):
    """Один знімок CPU % і пам'яті контейнера."""
    s = c.stats(stream=False)
    cpu_total = s["cpu_stats"]["cpu_usage"]["total_usage"]
    cpu_prev = s["precpu_stats"].get("cpu_usage", {}).get("total_usage", 0)
    sys_total = s["cpu_stats"].get("system_cpu_usage", 0)
    sys_prev = s["precpu_stats"].get("system_cpu_usage", 0)
    cpus = s["cpu_stats"].get("online_cpus") or 1
    cpu = 0.0
    if sys_total > sys_prev and cpu_total >= cpu_prev:
        cpu = (cpu_total - cpu_prev) / (sys_total - sys_prev) * cpus * 100
    mem = s["memory_stats"]
    inner = mem.get("stats", {})
    cache = inner.get("inactive_file", inner.get("cache", 0))
    used = mem.get("usage", 0) - cache
    return {
        "name": c.name,
        "service": c.labels.get("com.docker.compose.service") or "worker-auto",
        "cpu_percent": round(cpu, 1),
        "mem_mb": round(used / 1024 / 1024, 1),
        "mem_limit_mb": round(mem.get("limit", 0) / 1024 / 1024),
    }


def safe_stats(c):
    try:
        return container_stats(c)
    except Exception:
        return None  # контейнер міг зупинитись просто зараз


def stats_loop():
    """Раз на INTERVAL кладе навантаження всіх контейнерів проєкту в Redis."""
    while True:
        try:
            containers = client.containers.list(
                filters={"label": f"com.docker.compose.project={project}"}
            ) + extra_workers()
            with ThreadPoolExecutor(max_workers=8) as pool:
                result = [x for x in pool.map(safe_stats, containers) if x]
            r.set(STATS_KEY, json.dumps(result), ex=30)
        except Exception:
            log.exception("stats iteration failed")
        time.sleep(INTERVAL)
def main():
    draining = set()   # id воркерів, яким вже надіслано SIGTERM
    empty_since = None
    last_up = 0.0
    log.info("autoscaler started: MAX_WORKERS=%s", MAX_WORKERS)
    threading.Thread(target=stats_loop, daemon=True).start()
    while True:
        try:
            # Прибираємо завершені додаткові контейнери
            for c in extra_workers(all_states=True):
                if c.status != "running":
                    log.info("removing %s (%s)", c.name, c.status)
                    c.remove()
                    draining.discard(c.id)

            base = base_workers()
            running_extra = extra_workers()
            active = [c for c in running_extra if c.id not in draining]
            total = len(base) + len(running_extra)   # зупинні теж займають пам'ять
            queued = r.llen(QUEUE_KEY)
            now = time.monotonic()

            if queued > 0:
                empty_since = None
                if base and total < MAX_WORKERS and now - last_up >= UP_COOLDOWN:
                    count = min(queued, MAX_WORKERS - total)
                    log.info("queue=%s workers=%s -> +%s", queued, total, count)
                    for _ in range(count):
                        start_extra(base[0])
                    last_up = now
            else:
                if empty_since is None:
                    empty_since = now
                elif now - empty_since >= SCALE_DOWN_AFTER and active:
                    victim = active[0]
                    log.info("queue empty, stopping %s", victim.name)
                    victim.kill(signal="SIGTERM")   # м'яка зупинка: Celery дорахує поточну задачу
                    draining.add(victim.id)
                    empty_since = now               # наступного зупиняємо ще через SCALE_DOWN_AFTER
        except Exception:
            log.exception("autoscaler iteration failed")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()