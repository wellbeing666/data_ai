import json
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.agents.chart_code_refiner_agent import create_refined_chart_script
from app.agents.chart_config_agent import create_chart_config
from app.agents.chart_suggestion_agent import create_chart_refine_suggestions
from app.agents.controller_agent import create_controller_plan
from app.agents.preflight_agent import create_preflight_assessment
from app.agents.roadmap_agent import create_analysis_roadmap
from app.agents.vision_parsing_agent import VisionParsingAgent, write_visual_extracted_csv
from app.sandbox.code_safety import validate_script_static_safety
from app.sandbox.local_executor import LocalSubprocessSandboxExecutor
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
ROADMAP_FILENAME = "analysis_roadmap.json"
QUALITY_REVIEW_FILENAME = "quality_review.json"


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
    events = [create_event("queued", "pending", "统一分析任务已创建。")]
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



def create_workflow_preflight(dataset_id: str, user_goal: str) -> dict[str, Any]:
    asset_type = _safe_asset_type(dataset_id)
    if asset_type == IMAGE_ASSET_TYPE:
        return {
            "dataset_id": dataset_id,
            "user_goal": user_goal,
            "asset_type": asset_type,
            "preflight_path": None,
            "intent_type": "ambiguous",
            "is_task_clear": False,
            "clarity_score": 0.35,
            "detected_fields": [],
            "data_quality_report": {
                "row_count": 0,
                "column_count": 0,
                "missing_fields": [],
                "warnings": ["图片输入需要先进入视觉解析 Agent，抽取结构化数据后再进行意图识别。"],
            },
            "clarifying_questions": ["请确认图片中希望优先识别表格、图表，还是业务看板指标。"],
            "intent_questions": [
                {
                    "question_id": "image_scope",
                    "question": "希望优先从图片中识别哪类内容？",
                    "options": [
                        {"value": "table", "label": "表格数据", "append_text": "请优先识别图片中的表格并抽取为结构化数据。"},
                        {"value": "chart", "label": "图表数据", "append_text": "请优先识别图片中的图表坐标、图例和数值。"},
                        {"value": "dashboard", "label": "看板指标", "append_text": "请优先抽取看板中的核心指标、维度和时间信息。"},
                        {"value": "auto", "label": "让 AI 自动判断", "append_text": "请自动选择最可靠的结构化数据来源。"},
                    ],
                }
            ],
            "suggested_goals": ["请从图片中抽取结构化数据，并生成趋势或分组对比图。"],
            "optimized_goal": "请从图片中抽取可靠的结构化数据，优先生成趋势或分组对比图，并说明图片识别可能带来的限制。",
            "next_action": "needs_user_choice",
            "data_understanding": {},
        }

    load_uploaded_dataset(dataset_id)
    dataset_profile = generate_dataset_profile(dataset_id)
    preflight = create_preflight_assessment(user_goal=user_goal, dataset_profile=dataset_profile)
    dataset_dir = get_dataset_dir(dataset_id)
    preflight_path = dataset_dir / "preflight_assessment.json"
    _write_json(preflight_path, preflight)
    return {
        "dataset_id": dataset_id,
        "user_goal": user_goal,
        "asset_type": asset_type,
        "preflight_path": str(preflight_path),
        **preflight,
    }


def create_workflow_chart_config(
    job_id: str,
    instruction: str,
    current_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    workflow_type = _workflow_type_for_job_dir(job_dir)
    dataset_profile = _read_json_if_exists(job_dir / "dataset_profile.json") or {}
    result_filename = "prediction_result.json" if workflow_type == PREDICTION_TASK_TYPE else "analysis_result.json"
    result_payload = _read_json_if_exists(job_dir / result_filename) or _read_json_if_exists(job_dir / "report_data.json") or {}
    if not result_payload:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前任务还没有可用于生成图表配置的分析结果。",
        )
    chart_config = create_chart_config(
        instruction=instruction,
        result_payload=result_payload,
        dataset_profile=dataset_profile,
        current_config=current_config,
    )
    config_dir = job_dir / "chart_configs"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / f"chart_config_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.json"
    _write_json(config_path, chart_config)
    return {**chart_config, "config_path": str(config_path)}



