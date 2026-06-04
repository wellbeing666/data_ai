import json
import re
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
from app.agents.roadmap_agent import create_analysis_roadmap, render_analysis_roadmap
from app.agents.vision_parsing_agent import VisionParsingAgent, write_visual_extracted_csv
from app.sandbox.code_safety import validate_script_static_safety
from app.sandbox.local_executor import LocalSubprocessSandboxExecutor
from app.services.auto_repair_analysis import run_auto_repair_analysis_job
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_reader import find_uploaded_image_file, get_dataset_dir, get_uploaded_asset_type, load_uploaded_dataset
from app.services.execution_log_service import create_event, get_execution_log, write_execution_log
from app.services.job_control_service import JobCancelled, checkpoint_job_control, read_job_control, request_job_action, reset_runtime_control, write_job_control
from app.services.llm_client import get_llm_client
from app.services.prediction_workflow import run_prediction_job
from app.services.rag_service import format_rag_context, get_rag_service
from app.services.report_service import generate_pptx_report


JOB_ROOT = Path("storage/jobs")
WORKFLOW_STATUS_FILENAME = "workflow_task_status.json"
MAX_RETRIES = 3
PREDICTION_TASK_TYPE = "what_if_prediction"
ANALYSIS_WORKFLOW_TYPE = "auto_repair"
IMAGE_ASSET_TYPE = "image"
ROADMAP_FILENAME = "analysis_roadmap.json"
QUALITY_REVIEW_FILENAME = "quality_review.json"

FOLLOW_UP_SYSTEM_PROMPT = """你是 AI 原生数据分析工作台的追问分析 Agent。

用户会在一次分析任务完成后提出后续问题。你必须基于已生成的结构化产物回答，不要泛泛复述报告摘要。

要求：
1. 先直接回答问题，再给支撑依据。
2. 优先使用 analysis_result、prediction_result、report_data、evidence_chain、explanation、quality_review 和 report.md 中的数据。
3. 涉及下降原因、影响因素或预测时，只能表述为相关信号、可能原因或待验证线索，不能写成确定因果。
4. 如果现有产物无法回答，明确说明缺少哪些数据或证据。
5. 返回一个合法 JSON 对象，不要输出 Markdown 代码块。

返回格式：
{
  "answer": "直接答案",
  "supporting_points": ["依据 1", "依据 2"],
  "evidence_refs": ["产物名或证据位置"],
  "limitations": ["限制说明"]
}
"""


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
    write_job_control(job_dir, {"cancel_requested": False, "pause_requested": False, "requested_action": "", "control_status": "pending"})
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
    refined_script_path = refinements_dir / f"refined_chart_{timestamp}.py.txt"
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
    job_dir = (JOB_ROOT / job_id).resolve()
    try:
        result = run_workflow_job(
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
        final_status = str(result.get("status") or "")
        if final_status == "success":
            reset_runtime_control(job_dir, status="idle", message="任务已完成。")
        elif final_status == "failed":
            reset_runtime_control(job_dir, status="failed", message="任务未完成。")
        elif final_status == "cancelled":
            reset_runtime_control(job_dir, status="cancelled", message="任务已取消。")
        else:
            reset_runtime_control(job_dir, status="idle", message="任务已结束。")
    except JobCancelled:
        current_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME) or {}
        events = _event_list(current_status.get("events"))
        events.append(create_event("cancelled", "cancelled", "统一分析任务已取消。"))
        reset_runtime_control(job_dir, status="cancelled", message="任务已取消。")
        _write_workflow_status(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="cancelled",
            current_stage="cancelled",
            workflow_type=current_status.get("workflow_type"),
            task_type=current_status.get("task_type"),
            asset_type=current_status.get("asset_type") or _safe_asset_type(dataset_id),
            attempts=_dict_list(current_status.get("attempts")),
            events=events,
            max_retries=_validate_max_retries(max_retries),
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:  # pragma: no cover - background safety net
        current_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME) or {}
        events = _event_list(current_status.get("events"))
        events.append(create_event("failed", "failed", f"统一分析任务执行失败：{exc}"))
        reset_runtime_control(job_dir, status="failed", message="任务未完成。")
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
    reset_runtime_control(job_dir, status="running", message="任务正在执行。")
    checkpoint_job_control(job_dir)

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
    render_result = render_analysis_roadmap(roadmap, job_dir)
    roadmap = {**roadmap, **render_result}
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
    checkpoint_job_control(job_dir)

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
    if status_value not in {"success", "failed", "cancelled"}:
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

    if _is_authoritative_workflow_state(workflow_status, prediction_status, analysis_status):
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到当前分析任务。")
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
        "evidence_chain": status_data.get("evidence_chain_path"),
        "cleaning_report": status_data.get("cleaning_report_path"),
        "report": status_data.get("report_path"),
        "pptx": status_data.get("pptx_path"),
        "pptx_preview": status_data.get("pptx_preview_path"),
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



