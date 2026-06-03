import json
import traceback
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.agents.controller_agent import create_controller_plan
from app.agents.vision_parsing_agent import VisionParsingAgent, write_visual_extracted_csv
from app.services.auto_repair_analysis import run_auto_repair_analysis_job
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_reader import find_uploaded_image_file, get_dataset_dir, get_uploaded_asset_type, load_uploaded_dataset
from app.services.execution_log_service import create_event, get_execution_log, write_execution_log
from app.services.prediction_workflow import run_prediction_job
from app.services.rag_service import format_rag_context, get_rag_service


JOB_ROOT = Path("storage/jobs")
WORKFLOW_STATUS_FILENAME = "workflow_task_status.json"
MAX_RETRIES = 3
PREDICTION_TASK_TYPE = "what_if_prediction"
ANALYSIS_WORKFLOW_TYPE = "auto_repair"
IMAGE_ASSET_TYPE = "image"


def create_workflow_job_record(
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    effective_max_retries = _validate_max_retries(max_retries)
    job_id = uuid4().hex
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=False)
    events = [create_event("queued", "pending", "Unified workflow job created.")]
    asset_type = _safe_asset_type(dataset_id)
    return _write_workflow_status(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="pending",
        current_stage="queued",
        workflow_type=None,
        task_type=None,
        asset_type=asset_type,
        attempts=[],
        events=events,
        max_retries=effective_max_retries,
        timeout_seconds=timeout_seconds,
    )


def run_workflow_job_background(
    job_id: str,
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 90,
) -> None:
    try:
        run_workflow_job(
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:  # pragma: no cover - background safety net
        job_dir = (JOB_ROOT / job_id).resolve()
        current_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME) or {}
        events = _event_list(current_status.get("events"))
        events.append(create_event("failed", "failed", f"Unified workflow failed: {exc}"))
        _write_workflow_status(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="failed",
            current_stage="failed",
            workflow_type=current_status.get("workflow_type"),
            task_type=current_status.get("task_type"),
            asset_type=current_status.get("asset_type") or _safe_asset_type(dataset_id),
            attempts=_dict_list(current_status.get("attempts")),
            events=events,
            max_retries=_validate_max_retries(max_retries),
            timeout_seconds=timeout_seconds,
            error={
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=8),
            },
        )


