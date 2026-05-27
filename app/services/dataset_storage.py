from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status


UPLOAD_ROOT = Path("storage/uploads")
ALLOWED_FILE_TYPES = {".csv", ".xlsx", ".xls"}
CHUNK_SIZE = 1024 * 1024


async def save_uploaded_dataset(file: UploadFile) -> dict[str, str]:
    filename = _get_safe_filename(file.filename)
    file_type = Path(filename).suffix.lower()

    if file_type not in ALLOWED_FILE_TYPES:
        allowed = ", ".join(sorted(ALLOWED_FILE_TYPES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed types: {allowed}",
        )

    dataset_id = uuid4().hex
    dataset_dir = UPLOAD_ROOT / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=False)

    file_path = dataset_dir / filename
    await _save_upload_file(file, file_path)

    return {
        "dataset_id": dataset_id,
        "filename": filename,
        "file_type": file_type.lstrip("."),
        "file_path": str(file_path),
    }


def _get_safe_filename(filename: str | None) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    safe_filename = Path(filename).name
    if not safe_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is invalid.",
        )

    return safe_filename


async def _save_upload_file(file: UploadFile, file_path: Path) -> None:
    with file_path.open("wb") as output:
        while chunk := await file.read(CHUNK_SIZE):
            output.write(chunk)
