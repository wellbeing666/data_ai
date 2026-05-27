from typing import Any

from pydantic import BaseModel, Field


class PredictionJobRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    user_goal: str = Field(..., min_length=1)
    max_retries: int = Field(default=3, ge=0, le=5)
    timeout_seconds: int = Field(default=90, ge=1, le=300)


class PredictionAttemptResult(BaseModel):
    attempt: int
    script_path: str
    safety_result_path: str | None = None
    execution_result_path: str
    validation_result_path: str
    passed: bool
    should_retry: bool
    severity: str
    safety_issues: list[str] | None = None


class PredictionJobResponse(BaseModel):
    job_id: str
    status: str
    current_stage: str | None = None
    attempts: list[PredictionAttemptResult] = Field(default_factory=list)
    final_prediction_result_path: str | None = None
    final_report_data_path: str | None = None
    final_validation_result_path: str | None = None
    job_dir: str
    dataset_profile_path: str | None = None
    rag_retrieval_path: str | None = None
    hypothesis_plan_path: str | None = None
    prediction_plan_path: str | None = None
    prediction_explanation_path: str | None = None
    effective_max_retries: int | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    error: dict[str, Any] | None = None


class PredictionLogResponse(BaseModel):
    job_id: str
    dataset_id: str | None = None
    status: str
    workflow_type: str = "what_if_prediction"
    user_goal: str
    prediction_plan: dict[str, Any] | None = None
    generated_python_code_paths: list[str] = Field(default_factory=list)
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 0
    artifacts: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