def run_workflow_job(
    *,
    job_id: str,
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    effective_max_retries = _validate_max_retries(max_retries)
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    current_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME) or {}
    events = _event_list(current_status.get("events"))
    if not events:
        events.append(create_event("queued", "pending", "Unified workflow job created."))
    asset_type = _safe_asset_type(dataset_id)

    events.append(create_event("loading_dataset", "running", "Loading uploaded dataset and profile."))
    _write_workflow_status(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="running",
        current_stage="loading_dataset",
        workflow_type=None,
        task_type=None,
        asset_type=asset_type,
        attempts=[],
        events=events,
        max_retries=effective_max_retries,
        timeout_seconds=timeout_seconds,
    )

    visual_parse_result_path = None
    visual_extracted_dataset_path = None
    visual_extraction_confidence = None
    if asset_type == IMAGE_ASSET_TYPE:
        events.append(create_event("visual_parsing", "running", "Vision Parsing Agent is extracting structured data from the image."))
        _write_workflow_status(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="running",
            current_stage="visual_parsing",
            workflow_type=None,
            task_type=None,
            asset_type=asset_type,
            attempts=[],
            events=events,
            max_retries=effective_max_retries,
            timeout_seconds=timeout_seconds,
        )
        parse_result = VisionParsingAgent().parse_image(
            image_path=find_uploaded_image_file(dataset_id),
            user_goal=user_goal,
        )
        visual_parse_result_path = str(job_dir / "visual_parse_result.json")
        _write_json(job_dir / "visual_parse_result.json", parse_result)
        visual_extraction_confidence = parse_result.get("confidence")
        if not parse_result.get("success"):
            events.append(create_event("visual_parsing", "failed", "Vision Parsing Agent could not extract reliable structured data."))
            return _write_workflow_status(
                job_dir=job_dir,
                job_id=job_id,
                dataset_id=dataset_id,
                user_goal=user_goal,
                status_value="failed",
                current_stage="failed",
                workflow_type=None,
                task_type="visual_parsing_failed",
                asset_type=asset_type,
                attempts=[],
                events=events,
                max_retries=effective_max_retries,
                timeout_seconds=timeout_seconds,
                visual_parse_result_path=visual_parse_result_path,
                visual_extraction_confidence=_float_or_none(visual_extraction_confidence),
                error={
                    "type": "VisualParsingError",
                    "message": "图片中未能抽取出至少 2 列、1 行的可靠结构化数据，请上传更清晰的截图或原始表格文件。",
                    "warnings": parse_result.get("warnings") if isinstance(parse_result.get("warnings"), list) else [],
                },
            )
        extracted_path = get_dataset_dir(dataset_id) / "visual_extracted.csv"
        write_visual_extracted_csv(parse_result, extracted_path)
        visual_extracted_dataset_path = str(extracted_path)
        events.append(create_event("visual_parsing", "success", "Vision Parsing Agent extracted structured data from the image."))

    load_uploaded_dataset(dataset_id)
    dataset_profile = generate_dataset_profile(dataset_id)
    _write_json(job_dir / "dataset_profile.json", dataset_profile)

    events.append(create_event("rag_retrieval", "running", "Retrieving business knowledge for controller routing."))
    rag_search_result = get_rag_service().search(query=user_goal, dataset_profile=dataset_profile)
    rag_context = format_rag_context(rag_search_result)
    _write_json(job_dir / "rag_retrieval.json", rag_search_result)

    events.append(create_event("controller", "running", "Controller Agent is choosing the workflow."))
    controller_plan = create_controller_plan(user_goal, dataset_profile, rag_context=rag_context)
    task_type = str(controller_plan.get("task_type") or "general_data_analysis")
    workflow_type = PREDICTION_TASK_TYPE if task_type == PREDICTION_TASK_TYPE else ANALYSIS_WORKFLOW_TYPE
    _write_json(job_dir / "controller_plan.json", controller_plan)
    events.append(create_event("controller", "success", f"Controller selected {task_type}."))
    _write_workflow_status(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="running",
        current_stage="controller",
        workflow_type=workflow_type,
        task_type=task_type,
        asset_type=asset_type,
        attempts=[],
        events=events,
        max_retries=effective_max_retries,
        timeout_seconds=timeout_seconds,
        controller_plan_path=str(job_dir / "controller_plan.json"),
        rag_retrieval_path=str(job_dir / "rag_retrieval.json"),
        dataset_profile_path=str(job_dir / "dataset_profile.json"),
        visual_parse_result_path=visual_parse_result_path,
        visual_extracted_dataset_path=visual_extracted_dataset_path,
        visual_extraction_confidence=_float_or_none(visual_extraction_confidence),
    )

    if task_type == PREDICTION_TASK_TYPE:
        result = run_prediction_job(
            dataset_id=dataset_id,
            user_goal=user_goal,
            max_retries=effective_max_retries,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
        )
        return _normalize_workflow_status(result, workflow_type=PREDICTION_TASK_TYPE, task_type=task_type)

    result = run_auto_repair_analysis_job(
        dataset_id=dataset_id,
        user_goal=user_goal,
        max_retries=effective_max_retries,
        timeout_seconds=timeout_seconds,
        job_id=job_id,
    )
    return _normalize_workflow_status(result, workflow_type=ANALYSIS_WORKFLOW_TYPE, task_type=task_type)


def get_workflow_job_status(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id)
    prediction_status = _read_json_if_exists(job_dir / "prediction_task_status.json")
    if prediction_status is not None:
        return _normalize_workflow_status(
            prediction_status,
            workflow_type=PREDICTION_TASK_TYPE,
            task_type=_controller_task_type(job_dir) or PREDICTION_TASK_TYPE,
        )

    analysis_status = _read_json_if_exists(job_dir / "task_status.json")
    if analysis_status is not None:
        return _normalize_workflow_status(
            analysis_status,
            workflow_type=ANALYSIS_WORKFLOW_TYPE,
            task_type=_controller_task_type(job_dir) or "general_data_analysis",
        )

    workflow_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME)
    if workflow_status is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow status not found.")
    return _normalize_workflow_status(
        workflow_status,
        workflow_type=workflow_status.get("workflow_type"),
        task_type=workflow_status.get("task_type"),
    )


