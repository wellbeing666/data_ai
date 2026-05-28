import csv
import json
from pathlib import Path
from typing import Any

from app.services.doubao_vision_client import DoubaoVisionClient
from app.services.llm_client import LLMResponseParseError, parse_llm_json


SYSTEM_PROMPT = """You are a Visual Data Parsing Agent.

Extract structured tabular data from business screenshots, chart screenshots, and dashboard images.
Return only one valid JSON object. Do not output markdown or explanations.

Required JSON schema:
{
  "success": true,
  "image_type": "table|chart|dashboard|other",
  "tables": [
    {
      "title": "",
      "columns": [],
      "rows": [],
      "confidence": 0.0
    }
  ],
  "chart_data": [],
  "selected_table": {
    "columns": [],
    "rows": []
  },
  "columns": [],
  "rows": [],
  "confidence": 0.0,
  "warnings": [],
  "limitations": []
}

Rules:
- Use the user's goal to choose the most relevant table if multiple tables are visible.
- Preserve original column meanings but use concise column names.
- Rows may be objects keyed by column name or arrays matching columns.
- If exact numeric values cannot be read, do not invent them; add a warning.
- If the image cannot provide at least 2 columns and 1 data row, return success=false.
"""


def build_user_prompt(user_goal: str) -> str:
    return f"""User goal:
{user_goal}

Extract the main analyzable table or chart data from this image.
Return JSON only.
"""


class VisionParsingAgent:
    def __init__(self, vision_client: DoubaoVisionClient | None = None) -> None:
        self.vision_client = vision_client or DoubaoVisionClient()

    def parse_image(
        self,
        *,
        image_path: str | Path,
        user_goal: str,
    ) -> dict[str, Any]:
        result = self.vision_client.parse_image_json(
            image_path=image_path,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(user_goal),
            temperature=0.1,
        )
        return normalize_visual_parse_result(result)


def normalize_visual_parse_result(result: Any) -> dict[str, Any]:
    result = _coerce_response_object(result)
    if not isinstance(result, dict):
        return _failure("Vision model response must be a JSON object.")

    tables = _normalize_tables(_first_present(result, "tables", "table_list", "sheets"))
    selected_table = _normalize_table(_first_present(result, "selected_table", "table", "data_table", "main_table"))
    if not selected_table["columns"] or not selected_table["rows"]:
        selected_table = _best_table(tables)

    chart_data = _normalize_chart_data(_first_present(result, "chart_data", "chartData", "series", "data_points"))
    chart_table = _table_from_chart_data(chart_data)
    if (not selected_table["columns"] or not selected_table["rows"]) and chart_table["rows"]:
        selected_table = chart_table

    rows_value = _first_present(result, "rows", "records", "data", "values")
    columns = _column_names(_first_present(result, "columns", "fields", "headers")) or selected_table["columns"]
    if not columns:
        columns = _infer_columns(rows_value)
    rows = _normalize_rows(rows_value, columns) if columns else []
    if not rows:
        rows = selected_table["rows"]
        columns = selected_table["columns"]

    columns, rows = _clean_table(columns, rows)
    warnings = _string_list(result.get("warnings"))
    limitations = _string_list(result.get("limitations"))
    confidence = _confidence(result.get("confidence"), selected_table.get("confidence"))
    success = bool(result.get("success", True)) and len(columns) >= 2 and len(rows) >= 1

    if not success:
        warnings = warnings or ["No reliable structured table was extracted from the image."]

    return {
        "success": success,
        "image_type": str(result.get("image_type") or "other"),
        "tables": tables,
        "chart_data": chart_data,
        "selected_table": {
            "columns": columns,
            "rows": rows,
            "confidence": confidence,
        },
        "columns": columns,
        "rows": rows,
        "confidence": confidence,
        "warnings": warnings,
        "limitations": limitations,
    }


def write_visual_extracted_csv(parse_result: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    columns = _string_list(parse_result.get("columns"))
    rows = _normalize_rows(parse_result.get("rows"), columns)
    if len(columns) < 2 or not rows:
        raise ValueError("Visual parse result does not contain at least 2 columns and 1 row.")

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})
    return path


