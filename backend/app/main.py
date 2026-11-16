import os

from fastapi import FastAPI

from app.routers import auth, tasks

app = FastAPI(root_path="/api")
app.include_router(auth.router)
app.include_router(tasks.router)


@app.get("/whoami")
def whoami():
    return {"instance": os.getenv("INSTANCE_NAME", "unknown")}