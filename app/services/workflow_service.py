import json
import re
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.agents.analysis_ir_agent import create_analysis_ir, render_analysis_ir_for_agent
from app.agents.chart_code_refiner_agent import create_refined_chart_script
from app.agents.chart_config_agent import create_chart_config
from app.agents.chart_suggestion_agent import create_chart_refine_suggestions
from app.agents.controller_agent import create_controller_plan
from app.agents.insight_mining_agent import DEFAULT_INSIGHT_GOAL
from app.agents.postprocess_sidecar_agent import create_dashboard_config
from app.agents.preflight_agent import create_preflight_assessment
from app.agents.roadmap_agent import create_analysis_roadmap, render_analysis_roadmap
from app.agents.selection_to_query_agent import create_selection_followup_patch
from app.agents.vision_parsing_agent import VisionParsingAgent, write_visual_extracted_csv
from app.sandbox.code_safety import validate_script_static_safety
from app.sandbox.local_executor import LocalSubprocessSandboxExecutor
from app.services.auto_repair_analysis import run_auto_repair_analysis_job
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_reader import find_uploaded_image_file, get_dataset_dir, get_uploaded_asset_type, load_uploaded_dataset
from app.services.execution_log_service import create_event, get_execution_log, write_execution_log
from app.services.insight_mining_service import INSIGHT_TASK_TYPE, INSIGHT_WORKFLOW_TYPE, run_insight_mining_job
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
ANALYSIS_IR_FILENAME = "analysis_ir.json"

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


AGENT_WORKSPACE_FILENAME = "agent_workspace.json"

AGENT_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "agent_id": "visual_parser",
        "display_name": "视觉解析 Agent",
        "avatar": "👁️",
        "role": "多模态结构化专家",
        "description": "把图片、截图或看板识别成可分析的表格数据，并记录识别置信度。",
        "stage_names": ["visual_parsing"],
        "tags": ["图片", "OCR替代", "结构化"],
    },
    {
        "agent_id": "rag_retriever",
        "display_name": "RAG 检索 Agent",
        "avatar": "📚",
        "role": "业务知识检索员",
        "description": "从知识库召回业务口径、指标定义和分析约束，提供给主控和解释链路。",
        "stage_names": ["rag_retrieval"],
        "tags": ["知识库", "业务口径"],
    },
    {
        "agent_id": "analysis_ir_agent",
        "display_name": "Analysis IR 编译器",
        "avatar": "🧩",
        "role": "语义中间表示编译器",
        "description": "把自然语言目标编译为统一的强类型 analysis_ir.json，锁定实体、粒度、指标、时间窗和证据口径。",
        "stage_names": ["analysis_ir"],
        "tags": ["语义编译", "IR", "口径锁定"],
    },
    {
        "agent_id": "controller_agent",
        "display_name": "主控 Agent",
        "avatar": "🧭",
        "role": "任务导演",
        "description": "理解用户目标、识别任务类型，并决定进入普通分析、预测或智能洞察工作流。",
        "stage_names": ["controller", "queued", "loading_dataset"],
        "tags": ["规划", "分流"],
    },
    {
        "agent_id": "data_understanding_agent",
        "display_name": "数据理解 Agent",
        "avatar": "🧬",
        "role": "字段语义分析师",
        "description": "识别指标、维度、日期、质量问题和字段业务含义。",
        "stage_names": ["data_understanding"],
        "tags": ["字段", "语义", "数据质量"],
    },
    {
        "agent_id": "analysis_agent",
        "display_name": "分析计划 Agent",
        "avatar": "📐",
        "role": "统计方案设计师",
        "description": "选择分析方法、图表计划、指标口径和分组维度。",
        "stage_names": ["analysis", "analysis_plan"],
        "tags": ["统计", "图表计划"],
    },
    {
        "agent_id": "hypothesis_agent",
        "display_name": "假设解析 Agent",
        "avatar": "🧪",
        "role": "What-if 假设翻译官",
        "description": "把用户的假设问题翻译为干预变量、目标指标和对象维度。",
        "stage_names": ["hypothesis"],
        "tags": ["预测", "假设"],
    },
    {
        "agent_id": "prediction_agent",
        "display_name": "预测计划 Agent",
        "avatar": "🔮",
        "role": "预测建模规划师",
        "description": "选择预测目标、特征、模型候选和保守解释边界。",
        "stage_names": ["prediction_plan"],
        "tags": ["预测", "模型"],
    },
    {
        "agent_id": "code_agent",
        "display_name": "代码 Agent",
        "avatar": "🐍",
        "role": "Python 分析工程师",
        "description": "生成可审计、可在沙箱执行的 Python 分析脚本。",
        "stage_names": ["code_generation", "repair"],
        "tags": ["代码生成", "修复"],
    },
    {
        "agent_id": "safety_agent",
        "display_name": "代码安全检查 Agent",
        "avatar": "🛡️",
        "role": "沙箱安全守门员",
        "description": "检查危险导入、系统命令和越权文件访问。",
        "stage_names": ["code_safety"],
        "tags": ["安全", "审计"],
    },
    {
        "agent_id": "sandbox_executor",
        "display_name": "沙箱执行器",
        "avatar": "⚙️",
        "role": "隔离运行时",
        "description": "执行通过安全检查的脚本并收集图表、stdout、stderr 和 JSON 产物。",
        "stage_names": ["sandbox"],
        "tags": ["执行", "产物"],
    },
    {
        "agent_id": "validation_agent",
        "display_name": "验证 Agent",
        "avatar": "✅",
        "role": "结果审计员",
        "description": "验证输出结构、业务合理性、图表存在性和是否需要重试。",
        "stage_names": ["validation"],
        "tags": ["验证", "质量"],
    },
    {
        "agent_id": "debate_matrix_agent",
        "display_name": "Debate Matrix 双 Agent",
        "avatar": "⚖️",
        "role": "洞察辩论组",
        "description": "让商业洞察与统计质检两种角色互相挑战，形成更稳健的结论。",
        "stage_names": ["debate_matrix"],
        "tags": ["辩论", "稳健性"],
    },
    {
        "agent_id": "explanation_agent",
        "display_name": "解释 Agent",
        "avatar": "🗣️",
        "role": "业务解读者",
        "description": "把分析产物转化为结论、建议、限制和 PPT 大纲。",
        "stage_names": ["explanation", "prediction_explanation"],
        "tags": ["报告", "解释"],
    },
    {
        "agent_id": "quality_review_agent",
        "display_name": "质检 Agent",
        "avatar": "🔍",
        "role": "结论复核官",
        "description": "检查数字证据、因果表述、样本限制和风险提示。",
        "stage_names": ["quality_review"],
        "tags": ["证据", "风险"],
    },
    {
        "agent_id": "cross_artifact_consistency_agent",
        "display_name": "跨产物口径一致性 Agent",
        "avatar": "🧭",
        "role": "多产物口径审计员",
        "description": "扫描解释文本、报告、PPT 大纲、Dashboard、图表标题和追问回答的口径一致性。",
        "stage_names": ["cross_artifact_consistency"],
        "tags": ["一致性", "可信口径"],
    },
    {
        "agent_id": "dashboard_agent",
        "display_name": "Dashboard 生成 Agent",
        "avatar": "📊",
        "role": "交互看板设计师",
        "description": "把一次性结果整理为可筛选、可拖拽、可刷新的 Dashboard 配置。",
        "stage_names": ["sidecar_postprocess", "dashboard_generation", "dashboard_saved"],
        "tags": ["Dashboard", "持续监控"],
    },
    {
        "agent_id": "report_agent",
        "display_name": "报告 Agent",
        "avatar": "📄",
        "role": "交付物生成器",
        "description": "生成 Markdown 报告、PPTX 和预览材料。",
        "stage_names": ["report", "pptx"],
        "tags": ["报告", "PPT"],
    },
]

