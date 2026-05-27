from pydantic import BaseModel, Field


class ReportGenerateRequest(BaseModel):
    analysis_result_path: str = Field(..., min_length=1)
    chart_paths: list[str] = Field(default_factory=list)
    output_path: str | None = None


class ReportGenerateResponse(BaseModel):
    report_path: str
    analysis_result_path: str
    chart_paths: list[str]
