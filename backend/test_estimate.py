from app.queue_estimate import estimate_wait

assert estimate_wait(0, 0, 1, 30) == 0      # попереду нікого
assert estimate_wait(0, 1, 1, 30) == 30     # чекаємо одну задачу, що рахується
assert estimate_wait(2, 1, 1, 30) == 90     # три задачі по 30 с
assert estimate_wait(3, 1, 2, 30) == 60     # 4 задачі на 2 воркерах
assert isinstance(estimate_wait(1, 0, 3, 10), int)  # 3.33 -> ціле

try:
    estimate_wait(1, 0, 0, 30)
except ValueError:
    pass
else:
    raise AssertionError("workers=0 має давати ValueError")

print("OK")