def get_workflow_job_log(job_id: str) -> dict[str, Any]:
    status_data = get_workflow_job_status(job_id)
    try:
        log_data = get_execution_log(job_id)
    except HTTPException:
        log_data = {
            "job_id": status_data["job_id"],
            "dataset_id": None,
            "status": status_data["status"],
            "workflow_type": status_data.get("workflow_type") or "pending",
            "user_goal": "",
            "generated_python_code_paths": [],
            "execution_results": [],
            "validation_results": [],
            "retry_count": 0,
            "max_retries": int(status_data.get("effective_max_retries") or 0),
            "artifacts": {},
            "events": status_data.get("events") or [],
        }
    log_data = {
        **log_data,
        "workflow_type": status_data.get("workflow_type") or log_data.get("workflow_type") or "pending",
        "task_type": status_data.get("task_type"),
        "asset_type": status_data.get("asset_type"),
    }
    artifacts = log_data.get("artifacts") if isinstance(log_data.get("artifacts"), dict) else {}
    log_data["artifacts"] = {
        **artifacts,
        "visual_parse_result": status_data.get("visual_parse_result_path"),
        "visual_extracted_dataset": status_data.get("visual_extracted_dataset_path"),
        "charts": status_data.get("chart_paths") or [],
    }
    if log_data["workflow_type"] == PREDICTION_TASK_TYPE:
        log_data.setdefault("prediction_plan", _read_json_if_exists(Path(str(status_data.get("prediction_plan_path") or ""))))
        log_data.setdefault("analysis_plan", None)
    else:
        log_data.setdefault("analysis_plan", _read_json_if_exists(Path(str(status_data.get("analysis_plan_path") or ""))))
        log_data.setdefault("prediction_plan", None)
    return log_data


