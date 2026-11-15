import os

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+psycopg2://slae:slae@postgres:5432/slae"
)
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
TASK_TIME_LIMIT = int(os.getenv("TASK_TIME_LIMIT", "600"))  