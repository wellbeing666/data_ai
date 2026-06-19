from contextlib import asynccontextmanager
import asyncio
import logging
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.services.auth_service import init_auth_storage


logger = logging.getLogger(__name__)


def _ensure_storage_dirs() -> None:
    Path("storage").mkdir(parents=True, exist_ok=True)
    Path("storage/uploads").mkdir(parents=True, exist_ok=True)
    Path("storage/jobs").mkdir(parents=True, exist_ok=True)


def _startup_auth_timeout_seconds() -> int:
    try:
        return max(1, int(get_settings().startup_auth_init_timeout))
    except Exception:
        return 12


async def _init_auth_storage_for_startup() -> None:
    timeout_seconds = _startup_auth_timeout_seconds()
    result_queue: Queue[tuple[str, Any]] = Queue(maxsize=1)

    def runner() -> None:
        try:
            init_auth_storage()
        except Exception as exc:
            result_queue.put(("error", exc))
        else:
            result_queue.put(("ok", None))

    worker = Thread(target=runner, name="auth-storage-init", daemon=True)
    worker.start()
    await asyncio.to_thread(worker.join, timeout_seconds)

    if worker.is_alive():
        logger.error("认证存储初始化超时，服务已继续启动；认证相关接口将在数据库恢复后重试。")
        return

    try:
        status, payload = result_queue.get_nowait()
    except Empty:
        return

    if status == "error":
        logger.error("认证存储初始化失败，服务已继续启动；认证相关接口将在数据库恢复后重试：%s", payload)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _ensure_storage_dirs()
    await _init_auth_storage_for_startup()
    yield


app = FastAPI(
    title="AI Native Data Analysis Workbench API",
    description="Minimal backend skeleton for an AI native data analysis workbench.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router)
app.mount("/storage", StaticFiles(directory="storage"), name="storage")