def generate_workflow_pptx(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = get_workflow_job_status(job_id)
    if status_data.get("status") != "success":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="请等待分析完成后再生成 PPTX。",
        )
    workflow_type = str(status_data.get("workflow_type") or _workflow_type_for_job_dir(job_dir))
    result_key = "final_prediction_result_path" if workflow_type == PREDICTION_TASK_TYPE else "final_result_path"
    fallback_name = "prediction_result.json" if workflow_type == PREDICTION_TASK_TYPE else "analysis_result.json"
    result_path = Path(str(status_data.get(result_key) or job_dir / fallback_name))
    if not result_path.exists():
        result_path = job_dir / fallback_name
    if not result_path.exists():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务缺少可用于生成 PPTX 的分析结果。")
    chart_paths = _collect_chart_paths(job_dir, workflow_type)
    _set_job_status(job_dir, status_value="success", current_stage="pptx", event=create_event("pptx", "running", "正在生成 PPTX。"))
    result = generate_pptx_report(str(result_path), chart_paths)
    artifacts = {
        "pptx_path": result.get("pptx_path"),
        "pptx_preview_path": result.get("pptx_preview_path"),
    }
    _set_job_status(
        job_dir,
        status_value="success",
        current_stage="success",
        event=create_event("pptx", "success", "PPTX 已生成。"),
        artifacts=artifacts,
    )
    return {
        "job_id": job_id,
        "pptx_path": result.get("pptx_path"),
        "pptx_preview_path": result.get("pptx_preview_path"),
        "message": "PPTX 已生成。",
        "status": "success",
    }

