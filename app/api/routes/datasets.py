from fastapi import APIRouter, File, UploadFile

from app.schemas.dataset import (
    CleaningApplyRequest,
    CleaningPlanResponse,
    CleaningReportResponse,
    DatasetProfileResponse,
    DatasetUploadResponse,
    SampleDatasetRequest,
    SampleDatasetResponse,
    SampleDatasetTypeListResponse,
)
from app.services.data_cleaning_service import apply_cleaning_plan, build_cleaning_plan, get_cleaning_report
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_storage import save_uploaded_dataset
from app.services.sample_dataset_service import create_sample_dataset, list_sample_dataset_types


router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(file: UploadFile = File(...)) -> DatasetUploadResponse:
    result = await save_uploaded_dataset(file)
    return DatasetUploadResponse(**result)


@router.post("/samples", response_model=SampleDatasetResponse)
def create_sample_dataset_endpoint(request: SampleDatasetRequest) -> SampleDatasetResponse:
    result = create_sample_dataset(request.sample_type)
    return SampleDatasetResponse(**result)


@router.get("/samples", response_model=SampleDatasetTypeListResponse)
def list_sample_datasets_endpoint() -> SampleDatasetTypeListResponse:
    return SampleDatasetTypeListResponse(samples=list_sample_dataset_types())


@router.get("/{dataset_id}/profile", response_model=DatasetProfileResponse)
def get_dataset_profile(dataset_id: str) -> DatasetProfileResponse:
    result = generate_dataset_profile(dataset_id)
    return DatasetProfileResponse(**result)


@router.post("/{dataset_id}/cleaning-plan", response_model=CleaningPlanResponse)
def create_dataset_cleaning_plan(dataset_id: str) -> CleaningPlanResponse:
    return CleaningPlanResponse(**build_cleaning_plan(dataset_id))


@router.post("/{dataset_id}/apply-cleaning", response_model=CleaningReportResponse)
def apply_dataset_cleaning(dataset_id: str, request: CleaningApplyRequest) -> CleaningReportResponse:
    return CleaningReportResponse(**apply_cleaning_plan(dataset_id, request.selected_strategies))


@router.get("/{dataset_id}/cleaning-report", response_model=CleaningReportResponse)
def read_dataset_cleaning_report(dataset_id: str) -> CleaningReportResponse:
    return CleaningReportResponse(**get_cleaning_report(dataset_id))
