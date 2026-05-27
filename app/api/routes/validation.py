from fastapi import APIRouter

from app.schemas.validation import ValidationResponse
from app.services.validation_service import validate_job_outputs


router = APIRouter(prefix="/api/validation", tags=["validation"])


@router.get("/jobs/{job_id}", response_model=ValidationResponse)
def validate_job(job_id: str) -> ValidationResponse:
    result = validate_job_outputs(job_id)
    return ValidationResponse(**result)
