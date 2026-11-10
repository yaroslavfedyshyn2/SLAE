import os
import os

from fastapi import FastAPI

from app.routers import auth

app = FastAPI(root_path="/api")
app.include_router(auth.router)


@app.get("/whoami")
def whoami():
    return {"instance": os.getenv("INSTANCE_NAME", "unknown")}