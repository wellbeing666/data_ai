from fastapi import APIRouter, File, UploadFile

from app.schemas.dataset import (
    DatasetProfileResponse,
    DatasetUploadResponse,
    SampleDatasetRequest,
    SampleDatasetResponse,
    SampleDatasetTypeListResponse,
)
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