def create_workflow_chart_suggestions(job_id: str, chart_path: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = get_workflow_job_status(job_id)
    workflow_type = str(status_data.get("workflow_type") or _workflow_type_for_job_dir(job_dir))
    dataset_profile = _read_json_if_exists(job_dir / "dataset_profile.json") or {}
    result_filename = "prediction_result.json" if workflow_type == PREDICTION_TASK_TYPE else "analysis_result.json"
    result_payload = _read_json_if_exists(job_dir / result_filename) or _read_json_if_exists(job_dir / "report_data.json") or {}
    visual_parse_result = _read_json_if_exists(job_dir / "visual_parse_result.json")
    suggestions = create_chart_refine_suggestions(
        user_goal=str(status_data.get("user_goal") or ""),
        chart_path=chart_path,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        workflow_type=workflow_type,
        visual_parse_result=visual_parse_result,
    )
    return {
        "job_id": job_id,
        "chart_path": chart_path,
        "suggestions": suggestions,
    }

def refine_workflow_chart(
    job_id: str,
    chart_path: str,
    instruction: str,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = get_workflow_job_status(job_id)
    if status_data.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请等待当前分析完成后再调整图表。",
        )
    dataset_id = str(status_data.get("dataset_id") or "")
    if not dataset_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前任务缺少数据集信息。")

    workflow_type = str(status_data.get("workflow_type") or _workflow_type_for_job_dir(job_dir))
    result_filename = "prediction_result.json" if workflow_type == PREDICTION_TASK_TYPE else "analysis_result.json"
    result_payload = _read_json_if_exists(job_dir / result_filename) or {}
    dataset_profile = _read_json_if_exists(job_dir / "dataset_profile.json") or {}
    source_script_path = _latest_existing_script_path(status_data)
    if source_script_path is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务缺少可用于调整图表的脚本。")

    input_file, _ = load_uploaded_dataset(dataset_id)
    original_script = source_script_path.read_text(encoding="utf-8")
    refined_script = create_refined_chart_script(
        input_file=str(input_file.resolve()),
        output_dir=str(job_dir),
        original_script=original_script,
        target_chart_path=chart_path,
        instruction=instruction,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        workflow_type=workflow_type,
    )

    refinements_dir = job_dir / "chart_refinements"
    refinements_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    refined_script_path = refinements_dir / f"refined_chart_{timestamp}.py"
    refined_script_path.write_text(refined_script, encoding="utf-8")

    safety_issues = validate_script_static_safety(
        refined_script_path,
        input_file=input_file.resolve(),
        output_dir=job_dir,
    )
    if safety_issues:
        result = {
            "success": False,
            "message": "图表调整脚本未通过安全检查。",
            "job_id": job_id,
            "chart_path": chart_path,
            "instruction": instruction,
            "source_script_path": str(source_script_path),
            "refined_script_path": str(refined_script_path),
            "execution_result_path": None,
            "chart_paths": _collect_chart_paths(job_dir, workflow_type),
            "safety_issues": safety_issues,
        }
        _write_json(refinements_dir / f"refinement_result_{timestamp}.json", result)
        return result

    before_chart_files = _chart_file_set(job_dir)
    execution_result = LocalSubprocessSandboxExecutor().execute(
        generated_script_path=str(refined_script_path),
        input_file=str(input_file.resolve()),
        output_dir=str(job_dir),
        timeout_seconds=timeout_seconds,
    )
    if execution_result.get("success"):
        _replace_target_chart_if_new_chart_created(
            job_dir=job_dir,
            job_id=job_id,
            chart_path=chart_path,
            before_chart_files=before_chart_files,
        )
    execution_result_path = refinements_dir / f"refinement_execution_{timestamp}.json"
    _write_json(execution_result_path, execution_result)
    chart_paths = _collect_chart_paths(job_dir, workflow_type)
    result = {
        "success": bool(execution_result.get("success")),
        "message": "图表已按要求重新渲染。" if execution_result.get("success") else "图表调整脚本执行失败，请修改要求后重试。",
        "job_id": job_id,
        "chart_path": chart_path,
        "instruction": instruction,
        "source_script_path": str(source_script_path),
        "refined_script_path": str(refined_script_path),
        "execution_result_path": str(execution_result_path),
        "chart_paths": chart_paths,
        "safety_issues": [],
    }
    _write_json(refinements_dir / f"refinement_result_{timestamp}.json", result)
    return result


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
        events.append(create_event("failed", "failed", f"统一分析任务执行失败：{exc}"))
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
        events.append(create_event("queued", "pending", "统一分析任务已创建。"))
    asset_type = _safe_asset_type(dataset_id)

    events.append(create_event("loading_dataset", "running", "正在读取数据并生成字段画像。"))
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
        events.append(create_event("visual_parsing", "running", "视觉解析 Agent 正在从图片中抽取结构化数据。"))
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
            events.append(create_event("visual_parsing", "failed", "视觉解析 Agent 未能从图片中抽取可靠结构化数据。"))
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
        events.append(create_event("visual_parsing", "success", "视觉解析 Agent 已完成图片结构化抽取。"))

    load_uploaded_dataset(dataset_id)
    dataset_profile = generate_dataset_profile(dataset_id)
    _write_json(job_dir / "dataset_profile.json", dataset_profile)

    events.append(create_event("rag_retrieval", "running", "正在检索业务知识，为主控分流提供参考。"))
    rag_search_result = get_rag_service().search(query=user_goal, dataset_profile=dataset_profile)
    rag_context = format_rag_context(rag_search_result)
    _write_json(job_dir / "rag_retrieval.json", rag_search_result)

    events.append(create_event("controller", "running", "主控 Agent 正在选择分析工作流。"))
    controller_plan = create_controller_plan(user_goal, dataset_profile, rag_context=rag_context)
    task_type = str(controller_plan.get("task_type") or "general_data_analysis")
    workflow_type = PREDICTION_TASK_TYPE if task_type == PREDICTION_TASK_TYPE else ANALYSIS_WORKFLOW_TYPE
    _write_json(job_dir / "controller_plan.json", controller_plan)
    events.append(create_event("controller", "success", f"主控 Agent 已选择任务类型：{task_type}。"))

    events.append(create_event("roadmap", "running", "路线图 Agent 正在生成可视化分析路线。"))
    roadmap = create_analysis_roadmap(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        controller_plan=controller_plan,
        workflow_type=workflow_type,
    )
    analysis_roadmap_path = str(job_dir / ROADMAP_FILENAME)
    _write_json(job_dir / ROADMAP_FILENAME, roadmap)
    events.append(create_event("roadmap", "success", "路线图 Agent 已生成可视化分析路线。"))
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
        analysis_roadmap_path=analysis_roadmap_path,
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


def list_workflow_jobs(limit: int = 30, query: str | None = None) -> dict[str, Any]:
    safe_limit = max(1, min(int(limit), 100))
    normalized_query = _normalize_search_query(query)
    if not JOB_ROOT.exists():
        return {"jobs": []}

    job_dirs = [path for path in JOB_ROOT.iterdir() if path.is_dir()]
    job_dirs.sort(key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True)
    jobs: list[dict[str, Any]] = []
    for job_dir in job_dirs:
        status_data = _history_status_data(job_dir)
        if not status_data:
            continue
        workflow_type = _workflow_type_for_job_dir(job_dir)
        task_type = _controller_task_type(job_dir) or str(status_data.get("task_type") or "")
        normalized = _normalize_workflow_status(status_data, workflow_type=workflow_type, task_type=task_type)
        dataset_id = str(status_data.get("dataset_id") or normalized.get("dataset_id") or "")
        dataset_filename, file_type = _dataset_file_info(dataset_id)
        job_item = {
            "job_id": str(normalized.get("job_id") or job_dir.name),
            "dataset_id": dataset_id or None,
            "dataset_filename": dataset_filename,
            "file_type": file_type,
            "user_goal": str(status_data.get("user_goal") or normalized.get("user_goal") or ""),
            "status": str(normalized.get("status") or "pending"),
            "current_stage": normalized.get("current_stage"),
            "workflow_type": normalized.get("workflow_type"),
            "task_type": normalized.get("task_type"),
            "asset_type": normalized.get("asset_type"),
            "chart_count": len(normalized.get("chart_paths") or []),
            "created_at": _iso_from_timestamp(job_dir.stat().st_ctime),
            "updated_at": _iso_from_timestamp(job_dir.stat().st_mtime),
        }
        if normalized_query and not _workflow_job_matches_query(job_item, normalized_query):
            continue
        jobs.append(job_item)
        if len(jobs) >= safe_limit:
            break
    return {"jobs": jobs}


def delete_workflow_job(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id)
    status_data = _history_status_data(job_dir) or {}
    status_value = str(status_data.get("status") or "")
    if status_value not in {"success", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="运行中或排队中的分析对话不能删除，请等待任务结束后再删除。",
        )

    try:
        shutil.rmtree(job_dir)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除分析对话失败：{exc}",
        ) from exc
    return {"deleted": True, "job_id": job_id}