STAGE_TO_AGENT: dict[str, str] = {}
for _agent_blueprint in AGENT_BLUEPRINTS:
    for _stage_name in _agent_blueprint.get("stage_names", []):
        STAGE_TO_AGENT[str(_stage_name)] = str(_agent_blueprint["agent_id"])



def create_workflow_job_record(
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 90,
    owner_user_id: str | None = None,
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
        owner_user_id=owner_user_id,
    )



def create_workflow_preflight(dataset_id: str, user_goal: str, owner_user_id: str | None = None) -> dict[str, Any]:
    asset_type = _safe_asset_type(dataset_id)
    if asset_type == IMAGE_ASSET_TYPE:
        return {
            "dataset_id": dataset_id,
            "owner_user_id": owner_user_id,
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
        "owner_user_id": owner_user_id,
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
    analysis_ir = _read_json_if_exists(job_dir / ANALYSIS_IR_FILENAME) or {}
    compiled_instruction = render_analysis_ir_for_agent(
        analysis_ir,
        delta={"interaction": "dashboard_chart_config", "instruction": instruction, "current_config": current_config or {}},
    ) if analysis_ir else instruction
    chart_config = create_chart_config(
        instruction=compiled_instruction,
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
    analysis_ir = _read_json_if_exists(job_dir / ANALYSIS_IR_FILENAME) or {}
    suggestion_goal = render_analysis_ir_for_agent(
        analysis_ir,
        delta={"interaction": "chart_suggestions", "chart_path": chart_path, "raw_user_goal": status_data.get("user_goal")},
    ) if analysis_ir else str(status_data.get("user_goal") or "")
    suggestions = create_chart_refine_suggestions(
        user_goal=suggestion_goal,
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
    owner_user_id = str(status_data.get("owner_user_id") or "") or None
    result_filename = "prediction_result.json" if workflow_type == PREDICTION_TASK_TYPE else "analysis_result.json"
    result_payload = _read_json_if_exists(job_dir / result_filename) or {}
    dataset_profile = _read_json_if_exists(job_dir / "dataset_profile.json") or {}
    source_script_path = _latest_existing_script_path(status_data)
    if source_script_path is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前任务缺少可用于调整图表的脚本。")

    input_file, _ = load_uploaded_dataset(dataset_id)
    original_script = source_script_path.read_text(encoding="utf-8")
    analysis_ir = _read_json_if_exists(job_dir / ANALYSIS_IR_FILENAME) or {}
    compiled_instruction = render_analysis_ir_for_agent(
        analysis_ir,
        delta={"interaction": "chart_refine", "instruction": instruction, "chart_path": chart_path},
    ) if analysis_ir else instruction
    refined_script = create_refined_chart_script(
        input_file=str(input_file.resolve()),
        output_dir=str(job_dir),
        original_script=original_script,
        target_chart_path=chart_path,
        instruction=compiled_instruction,
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
        owner_user_id=owner_user_id,
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
    owner_user_id: str | None = None,
) -> None:
    job_dir = (JOB_ROOT / job_id).resolve()
    try:
        result = run_workflow_job(
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            owner_user_id=owner_user_id,
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
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    effective_max_retries = _validate_max_retries(max_retries)
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    current_status = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME) or {}
    owner_user_id = owner_user_id or str(current_status.get("owner_user_id") or "") or _owner_from_existing(job_dir)
    if _is_insight_goal(user_goal):
        user_goal = DEFAULT_INSIGHT_GOAL
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

    events.append(create_event("analysis_ir", "running", "Analysis IR 编译器正在锁定实体、粒度、指标、时间窗和证据需求。"))
    try:
        preflight = _read_json_if_exists(get_dataset_dir(dataset_id) / "preflight_assessment.json") or {}
    except HTTPException:
        preflight = {}
    analysis_ir = create_analysis_ir(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        preflight=preflight,
        rag_context=rag_context,
    )
    analysis_ir_path = str(job_dir / ANALYSIS_IR_FILENAME)
    _write_json(job_dir / ANALYSIS_IR_FILENAME, analysis_ir)
    compiled_goal = render_analysis_ir_for_agent(
        analysis_ir,
        delta={"stage": "controller", "raw_user_goal": user_goal},
    )
    events.append(create_event("analysis_ir", "success", "Analysis IR 已生成，后续 Agent 将统一消费 IR + delta。"))

    events.append(create_event("controller", "running", "主控 Agent 正在选择分析工作流。"))
    controller_plan = create_controller_plan(compiled_goal, dataset_profile, rag_context=rag_context)
    task_type = str(controller_plan.get("task_type") or "general_data_analysis")
    if _is_insight_goal(user_goal):
        task_type = INSIGHT_TASK_TYPE
        controller_plan = {**controller_plan, "task_type": INSIGHT_TASK_TYPE, "task_name": "智能洞察挖掘"}
    if task_type == PREDICTION_TASK_TYPE:
        workflow_type = PREDICTION_TASK_TYPE
    elif task_type == INSIGHT_TASK_TYPE:
        workflow_type = INSIGHT_WORKFLOW_TYPE
    else:
        workflow_type = ANALYSIS_WORKFLOW_TYPE
    _write_json(job_dir / "controller_plan.json", controller_plan)
    events.append(create_event("controller", "success", f"主控 Agent 已选择任务类型：{task_type}。"))

    events.append(create_event("roadmap", "running", "路线图 Agent 正在生成可视化分析路线。"))
    roadmap = create_analysis_roadmap(
        user_goal=render_analysis_ir_for_agent(analysis_ir, delta={"stage": "roadmap", "raw_user_goal": user_goal}),
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
        analysis_ir_path=analysis_ir_path,
        dataset_profile_path=str(job_dir / "dataset_profile.json"),
        analysis_roadmap_path=analysis_roadmap_path,
        visual_parse_result_path=visual_parse_result_path,
        visual_extracted_dataset_path=visual_extracted_dataset_path,
        visual_extraction_confidence=_float_or_none(visual_extraction_confidence),
    )
    checkpoint_job_control(job_dir)

    if task_type == INSIGHT_TASK_TYPE:
        result = _call_job_runner(
            run_insight_mining_job,
            dataset_id=dataset_id,
            user_goal=user_goal,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
            owner_user_id=owner_user_id,
        )
        return _normalize_workflow_status(result, workflow_type=INSIGHT_WORKFLOW_TYPE, task_type=task_type)

    if task_type == PREDICTION_TASK_TYPE:
        result = _call_job_runner(
            run_prediction_job,
            dataset_id=dataset_id,
            user_goal=user_goal,
            max_retries=effective_max_retries,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
            owner_user_id=owner_user_id,
        )
        return _normalize_workflow_status(result, workflow_type=PREDICTION_TASK_TYPE, task_type=task_type)

    result = _call_job_runner(
        run_auto_repair_analysis_job,
        dataset_id=dataset_id,
        user_goal=user_goal,
        max_retries=effective_max_retries,
        timeout_seconds=timeout_seconds,
        job_id=job_id,
        owner_user_id=owner_user_id,
    )
    return _normalize_workflow_status(result, workflow_type=ANALYSIS_WORKFLOW_TYPE, task_type=task_type)


def _call_job_runner(runner: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return runner(**kwargs)
    except TypeError as exc:
        if "owner_user_id" in kwargs and "owner_user_id" in str(exc):
            compatible_kwargs = dict(kwargs)
            compatible_kwargs.pop("owner_user_id", None)
            return runner(**compatible_kwargs)
        raise


def list_workflow_jobs(
    limit: int = 30,
    query: str | None = None,
    owner_user_id: str | None = None,
    include_all: bool = False,
) -> dict[str, Any]:
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
        job_owner = str(status_data.get("owner_user_id") or "") or None
        if owner_user_id and not include_all and job_owner != owner_user_id:
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
            "owner_user_id": normalized.get("owner_user_id") or job_owner,
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


def delete_workflow_job(
    job_id: str,
    requester_user_id: str | None = None,
    requester_is_admin: bool = False,
) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id)
    status_data = _history_status_data(job_dir) or {}
    if requester_user_id and not requester_is_admin:
        owner = str(status_data.get("owner_user_id") or "") or None
        if owner and owner != requester_user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不能删除其他用户的分析记录。")
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
        branch_task_type = _controller_task_type(job_dir) or str(analysis_status.get("task_type") or "general_data_analysis")
        branch_workflow_type = INSIGHT_WORKFLOW_TYPE if branch_task_type == INSIGHT_TASK_TYPE or str(analysis_status.get("workflow_type") or "") == INSIGHT_WORKFLOW_TYPE else ANALYSIS_WORKFLOW_TYPE
        return _normalize_workflow_status(
            analysis_status,
            workflow_type=branch_workflow_type,
            task_type=branch_task_type,
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
                "sidecar_results": status_data.get("sidecar_results") or {},
            },
            "events": status_data.get("events") or [],
        }
    log_data = {
        **log_data,
        "workflow_type": status_data.get("workflow_type") or log_data.get("workflow_type") or "pending",
        "task_type": status_data.get("task_type"),
        "asset_type": status_data.get("asset_type"),
        "owner_user_id": status_data.get("owner_user_id"),
    }
    artifacts = log_data.get("artifacts") if isinstance(log_data.get("artifacts"), dict) else {}
    log_data["artifacts"] = {
        **artifacts,
        "visual_parse_result": status_data.get("visual_parse_result_path"),
        "visual_extracted_dataset": status_data.get("visual_extracted_dataset_path"),
        "analysis_ir": status_data.get("analysis_ir_path"),
        "charts": status_data.get("chart_paths") or [],
        "analysis_roadmap": status_data.get("analysis_roadmap_path"),
        "quality_review": status_data.get("quality_review_path"),
        "evidence_chain": status_data.get("evidence_chain_path"),
        "debate_reflection": status_data.get("debate_reflection_path"),
        "sidecar_results": status_data.get("sidecar_results") or {},
        "insight_result": status_data.get("insight_result_path"),
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




def get_workflow_agents(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = _history_status_data(job_dir) or {}
    workspace = _read_agent_workspace(job_dir)
    events = _event_list(status_data.get("events"))
    artifact_messages = _agent_artifact_messages(job_dir, status_data)
    messages_by_agent: dict[str, list[dict[str, Any]]] = {str(item["agent_id"]): [] for item in AGENT_BLUEPRINTS}

    for index, event in enumerate(events):
        stage = str(event.get("stage") or "")
        agent_id = STAGE_TO_AGENT.get(stage) or _agent_id_from_stage(stage)
        message_id = f"{agent_id}_{index}_{_safe_message_token(stage)}"
        messages_by_agent.setdefault(agent_id, []).append(
            {
                "message_id": message_id,
                "agent_id": agent_id,
                "timestamp": event.get("timestamp"),
                "stage": stage,
                "status": event.get("status") or "info",
                "title": _stage_agent_message_title(stage, str(event.get("status") or "")),
                "content": event.get("message") or "",
                "artifact_path": None,
                "metadata": {},
            }
        )
    for message in artifact_messages:
        messages_by_agent.setdefault(str(message.get("agent_id") or "generic_agent"), []).append(message)

    hidden_messages = set(str(item) for item in workspace.get("hidden_messages", []) if item)
    overrides = workspace.get("agent_overrides") if isinstance(workspace.get("agent_overrides"), dict) else {}
    agents: list[dict[str, Any]] = []
    for blueprint in AGENT_BLUEPRINTS:
        agent_id = str(blueprint["agent_id"])
        raw_messages = [item for item in messages_by_agent.get(agent_id, []) if str(item.get("message_id")) not in hidden_messages]
        raw_messages.sort(key=lambda item: str(item.get("timestamp") or ""))
        override = overrides.get(agent_id) if isinstance(overrides.get(agent_id), dict) else {}
        agent_payload = {
            **blueprint,
            **{key: value for key, value in override.items() if key in {"display_name", "description", "role", "avatar", "tags", "notes"}},
            "status": _agent_runtime_status(agent_id, status_data, raw_messages),
            "message_count": len(raw_messages),
            "last_active_at": raw_messages[-1].get("timestamp") if raw_messages else None,
            "messages": raw_messages[-40:],
        }
        agents.append(agent_payload)

    return {
        "job_id": job_id,
        "agents": agents,
        "workspace_path": str(job_dir / AGENT_WORKSPACE_FILENAME),
        "message": "Agent 画像已读取。",
    }


def update_workflow_agent(job_id: str, agent_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    known_ids = {str(item["agent_id"]) for item in AGENT_BLUEPRINTS}
    if agent_id not in known_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent 不存在。")
    workspace = _read_agent_workspace(job_dir)
    overrides = workspace.get("agent_overrides") if isinstance(workspace.get("agent_overrides"), dict) else {}
    current = overrides.get(agent_id) if isinstance(overrides.get(agent_id), dict) else {}
    allowed: dict[str, Any] = {}
    for key in ("display_name", "description", "role", "avatar", "notes"):
        if key in updates and updates[key] is not None:
            allowed[key] = str(updates[key])[:1200]
    if isinstance(updates.get("tags"), list):
        allowed["tags"] = [str(item)[:40] for item in updates["tags"] if str(item or "").strip()][:8]
    overrides[agent_id] = {**current, **allowed, "updated_at": datetime.now(timezone.utc).isoformat()}
    workspace["agent_overrides"] = overrides
    workspace["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(job_dir / AGENT_WORKSPACE_FILENAME, workspace)
    return get_workflow_agents(job_id)


def delete_workflow_agent_message(job_id: str, agent_id: str, message_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    workspace = _read_agent_workspace(job_dir)
    hidden = [str(item) for item in workspace.get("hidden_messages", []) if item]
    if message_id not in hidden:
        hidden.append(message_id)
    workspace["hidden_messages"] = hidden
    workspace["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(job_dir / AGENT_WORKSPACE_FILENAME, workspace)
    return get_workflow_agents(job_id)


def _read_agent_workspace(job_dir: Path) -> dict[str, Any]:
    data = _read_json_if_exists(job_dir / AGENT_WORKSPACE_FILENAME)
    if data:
        data.setdefault("agent_overrides", {})
        data.setdefault("hidden_messages", [])
        return data
    return {"agent_overrides": {}, "hidden_messages": [], "created_at": datetime.now(timezone.utc).isoformat()}


def _agent_id_from_stage(stage: str) -> str:
    text = str(stage or "").lower()
    if "cross_artifact" in text or "consistency" in text or "口径" in text:
        return "cross_artifact_consistency_agent"
    if "dashboard" in text or "sidecar" in text:
        return "dashboard_agent"
    if "report" in text or "ppt" in text:
        return "report_agent"
    if "code" in text:
        return "code_agent"
    if "validation" in text:
        return "validation_agent"
    if "sandbox" in text or "execution" in text:
        return "sandbox_executor"
    if "quality" in text:
        return "quality_review_agent"
    return "controller_agent"


def _stage_agent_message_title(stage: str, status_value: str) -> str:
    status_text = {"running": "执行中", "success": "已完成", "failed": "失败", "warning": "需关注", "pending": "等待中"}.get(status_value, status_value or "记录")
    return f"{stage or 'stage'} · {status_text}"


def _safe_message_token(value: str) -> str:
    token = re.sub(r"[^0-9A-Za-z_\-]+", "_", str(value or "stage"))
    return token[:48] or "stage"


def _agent_runtime_status(agent_id: str, status_data: dict[str, Any], messages: list[dict[str, Any]]) -> str:
    current_stage = str(status_data.get("current_stage") or "")
    current_agent_id = STAGE_TO_AGENT.get(current_stage) or _agent_id_from_stage(current_stage)
    if status_data.get("status") in {"failed", "cancelled"} and current_agent_id == agent_id:
        return "failed"
    if current_agent_id == agent_id and status_data.get("status") in {"running", "pending"}:
        return "active"
    if any(str(message.get("status")) == "failed" for message in messages):
        return "failed"
    if messages:
        return "done"
    return "idle"


def _agent_artifact_messages(job_dir: Path, status_data: dict[str, Any]) -> list[dict[str, Any]]:
    artifact_map = [
        ("controller_agent", "controller_plan_path", "controller_plan.json", "主控计划产物"),
        ("rag_retriever", "rag_retrieval_path", "rag_retrieval.json", "RAG 检索产物"),
        ("analysis_ir_agent", "analysis_ir_path", ANALYSIS_IR_FILENAME, "Analysis IR 编译产物"),
        ("visual_parser", "visual_parse_result_path", "visual_parse_result.json", "视觉解析产物"),
        ("data_understanding_agent", "data_understanding_path", "data_understanding.json", "字段理解产物"),
        ("analysis_agent", "analysis_plan_path", "analysis_plan.json", "分析计划产物"),
        ("hypothesis_agent", "hypothesis_plan_path", "hypothesis_plan.json", "假设解析产物"),
        ("prediction_agent", "prediction_plan_path", "prediction_plan.json", "预测计划产物"),
        ("explanation_agent", "explanation_path", "explanation.json", "解释产物"),
        ("explanation_agent", "prediction_explanation_path", "prediction_explanation.json", "预测解释产物"),
        ("quality_review_agent", "quality_review_path", "quality_review.json", "质检产物"),
        ("debate_matrix_agent", "debate_reflection_path", "debate_reflection.json", "辩论产物"),
        ("report_agent", "report_path", "report.md", "报告文件"),
        ("report_agent", "pptx_preview_path", "pptx_preview.json", "PPT 预览产物"),
    ]
    sidecar = _normalize_sidecar_results(status_data.get("sidecar_results"), job_dir)
    messages: list[dict[str, Any]] = []
    index = 0
    for agent_id, status_key, fallback_name, title in artifact_map:
        raw_path = status_data.get(status_key) or str(job_dir / fallback_name)
        path = _resolve_job_path(job_dir, raw_path)
        if not path or not path.exists():
            continue
        messages.append(_artifact_message(agent_id, index, title, path, job_dir))
        index += 1
    sidecar_agent_map = {
        "dashboard_config": "dashboard_agent",
        "next_step_suggestions": "explanation_agent",
        "anomalies": "explanation_agent",
        "significance_tests": "quality_review_agent",
        "consistency_report": "cross_artifact_consistency_agent",
        "suggested_rewrites": "cross_artifact_consistency_agent",
    }
    sidecar_title_map = {
        "dashboard_config": "Dashboard 配置产物",
        "next_step_suggestions": "追问推荐产物",
        "anomalies": "异常扫描产物",
        "significance_tests": "显著性建议产物",
        "consistency_report": "跨产物口径一致性报告",
        "suggested_rewrites": "口径修订建议产物",
    }
    for key, raw_path in sidecar.items():
        path = _resolve_job_path(job_dir, raw_path)
        if not path or not path.exists():
            continue
        agent_id = sidecar_agent_map.get(key, "explanation_agent")
        title = sidecar_title_map.get(key, f"{key} 产物")
        messages.append(_artifact_message(agent_id, index, title, path, job_dir))
        index += 1
    return messages


def _artifact_message(agent_id: str, index: int, title: str, path: Path, job_dir: Path) -> dict[str, Any]:
    summary = _summarize_artifact(path)
    return {
        "message_id": f"{agent_id}_artifact_{index}_{_safe_message_token(path.name)}",
        "agent_id": agent_id,
        "timestamp": _iso_from_timestamp(path.stat().st_mtime),
        "stage": "artifact",
        "status": "success",
        "title": title,
        "content": summary,
        "artifact_path": str(path),
        "metadata": {"relative_path": str(path.relative_to(job_dir)) if _is_relative_to(path, job_dir) else str(path)},
    }


def _summarize_artifact(path: Path) -> str:
    if path.suffix.lower() == ".md":
        text = _read_text_if_exists(path, max_chars=600)
        return text.replace("\n", " ")[:260] or "报告文件已生成。"
    data = _read_json_if_exists(path)
    if not data:
        return f"文件已生成：{path.name}。"
    for key in ("summary", "reasoning_summary", "analysis_goal", "prediction_goal", "final_consensus", "message"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:300]
    if isinstance(data.get("key_findings"), list) and data["key_findings"]:
        return "；".join(str(item) for item in data["key_findings"][:3])[:300]
    keys = "、".join(list(data.keys())[:8])
    return f"结构化产物已生成，包含字段：{keys}。"


def _resolve_job_path(job_dir: Path, raw_path: Any) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        candidates = [(Path.cwd() / path).resolve(), (job_dir / path).resolve()]
        path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
    try:
        return path.resolve()
    except OSError:
        return None



def get_workflow_dashboard(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    dashboard_path = _dashboard_config_path(job_dir)
    dashboard = _read_json_if_exists(dashboard_path)
    if not dashboard or _dashboard_needs_upgrade(dashboard):
        dashboard = _build_fresh_dashboard(job_id, job_dir, previous_dashboard=dashboard)
        _write_json(dashboard_path, dashboard)
    else:
        dashboard = _attach_dashboard_source_rows(job_dir, dashboard)
        dashboard = _refresh_dashboard_filters(job_dir, dashboard)
        _write_json(dashboard_path, dashboard)
    return {
        "job_id": job_id,
        "dashboard": dashboard,
        "dashboard_path": str(dashboard_path),
        "message": "Dashboard 配置已读取。",
    }



def update_workflow_dashboard(job_id: str, dashboard: dict[str, Any]) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    if not isinstance(dashboard, dict) or not dashboard:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Dashboard 配置不能为空。")
    dashboard_path = _dashboard_config_path(job_dir)
    sanitized_dashboard = dict(dashboard)
    sanitized_dashboard.pop("sharing", None)
    sanitized_dashboard["permissions"] = {**(sanitized_dashboard.get("permissions") if isinstance(sanitized_dashboard.get("permissions"), dict) else {}), "can_save": True, "can_share": False, "can_embed": False}
    dashboard_payload = {
        **sanitized_dashboard,
        "schema_version": int(sanitized_dashboard.get("schema_version") or 2),
        "source_job_id": str(sanitized_dashboard.get("source_job_id") or job_id),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    dashboard_payload = _attach_dashboard_source_rows(job_dir, dashboard_payload)
    dashboard_payload = _refresh_dashboard_filters(job_dir, dashboard_payload)
    _write_json(dashboard_path, dashboard_payload)
    sidecar_results = _normalize_sidecar_results({"dashboard_config": str(dashboard_path)}, job_dir)
    _set_job_status(
        job_dir,
        status_value=None,
        current_stage="dashboard_saved",
        event=create_event("dashboard_generation", "success", "Dashboard 配置已保存。"),
        artifacts={"sidecar_results": sidecar_results},
    )
    return {
        "job_id": job_id,
        "dashboard": dashboard_payload,
        "dashboard_path": str(dashboard_path),
        "message": "Dashboard 配置已保存。",
    }



def refresh_workflow_dashboard(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    dashboard_path = _dashboard_config_path(job_dir)
    previous_dashboard = _read_json_if_exists(dashboard_path)
    dashboard = _build_fresh_dashboard(job_id, job_dir, previous_dashboard=previous_dashboard)
    refresh_state = dashboard.get("refresh") if isinstance(dashboard.get("refresh"), dict) else {}
    previous_refresh = previous_dashboard.get("refresh") if isinstance(previous_dashboard, dict) and isinstance(previous_dashboard.get("refresh"), dict) else {}
    refreshed_at = datetime.now(timezone.utc).isoformat()
    dashboard["refresh"] = {
        **refresh_state,
        "enabled": bool(previous_refresh.get("enabled") or refresh_state.get("enabled")),
        "interval_seconds": int(previous_refresh.get("interval_seconds") or refresh_state.get("interval_seconds") or 300),
        "last_refreshed_at": refreshed_at,
        "refresh_count": int(previous_refresh.get("refresh_count") or refresh_state.get("refresh_count") or 0) + 1,
    }
    dashboard["updated_at"] = refreshed_at
    _write_json(dashboard_path, dashboard)
    _append_job_event(job_dir, create_event("dashboard_generation", "success", "Dashboard 已重新读取数据并刷新。"))
    return {
        "job_id": job_id,
        "dashboard": dashboard,
        "dashboard_path": str(dashboard_path),
        "message": "Dashboard 已刷新。",
    }





def _dashboard_needs_upgrade(dashboard: dict[str, Any]) -> bool:
    if int(dashboard.get("schema_version") or 0) < 2:
        return True
    if dashboard.get("sharing"):
        return True
    widgets = dashboard.get("widgets") if isinstance(dashboard.get("widgets"), list) else []
    if widgets and all(str(widget.get("type") or "") == "chart" and not widget.get("x") for widget in widgets if isinstance(widget, dict)):
        return True
    return False


def _build_fresh_dashboard(job_id: str, job_dir: Path, previous_dashboard: dict[str, Any] | None = None) -> dict[str, Any]:
    status_data = _history_status_data(job_dir) or {}
    dataset_profile = _load_dashboard_dataset_profile(job_dir, status_data)
    result_payload = _dashboard_result_payload(job_dir, status_data)
    report_data = _dashboard_report_data(job_dir, status_data)
    sidecar = _normalize_sidecar_results(status_data.get("sidecar_results"), job_dir)
    anomalies = _read_json_if_exists(_resolve_job_path(job_dir, sidecar.get("anomalies")) or (job_dir / "anomaly_scan.json")) or {}
    next_steps = _read_json_if_exists(_resolve_job_path(job_dir, sidecar.get("next_step_suggestions")) or (job_dir / "next_steps.json")) or {}
    chart_paths = _string_list(status_data.get("chart_paths")) or _string_list(result_payload.get("charts"))
    dashboard = create_dashboard_config(
        job_dir=job_dir,
        user_goal=str(status_data.get("user_goal") or (previous_dashboard or {}).get("source_goal") or ""),
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        report_data=report_data,
        chart_paths=chart_paths,
        anomalies=anomalies,
        next_steps=next_steps,
        workflow_type=str(status_data.get("workflow_type") or status_data.get("task_type") or "auto_repair"),
    )
    dashboard["source_job_id"] = job_id
    dashboard = _attach_dashboard_source_rows(job_dir, dashboard)
    dashboard = _refresh_dashboard_filters(job_dir, dashboard)
    return _merge_dashboard_preferences(dashboard, previous_dashboard or {})


def _load_dashboard_dataset_profile(job_dir: Path, status_data: dict[str, Any]) -> dict[str, Any]:
    explicit = _resolve_job_path(job_dir, status_data.get("dataset_profile_path"))
    if explicit and explicit.exists():
        profile = _read_json_if_exists(explicit)
        if profile:
            return profile
    fallback = _read_json_if_exists(job_dir / "dataset_profile.json")
    if fallback:
        return fallback
    dataset_id = str(status_data.get("dataset_id") or "")
    if dataset_id:
        try:
            return generate_dataset_profile(dataset_id)
        except HTTPException:
            pass
    return {"columns": [], "row_count": 0, "column_count": 0, "sample_rows": [], "numeric_summary": {}, "text_summary": {}}


def _dashboard_result_payload(job_dir: Path, status_data: dict[str, Any]) -> dict[str, Any]:
    for key, fallback in (
        ("final_result_path", "analysis_result.json"),
        ("final_prediction_result_path", "prediction_result.json"),
        ("insight_result_path", "insight_result.json"),
    ):
        path = _resolve_job_path(job_dir, status_data.get(key)) or (job_dir / fallback)
        data = _read_json_if_exists(path)
        if data:
            return data
    return {}


def _dashboard_report_data(job_dir: Path, status_data: dict[str, Any]) -> dict[str, Any]:
    path = _resolve_job_path(job_dir, status_data.get("final_report_data_path")) or (job_dir / "report_data.json")
    return _read_json_if_exists(path) or {}


def _attach_dashboard_source_rows(job_dir: Path, dashboard: dict[str, Any]) -> dict[str, Any]:
    status_data = _history_status_data(job_dir) or {}
    dataset_id = str(status_data.get("dataset_id") or "")
    if not dataset_id:
        return dashboard
    try:
        file_path, df = load_uploaded_dataset(dataset_id)
    except HTTPException:
        return dashboard
    limit = 800
    rows = _dataframe_records(df, limit=limit)
    data_sources = dashboard.get("data_sources") if isinstance(dashboard.get("data_sources"), dict) else {}
    data_sources["dataset_rows"] = {
        "label": "原始/清洗后数据",
        "file_path": str(file_path),
        "rows": rows,
        "columns": [str(column) for column in df.columns],
        "row_count": int(len(df)),
        "sampled": int(len(df)) > limit,
    }
    dashboard["data_sources"] = data_sources
    _sync_table_widget_rows(dashboard, rows)
    return dashboard


def _refresh_dashboard_filters(job_dir: Path, dashboard: dict[str, Any]) -> dict[str, Any]:
    data_sources = dashboard.get("data_sources") if isinstance(dashboard.get("data_sources"), dict) else {}
    dataset_rows = data_sources.get("dataset_rows") if isinstance(data_sources.get("dataset_rows"), dict) else {}
    rows = dataset_rows.get("rows") if isinstance(dataset_rows.get("rows"), list) else []
    filters = dashboard.get("filters") if isinstance(dashboard.get("filters"), list) else []
    if not rows or not filters:
        return dashboard
    refreshed = []
    for filter_item in filters:
        if not isinstance(filter_item, dict):
            continue
        field = str(filter_item.get("field") or "")
        if not field:
            continue
        options: list[str] = []
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            value = row.get(field)
            if value is None or value == "":
                continue
            text = str(value)
            if text not in seen:
                seen.add(text)
                options.append(text)
            if len(options) >= 80:
                break
        refreshed.append({**filter_item, "value": "" if str(filter_item.get("value") or "") == "全部" else str(filter_item.get("value") or ""), "options": options or filter_item.get("options") or []})
    dashboard["filters"] = refreshed
    return dashboard


def _sync_table_widget_rows(dashboard: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    widgets = dashboard.get("widgets") if isinstance(dashboard.get("widgets"), list) else []
    if not rows:
        return
    columns = list(rows[0].keys())[:10]
    for widget in widgets:
        if isinstance(widget, dict) and widget.get("type") == "table" and str(widget.get("source") or "dataset_rows") == "dataset_rows":
            widget["rows"] = rows[:120]
            widget["columns"] = columns


def _merge_dashboard_preferences(new_dashboard: dict[str, Any], previous_dashboard: dict[str, Any]) -> dict[str, Any]:
    if not previous_dashboard:
        return new_dashboard
    if isinstance(previous_dashboard.get("refresh"), dict):
        new_refresh = new_dashboard.get("refresh") if isinstance(new_dashboard.get("refresh"), dict) else {}
        old_refresh = previous_dashboard["refresh"]
        new_dashboard["refresh"] = {
            **new_refresh,
            "enabled": bool(old_refresh.get("enabled", new_refresh.get("enabled", False))),
            "interval_seconds": int(old_refresh.get("interval_seconds") or new_refresh.get("interval_seconds") or 300),
            "last_refreshed_at": old_refresh.get("last_refreshed_at") or new_refresh.get("last_refreshed_at"),
            "refresh_count": int(old_refresh.get("refresh_count") or new_refresh.get("refresh_count") or 0),
        }
    old_filter_values = {
        str(item.get("field") or item.get("id")): item.get("value")
        for item in previous_dashboard.get("filters", [])
        if isinstance(item, dict)
    }
    if old_filter_values:
        next_filters = []
        for item in new_dashboard.get("filters", []):
            if not isinstance(item, dict):
                continue
            key = str(item.get("field") or item.get("id"))
            value = old_filter_values.get(key, item.get("value", ""))
            next_filters.append({**item, "value": "" if str(value or "") == "全部" else value})
        new_dashboard["filters"] = next_filters
    if isinstance(previous_dashboard.get("layout"), list):
        new_ids = {str(widget.get("id")) for widget in new_dashboard.get("widgets", []) if isinstance(widget, dict)}
        preserved = [item for item in previous_dashboard["layout"] if isinstance(item, dict) and str(item.get("i")) in new_ids]
        missing = [item for item in new_dashboard.get("layout", []) if isinstance(item, dict) and str(item.get("i")) not in {str(old.get("i")) for old in preserved}]
        if preserved:
            new_dashboard["layout"] = [*preserved, *missing]
    new_dashboard.pop("sharing", None)
    permissions = new_dashboard.get("permissions") if isinstance(new_dashboard.get("permissions"), dict) else {}
    new_dashboard["permissions"] = {**permissions, "can_save": True, "can_share": False, "can_embed": False}
    return new_dashboard


def _dataframe_records(df: Any, *, limit: int) -> list[dict[str, Any]]:
    sample = df.head(limit).astype(object).where(df.head(limit).notna(), None)
    records: list[dict[str, Any]] = []
    for row in sample.to_dict(orient="records"):
        records.append({str(key): _jsonable_value(value) for key, value in row.items()})
    return records


def _jsonable_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return value



def _dashboard_config_path(job_dir: Path) -> Path:
    status_data = _history_status_data(job_dir) or {}
    sidecar_results = _normalize_sidecar_results(status_data.get("sidecar_results"), job_dir)
    raw_path = sidecar_results.get("dashboard_config") or str(job_dir / "dashboard_config.json")
    dashboard_path = Path(raw_path)
    if not dashboard_path.is_absolute():
        dashboard_path = (Path.cwd() / dashboard_path).resolve()
    if not _is_relative_to(dashboard_path, job_dir.resolve()):
        dashboard_path = (job_dir / "dashboard_config.json").resolve()
    return dashboard_path

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

def create_workflow_follow_up(job_id: str, question: str, source_delta: dict[str, Any] | None = None) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = get_workflow_job_status(job_id)
    if status_data.get("status") != "success":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请等待分析完成后再继续追问。")
    normalized_question = str(question or "").strip()
    if not normalized_question:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="追问内容不能为空。")
    artifacts = _follow_up_artifacts(job_dir)
    analysis_ir = artifacts.get(ANALYSIS_IR_FILENAME) if isinstance(artifacts.get(ANALYSIS_IR_FILENAME), dict) else {}
    compiled_query = render_analysis_ir_for_agent(
        analysis_ir,
        delta={"interaction": "follow_up", "question": normalized_question, "source_delta": source_delta or {}},
    ) if analysis_ir else normalized_question
    answer = _build_follow_up_answer(normalized_question, artifacts, status_data, compiled_query=compiled_query)
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
        "source_delta": source_delta or {},
    }
    _write_json(follow_up_path, payload)
    _append_job_event(job_dir, create_event("follow_up", "success", "已基于现有分析产物生成追问回答。"))
    return {**payload, "follow_up_path": str(follow_up_path)}


def create_workflow_selection_question(job_id: str, selection_spec: dict[str, Any]) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = get_workflow_job_status(job_id)
    if status_data.get("status") != "success":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请等待分析完成后再使用图形刷选追问。")
    patch, patch_path, latest_patch_path, artifacts = _compile_and_store_selection_patch(job_dir, selection_spec)
    question = str(patch.get("question") or "为什么图中被圈选的数据范围值得关注？").strip()
    _append_job_event(job_dir, create_event("selection_question", "success", "图形刷选已编译为候选追问，等待用户确认。"))
    return {
        "job_id": job_id,
        "question": question,
        "selection_patch_path": str(patch_path),
        "latest_patch_path": str(latest_patch_path),
        "used_artifacts": sorted(artifacts.keys()),
        "source_delta": patch,
        "selection_spec": selection_spec,
    }


def create_workflow_selection_follow_up(job_id: str, selection_spec: dict[str, Any], question: str | None = None) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id).resolve()
    status_data = get_workflow_job_status(job_id)
    if status_data.get("status") != "success":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="请等待分析完成后再使用图形刷选追问。")
    patch, patch_path, _latest_patch_path, _artifacts = _compile_and_store_selection_patch(job_dir, selection_spec)
    normalized_question = str(question or patch.get("question") or "为什么图中被圈选的数据范围值得关注？").strip()
    if not normalized_question:
        normalized_question = "为什么图中被圈选的数据范围值得关注？"
    patch["question"] = normalized_question
    _write_json(patch_path, patch)
    _write_json(job_dir / "followup_ir_patch.json", patch)
    result = create_workflow_follow_up(job_id, normalized_question, source_delta=patch)
    if result.get("follow_up_path"):
        follow_up_payload = _read_json_if_exists(Path(str(result["follow_up_path"]))) or {}
        follow_up_payload.update({"selection_patch_path": str(patch_path), "selection_spec": selection_spec})
        _write_json(Path(str(result["follow_up_path"])), follow_up_payload)
    _append_job_event(job_dir, create_event("selection_follow_up", "success", "用户确认图形刷选追问后已生成回答。"))
    return {**result, "selection_patch_path": str(patch_path), "selection_spec": selection_spec}


def _compile_and_store_selection_patch(
    job_dir: Path,
    selection_spec: dict[str, Any],
) -> tuple[dict[str, Any], Path, Path, dict[str, Any]]:
    if not isinstance(selection_spec, dict) or not selection_spec:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="selection_spec 不能为空。")
    artifacts = _follow_up_artifacts(job_dir)
    analysis_ir = artifacts.get(ANALYSIS_IR_FILENAME) if isinstance(artifacts.get(ANALYSIS_IR_FILENAME), dict) else {}
    patch = create_selection_followup_patch(
        selection_spec=selection_spec,
        analysis_ir=analysis_ir,
        artifacts=artifacts,
    )
    followups_dir = job_dir / "followups"
    followups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    patch_path = followups_dir / f"followup_ir_patch_{timestamp}.json"
    latest_patch_path = job_dir / "followup_ir_patch.json"
    _write_json(patch_path, patch)
    _write_json(latest_patch_path, patch)
    return patch, patch_path, latest_patch_path, artifacts


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
        ANALYSIS_IR_FILENAME,
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
        "debate_reflection.json",
        "cleaning_report.json",
    ):
        value = _read_json_if_exists(job_dir / filename)
        if value:
            artifacts[filename] = value
    report_text = _read_text_if_exists(job_dir / "report.md")
    if report_text:
        artifacts["report.md"] = report_text
    return artifacts


def _build_follow_up_answer(question: str, artifacts: dict[str, Any], status_data: dict[str, Any], compiled_query: str | None = None) -> str:
    fallback = _build_rule_follow_up_answer(question, artifacts)
    prompt_payload = {
        "question": question,
        "compiled_query": compiled_query or question,
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
    analysis_ir_path: str | None = None,
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
    insight_result_path: str | None = None,
    debate_reflection_path: str | None = None,
    sidecar_results: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    owner_user_id = owner_user_id or _owner_from_existing(job_dir)
    status_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "owner_user_id": owner_user_id,
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
        "analysis_ir_path": analysis_ir_path,
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
        "insight_result_path": insight_result_path,
        "debate_reflection_path": debate_reflection_path,
        "sidecar_results": _normalize_sidecar_results(sidecar_results, job_dir),
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
            "owner_user_id": owner_user_id,
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
                "analysis_ir": analysis_ir_path,
                "analysis_roadmap": analysis_roadmap_path,
                "quality_review": quality_review_path,
                "cleaning_report": cleaning_report_path,
                "evidence_chain": evidence_chain_path,
                "report": report_path,
                "pptx": pptx_path,
                "pptx_preview": pptx_preview_path,
                "insight_result": insight_result_path,
                "debate_reflection": debate_reflection_path,
                "sidecar_results": _normalize_sidecar_results(sidecar_results, job_dir),
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
            "analysis_ir_path": _existing_or_none(data.get("analysis_ir_path"), job_dir / ANALYSIS_IR_FILENAME),
            "dataset_profile_path": _existing_or_none(data.get("dataset_profile_path"), job_dir / "dataset_profile.json"),
            "analysis_roadmap_path": _existing_or_none(data.get("analysis_roadmap_path"), job_dir / ROADMAP_FILENAME),
            "quality_review_path": _existing_or_none(data.get("quality_review_path"), job_dir / QUALITY_REVIEW_FILENAME),
            "cleaning_report_path": _existing_or_none(data.get("cleaning_report_path"), job_dir / "cleaning_report.json"),
            "evidence_chain_path": _existing_or_none(data.get("evidence_chain_path"), job_dir / "evidence_chain.json"),
            "report_path": _existing_or_none(data.get("report_path"), job_dir / "report.md"),
            "pptx_path": _existing_or_none(data.get("pptx_path"), job_dir / "report.pptx"),
            "pptx_preview_path": _existing_or_none(data.get("pptx_preview_path"), job_dir / "pptx_preview.json"),
            "insight_result_path": _existing_or_none(data.get("insight_result_path"), job_dir / "analysis_result.json") if str(workflow_type or data.get("workflow_type") or "") == INSIGHT_WORKFLOW_TYPE else data.get("insight_result_path"),
            "debate_reflection_path": _existing_or_none(data.get("debate_reflection_path"), job_dir / "debate_reflection.json"),
            "sidecar_results": _normalize_sidecar_results(data.get("sidecar_results"), job_dir),
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
        "owner_user_id": str(data.get("owner_user_id") or "") or None,
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
        "analysis_ir_path": data.get("analysis_ir_path"),
        "dataset_profile_path": data.get("dataset_profile_path"),
        "analysis_roadmap_path": data.get("analysis_roadmap_path"),
        "quality_review_path": data.get("quality_review_path"),
        "cleaning_report_path": data.get("cleaning_report_path"),
        "evidence_chain_path": data.get("evidence_chain_path"),
        "report_path": data.get("report_path"),
        "pptx_path": data.get("pptx_path"),
        "pptx_preview_path": data.get("pptx_preview_path"),
        "insight_result_path": data.get("insight_result_path"),
        "debate_reflection_path": data.get("debate_reflection_path"),
        "sidecar_results": _normalize_sidecar_results(data.get("sidecar_results"), job_dir),
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
    if str(workflow_type or task_type or "") == INSIGHT_WORKFLOW_TYPE:
        return "智能洞察 自动洞察 insight mining"
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


def _is_insight_goal(user_goal: str) -> bool:
    text = str(user_goal or "").lower()
    return any(keyword in text for keyword in (
        "智能洞察",
        "洞察挖掘",
        "自动洞察",
        "自动扫描",
        "无需目标",
        "不提交分析目标",
        "insight mining",
        "auto insight",
    ))


def _owner_from_existing(job_dir: Path) -> str | None:
    for filename in (WORKFLOW_STATUS_FILENAME, "task_status.json", "prediction_task_status.json"):
        data = _read_json_if_exists(job_dir / filename)
        if data and data.get("owner_user_id"):
            return str(data.get("owner_user_id"))
    return None


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
    status_data = _read_json_if_exists(job_dir / WORKFLOW_STATUS_FILENAME) or _read_json_if_exists(job_dir / "task_status.json") or {}
    workflow_type = str(status_data.get("workflow_type") or "")
    task_type = str(status_data.get("task_type") or _controller_task_type(job_dir) or "")
    if workflow_type == INSIGHT_WORKFLOW_TYPE or task_type == INSIGHT_TASK_TYPE:
        return INSIGHT_WORKFLOW_TYPE
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


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _normalize_sidecar_results(value: Any, job_dir: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(value, dict):
        for key, raw_path in value.items():
            if isinstance(raw_path, str) and raw_path.strip():
                result[str(key)] = raw_path
    fallback_files = {
        "anomalies": "anomaly_scan.json",
        "next_step_suggestions": "next_steps.json",
        "significance_tests": "significance_tests.json",
        "dashboard_config": "dashboard_config.json",
    }
    for key, filename in fallback_files.items():
        fallback_path = job_dir / filename
        if key not in result and fallback_path.exists() and fallback_path.is_file():
            result[key] = str(fallback_path)
    return result


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












