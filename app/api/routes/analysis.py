from fastapi import APIRouter, BackgroundTasks

from app.schemas.analysis import (
    AnalysisJobRequest,
    AnalysisJobResponse,
    AutoRepairAnalysisJobRequest,
    AutoRepairAnalysisJobResponse,
    ExecutionLogResponse,
)
from app.services.auto_repair_analysis import (
    create_auto_repair_job_record,
    get_auto_repair_job_status,
    run_auto_repair_analysis_job,
    run_auto_repair_analysis_job_background,
)
from app.services.execution_log_service import get_execution_log
from app.services.grade_analysis import create_grade_analysis_job


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/jobs", response_model=AnalysisJobResponse)
def create_analysis_job(request: AnalysisJobRequest) -> AnalysisJobResponse:
    result = create_grade_analysis_job(
        dataset_id=request.dataset_id,
        user_goal=request.user_goal,
    )
    return AnalysisJobResponse(**result)


@router.post("/auto-repair-jobs", response_model=AutoRepairAnalysisJobResponse)
def create_auto_repair_analysis_job(
    request: AutoRepairAnalysisJobRequest,
) -> AutoRepairAnalysisJobResponse:
    result = run_auto_repair_analysis_job(
        dataset_id=request.dataset_id,
        user_goal=request.user_goal,
        max_retries=request.max_retries,
        timeout_seconds=request.timeout_seconds,
    )
    return AutoRepairAnalysisJobResponse(**result)


@router.post("/auto-repair-jobs/async", response_model=AutoRepairAnalysisJobResponse)
def create_auto_repair_analysis_job_async(
    request: AutoRepairAnalysisJobRequest,
    background_tasks: BackgroundTasks,
) -> AutoRepairAnalysisJobResponse:
    result = create_auto_repair_job_record(
        dataset_id=request.dataset_id,
        user_goal=request.user_goal,
        max_retries=request.max_retries,
        timeout_seconds=request.timeout_seconds,
    )
    background_tasks.add_task(
        run_auto_repair_analysis_job_background,
        result["job_id"],
        request.dataset_id,
        request.user_goal,
        request.max_retries,
        request.timeout_seconds,
    )
    return AutoRepairAnalysisJobResponse(**result)


@router.get("/auto-repair-jobs/{job_id}", response_model=AutoRepairAnalysisJobResponse)
def read_auto_repair_analysis_job_status(job_id: str) -> AutoRepairAnalysisJobResponse:
    return AutoRepairAnalysisJobResponse(**get_auto_repair_job_status(job_id))


@router.get("/jobs/{job_id}/logs", response_model=ExecutionLogResponse)
def read_analysis_job_logs(job_id: str) -> ExecutionLogResponse:
    return ExecutionLogResponse(**get_execution_log(job_id))
