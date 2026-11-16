import os
import shutil

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import MAX_ACTIVE_TASKS, MAX_N, MAX_UPLOAD_BYTES, UPLOAD_DIR
from app.database import get_db
from app.deps import get_current_user
from app.models import Task, User
from app.schemas import TaskCreate, TaskOut
from app.tasks import solve_task, upload_path

router = APIRouter(prefix="/tasks", tags=["tasks"])

ACTIVE_STATUSES = ("QUEUED", "RUNNING")


def check_n(n: int) -> None:
    if n < 1 or n > MAX_N:
        raise HTTPException(400, f"n must be between 1 and {MAX_N}")


def check_active_limit(db: Session, user: User) -> None:
    active = db.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.user_id == user.id, Task.status.in_(ACTIVE_STATUSES))
    )
    if active >= MAX_ACTIVE_TASKS:
        raise HTTPException(
            429, f"Too many active tasks (max {MAX_ACTIVE_TASKS}). Wait for one to finish."
        )


def inspect_matrix_file(f) -> int:
    """Дешева перевірка без повного парсингу: рахуємо рядки й стовпці.
    Очікується n рядків по n+1 число (матриця A і стовпець b). Повертає n."""
    f.seek(0)
    rows, cols = 0, None
    for raw in f:
        line = raw.strip()
        if not line:
            continue
        count = len(line.replace(b",", b" ").split())
        if cols is None:
            cols = count
        elif count != cols:
            raise HTTPException(400, f"Row {rows + 1} has {count} values, expected {cols}")
        rows += 1
        if rows > MAX_N:
            raise HTTPException(400, f"Matrix is larger than the limit of {MAX_N} unknowns")
    if rows == 0:
        raise HTTPException(400, "File is empty")
    if cols != rows + 1:
        raise HTTPException(
            400,
            f"Expected {rows} rows of {rows + 1} values (matrix A and column b), "
            f"got {rows} rows of {cols}",
        )
    return rows


def enqueue(db: Session, task: Task) -> None:
    try:
        solve_task.delay(task.id)
    except Exception:
        task.status = "FAILED"
        task.error = "Task queue is unavailable"
        task.finished_at = func.now()
        db.commit()
        raise HTTPException(503, "Task queue is unavailable, try again later")


@router.post("", response_model=TaskOut, status_code=201)
def create_task(
    data: TaskCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_n(data.n)
    check_active_limit(db, user)
    task = Task(user_id=user.id, n=data.n, source="random", status="QUEUED")
    db.add(task)
    db.commit()
    db.refresh(task)
    enqueue(db, task)
    return task


@router.post("/upload", response_model=TaskOut, status_code=201)
def upload_task(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    check_active_limit(db, user)
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File is too large (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)")

    n = inspect_matrix_file(file.file)

    task = Task(user_id=user.id, n=n, source="upload", status="QUEUED")
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        file.file.seek(0)
        with open(upload_path(task.id), "wb") as out:
            shutil.copyfileobj(file.file, out, 1024 * 1024)
    except OSError:
        task.status = "FAILED"
        task.error = "Could not store the uploaded file"
        task.finished_at = func.now()
        db.commit()
        raise HTTPException(500, "Could not store the uploaded file")

    enqueue(db, task)
    return task


@router.get("/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise HTTPException(404, "Task not found")
    return task