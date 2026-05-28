from fastapi import APIRouter

from app.api.routes import analysis, datasets, health, knowledge, predictions, reports, sandbox, validation, workflows


api_router = APIRouter()
api_router.include_router(analysis.router)
api_router.include_router(datasets.router)
api_router.include_router(health.router)
api_router.include_router(knowledge.router)
api_router.include_router(predictions.router)
api_router.include_router(reports.router)
api_router.include_router(sandbox.router)
api_router.include_router(validation.router)
api_router.include_router(workflows.router)
