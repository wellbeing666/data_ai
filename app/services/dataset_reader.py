from pathlib import Path

import pandas as pd
from fastapi import HTTPException, status

from app.services.dataset_storage import IMAGE_FILE_TYPES, TABULAR_FILE_TYPES, UPLOAD_ROOT


CSV_ENCODINGS = ("utf-8", "utf-8-sig", "gbk")
CLEANED_DATASET_FILENAME = "cleaned_dataset.csv"
VISUAL_EXTRACTED_FILENAME = "visual_extracted.csv"
_RESERVED_TABULAR_OUTPUTS = {
    CLEANED_DATASET_FILENAME,
    VISUAL_EXTRACTED_FILENAME,
}


def load_uploaded_dataset(dataset_id: str, prefer_cleaned: bool = True) -> tuple[Path, pd.DataFrame]:
    dataset_dir = get_dataset_dir(dataset_id)
    file_path = find_dataset_file(dataset_dir, prefer_cleaned=prefer_cleaned)
    return file_path, read_dataset(file_path)


def get_dataset_dir(dataset_id: str) -> Path:
    if not dataset_id or Path(dataset_id).name != dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid dataset_id.",
        )

    dataset_dir = UPLOAD_ROOT / dataset_id
    if not dataset_dir.exists() or not dataset_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )

    return dataset_dir


def find_dataset_file(dataset_dir: Path, prefer_cleaned: bool = True) -> Path:
    if prefer_cleaned:
        for filename in (CLEANED_DATASET_FILENAME, VISUAL_EXTRACTED_FILENAME):
            preferred_path = dataset_dir / filename
            if preferred_path.exists() and preferred_path.is_file() and preferred_path.suffix.lower() in TABULAR_FILE_TYPES:
                return preferred_path

    dataset_files = [
        path
        for path in dataset_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in TABULAR_FILE_TYPES
        and path.name not in _RESERVED_TABULAR_OUTPUTS
    ]

    if not dataset_files:
        extracted_path = dataset_dir / VISUAL_EXTRACTED_FILENAME
        if extracted_path.exists() and extracted_path.is_file():
            return extracted_path
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset file not found.",
        )

    return sorted(dataset_files, key=lambda path: path.name)[0]


def find_original_dataset_file(dataset_dir: Path) -> Path:
    dataset_files = [
        path
        for path in dataset_dir.iterdir()
        if path.is_file()
        and path.suffix.lower() in TABULAR_FILE_TYPES
        and path.name not in _RESERVED_TABULAR_OUTPUTS
    ]
    if dataset_files:
        return sorted(dataset_files, key=lambda path: path.name)[0]

    extracted_path = dataset_dir / VISUAL_EXTRACTED_FILENAME
    if extracted_path.exists() and extracted_path.is_file():
        return extracted_path

    return find_dataset_file(dataset_dir, prefer_cleaned=False)


def get_uploaded_asset_type(dataset_id: str) -> str:
    dataset_dir = get_dataset_dir(dataset_id)
    if any(path.is_file() and path.suffix.lower() in IMAGE_FILE_TYPES for path in dataset_dir.iterdir()):
        return "image"
    return "tabular"


def find_uploaded_image_file(dataset_id: str) -> Path:
    dataset_dir = get_dataset_dir(dataset_id)
    image_files = [
        path
        for path in dataset_dir.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_FILE_TYPES
    ]
    if not image_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image file not found.",
        )
    return sorted(image_files, key=lambda path: path.name)[0]


def read_dataset(file_path: Path) -> pd.DataFrame:
    file_type = file_path.suffix.lower()

    try:
        if file_type == ".csv":
            return read_csv(file_path)
        if file_type in {".xlsx", ".xls"}:
            return pd.read_excel(file_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read dataset: {exc}",
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported dataset file type.",
    )


def read_csv(file_path: Path) -> pd.DataFrame:
    last_error: Exception | None = None
    for encoding in CSV_ENCODINGS:
        try:
            return pd.read_csv(file_path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Failed to decode CSV file: {last_error}",
    )
