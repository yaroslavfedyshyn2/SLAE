def estimate_wait(queued_ahead: int, running: int, workers: int, avg_seconds: float) -> int:
    """
    Оцінка очікування (у секундах, ціле число) для задачі в черзі.

    queued_ahead - скільки задач у статусі QUEUED стоїть перед цією
    running      - скільки задач зараз у статусі RUNNING
    workers      - кількість воркерів (має бути >= 1, інакше ValueError)
    avg_seconds  - середній час виконання однієї задачі

    Формула: (queued_ahead + running) / workers * avg_seconds
    """
    if workers < 1:
        raise ValueError("workers must be >= 1")
    seconds = (queued_ahead + running) / workers * avg_seconds
    return max(0, round(seconds))