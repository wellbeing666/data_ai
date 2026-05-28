from fastapi import APIRouter

from app.core.config import get_settings


router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str | bool]:
    settings = get_settings()
    return {
        "status": "ok",
        "llm_mode": settings.llm_mode,
        "deepseek_configured": settings.is_deepseek_configured,
        "doubao_configured": settings.is_doubao_configured,
        "message": settings.llm_status,
    }