def get_workflow_job_status(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id)
    workflow_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME)
    prediction_status = _read_json_if_exists(job_dir / "prediction_task_status.json")
    analysis_status = _read_json_if_exists(job_dir / "task_status.json")

    if _is_authoritative_workflow_failure(workflow_status, prediction_status, analysis_status):
        return _normalize_workflow_status(
            workflow_status or {},
            workflow_type=(workflow_status or {}).get("workflow_type") or _workflow_type_for_job_dir(job_dir),
            task_type=(workflow_status or {}).get("task_type") or _controller_task_type(job_dir),
        )

    if prediction_status is not None:
        return _normalize_workflow_status(
            prediction_status,
            workflow_type=PREDICTION_TASK_TYPE,
            task_type=_controller_task_type(job_dir) or PREDICTION_TASK_TYPE,
        )

    if analysis_status is not None:
        return _normalize_workflow_status(
            analysis_status,
            workflow_type=ANALYSIS_WORKFLOW_TYPE,
            task_type=_controller_task_type(job_dir) or "general_data_analysis",
        )

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
            "artifacts": {
                "analysis_roadmap": status_data.get("analysis_roadmap_path"),
                "quality_review": status_data.get("quality_review_path"),
            },
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
        "analysis_roadmap": status_data.get("analysis_roadmap_path"),
        "quality_review": status_data.get("quality_review_path"),
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
    analysis_roadmap_path: str | None = None,
    quality_review_path: str | None = None,
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
        "analysis_roadmap_path": analysis_roadmap_path,
        "quality_review_path": quality_review_path,
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
            "artifacts": {
                "analysis_roadmap": analysis_roadmap_path,
                "quality_review": quality_review_path,
            },
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
            "analysis_roadmap_path": _existing_or_none(data.get("analysis_roadmap_path"), job_dir / ROADMAP_FILENAME),
            "quality_review_path": _existing_or_none(data.get("quality_review_path"), job_dir / QUALITY_REVIEW_FILENAME),
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
        "dataset_id": str(data.get("dataset_id") or "") or None,
        "user_goal": str(data.get("user_goal") or "") or None,
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
        "analysis_roadmap_path": data.get("analysis_roadmap_path"),
        "quality_review_path": data.get("quality_review_path"),
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




