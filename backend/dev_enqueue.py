import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Task, User
from app.tasks import solve_task

n = int(sys.argv[1]) if len(sys.argv) > 1 else 300

db = SessionLocal()
user = db.scalar(select(User).order_by(User.id))
if user is None:
    sys.exit("Немає користувачів: спершу зареєструйтесь через /auth/register")

task = Task(user_id=user.id, n=n, status="QUEUED", source="random")
db.add(task)
db.commit()
solve_task.delay(task.id)
print(f"task {task.id} n={n} queued")