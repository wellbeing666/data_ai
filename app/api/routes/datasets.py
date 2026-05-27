from fastapi import APIRouter, File, UploadFile

from app.schemas.dataset import DatasetProfileResponse, DatasetUploadResponse
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_storage import save_uploaded_dataset


router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.post("/upload", response_model=DatasetUploadResponse)
async def upload_dataset(file: UploadFile = File(...)) -> DatasetUploadResponse:
    result = await save_uploaded_dataset(file)
    return DatasetUploadResponse(**result)


@router.get("/{dataset_id}/profile", response_model=DatasetProfileResponse)
def get_dataset_profile(dataset_id: str) -> DatasetProfileResponse:
    result = generate_dataset_profile(dataset_id)
    return DatasetProfileResponse(**result)
