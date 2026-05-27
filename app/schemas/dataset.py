from typing import Any

from pydantic import BaseModel


class DatasetUploadResponse(BaseModel):
    dataset_id: str
    filename: str
    file_type: str
    file_path: str


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
