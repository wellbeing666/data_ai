from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router


app = FastAPI(
    title="AI Native Data Analysis Workbench API",
    description="Minimal backend skeleton for an AI native data analysis workbench.",
    version="0.1.0",
)

app.include_router(api_router)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")