def _normalize_tables(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    tables = []
    for item in value:
        table = _normalize_table(item)
        if table["columns"] and table["rows"]:
            tables.append(table)
    return tables


def _normalize_table(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"title": "", "columns": [], "rows": [], "confidence": 0.0}
    columns = _column_names(_first_present(value, "columns", "fields", "headers"))
    rows_value = _first_present(value, "rows", "records", "data", "values")
    if not columns:
        columns = _infer_columns(rows_value)
    rows = _normalize_rows(rows_value, columns)
    columns, rows = _clean_table(columns, rows)
    return {
        "title": str(value.get("title") or ""),
        "columns": columns,
        "rows": rows,
        "confidence": _confidence(value.get("confidence")),
    }


def _best_table(tables: list[dict[str, Any]]) -> dict[str, Any]:
    if not tables:
        return {"title": "", "columns": [], "rows": [], "confidence": 0.0}
    return max(tables, key=lambda table: len(table["columns"]) * max(1, len(table["rows"])))


def _clean_table(columns: list[str], rows: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    deduped_columns = []
    seen = set()
    for index, column in enumerate(columns):
        name = column.strip() or f"column_{index + 1}"
        if name in seen:
            name = f"{name}_{index + 1}"
        seen.add(name)
        deduped_columns.append(name)

    clean_rows = []
    for row in rows:
        clean_row = {column: _cell_value(row.get(column, "")) for column in deduped_columns}
        if any(value not in {"", None} for value in clean_row.values()):
            clean_rows.append(clean_row)
    return deduped_columns, clean_rows


def _normalize_rows(value: Any, columns: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not columns:
        return []
    rows = []
    for item in value:
        if isinstance(item, dict):
            rows.append(_row_from_dict(item, columns))
        elif isinstance(item, list):
            rows.append(
                {
                    column: item[index] if index < len(item) else ""
                    for index, column in enumerate(columns)
                }
            )
    return rows


def _coerce_response_object(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return _coerce_response_object(parse_llm_json(value))
        except LLMResponseParseError:
            return value
    if isinstance(value, list):
        table = _table_from_list(value)
        if table["columns"] and table["rows"]:
            return {
                "success": True,
                "image_type": "table",
                "selected_table": table,
                "columns": table["columns"],
                "rows": table["rows"],
                "confidence": table["confidence"],
                "warnings": [],
                "limitations": [],
            }
        if len(value) == 1:
            return _coerce_response_object(value[0])
        return value
    if isinstance(value, dict):
        unwrapped = _unwrap_payload(value)
        if unwrapped is not value:
            return _coerce_response_object(unwrapped)
    return value


def _unwrap_payload(value: dict[str, Any]) -> Any:
    table_keys = {"columns", "headers", "fields", "rows", "records", "values", "data"}
    if table_keys.intersection(value):
        return value
    for key in ("result", "response", "output", "content", "payload", "data"):
        child = value.get(key)
        if isinstance(child, (dict, list, str)):
            return child
    return value


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping.get(key) is not None:
            return mapping.get(key)
    return None


def _column_names(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    names = []
    for index, item in enumerate(value):
        if isinstance(item, dict):
            name = item.get("name") or item.get("field") or item.get("title") or item.get("label")
            names.append(str(name or f"column_{index + 1}").strip())
        else:
            names.append(str(item).strip())
    return [name for name in names if name]


def _infer_columns(rows_value: Any) -> list[str]:
    if not isinstance(rows_value, list) or not rows_value:
        return []
    first_row = rows_value[0]
    if isinstance(first_row, dict):
        columns = []
        for row in rows_value:
            if not isinstance(row, dict):
                continue
            for key in row:
                name = str(key).strip()
                if name and name not in columns:
                    columns.append(name)
        return columns
    if isinstance(first_row, list):
        return [f"column_{index + 1}" for index in range(len(first_row))]
    return []


def _row_from_dict(item: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    lowered_lookup = {str(key).strip().lower(): key for key in item}
    row = {}
    for column in columns:
        if column in item:
            row[column] = item.get(column, "")
            continue
        source_key = lowered_lookup.get(column.strip().lower())
        row[column] = item.get(source_key, "") if source_key is not None else ""
    return row


def _table_from_list(value: list[Any]) -> dict[str, Any]:
    columns = _infer_columns(value)
    rows = _normalize_rows(value, columns)
    columns, rows = _clean_table(columns, rows)
    return {"title": "", "columns": columns, "rows": rows, "confidence": 0.6 if rows else 0.0}


def _normalize_chart_data(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("data", "points", "items", "series"):
            child = value.get(key)
            if isinstance(child, list):
                return child
    return []


def _table_from_chart_data(chart_data: list[Any]) -> dict[str, Any]:
    if not chart_data:
        return {"title": "", "columns": [], "rows": [], "confidence": 0.0}
    table = _table_from_list(chart_data)
    if len(table["columns"]) >= 2 and table["rows"]:
        table["title"] = "chart_data"
    return table


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _cell_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return value
    return json.dumps(value, ensure_ascii=False)


def _confidence(*values: Any) -> float:
    for value in values:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            continue
        return max(0.0, min(confidence, 1.0))
    return 0.0


def _failure(message: str) -> dict[str, Any]:
    return {
        "success": False,
        "image_type": "other",
        "tables": [],
        "chart_data": [],
        "selected_table": {"columns": [], "rows": [], "confidence": 0.0},
        "columns": [],
        "rows": [],
        "confidence": 0.0,
        "warnings": [message],
        "limitations": [],
    }
