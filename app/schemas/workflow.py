from typing import Any

from pydantic import BaseModel, Field


class WorkflowJobRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    user_goal: str = Field(..., min_length=1)
    max_retries: int = Field(default=3, ge=0, le=5)
    timeout_seconds: int = Field(default=90, ge=1, le=300)


class WorkflowPreflightRequest(BaseModel):
    dataset_id: str = Field(..., min_length=1)
    user_goal: str = Field(..., min_length=1)


class WorkflowPreflightResponse(BaseModel):
    dataset_id: str
    user_goal: str
    asset_type: str = "tabular"
    preflight_path: str | None = None
    intent_type: str
    is_task_clear: bool
    clarity_score: float
    detected_fields: list[dict[str, Any]] = Field(default_factory=list)
    data_quality_report: dict[str, Any] = Field(default_factory=dict)
    clarifying_questions: list[str] = Field(default_factory=list)
    intent_questions: list[dict[str, Any]] = Field(default_factory=list)
    suggested_goals: list[str] = Field(default_factory=list)
    optimized_goal: str = ""
    next_action: str
    data_understanding: dict[str, Any] = Field(default_factory=dict)


class WorkflowControlRequest(BaseModel):
    action: str = Field(..., min_length=1)


class WorkflowControlResponse(BaseModel):
    job_id: str
    action: str
    accepted: bool
    message: str
    status: str | None = None


class WorkflowPptxGenerateResponse(BaseModel):
    job_id: str
    pptx_path: str | None = None
    pptx_preview_path: str | None = None
    message: str
    status: str | None = None


class WorkflowFollowUpRequest(BaseModel):
    question: str = Field(..., min_length=1)


class WorkflowFollowUpResponse(BaseModel):
    job_id: str
    question: str
    answer: str
    follow_up_path: str | None = None
    created_at: str | None = None
    used_artifacts: list[str] = Field(default_factory=list)


class ChartConfigRequest(BaseModel):
    instruction: str = Field(..., min_length=1)
    current_config: dict[str, Any] | None = None


class ChartConfigResponse(BaseModel):
    chart_id: str
    title: str
    description: str
    echarts_option: dict[str, Any] = Field(default_factory=dict)
    data_preview: list[dict[str, Any]] = Field(default_factory=list)
    applied_filters: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    config_path: str | None = None


class ChartSuggestionResponse(BaseModel):
    job_id: str
    chart_path: str
    suggestions: list[str] = Field(default_factory=list)


class ChartRefineRequest(BaseModel):
    chart_path: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1)


class ChartRefineResponse(BaseModel):
    success: bool
    message: str
    job_id: str
    chart_path: str
    instruction: str
    source_script_path: str | None = None
    refined_script_path: str | None = None
    execution_result_path: str | None = None
    chart_paths: list[str] = Field(default_factory=list)
    safety_issues: list[str] = Field(default_factory=list)


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
    analysis_roadmap_path: str | None = None
    quality_review_path: str | None = None
    cleaning_report_path: str | None = None
    evidence_chain_path: str | None = None
    report_path: str | None = None
    pptx_path: str | None = None
    pptx_preview_path: str | None = None
    job_control_path: str | None = None
    control_state: dict[str, Any] = Field(default_factory=dict)
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


class WorkflowJobDeleteResponse(BaseModel):
    deleted: bool
    job_id: str


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