def control_workflow_job(job_id: str, action: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    normalized_action = str(action or "").strip()
    allowed_actions = {
        "cancel",
        "pause",
        "resume",
        "rerun_all",
        "rerun_failed",
        "rerun_explanation",
        "rerun_charts",
        "rerun_quality",
    }
    if normalized_action not in allowed_actions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不支持的任务控制操作。")

    status_data = get_workflow_job_status(job_id)
    status_value = str(status_data.get("status") or "")
    control_state = read_job_control(job_dir)
    is_active = status_value in {"pending", "running"}
    is_terminal = status_value in {"success", "failed", "cancelled"}

    if normalized_action == "pause":
        if not is_active:
            return _control_response(job_id, normalized_action, False, "当前任务没有正在执行的步骤。", status_value)
        request_job_action(job_dir, normalized_action)
        _append_job_event(job_dir, create_event("control", "running", "已请求暂停任务。"))
        return _control_response(job_id, normalized_action, True, "已请求暂停，任务会停在最近的安全节点。", status_value)

    if normalized_action == "resume":
        if not control_state.get("pause_requested") and control_state.get("control_status") != "paused":
            return _control_response(job_id, normalized_action, False, "当前任务没有处于暂停状态。", status_value)
        request_job_action(job_dir, normalized_action)
        _append_job_event(job_dir, create_event("control", "running", "任务已继续执行。"))
        return _control_response(job_id, normalized_action, True, "任务已继续执行。", status_value)

    if normalized_action == "cancel":
        if not is_active and not control_state.get("pause_requested"):
            return _control_response(job_id, normalized_action, False, "当前任务已结束，无需取消。", status_value)
        request_job_action(job_dir, normalized_action)
        _append_job_event(job_dir, create_event("control", "running", "已请求取消任务。"))
        return _control_response(job_id, normalized_action, True, "已请求取消，任务会在安全节点停止。", status_value)

    if is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前分析仍在执行，请先取消或等待完成后再重跑。")
    if not is_terminal:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务状态暂不支持重跑。")
    if normalized_action in {"rerun_explanation", "rerun_charts", "rerun_quality"} and status_value != "success":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请在分析成功后重跑单个 Agent。")

    request_job_action(job_dir, normalized_action)
    _set_job_status(
        job_dir,
        status_value="running",
        current_stage=normalized_action,
        event=create_event(normalized_action, "running", _rerun_message(normalized_action)),
    )
    message_map = {
        "rerun_all": "已开始完整重跑。",
        "rerun_failed": "已开始从失败阶段重跑。",
        "rerun_explanation": "已开始重跑解释 Agent。",
        "rerun_charts": "已开始重跑图表 Agent。",
        "rerun_quality": "已开始重跑质检 Agent。",
    }
    return {
        "job_id": job_id,
        "action": normalized_action,
        "accepted": True,
        "message": message_map[normalized_action],
        "status": "running",
        "background_action": normalized_action,
    }


def rerun_workflow_job_background(job_id: str, action: str) -> None:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = _history_status_data(job_dir) or get_workflow_job_status(job_id)
    dataset_id = str(status_data.get("dataset_id") or "")
    user_goal = str(status_data.get("user_goal") or "")
    max_retries = int(status_data.get("effective_max_retries") or 3)
    timeout_seconds = int(status_data.get("timeout_seconds") or 90)
    reset_runtime_control(job_dir, status="running", message=_rerun_message(action))
    try:
        if action in {"rerun_all", "rerun_failed"}:
            run_workflow_job(
                job_id=job_id,
                dataset_id=dataset_id,
                user_goal=user_goal,
                max_retries=max_retries,
                timeout_seconds=timeout_seconds,
            )
        else:
            _refresh_workflow_artifact(job_id, action)
            _set_job_status(
                job_dir,
                status_value="success",
                current_stage="success",
                event=create_event(action, "success", "指定 Agent 已完成重跑。"),
            )
        reset_runtime_control(job_dir, status="idle", message="重跑已完成。")
    except JobCancelled:
        reset_runtime_control(job_dir, status="cancelled", message="任务已取消。")
        _set_job_status(
            job_dir,
            status_value="cancelled",
            current_stage="cancelled",
            event=create_event("cancelled", "cancelled", "任务已取消。"),
        )
    except Exception as exc:  # pragma: no cover - background safety net
        reset_runtime_control(job_dir, status="failed", message="重跑未完成。")
        _set_job_status(
            job_dir,
            status_value="failed",
            current_stage="failed",
            event=create_event("failed", "failed", f"重跑未完成：{exc}"),
            error={"type": exc.__class__.__name__, "message": str(exc), "traceback": traceback.format_exc(limit=8)},
        )


def _control_response(job_id: str, action: str, accepted: bool, message: str, status_value: str | None) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "action": action,
        "accepted": accepted,
        "message": message,
        "status": status_value,
        "background_action": None,
    }

def create_workflow_follow_up(job_id: str, question: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = get_workflow_job_status(job_id)
    if status_data.get("status") != "success":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请等待分析完成后再继续追问。")
    normalized_question = str(question or "").strip()
    if not normalized_question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="追问内容不能为空。")
    artifacts = _follow_up_artifacts(job_dir)
    answer = _build_follow_up_answer(normalized_question, artifacts, status_data)
    followups_dir = job_dir / "followups"
    followups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    follow_up_path = followups_dir / f"followup_{timestamp}.json"
    payload = {
        "job_id": job_id,
        "question": normalized_question,
        "answer": answer,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "used_artifacts": sorted(artifacts.keys()),
    }
    _write_json(follow_up_path, payload)
    _append_job_event(job_dir, create_event("follow_up", "success", "已基于现有分析产物生成追问回答。"))
    return {**payload, "follow_up_path": str(follow_up_path)}