def delete_workflow_chart(job_id: str, chart_path: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    resolved_chart = _resolve_chart_file(job_dir, job_id, chart_path)
    if not resolved_chart.exists() or not resolved_chart.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chart not found.")

    resolved_chart.unlink()
    for filename in ("analysis_result.json", "prediction_result.json", "report_data.json"):
        artifact_path = job_dir / filename
        artifact_data = _read_json_if_exists(artifact_path)
        if not artifact_data:
            continue
        updated_data, changed = _remove_deleted_chart_refs(artifact_data, resolved_chart, job_dir)
        if changed:
            _write_json(artifact_path, updated_data)

    workflow_type = _workflow_type_for_job_dir(job_dir)
    return {
        "deleted": True,
        "chart_path": _chart_storage_path(job_dir, resolved_chart),
        "chart_paths": _collect_chart_paths(job_dir, workflow_type),
    }


def _write_workflow_status(
    *,
    job_dir: Path,
    job_id: str,
    dataset_id: str,
    user_goal: str,
    status_value: str,
    current_stage: str,
    workflow_type: Any,
    task_type: Any,
    asset_type: str | None,
    attempts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    max_retries: int,
    timeout_seconds: int,
    controller_plan_path: str | None = None,
    rag_retrieval_path: str | None = None,
    dataset_profile_path: str | None = None,
    visual_parse_result_path: str | None = None,
    visual_extracted_dataset_path: str | None = None,
    visual_extraction_confidence: float | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "user_goal": user_goal,
        "status": status_value,
        "current_stage": current_stage,
        "workflow_type": workflow_type,
        "task_type": task_type,
        "asset_type": asset_type,
        "attempts": attempts,
        "job_dir": str(job_dir),
        "controller_plan_path": controller_plan_path,
        "rag_retrieval_path": rag_retrieval_path,
        "dataset_profile_path": dataset_profile_path,
        "visual_parse_result_path": visual_parse_result_path,
        "visual_extracted_dataset_path": visual_extracted_dataset_path,
        "visual_extraction_confidence": visual_extraction_confidence,
        "effective_max_retries": max_retries,
        "timeout_seconds": timeout_seconds,
        "events": events,
        "error": error,
    }
    _write_json(job_dir / WORKFLOW_STATUS_FILENAME, status_data)
    write_execution_log(
        job_dir,
        {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "status": status_value,
            "workflow_type": str(workflow_type or "pending"),
            "task_type": task_type,
            "asset_type": asset_type,
            "user_goal": user_goal,
            "generated_python_code_paths": [],
            "execution_results": [],
            "validation_results": [],
            "retry_count": 0,
            "max_retries": max_retries,
            "artifacts": {},
            "visual_parse_result": visual_parse_result_path,
            "visual_extracted_dataset": visual_extracted_dataset_path,
            "events": events,
        },
    )
    return _normalize_workflow_status(status_data, workflow_type=workflow_type, task_type=task_type)


def _normalize_workflow_status(
    data: dict[str, Any],
    *,
    workflow_type: Any,
    task_type: Any,
) -> dict[str, Any]:
    job_dir = Path(str(data.get("job_dir") or ""))
    if job_dir.exists():
        data = {
            **data,
            "controller_plan_path": _existing_or_none(data.get("controller_plan_path"), job_dir / "controller_plan.json"),
            "rag_retrieval_path": _existing_or_none(data.get("rag_retrieval_path"), job_dir / "rag_retrieval.json"),
            "dataset_profile_path": _existing_or_none(data.get("dataset_profile_path"), job_dir / "dataset_profile.json"),
            "visual_parse_result_path": _existing_or_none(data.get("visual_parse_result_path"), job_dir / "visual_parse_result.json"),
            "visual_extracted_dataset_path": data.get("visual_extracted_dataset_path"),
            "data_understanding_path": _existing_or_none(data.get("data_understanding_path"), job_dir / "data_understanding.json"),
            "analysis_plan_path": _existing_or_none(data.get("analysis_plan_path"), job_dir / "analysis_plan.json"),
            "explanation_path": _existing_or_none(data.get("explanation_path"), job_dir / "explanation.json"),
            "hypothesis_plan_path": _existing_or_none(data.get("hypothesis_plan_path"), job_dir / "hypothesis_plan.json"),
            "prediction_plan_path": _existing_or_none(data.get("prediction_plan_path"), job_dir / "prediction_plan.json"),
            "prediction_explanation_path": _existing_or_none(data.get("prediction_explanation_path"), job_dir / "prediction_explanation.json"),
            "final_result_path": _existing_or_none(data.get("final_result_path"), job_dir / "analysis_result.json"),
            "final_prediction_result_path": _existing_or_none(data.get("final_prediction_result_path"), job_dir / "prediction_result.json"),
            "final_report_data_path": _existing_or_none(data.get("final_report_data_path"), job_dir / "report_data.json"),
            "chart_paths": _collect_chart_paths(job_dir, str(workflow_type or data.get("workflow_type") or "")),
            "final_validation_result_path": _existing_or_none(
                data.get("final_validation_result_path"),
                job_dir / ("prediction_validation_result.json" if workflow_type == PREDICTION_TASK_TYPE else "validation_result.json"),
            ),
        }
    return {
        "job_id": str(data.get("job_id") or ""),
        "status": str(data.get("status") or "pending"),
        "current_stage": str(data.get("current_stage") or data.get("status") or "pending"),
        "workflow_type": str(workflow_type or data.get("workflow_type") or ""),
        "task_type": str(task_type or data.get("task_type") or ""),
        "asset_type": str(data.get("asset_type") or _asset_type_from_job_dir(job_dir)),
        "attempts": _dict_list(data.get("attempts")),
        "job_dir": str(data.get("job_dir") or ""),
        "controller_plan_path": data.get("controller_plan_path"),
        "rag_retrieval_path": data.get("rag_retrieval_path"),
        "dataset_profile_path": data.get("dataset_profile_path"),
        "visual_parse_result_path": data.get("visual_parse_result_path"),
        "visual_extracted_dataset_path": _visual_extracted_path(data, job_dir),
        "visual_extraction_confidence": data.get("visual_extraction_confidence") if data.get("visual_extraction_confidence") is not None else _visual_confidence(job_dir),
        "data_understanding_path": data.get("data_understanding_path"),
        "analysis_plan_path": data.get("analysis_plan_path"),
        "explanation_path": data.get("explanation_path"),
        "hypothesis_plan_path": data.get("hypothesis_plan_path"),
        "prediction_plan_path": data.get("prediction_plan_path"),
        "prediction_explanation_path": data.get("prediction_explanation_path"),
        "final_result_path": data.get("final_result_path"),
        "final_prediction_result_path": data.get("final_prediction_result_path"),
        "final_report_data_path": data.get("final_report_data_path"),
        "chart_paths": _string_list(data.get("chart_paths")),
        "final_validation_result_path": data.get("final_validation_result_path"),
        "effective_max_retries": data.get("effective_max_retries"),
        "events": _event_list(data.get("events")),
        "error": data.get("error") if isinstance(data.get("error"), dict) else None,
    }


def _controller_task_type(job_dir: Path) -> str | None:
    controller_plan = _read_json_if_exists(job_dir / "controller_plan.json")
    if not controller_plan:
        return None
    task_type = controller_plan.get("task_type")
    return str(task_type) if task_type else None


def _validate_max_retries(max_retries: int) -> int:
    return max(0, min(int(max_retries), MAX_RETRIES))


def _get_job_dir(job_id: str) -> Path:
    if not job_id or Path(job_id).name != job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id.")
    job_dir = JOB_ROOT / job_id
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow job not found.")
    return job_dir



def _collect_chart_paths(job_dir: Path, workflow_type: str) -> list[str]:
    if not job_dir.exists():
        return []

    result_filename = "prediction_result.json" if workflow_type == PREDICTION_TASK_TYPE else "analysis_result.json"
    result_data = _read_json_if_exists(job_dir / result_filename) or {}
    paths = _extract_chart_paths(result_data.get("charts"), job_dir)
    if not paths:
        charts_dir = job_dir / "charts"
        paths = [str(path) for path in sorted(charts_dir.glob("*.png")) if path.is_file() and path.stat().st_size > 0] if charts_dir.exists() else []
    return _deduplicate_strings(paths)


def _extract_chart_paths(value: Any, job_dir: Path) -> list[str]:
    if not isinstance(value, list):
        return []

    paths: list[str] = []
    for item in value:
        raw_path: Any = item
        if isinstance(item, dict):
            raw_path = (
                item.get("path")
                or item.get("file_path")
                or item.get("chart_path")
                or item.get("url")
                or item.get("file")
                or item.get("filename")
            )
        normalized = _normalize_chart_path(raw_path, job_dir)
        if normalized:
            paths.append(normalized)
    return _deduplicate_strings(paths)


def _normalize_chart_path(value: Any, job_dir: Path) -> str | None:
    if not isinstance(value, str):
        return None

    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized

    local_path = Path(normalized)
    if normalized.startswith("/storage/"):
        local_path = Path(normalized.lstrip("/"))
    elif normalized.startswith("storage/"):
        local_path = Path(normalized)
    elif normalized.startswith("charts/"):
        local_path = job_dir / normalized
    elif "/" not in normalized:
        local_path = job_dir / "charts" / normalized

    if local_path.is_absolute() or str(local_path).startswith("storage"):
        return str(local_path)
    return str(local_path)


def _workflow_type_for_job_dir(job_dir: Path) -> str:
    if (job_dir / "prediction_result.json").exists() or (job_dir / "prediction_task_status.json").exists():
        return PREDICTION_TASK_TYPE
    status_data = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME) or {}
    workflow_type = str(status_data.get("workflow_type") or "")
    return workflow_type or ANALYSIS_WORKFLOW_TYPE


