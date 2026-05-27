from fastapi import APIRouter

from app.schemas.report import ReportGenerateRequest, ReportGenerateResponse
from app.services.report_service import generate_markdown_report


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/generate", response_model=ReportGenerateResponse)
def generate_report(request: ReportGenerateRequest) -> ReportGenerateResponse:
    result = generate_markdown_report(
        analysis_result_path=request.analysis_result_path,
        chart_paths=request.chart_paths,
        output_path=request.output_path,
    )
    return ReportGenerateResponse(**result)