def _refresh_workflow_artifact(job_id: str, action: str) -> None:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = (
        _read_json_if_exists(job_dir / "prediction_task_status.json")
        or _read_json_if_exists(job_dir / "task_status.json")
        or get_workflow_job_status(job_id)
    )
    workflow_type = str(status_data.get("workflow_type") or _workflow_type_for_job_dir(job_dir))
    dataset_profile = _read_json_if_exists(job_dir / "dataset_profile.json") or {}
    user_goal = str(status_data.get("user_goal") or "")
    if action == "rerun_charts":
        _rerun_latest_chart_script(job_dir, status_data)
        _append_job_event(job_dir, create_event("rerun_charts", "success", "图表 Agent 已基于当前脚本重新渲染图表。"))
        return

    if workflow_type == PREDICTION_TASK_TYPE:
        from app.agents.prediction_explanation_agent import create_prediction_explanation
        from app.agents.quality_review_agent import create_quality_review
        from app.services.evidence_service import build_evidence_chain, merge_evidence_into_quality_review
        from app.services.report_service import generate_markdown_report

        prediction_result = _read_json_if_exists(job_dir / "prediction_result.json") or {}
        chart_paths = _collect_chart_paths(job_dir, PREDICTION_TASK_TYPE)
        explanation = _read_json_if_exists(job_dir / "prediction_explanation.json") or {}
        if action in {"rerun_explanation", "rerun_quality"}:
            if action == "rerun_explanation":
                explanation = create_prediction_explanation(user_goal, prediction_result, chart_paths)
                _write_json(job_dir / "prediction_explanation.json", explanation)
            evidence = build_evidence_chain(
                job_dir=job_dir,
                explanation=explanation,
                result_payload=prediction_result,
                report_data=_read_json_if_exists(job_dir / "report_data.json") or {},
                prediction_result=prediction_result,
                chart_paths=chart_paths,
            )
            quality = create_quality_review(user_goal, dataset_profile, prediction_result, explanation, {}, chart_paths, "what_if_prediction")
            _write_json(job_dir / "quality_review.json", merge_evidence_into_quality_review(quality, evidence))
            generate_markdown_report(str(job_dir / "prediction_result.json"), chart_paths, include_pptx=True)
            _append_job_event(job_dir, create_event(action, "success", "指定 Agent 已完成重跑。"))
        return

    from app.agents.explanation_agent import create_explanation
    from app.agents.quality_review_agent import create_quality_review
    from app.services.evidence_service import build_evidence_chain, merge_evidence_into_quality_review
    from app.services.report_service import generate_markdown_report

    analysis_result = _read_json_if_exists(job_dir / "analysis_result.json") or {}
    analysis_plan = _read_json_if_exists(job_dir / "analysis_plan.json") or {}
    chart_paths = _collect_chart_paths(job_dir, ANALYSIS_WORKFLOW_TYPE)
    explanation = _read_json_if_exists(job_dir / "explanation.json") or {}
    if action == "rerun_explanation":
        explanation = create_explanation(
            user_goal=user_goal,
            dataset_profile=dataset_profile,
            analysis_result=analysis_result,
            chart_paths=chart_paths,
            limitations=_string_list(analysis_plan.get("limitations")),
        )
        _write_json(job_dir / "explanation.json", explanation)
    if action in {"rerun_explanation", "rerun_quality"}:
        evidence = build_evidence_chain(
            job_dir=job_dir,
            explanation=explanation,
            result_payload=analysis_result,
            report_data=_read_json_if_exists(job_dir / "report_data.json") or {},
            chart_paths=chart_paths,
        )
        quality = create_quality_review(user_goal, dataset_profile, analysis_result, explanation, {}, chart_paths, "auto_repair")
        _write_json(job_dir / "quality_review.json", merge_evidence_into_quality_review(quality, evidence))
        generate_markdown_report(str(job_dir / "analysis_result.json"), chart_paths, include_pptx=True)
        _append_job_event(job_dir, create_event(action, "success", "指定 Agent 已完成重跑。"))


