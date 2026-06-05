from typing import Any

from pydantic import BaseModel, Field


class AnalysisJobRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    user_goal: str = Field(..., min_length=1)


class AnalysisJobResponse(BaseModel):
    job_id: str
    analysis_type: str
    result_path: str
    charts_dir: str


class AutoRepairAnalysisJobRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    user_goal: str = Field(..., min_length=1)
    max_retries: int = Field(default=3, ge=0, le=5)
    timeout_seconds: int = Field(default=60, ge=1, le=300)


class AutoRepairAttemptResult(BaseModel):
    attempt: int
    script_path: str
    safety_result_path: str | None = None
    execution_result_path: str
    validation_result_path: str
    passed: bool
    should_retry: bool
    severity: str
    safety_issues: list[str] | None = None


class AutoRepairAnalysisJobResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str | None = None
    attempts: list[AutoRepairAttemptResult]
    final_result_path: str | None
    final_report_data_path: str | None
    final_validation_result_path: str | None
    job_dir: str
    controller_plan_path: str | None = None
    rag_retrieval_path: str | None = None
    dataset_profile_path: str | None = None
    data_understanding_path: str | None = None
    analysis_plan_path: str | None = None
    explanation_path: str | None = None
    quality_review_path: str | None = None
    evidence_chain_path: str | None = None
    debate_reflection_path: str | None = None
    report_path: str | None = None
    pptx_path: str | None = None
    pptx_preview_path: str | None = None
    sidecar_results: dict[str, str] = Field(default_factory=dict)
    effective_max_retries: int | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class ExecutionLogEvent(BaseModel):
    timestamp: str
    stage: str
    status: str
    message: str
    attempt: int | None = None


class ExecutionLogResponse(BaseModel):
    job_id: str
    dataset_id: str | None = None
    status: str
    workflow_type: str
    user_goal: str
    analysis_plan: dict[str, Any] | None = None
    generated_python_code_paths: list[str] = Field(default_factory=list)
    executor_code_path: str | None = None
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 0
    artifacts: dict[str, Any] = Field(default_factory=dict)
    events: list[ExecutionLogEvent] = Field(default_factory=list)

