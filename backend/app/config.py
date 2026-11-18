import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://slae:slae@postgres:5432/slae"
)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TASK_TIME_LIMIT = int(os.getenv("TASK_TIME_LIMIT", "600"))  
MAX_N = int(os.getenv("MAX_N", "5000"))
MAX_ACTIVE_TASKS = int(os.getenv("MAX_ACTIVE_TASKS", "5"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "300")) * 1024 * 1024
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/data/uploads")
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "1"))
DEFAULT_AVG_SECONDS = float(os.getenv("DEFAULT_AVG_SECONDS", "30"))