def _history_status_data(job_dir: Path) -> dict[str, Any] | None:
    prediction_status = _read_json_if_exists(job_dir / "prediction_task_status.json")
    analysis_status = _read_json_if_exists(job_dir / "task_status.json")
    workflow_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME)
    if _is_authoritative_workflow_failure(workflow_status, prediction_status, analysis_status):
        return workflow_status
    for data in (prediction_status, analysis_status, workflow_status):
        if data:
            return data
    return None



def _is_authoritative_workflow_failure(
    workflow_status: dict[str, Any] | None,
    prediction_status: dict[str, Any] | None,
    analysis_status: dict[str, Any] | None,
) -> bool:
    if not workflow_status or workflow_status.get("status") != "failed" or not workflow_status.get("error"):
        return False
    branch_status = prediction_status or analysis_status
    if branch_status is None:
        return True
    if branch_status.get("status") in {"success", "failed"}:
        return False
    return True



def _normalize_search_query(query: str | None) -> str:
    return " ".join(str(query or "").casefold().split())


def _workflow_job_matches_query(job_item: dict[str, Any], query: str) -> bool:
    searchable_values = [
        job_item.get("job_id"),
        job_item.get("dataset_id"),
        job_item.get("dataset_filename"),
        job_item.get("file_type"),
        job_item.get("user_goal"),
        job_item.get("status"),
        _status_search_label(job_item.get("status")),
        job_item.get("current_stage"),
        job_item.get("workflow_type"),
        _workflow_search_label(job_item.get("workflow_type"), job_item.get("task_type")),
        job_item.get("task_type"),
        job_item.get("asset_type"),
        _asset_search_label(job_item.get("asset_type")),
        job_item.get("created_at"),
        job_item.get("updated_at"),
    ]
    haystack = " ".join(str(value).casefold() for value in searchable_values if value)
    return all(token in haystack for token in query.split())


def _status_search_label(value: Any) -> str:
    labels = {
        "pending": "排队 等待",
        "running": "运行中 执行中",
        "success": "成功 已完成",
        "failed": "失败",
    }
    return labels.get(str(value or ""), "")


def _workflow_search_label(workflow_type: Any, task_type: Any) -> str:
    if str(workflow_type or task_type or "") == PREDICTION_TASK_TYPE:
        return "情景预测 what-if 预测"
    return "数据分析 普通分析"


