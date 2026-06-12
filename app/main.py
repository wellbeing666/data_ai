from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.services.auth_service import init_auth_storage


def _ensure_storage_dirs() -> None:
    Path("storage").mkdir(parents=True, exist_ok=True)
    Path("storage/uploads").mkdir(parents=True, exist_ok=True)
    Path("storage/jobs").mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_auth_storage()
    _ensure_storage_dirs()
    yield


app = FastAPI(
    title="AI Native Data Analysis Workbench API",
    description="Minimal backend skeleton for an AI native data analysis workbench.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")
