from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.agents.insight_mining_agent import DEFAULT_INSIGHT_GOAL
from app.schemas.workflow import (
    ChartConfigRequest,
    ChartConfigResponse,
    DashboardConfigResponse,
    DashboardConfigUpdateRequest,
    ChartRefineRequest,
    ChartRefineResponse,
    ChartSuggestionResponse,
    WorkflowControlRequest,
    WorkflowControlResponse,
    WorkflowFollowUpRequest,
    WorkflowFollowUpResponse,
    WorkflowJobDeleteResponse,
    WorkflowJobListResponse,
    WorkflowJobRequest,
    WorkflowJobResponse,
    WorkflowLogResponse,
    WorkflowPptxGenerateResponse,
    WorkflowPreflightRequest,
    WorkflowPreflightResponse,
)
from app.services.auth_service import get_current_user
from app.services.workflow_service import (
    create_workflow_chart_config,
    create_workflow_chart_suggestions,
    control_workflow_job,
    create_workflow_follow_up,
    create_workflow_job_record,
    create_workflow_preflight,
    delete_workflow_chart,
    delete_workflow_job,
    get_workflow_dashboard,
    get_shared_workflow_dashboard,
    get_workflow_job_log,
    generate_workflow_pptx,
    get_workflow_job_status,
    list_workflow_jobs,
    refine_workflow_chart,
    refresh_workflow_dashboard,
    share_workflow_dashboard,
    update_workflow_dashboard,
    rerun_workflow_job_background,
    run_workflow_job_background,
)


router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _is_admin(user: dict[str, Any]) -> bool:
    return str(user.get("role") or "") == "admin"


def _ensure_job_access(job_id: str, user: dict[str, Any]) -> dict[str, Any]:
    status_data = get_workflow_job_status(job_id)
    owner_user_id = str(status_data.get("owner_user_id") or "") or None
    if owner_user_id and owner_user_id != str(user.get("id")) and not _is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能访问其他用户的分析记录。")
    return status_data


