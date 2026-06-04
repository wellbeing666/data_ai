from typing import Any

from pydantic import BaseModel, Field


class WorkflowJobRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    user_goal: str = Field(..., min_length=1)
    max_retries: int = Field(default=3, ge=0, le=5)
    timeout_seconds: int = Field(default=90, ge=1, le=300)


class WorkflowAttemptResult(BaseModel):
    attempt: int
    script_path: str
    safety_result_path: str | None = None
    execution_result_path: str
    validation_result_path: str
    passed: bool
    should_retry: bool
    severity: str
    safety_issues: list[str] | None = None


class WorkflowJobResponse(BaseModel):
    job_id: str
    dataset_id: str | None = None
    user_goal: str | None = None
    status: str
    current_stage: str | None = None
    workflow_type: str | None = None
    task_type: str | None = None
    asset_type: str | None = None
    attempts: list[WorkflowAttemptResult] = Field(default_factory=list)
    job_dir: str
    controller_plan_path: str | None = None
    rag_retrieval_path: str | None = None
    dataset_profile_path: str | None = None
    visual_parse_result_path: str | None = None
    visual_extracted_dataset_path: str | None = None
    visual_extraction_confidence: float | None = None
    data_understanding_path: str | None = None
    analysis_plan_path: str | None = None
    explanation_path: str | None = None
    hypothesis_plan_path: str | None = None
    prediction_plan_path: str | None = None
    prediction_explanation_path: str | None = None
    final_result_path: str | None = None
    final_prediction_result_path: str | None = None
    final_report_data_path: str | None = None
    chart_paths: list[str] = Field(default_factory=list)
    final_validation_result_path: str | None = None
    effective_max_retries: int | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class WorkflowJobListItem(BaseModel):
    job_id: str
    dataset_id: str | None = None
    dataset_filename: str | None = None
    file_type: str | None = None
    user_goal: str = ""
    status: str
    current_stage: str | None = None
    workflow_type: str | None = None
    task_type: str | None = None
    asset_type: str | None = None
    chart_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None


class WorkflowJobListResponse(BaseModel):
    jobs: list[WorkflowJobListItem] = Field(default_factory=list)


class WorkflowLogResponse(BaseModel):
    job_id: str
    dataset_id: str | None = None
    status: str
    workflow_type: str
    task_type: str | None = None
    asset_type: str | None = None
    user_goal: str
    analysis_plan: dict[str, Any] | None = None
    prediction_plan: dict[str, Any] | None = None
    generated_python_code_paths: list[str] = Field(default_factory=list)
    executor_code_path: str | None = None
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 0
    artifacts: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
