import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.services.dataset_reader import load_uploaded_dataset


PROFILE_FILENAME = "profile.json"


def generate_dataset_profile(dataset_id: str) -> dict[str, Any]:
    file_path, df = load_uploaded_dataset(dataset_id)
    dataset_dir = file_path.parent

    profile_path = dataset_dir / PROFILE_FILENAME
    profile = _build_profile(
        dataset_id=dataset_id,
        file_path=file_path,
        profile_path=profile_path,
        df=df,
    )

    with profile_path.open("w", encoding="utf-8") as output:
        json.dump(profile, output, ensure_ascii=False, indent=2)

    return profile


def _build_profile(
    dataset_id: str,
    file_path: Path,
    profile_path: Path,
    df: pd.DataFrame,
) -> dict[str, Any]:
    row_count = int(len(df))
    column_count = int(len(df.columns))
    columns = [str(column) for column in df.columns]

    return {
        "dataset_id": dataset_id,
        "filename": file_path.name,
        "file_type": file_path.suffix.lower().lstrip("."),
        "file_path": str(file_path),
        "profile_path": str(profile_path),
        "row_count": row_count,
        "column_count": column_count,
        "columns": columns,
        "dtypes": _build_dtype_summary(df),
        "missing_values": _build_missing_summary(df, row_count),
        "numeric_summary": _build_numeric_summary(df),
        "text_summary": _build_text_summary(df),
        "sample_rows": _build_sample_rows(df),
    }


def _build_dtype_summary(df: pd.DataFrame) -> dict[str, str]:
    return {str(column): str(dtype) for column, dtype in df.dtypes.items()}


def _build_missing_summary(df: pd.DataFrame, row_count: int) -> dict[str, dict[str, Any]]:
    summary = {}
    for column in df.columns:
        missing_count = int(df[column].isna().sum())
        ratio = round(missing_count / row_count, 4) if row_count else 0.0
        summary[str(column)] = {
            "count": missing_count,
            "ratio": ratio,
        }
    return summary


def _build_numeric_summary(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    summary = {}
    numeric_df = df.select_dtypes(include=["number"])

    for column in numeric_df.columns:
        series = numeric_df[column]
        summary[str(column)] = {
            "min": _to_json_value(series.min()),
            "max": _to_json_value(series.max()),
            "mean": _to_json_value(series.mean()),
        }

    return summary


def _build_text_summary(df: pd.DataFrame) -> dict[str, dict[str, list[str]]]:
    summary = {}
    text_df = df.select_dtypes(include=["object", "string", "category"])

    for column in text_df.columns:
        values = text_df[column].dropna().astype(str).unique()[:5]
        summary[str(column)] = {
            "unique_values": [str(value) for value in values],
        }

    return summary


def _build_sample_rows(df: pd.DataFrame) -> list[dict[str, Any]]:
    sample_df = df.head(5).astype(object).where(pd.notnull(df.head(5)), None)
    return [
        {str(key): _to_json_value(value) for key, value in row.items()}
        for row in sample_df.to_dict(orient="records")
    ]


def _to_json_value(value: Any) -> Any:
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        return value.item()

    if hasattr(value, "isoformat"):
        return value.isoformat()

    return value
