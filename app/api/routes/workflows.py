from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query

from app.schemas.workflow import WorkflowJobRequest, WorkflowJobResponse, WorkflowLogResponse
from app.services.workflow_service import (
    create_workflow_job_record,
    delete_workflow_chart,
    get_workflow_job_log,
    get_workflow_job_status,
    run_workflow_job_background,
)


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("/jobs/async", response_model=WorkflowJobResponse)
def create_workflow_job_async(
    request: WorkflowJobRequest,
    background_tasks: BackgroundTasks,
) -> WorkflowJobResponse:
    result = create_workflow_job_record(
        dataset_id=request.dataset_id,
        user_goal=request.user_goal,
        max_retries=request.max_retries,
        timeout_seconds=request.timeout_seconds,
    )
    background_tasks.add_task(
        run_workflow_job_background,
        result["job_id"],
        request.dataset_id,
        request.user_goal,
        request.max_retries,
        request.timeout_seconds,
    )
    return WorkflowJobResponse(**result)


@router.get("/jobs/{job_id}", response_model=WorkflowJobResponse)
def read_workflow_job_status(job_id: str) -> WorkflowJobResponse:
    return WorkflowJobResponse(**get_workflow_job_status(job_id))


@router.get("/jobs/{job_id}/logs", response_model=WorkflowLogResponse)
def read_workflow_job_logs(job_id: str) -> WorkflowLogResponse:
    return WorkflowLogResponse(**get_workflow_job_log(job_id))


@router.delete("/jobs/{job_id}/charts")
def remove_workflow_chart(
    job_id: str,
    chart_path: str = Query(..., min_length=1),
) -> dict[str, Any]:
    return delete_workflow_chart(job_id, chart_path)