@router.post("/preflight", response_model=WorkflowPreflightResponse)
def create_preflight(
    request: WorkflowPreflightRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowPreflightResponse:
    result = create_workflow_preflight(dataset_id=request.dataset_id, user_goal=request.user_goal, owner_user_id=str(current_user.get("id")))
    return WorkflowPreflightResponse(**result)


@router.post("/jobs/async", response_model=WorkflowJobResponse)
def create_workflow_job_async(
    request: WorkflowJobRequest,
    background_tasks: BackgroundTasks,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowJobResponse:
    effective_goal = DEFAULT_INSIGHT_GOAL if request.insight_mode else str(request.user_goal or "").strip()
    if not effective_goal:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请输入分析目标，或选择智能洞察模式。")
    result = create_workflow_job_record(
        dataset_id=request.dataset_id,
        user_goal=effective_goal,
        max_retries=request.max_retries,
        timeout_seconds=request.timeout_seconds,
        owner_user_id=str(current_user.get("id")),
    )
    background_tasks.add_task(
        run_workflow_job_background,
        result["job_id"],
        request.dataset_id,
        effective_goal,
        request.max_retries,
        request.timeout_seconds,
        str(current_user.get("id")),
    )
    return WorkflowJobResponse(**result)


@router.get("/jobs", response_model=WorkflowJobListResponse)
def read_workflow_job_list(
    limit: int = Query(default=30, ge=1, le=100),
    query: str | None = Query(default=None, max_length=100),
    include_all: bool = Query(default=False),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowJobListResponse:
    result = list_workflow_jobs(
        limit=limit,
        query=query,
        owner_user_id=str(current_user.get("id")),
        include_all=include_all and _is_admin(current_user),
    )
    return WorkflowJobListResponse(**result)


@router.get("/jobs/{job_id}", response_model=WorkflowJobResponse)
def read_workflow_job_status(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowJobResponse:
    return WorkflowJobResponse(**_ensure_job_access(job_id, current_user))


@router.post("/jobs/{job_id}/control", response_model=WorkflowControlResponse)
def control_job(
    job_id: str,
    request: WorkflowControlRequest,
    background_tasks: BackgroundTasks,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowControlResponse:
    _ensure_job_access(job_id, current_user)
    result = control_workflow_job(job_id=job_id, action=request.action)
    background_action = result.pop("background_action", None)
    if background_action:
        background_tasks.add_task(rerun_workflow_job_background, job_id, str(background_action))
    return WorkflowControlResponse(**result)


@router.post("/jobs/{job_id}/pptx", response_model=WorkflowPptxGenerateResponse)
def generate_job_pptx(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowPptxGenerateResponse:
    _ensure_job_access(job_id, current_user)
    result = generate_workflow_pptx(job_id=job_id)
    return WorkflowPptxGenerateResponse(**result)


@router.post("/jobs/{job_id}/follow-up", response_model=WorkflowFollowUpResponse)
def create_job_follow_up(
    job_id: str,
    request: WorkflowFollowUpRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowFollowUpResponse:
    _ensure_job_access(job_id, current_user)
    result = create_workflow_follow_up(job_id=job_id, question=request.question)
    return WorkflowFollowUpResponse(**result)


@router.get("/jobs/{job_id}/dashboard", response_model=DashboardConfigResponse)
def read_job_dashboard(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DashboardConfigResponse:
    _ensure_job_access(job_id, current_user)
    return DashboardConfigResponse(**get_workflow_dashboard(job_id))


@router.put("/jobs/{job_id}/dashboard", response_model=DashboardConfigResponse)
def save_job_dashboard(
    job_id: str,
    request: DashboardConfigUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DashboardConfigResponse:
    _ensure_job_access(job_id, current_user)
    return DashboardConfigResponse(**update_workflow_dashboard(job_id, request.dashboard))


@router.post("/jobs/{job_id}/dashboard/refresh", response_model=DashboardConfigResponse)
def refresh_job_dashboard(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DashboardConfigResponse:
    _ensure_job_access(job_id, current_user)
    return DashboardConfigResponse(**refresh_workflow_dashboard(job_id))


@router.post("/jobs/{job_id}/dashboard/share", response_model=DashboardConfigResponse)
def share_job_dashboard(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DashboardConfigResponse:
    _ensure_job_access(job_id, current_user)
    return DashboardConfigResponse(**share_workflow_dashboard(job_id))


@router.get("/jobs/{job_id}/dashboard/shared/{token}")
def read_shared_job_dashboard(job_id: str, token: str) -> dict[str, Any]:
    return get_shared_workflow_dashboard(job_id, token)


@router.get("/jobs/{job_id}/logs", response_model=WorkflowLogResponse)
def read_workflow_job_logs(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowLogResponse:
    _ensure_job_access(job_id, current_user)
    return WorkflowLogResponse(**get_workflow_job_log(job_id))


@router.post("/jobs/{job_id}/chart-config", response_model=ChartConfigResponse)
def create_job_chart_config(
    job_id: str,
    request: ChartConfigRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ChartConfigResponse:
    _ensure_job_access(job_id, current_user)
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
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ChartSuggestionResponse:
    _ensure_job_access(job_id, current_user)
    result = create_workflow_chart_suggestions(job_id=job_id, chart_path=chart_path)
    return ChartSuggestionResponse(**result)


@router.post("/jobs/{job_id}/chart-refine", response_model=ChartRefineResponse)
def refine_job_chart(
    job_id: str,
    request: ChartRefineRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> ChartRefineResponse:
    _ensure_job_access(job_id, current_user)
    result = refine_workflow_chart(
        job_id=job_id,
        chart_path=request.chart_path,
        instruction=request.instruction,
    )
    return ChartRefineResponse(**result)


@router.delete("/jobs/{job_id}", response_model=WorkflowJobDeleteResponse)
def remove_workflow_job(
    job_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> WorkflowJobDeleteResponse:
    _ensure_job_access(job_id, current_user)
    return WorkflowJobDeleteResponse(**delete_workflow_job(
        job_id,
        requester_user_id=str(current_user.get("id")),
        requester_is_admin=_is_admin(current_user),
    ))


@router.delete("/jobs/{job_id}/charts")
def remove_workflow_chart(
    job_id: str,
    chart_path: str = Query(..., min_length=1),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    _ensure_job_access(job_id, current_user)
    return delete_workflow_chart(job_id, chart_path)