def _rerun_latest_chart_script(job_dir: Path, status_data: dict[str, Any]) -> None:
    script_path = _latest_existing_script_path(status_data)
    if script_path is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务缺少可用于重跑图表的脚本。")
    dataset_id = str(status_data.get("dataset_id") or "")
    input_file, _ = load_uploaded_dataset(dataset_id)
    execution_result = LocalSubprocessSandboxExecutor().execute(
        generated_script_path=str(script_path),
        input_file=str(input_file.resolve()),
        output_dir=str(job_dir),
        timeout_seconds=int(status_data.get("timeout_seconds") or 90),
    )
    _write_json(job_dir / "rerun_chart_execution_result.json", execution_result)
    if not execution_result.get("success"):
        raise RuntimeError("图表重跑未完成，请查看执行日志。")

def _append_job_event(job_dir: Path, event: dict[str, Any]) -> None:
    for filename in (WORKFLOW_STATUS_FILENAME, "task_status.json", "prediction_task_status.json"):
        path = job_dir / filename
        data = _read_json_if_exists(path)
        if not data:
            continue
        events = _event_list(data.get("events"))
        events.append(event)
        data["events"] = events
        data["current_stage"] = event.get("stage") or data.get("current_stage")
        _write_json(path, data)



def _set_job_status(
    job_dir: Path,
    *,
    status_value: str | None = None,
    current_stage: str | None = None,
    event: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
) -> None:
    for filename in (WORKFLOW_STATUS_FILENAME, "task_status.json", "prediction_task_status.json"):
        path = job_dir / filename
        data = _read_json_if_exists(path)
        if not data:
            continue
        if status_value is not None:
            data["status"] = status_value
        if current_stage is not None:
            data["current_stage"] = current_stage
        if event is not None:
            events = _event_list(data.get("events"))
            events.append(event)
            data["events"] = events
        if error is not None:
            data["error"] = error
        if artifacts:
            for key, value in artifacts.items():
                if value is not None:
                    data[key] = value
        _write_json(path, data)

def _follow_up_artifacts(job_dir: Path) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for filename in (
        "dataset_profile.json",
        "controller_plan.json",
        "data_understanding.json",
        "analysis_plan.json",
        "hypothesis_plan.json",
        "prediction_plan.json",
        "analysis_result.json",
        "prediction_result.json",
        "report_data.json",
        "explanation.json",
        "prediction_explanation.json",
        "quality_review.json",
        "evidence_chain.json",
        "cleaning_report.json",
    ):
        value = _read_json_if_exists(job_dir / filename)
        if value:
            artifacts[filename] = value
    report_text = _read_text_if_exists(job_dir / "report.md")
    if report_text:
        artifacts["report.md"] = report_text
    return artifacts


def _build_follow_up_answer(question: str, artifacts: dict[str, Any], status_data: dict[str, Any]) -> str:
    fallback = _build_rule_follow_up_answer(question, artifacts)
    prompt_payload = {
        "question": question,
        "job_context": {
            "user_goal": status_data.get("user_goal"),
            "workflow_type": status_data.get("workflow_type"),
            "task_type": status_data.get("task_type"),
            "dataset_id": status_data.get("dataset_id"),
        },
        "available_artifacts": sorted(artifacts.keys()),
        "artifacts": _compact_for_prompt(artifacts),
    }
    try:
        result = get_llm_client().chat_json(
            messages=[
                {"role": "system", "content": FOLLOW_UP_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False, indent=2)},
            ],
            temperature=0.1,
        )
    except Exception:
        return fallback
    return _format_follow_up_answer(result) or fallback