def _resolve_chart_file(job_dir: Path, job_id: str, chart_path: str) -> Path:
    raw = str(chart_path or "").replace("\\", "/").strip()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="chart_path is required.")
    if raw.startswith("http://") or raw.startswith("https://"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only local job charts can be deleted.")

    storage_prefix = f"storage/jobs/{job_id}/"
    url_storage_prefix = f"/storage/jobs/{job_id}/"
    if raw.startswith(url_storage_prefix):
        candidate = Path(raw.lstrip("/"))
    elif raw.startswith(storage_prefix):
        candidate = Path(raw)
    elif f"/storage/jobs/{job_id}/" in raw:
        suffix = raw.split(f"/storage/jobs/{job_id}/", 1)[1]
        candidate = Path("storage") / "jobs" / job_id / suffix
    elif raw.startswith("charts/"):
        candidate = job_dir / raw
    elif "/charts/" in raw:
        candidate = job_dir / "charts" / raw.rsplit("/charts/", 1)[1]
    elif "/" not in raw:
        candidate = job_dir / "charts" / raw
    else:
        candidate = Path(raw)

    if not candidate.is_absolute():
        candidate = candidate.resolve()
    charts_dir = (job_dir / "charts").resolve()
    try:
        candidate.relative_to(charts_dir)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Chart path is outside this job.") from exc
    return candidate


def _chart_storage_path(job_dir: Path, chart_path: Path) -> str:
    job_id = job_dir.name
    try:
        relative = chart_path.resolve().relative_to(job_dir.resolve()).as_posix()
    except ValueError:
        relative = f"charts/{chart_path.name}"
    return f"storage/jobs/{job_id}/{relative}"


def _remove_deleted_chart_refs(data: dict[str, Any], deleted_path: Path, job_dir: Path) -> tuple[dict[str, Any], bool]:
    updated = dict(data)
    changed = False
    for key in ("charts", "chart_paths"):
        if key not in updated:
            continue
        value = updated.get(key)
        if not isinstance(value, list):
            continue
        filtered = []
        for item in value:
            raw_path = _chart_entry_path(item)
            if raw_path and _same_chart_path(raw_path, deleted_path, job_dir):
                changed = True
                continue
            filtered.append(item)
        updated[key] = filtered
    return updated, changed


def _chart_entry_path(item: Any) -> str | None:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("path", "file_path", "chart_path", "url", "file", "filename"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _same_chart_path(value: str, deleted_path: Path, job_dir: Path) -> bool:
    normalized = _normalize_chart_path(value, job_dir)
    if not normalized:
        return False
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return False
    try:
        candidate = Path(normalized)
        if not candidate.is_absolute():
            candidate = candidate.resolve()
        return candidate == deleted_path.resolve()
    except OSError:
        return Path(str(normalized).replace("\\", "/")).name == deleted_path.name


def _deduplicate_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _existing_or_none(value: Any, fallback_path: Path) -> str | None:
    if isinstance(value, str) and value:
        return value
    return str(fallback_path) if fallback_path.exists() else None


def _safe_asset_type(dataset_id: str) -> str:
    try:
        return get_uploaded_asset_type(dataset_id)
    except HTTPException:
        return "tabular"


def _asset_type_from_job_dir(job_dir: Path) -> str:
    if job_dir.exists() and (job_dir / "visual_parse_result.json").exists():
        return IMAGE_ASSET_TYPE
    return "tabular"


def _visual_extracted_path(data: dict[str, Any], job_dir: Path) -> str | None:
    value = data.get("visual_extracted_dataset_path")
    if isinstance(value, str) and value:
        return value
    dataset_id = str(data.get("dataset_id") or "")
    if dataset_id:
        try:
            path = get_dataset_dir(dataset_id) / "visual_extracted.csv"
        except HTTPException:
            path = Path("")
        if str(path) and path.exists():
            return str(path)
    if job_dir.exists() and (job_dir / "visual_extracted.csv").exists():
        return str(job_dir / "visual_extracted.csv")
    return None


def _visual_confidence(job_dir: Path) -> float | None:
    parse_result = _read_json_if_exists(job_dir / "visual_parse_result.json")
    if not parse_result:
        return None
    return _float_or_none(parse_result.get("confidence"))


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not str(path) or not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _event_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


