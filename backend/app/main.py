import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/whoami")
def whoami():
    return {"instance": os.getenv("INSTANCE_NAME", "unknown")}