def _format_follow_up_answer(result: Any) -> str:
    if isinstance(result, str):
        return result.strip()
    if not isinstance(result, dict):
        return ""
    answer = str(result.get("answer") or "").strip()
    points = _string_list(result.get("supporting_points"))[:5]
    evidence_refs = _string_list(result.get("evidence_refs"))[:5]
    limitations = _string_list(result.get("limitations"))[:4]
    parts: list[str] = []
    if answer:
        parts.append(answer)
    if points:
        parts.append("依据：" + "；".join(points) + "。")
    if evidence_refs:
        parts.append("证据：" + "；".join(evidence_refs) + "。")
    if limitations:
        parts.append("限制：" + "；".join(limitations) + "。")
    return " ".join(parts).strip()


def _build_rule_follow_up_answer(question: str, artifacts: dict[str, Any]) -> str:
    snippets = _search_artifact_snippets(question, artifacts, limit=5)
    if snippets:
        details = "；".join(f"{item['text']}（{item['source']}）" for item in snippets)
        return f"针对“{question}”，现有分析产物中最相关的线索是：{details}。这些线索用于定位可能原因或相关信号，仍需要结合原始业务背景和后续验证判断。"

    explanation = artifacts.get("explanation.json") or artifacts.get("prediction_explanation.json") or {}
    recommendations = _string_list(explanation.get("recommendations"))[:4] if isinstance(explanation, dict) else []
    summary = str(explanation.get("summary") or "当前问题需要进一步查看分析产物。") if isinstance(explanation, dict) else "当前问题需要进一步查看分析产物。"
    advice = "；".join(recommendations or ["建议在证据链中核对对应分组表、计算字段和图表后再决策。"])
    return f"{summary} 针对“{question}”，当前结构化产物中没有找到更细的直接证据。建议重点查看：{advice}"