def _asset_search_label(value: Any) -> str:
    return "图片 截图" if str(value or "") == IMAGE_ASSET_TYPE else "表格 数据"


def _dataset_file_info(dataset_id: str) -> tuple[str | None, str | None]:
    if not dataset_id:
        return None, None
    try:
        dataset_dir = get_dataset_dir(dataset_id)
    except HTTPException:
        return None, None
    files = [path for path in dataset_dir.iterdir() if path.is_file()]
    if not files:
        return None, None
    preferred = [path for path in files if path.suffix.lower() in {".csv", ".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".webp"}]
    file_path = sorted(preferred or files, key=lambda path: path.name)[0]
    return file_path.name, file_path.suffix.lower().lstrip(".") or None


def _iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


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



def _latest_existing_script_path(status_data: dict[str, Any]) -> Path | None:
    attempts = _dict_list(status_data.get("attempts"))
    for attempt in reversed(attempts):
        script_path = Path(str(attempt.get("script_path") or ""))
        if script_path.exists() and script_path.is_file():
            return script_path
    return None

def _chart_file_set(job_dir: Path) -> set[Path]:
    charts_dir = job_dir / "charts"
    if not charts_dir.exists():
        return set()
    return {path.resolve() for path in charts_dir.glob("*.png") if path.is_file()}


def _replace_target_chart_if_new_chart_created(
    *,
    job_dir: Path,
    job_id: str,
    chart_path: str,
    before_chart_files: set[Path],
) -> None:
    after_chart_files = _chart_file_set(job_dir)
    new_chart_files = after_chart_files - before_chart_files
    if not new_chart_files:
        return
    try:
        target_file = _resolve_chart_file(job_dir, job_id, chart_path).resolve()
    except HTTPException:
        return
    if target_file in new_chart_files or not target_file.exists():
        return

    ordered_new_files = sorted(
        new_chart_files,
        key=lambda path: path.stat().st_mtime if path.exists() else 0.0,
        reverse=True,
    )
    refined_file = ordered_new_files[0]
    try:
        shutil.copyfile(refined_file, target_file)
    except OSError:
        return

    for new_file in ordered_new_files:
        try:
            if new_file.exists() and new_file.resolve() != target_file:
                new_file.unlink()
        except OSError:
            pass

    for filename in ("analysis_result.json", "prediction_result.json", "report_data.json"):
        artifact_path = job_dir / filename
        artifact_data = _read_json_if_exists(artifact_path)
        if not artifact_data:
            continue
        updated_data, changed = _replace_refined_chart_refs(artifact_data, target_file, ordered_new_files, job_dir)
        if changed:
            _write_json(artifact_path, updated_data)


def _replace_refined_chart_refs(
    data: dict[str, Any],
    target_file: Path,
    refined_files: list[Path],
    job_dir: Path,
) -> tuple[dict[str, Any], bool]:
    updated = dict(data)
    changed = False
    target_entry = _chart_storage_path(job_dir, target_file)
    for key in ("charts", "chart_paths"):
        value = updated.get(key)
        if not isinstance(value, list):
            continue
        filtered = []
        target_present = False
        for item in value:
            raw_path = _chart_entry_path(item)
            if raw_path and any(_same_chart_path(raw_path, refined_file, job_dir) for refined_file in refined_files):
                changed = True
                continue
            if raw_path and _same_chart_path(raw_path, target_file, job_dir):
                target_present = True
            filtered.append(item)
        if not target_present:
            filtered.append(target_entry)
            changed = True
        updated[key] = filtered
    return updated, changed



def _collect_chart_paths(job_dir: Path, workflow_type: str) -> list[str]:
    if not job_dir.exists():
        return []

    result_filename = "prediction_result.json" if workflow_type == PREDICTION_TASK_TYPE else "analysis_result.json"
    paths: list[str] = []
    for filename in (result_filename, "report_data.json"):
        result_data = _read_json_if_exists(job_dir / filename) or {}
        paths.extend(_extract_chart_paths(result_data.get("charts"), job_dir))
        paths.extend(_extract_chart_paths(result_data.get("chart_paths"), job_dir))

    charts_dir = job_dir / "charts"
    if charts_dir.exists():
        paths.extend(
            str(path)
            for path in sorted(charts_dir.glob("*.png"))
            if path.is_file() and path.stat().st_size > 0
        )
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




