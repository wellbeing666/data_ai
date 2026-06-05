from typing import Any

from pydantic import BaseModel, Field


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    filename: str
    file_type: str
    file_path: str
    asset_type: str = "tabular"
    preview_url: str | None = None


class SampleDatasetRequest(BaseModel):
    sample_type: str = "sales_decline"


class SampleDatasetResponse(DatasetUploadResponse):
    sample_type: str
    recommended_goal: str
    description: str
    suggested_goals: list[str] = Field(default_factory=list)


class SampleDatasetType(BaseModel):
    sample_type: str
    filename: str
    description: str
    recommended_goal: str
    suggested_goals: list[str] = Field(default_factory=list)


class SampleDatasetTypeListResponse(BaseModel):
    samples: list[SampleDatasetType]


class MissingValueSummary(BaseModel):
    count: int
    ratio: float


class NumericColumnSummary(BaseModel):
    min: float | int | None
    max: float | int | None
    mean: float | None


class TextColumnSummary(BaseModel):
    unique_values: list[str]


class DatasetProfileResponse(BaseModel):
    dataset_id: str
    filename: str
    file_type: str
    file_path: str
    profile_path: str
    row_count: int
    column_count: int
    columns: list[str]
    dtypes: dict[str, str]
    missing_values: dict[str, MissingValueSummary]
    numeric_summary: dict[str, NumericColumnSummary]
    text_summary: dict[str, TextColumnSummary]
    sample_rows: list[dict[str, Any]]




class DatasetDataMapResponse(BaseModel):
    dataset_id: str
    data_map: dict[str, Any] = Field(default_factory=dict)
    data_map_path: str | None = None
    message: str = ""


class CleaningStrategyOption(BaseModel):
    strategy_id: str
    label: str
    description: str = ""
    recommended: bool = False


class CleaningIssue(BaseModel):
    issue_id: str
    issue_type: str
    column: str | None = None
    message: str
    affected_count: int = 0
    severity: str = "low"
    default_strategy_id: str = "keep"
    strategies: list[CleaningStrategyOption] = Field(default_factory=list)
    examples: list[Any] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CleaningPreview(BaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)


class CleaningPlanResponse(BaseModel):
    dataset_id: str
    asset_type: str = "tabular"
    source_file: str | None = None
    plan_path: str | None = None
    created_at: str | None = None
    row_count: int = 0
    column_count: int = 0
    columns: list[str] = Field(default_factory=list)
    has_issues: bool = False
    issues: list[CleaningIssue] = Field(default_factory=list)
    recommended_strategy_ids: dict[str, str] = Field(default_factory=dict)
    preview: CleaningPreview = Field(default_factory=CleaningPreview)
    message: str = ""


class CleaningApplyRequest(BaseModel):
    selected_strategies: dict[str, str] = Field(default_factory=dict)


class CleaningAppliedStrategy(BaseModel):
    issue_id: str
    issue_type: str | None = None
    column: str | None = None
    strategy_id: str
    strategy_label: str = ""
    description: str = ""
    rows_before: int = 0
    rows_after: int = 0
    columns_before: int = 0
    columns_after: int = 0


class CleaningReportResponse(BaseModel):
    dataset_id: str
    source_file: str | None = None
    cleaned_dataset_path: str | None = None
    cleaning_report_path: str | None = None
    created_at: str | None = None
    row_count_before: int = 0
    row_count_after: int = 0
    column_count_before: int = 0
    column_count_after: int = 0
    applied_strategies: list[CleaningAppliedStrategy] = Field(default_factory=list)
    preview: CleaningPreview = Field(default_factory=CleaningPreview)
    message: str = ""