def _compact_for_prompt(value: Any, *, depth: int = 0, max_depth: int = 5, max_items: int = 12, max_string: int = 1200) -> Any:
    if depth >= max_depth:
        return _short_value(value, max_string=240)
    if isinstance(value, dict):
        compact: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                compact["__truncated__"] = True
                break
            compact[str(key)] = _compact_for_prompt(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string=max_string,
            )
        return compact
    if isinstance(value, list):
        result = [
            _compact_for_prompt(item, depth=depth + 1, max_depth=max_depth, max_items=max_items, max_string=max_string)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            result.append({"__truncated__": True, "total_items": len(value)})
        return result
    return _short_value(value, max_string=max_string)


def _short_value(value: Any, *, max_string: int = 1200) -> Any:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    return text if len(text) <= max_string else text[:max_string] + "..."


def _search_artifact_snippets(question: str, artifacts: dict[str, Any], *, limit: int = 5) -> list[dict[str, str]]:
    keywords = _question_keywords(question)
    if not keywords:
        return []
    candidates: list[tuple[int, str, str]] = []
    for artifact_name, artifact_value in artifacts.items():
        for path, text in _iter_artifact_texts(artifact_value, artifact_name):
            normalized = text.strip()
            if not normalized or len(normalized) < 8:
                continue
            score = sum(1 for keyword in keywords if keyword and keyword in normalized)
            if score <= 0:
                continue
            if re.search(r"[-+]?\d+(?:\.\d+)?%?|\d+月", normalized):
                score += 1
            candidates.append((score, path, _clip_snippet(normalized)))
    candidates.sort(key=lambda item: (-item[0], len(item[2])))
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, source, snippet in candidates:
        if snippet in seen:
            continue
        seen.add(snippet)
        result.append({"source": source, "text": snippet})
        if len(result) >= limit:
            break
    return result


def _question_keywords(question: str) -> list[str]:
    text = str(question or "")
    priority_words = [
        "1月", "2月", "3月", "4月", "5月", "6月", "下降", "下滑", "加速", "关键", "原因",
        "销量", "销售额", "环比", "同比", "贡献", "地区", "渠道", "商品", "品类", "类别",
        "家电", "个护", "食品", "预测", "证据", "风险", "限制", "PPT", "图表",
    ]
    keywords = [word for word in priority_words if word in text]
    keywords.extend(re.findall(r"\d+月|[-+]?\d+(?:\.\d+)?%|[A-Za-z][A-Za-z0-9_]{2,}", text))
    deduped: list[str] = []
    for keyword in keywords:
        if keyword and keyword not in deduped:
            deduped.append(keyword)
    return deduped[:12]


def _iter_artifact_texts(value: Any, source: str) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def walk(current: Any, path: str) -> None:
        if isinstance(current, dict):
            for key, item in current.items():
                walk(item, f"{path}.{key}")
            return
        if isinstance(current, list):
            for index, item in enumerate(current[:60]):
                walk(item, f"{path}[{index}]")
            return
        if current is None:
            return
        text = str(current)
        if text.strip():
            results.append((path, text))

    walk(value, source)
    return results


def _clip_snippet(text: str, *, max_length: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= max_length else text[:max_length] + "..."


def _rerun_message(action: str) -> str:
    return {
        "rerun_all": "正在完整重跑分析任务。",
        "rerun_failed": "正在从失败阶段重新执行分析任务。",
        "rerun_explanation": "正在重跑解释 Agent。",
        "rerun_charts": "正在重跑图表 Agent。",
        "rerun_quality": "正在重跑质检 Agent。",
    }.get(action, "正在重跑分析任务。")

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
    cleaning_report_path: str | None = None,
    evidence_chain_path: str | None = None,
    report_path: str | None = None,
    pptx_path: str | None = None,
    pptx_preview_path: str | None = None,
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
        "cleaning_report_path": cleaning_report_path,
        "evidence_chain_path": evidence_chain_path,
        "report_path": report_path,
        "pptx_path": pptx_path,
        "pptx_preview_path": pptx_preview_path,
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
                "cleaning_report": cleaning_report_path,
                "evidence_chain": evidence_chain_path,
                "report": report_path,
                "pptx": pptx_path,
                "pptx_preview": pptx_preview_path,
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
            "cleaning_report_path": _existing_or_none(data.get("cleaning_report_path"), job_dir / "cleaning_report.json"),
            "evidence_chain_path": _existing_or_none(data.get("evidence_chain_path"), job_dir / "evidence_chain.json"),
            "report_path": _existing_or_none(data.get("report_path"), job_dir / "report.md"),
            "pptx_path": _existing_or_none(data.get("pptx_path"), job_dir / "report.pptx"),
            "pptx_preview_path": _existing_or_none(data.get("pptx_preview_path"), job_dir / "pptx_preview.json"),
            "job_control_path": _existing_or_none(data.get("job_control_path"), job_dir / "job_control.json"),
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
        "cleaning_report_path": data.get("cleaning_report_path"),
        "evidence_chain_path": data.get("evidence_chain_path"),
        "report_path": data.get("report_path"),
        "pptx_path": data.get("pptx_path"),
        "pptx_preview_path": data.get("pptx_preview_path"),
        "job_control_path": data.get("job_control_path"),
        "control_state": read_job_control(job_dir) if job_dir.exists() else {},
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
    if _is_authoritative_workflow_state(workflow_status, prediction_status, analysis_status):
        return workflow_status
    for data in (prediction_status, analysis_status, workflow_status):
        if data:
            return data
    return None



def _is_authoritative_workflow_state(
    workflow_status: dict[str, Any] | None,
    prediction_status: dict[str, Any] | None,
    analysis_status: dict[str, Any] | None,
) -> bool:
    if not workflow_status:
        return False
    status_value = str(workflow_status.get("status") or "")
    stage = str(workflow_status.get("current_stage") or "")
    if status_value == "cancelled":
        return True
    if status_value == "running" and (stage.startswith("rerun") or stage == "pptx"):
        return True
    if status_value == "failed" and workflow_status.get("error"):
        branch_status = prediction_status or analysis_status
        if branch_status is None:
            return True
        if branch_status.get("status") in {"success", "failed"}:
            return False
        return True
    return False

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
        "cancelled": "取消 已取消",
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


def _read_text_if_exists(path: Path, *, max_chars: int = 16000) -> str:
    if not str(path) or not path.exists() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    return text[:max_chars]


def _event_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []







