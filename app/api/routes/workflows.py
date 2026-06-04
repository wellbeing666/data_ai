from typing import Any

from fastapi import APIRouter, BackgroundTasks, Query

from app.schemas.workflow import (
    ChartConfigRequest,
    ChartConfigResponse,
    ChartRefineRequest,
    ChartRefineResponse,
    ChartSuggestionResponse,
    WorkflowJobDeleteResponse,
    WorkflowJobListResponse,
    WorkflowJobRequest,
    WorkflowJobResponse,
    WorkflowLogResponse,
    WorkflowPreflightRequest,
    WorkflowPreflightResponse,
)
from app.services.workflow_service import (
    create_workflow_chart_config,
    create_workflow_chart_suggestions,
    create_workflow_job_record,
    create_workflow_preflight,
    delete_workflow_chart,
    delete_workflow_job,
    get_workflow_job_log,
    get_workflow_job_status,
    list_workflow_jobs,
    refine_workflow_chart,
    run_workflow_job_background,
)


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


@router.post("/preflight", response_model=WorkflowPreflightResponse)
def create_preflight(request: WorkflowPreflightRequest) -> WorkflowPreflightResponse:
    result = create_workflow_preflight(dataset_id=request.dataset_id, user_goal=request.user_goal)
    return WorkflowPreflightResponse(**result)


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


@router.get("/jobs", response_model=WorkflowJobListResponse)
def read_workflow_job_list(
    limit: int = Query(default=30, ge=1, le=100),
    query: str | None = Query(default=None, max_length=100),
) -> WorkflowJobListResponse:
    return WorkflowJobListResponse(**list_workflow_jobs(limit=limit, query=query))


@router.get("/jobs/{job_id}", response_model=WorkflowJobResponse)
def read_workflow_job_status(job_id: str) -> WorkflowJobResponse:
    return WorkflowJobResponse(**get_workflow_job_status(job_id))


@router.get("/jobs/{job_id}/logs", response_model=WorkflowLogResponse)
def read_workflow_job_logs(job_id: str) -> WorkflowLogResponse:
    return WorkflowLogResponse(**get_workflow_job_log(job_id))


@router.post("/jobs/{job_id}/chart-config", response_model=ChartConfigResponse)
def create_job_chart_config(job_id: str, request: ChartConfigRequest) -> ChartConfigResponse:
    result = create_workflow_chart_config(
        job_id=job_id,
        instruction=request.instruction,
        current_config=request.current_config,
    )
    return ChartConfigResponse(**result)


@router.get("/jobs/{job_id}/chart-suggestions", response_model=ChartSuggestionResponse)
def read_job_chart_suggestions(
    job_id: str,
    chart_path: str = Query(..., min_length=1),
) -> ChartSuggestionResponse:
    result = create_workflow_chart_suggestions(job_id=job_id, chart_path=chart_path)
    return ChartSuggestionResponse(**result)


@router.post("/jobs/{job_id}/chart-refine", response_model=ChartRefineResponse)
def refine_job_chart(job_id: str, request: ChartRefineRequest) -> ChartRefineResponse:
    result = refine_workflow_chart(
        job_id=job_id,
        chart_path=request.chart_path,
        instruction=request.instruction,
    )
    return ChartRefineResponse(**result)


@router.delete("/jobs/{job_id}", response_model=WorkflowJobDeleteResponse)
def remove_workflow_job(job_id: str) -> WorkflowJobDeleteResponse:
    return WorkflowJobDeleteResponse(**delete_workflow_job(job_id))


@router.delete("/jobs/{job_id}/charts")
def remove_workflow_chart(
    job_id: str,
    chart_path: str = Query(..., min_length=1),
) -> dict[str, Any]:
    return delete_workflow_chart(job_id, chart_path)


