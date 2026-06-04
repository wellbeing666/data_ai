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
