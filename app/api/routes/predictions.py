from fastapi import APIRouter, BackgroundTasks

from app.schemas.prediction import (
    PredictionJobRequest,
    PredictionJobResponse,
    PredictionLogResponse,
)
from app.services.prediction_workflow import (
    create_prediction_job_record,
    get_prediction_job_log,
    get_prediction_job_status,
    run_prediction_job_background,
)


router = APIRouter(prefix="/api/predictions", tags=["predictions"])


@router.post("/jobs/async", response_model=PredictionJobResponse)
def create_prediction_job_async(
    request: PredictionJobRequest,
    background_tasks: BackgroundTasks,
) -> PredictionJobResponse:
    result = create_prediction_job_record(
        dataset_id=request.dataset_id,
        user_goal=request.user_goal,
        max_retries=request.max_retries,
        timeout_seconds=request.timeout_seconds,
    )
    background_tasks.add_task(
        run_prediction_job_background,
        result["job_id"],
        request.dataset_id,
        request.user_goal,
        request.max_retries,
        request.timeout_seconds,
    )
    return PredictionJobResponse(**result)


@router.get("/jobs/{job_id}", response_model=PredictionJobResponse)
def read_prediction_job_status(job_id: str) -> PredictionJobResponse:
    return PredictionJobResponse(**get_prediction_job_status(job_id))


@router.get("/jobs/{job_id}/logs", response_model=PredictionLogResponse)
def read_prediction_job_logs(job_id: str) -> PredictionLogResponse:
    return PredictionLogResponse(**get_prediction_job_log(job_id))
