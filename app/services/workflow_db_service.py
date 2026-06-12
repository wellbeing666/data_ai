from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.database import init_database_schema, mysql_connection


def init_workflow_storage() -> None:
    init_database_schema()


def upsert_workflow_job_record(
    status_data: dict[str, Any],
    *,
    dataset_filename: str | None = None,
    file_type: str | None = None,
) -> None:
    init_workflow_storage()
    now = _now_db()
    job_id = str(status_data.get("job_id") or "").strip()
    if not job_id:
        return
    payload = json.dumps(_json_safe(status_data), ensure_ascii=False)
    chart_count = len(status_data.get("chart_paths") or []) if isinstance(status_data.get("chart_paths"), list) else 0
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO analysis_conversations (
                    job_id, dataset_id, owner_user_id, user_goal, status, current_stage,
                    workflow_type, task_type, asset_type, dataset_filename, file_type,
                    chart_count, job_dir, status_payload, created_at, updated_at, deleted_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL)
                ON DUPLICATE KEY UPDATE
                    dataset_id = VALUES(dataset_id),
                    owner_user_id = VALUES(owner_user_id),
                    user_goal = VALUES(user_goal),
                    status = VALUES(status),
                    current_stage = VALUES(current_stage),
                    workflow_type = VALUES(workflow_type),
                    task_type = VALUES(task_type),
                    asset_type = VALUES(asset_type),
                    dataset_filename = COALESCE(VALUES(dataset_filename), dataset_filename),
                    file_type = COALESCE(VALUES(file_type), file_type),
                    chart_count = VALUES(chart_count),
                    job_dir = VALUES(job_dir),
                    status_payload = VALUES(status_payload),
                    updated_at = VALUES(updated_at),
                    deleted_at = NULL
                """,
                (
                    job_id,
                    _empty_to_none(status_data.get("dataset_id")),
                    _empty_to_none(status_data.get("owner_user_id")),
                    _empty_to_none(status_data.get("user_goal")),
                    str(status_data.get("status") or "pending"),
                    _empty_to_none(status_data.get("current_stage")),
                    _empty_to_none(status_data.get("workflow_type")),
                    _empty_to_none(status_data.get("task_type")),
                    _empty_to_none(status_data.get("asset_type")),
                    dataset_filename,
                    file_type,
                    chart_count,
                    str(status_data.get("job_dir") or ""),
                    payload,
                    now,
                    now,
                ),
            )
        conn.commit()


def list_workflow_job_records(
    *,
    limit: int,
    query: str | None = None,
    owner_user_id: str | None = None,
    include_all: bool = False,
) -> list[dict[str, Any]]:
    init_workflow_storage()
    safe_limit = max(1, min(int(limit), 100))
    conditions = ["deleted_at IS NULL"]
    params: list[Any] = []
    if owner_user_id and not include_all:
        conditions.append("owner_user_id = %s")
        params.append(owner_user_id)
    normalized_query = str(query or "").strip()
    if normalized_query:
        like = f"%{normalized_query}%"
        conditions.append("(job_id LIKE %s OR user_goal LIKE %s OR dataset_filename LIKE %s OR task_type LIKE %s OR workflow_type LIKE %s)")
        params.extend([like, like, like, like, like])
    where_clause = " AND ".join(conditions)
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT job_id, dataset_id, dataset_filename, file_type, user_goal, status,
                       current_stage, workflow_type, task_type, asset_type, owner_user_id,
                       chart_count, created_at, updated_at
                FROM analysis_conversations
                WHERE {where_clause}
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (*params, safe_limit),
            )
            rows = cursor.fetchall()
    return [_row_to_job_item(row) for row in rows]


def mark_workflow_job_deleted(job_id: str) -> None:
    init_workflow_storage()
    with mysql_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE analysis_conversations SET deleted_at = %s, updated_at = %s WHERE job_id = %s", (_now_db(), _now_db(), job_id))
        conn.commit()


def _row_to_job_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": str(row.get("job_id") or ""),
        "dataset_id": _empty_to_none(row.get("dataset_id")),
        "dataset_filename": _empty_to_none(row.get("dataset_filename")),
        "file_type": _empty_to_none(row.get("file_type")),
        "user_goal": str(row.get("user_goal") or ""),
        "status": str(row.get("status") or "pending"),
        "current_stage": _empty_to_none(row.get("current_stage")),
        "workflow_type": _empty_to_none(row.get("workflow_type")),
        "task_type": _empty_to_none(row.get("task_type")),
        "asset_type": _empty_to_none(row.get("asset_type")),
        "owner_user_id": _empty_to_none(row.get("owner_user_id")),
        "chart_count": int(row.get("chart_count") or 0),
        "created_at": _serialize_datetime(row.get("created_at")),
        "updated_at": _serialize_datetime(row.get("updated_at")),
    }


def _empty_to_none(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _now_db() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return _serialize_datetime(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
