import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the analysis roadmap Agent of an AI-native data analysis workbench.

Convert the user's goal and controller plan into a visual execution roadmap. Return only valid JSON.
All user-facing text must be Simplified Chinese. Do not invent data columns.

Required schema:
{
  "title": "路线图标题",
  "goal": "用户目标",
  "workflow_type": "auto_repair|what_if_prediction",
  "mermaid_code": "flowchart TD\n  S1[步骤] --> S2[步骤]",
  "steps": [
    {
      "step_id": "S1",
      "agent": "Agent 名称",
      "title": "步骤标题",
      "description": "步骤说明",
      "status_stage": "controller",
      "depends_on": [],
      "expected_artifacts": []
    }
  ]
}
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    controller_plan: dict[str, Any],
    workflow_type: str,
) -> str:
    return """Build a visual roadmap for this analysis workflow.

User goal:
{user_goal}

Workflow type:
{workflow_type}

Dataset columns:
{columns}

Controller plan JSON:
{controller_plan}

Return only the required JSON object.
""".format(
        user_goal=user_goal,
        workflow_type=workflow_type,
        columns=json.dumps(dataset_profile.get("columns") or [], ensure_ascii=False),
        controller_plan=json.dumps(controller_plan, ensure_ascii=False, indent=2),
    )


class RoadmapAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def create(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        controller_plan: dict[str, Any],
        workflow_type: str,
    ) -> dict[str, Any]:
        fallback = create_rule_based_roadmap(user_goal, dataset_profile, controller_plan, workflow_type)
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(user_goal, dataset_profile, controller_plan, workflow_type)},
                ],
                temperature=0.1,
            )
            return _normalize_result(result, fallback)
        except Exception:
            return fallback


def create_analysis_roadmap(
    user_goal: str,
    dataset_profile: dict[str, Any],
    controller_plan: dict[str, Any],
    workflow_type: str,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return RoadmapAgent(llm_client=llm_client).create(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        controller_plan=controller_plan,
        workflow_type=workflow_type,
    )


def create_rule_based_roadmap(
    user_goal: str,
    dataset_profile: dict[str, Any],
    controller_plan: dict[str, Any],
    workflow_type: str,
) -> dict[str, Any]:
    task_type = str(controller_plan.get("task_type") or "general_data_analysis")
    if workflow_type == "what_if_prediction" or task_type == "what_if_prediction":
        steps = [
            _step("S1", "数据服务", "数据接入与画像", "读取表格或图片抽取结果，生成字段、样本量、缺失值和数值分布画像。", "loading_dataset", [], ["dataset_profile.json"]),
            _step("S2", "RAG 检索", "业务知识补充", "检索与当前目标相关的业务口径，辅助后续 Agent 选择更稳健的解释方式。", "rag_retrieval", ["S1"], ["rag_retrieval.json"]),
            _step("S3", "主控 Agent", "任务分流", "识别目标属于情景预测，并确认进入 what-if 预测工作流。", "controller", ["S1", "S2"], ["controller_plan.json"]),
            _step("S4", "假设解析 Agent", "抽取情景假设", "识别干预变量、变化幅度、目标指标和对象维度。", "hypothesis", ["S3"], ["hypothesis_plan.json"]),
            _step("S5", "预测计划 Agent", "设计预测方案", "选择模型或规则模拟方法，确定特征字段、口径和输出结构。", "prediction_plan", ["S4"], ["prediction_plan.json"]),
            _step("S6", "代码 Agent 与安全检查", "生成可执行脚本", "把预测方案转成 Python 脚本，并在执行前进行静态安全校验。", "code_generation", ["S5"], ["generated_prediction_script_attempt_*.py.txt", "code_safety_result_attempt_*.json"]),
            _step("S7", "沙箱执行与验证 Agent", "运行并校验结果", "在沙箱中执行脚本，生成预测结果和图表，再验证字段口径、产物结构和谨慎表述。", "validation", ["S6"], ["prediction_result.json", "prediction_validation_result.json", "charts/"]),
            _step("S8", "预测解释 Agent", "形成预测报告", "输出预测发现、限制说明、建议动作和可汇报的 PPT 大纲。", "explanation", ["S7"], ["prediction_explanation.json", "report_data.json"]),
        ]
    else:
        controller_steps = controller_plan.get("steps") if isinstance(controller_plan.get("steps"), list) else []
        description = "；".join(_step_text(item) for item in controller_steps[:3] if _step_text(item))
        steps = [
            _step("S1", "数据服务", "数据接入与画像", "读取上传表格或视觉抽取后的结构化数据，生成字段、样本量、缺失值和数值分布画像。", "loading_dataset", [], ["dataset_profile.json"]),
            _step("S2", "RAG 检索", "业务知识补充", "检索相关业务口径，帮助后续 Agent 使用正确术语和谨慎结论。", "rag_retrieval", ["S1"], ["rag_retrieval.json"]),
            _step("S3", "主控 Agent", "任务分流与拆解", description or "把自然语言目标转成可执行的数据分析任务。", "controller", ["S1", "S2"], ["controller_plan.json"]),
            _step("S4", "数据理解 Agent", "识别字段语义", "判断日期字段、目标指标、维度字段、数值字段和数据质量问题。", "data_understanding", ["S3"], ["data_understanding.json"]),
            _step("S5", "分析计划 Agent", "制定分析方案", "确定分析指标、分组维度、统计检查、图表计划和必要限制说明。", "analysis", ["S4"], ["analysis_plan.json"]),
            _step("S6", "代码 Agent 与安全检查", "生成可执行脚本", "把分析计划转成 Python 脚本，并在执行前进行静态安全校验。", "code_generation", ["S5"], ["generated_script_attempt_*.py.txt", "code_safety_result_attempt_*.json"]),
            _step("S7", "沙箱执行与验证 Agent", "运行、验证和自动修复", "在沙箱中执行脚本，生成结果和图表；如验证发现问题，会带着修复建议重新生成。", "validation", ["S6"], ["analysis_result.json", "validation_result.json", "charts/"]),
            _step("S8", "解释 Agent", "形成结论报告", "将通过验证的结果转成中文关键发现、业务建议、限制说明和 PPT 大纲。", "explanation", ["S7"], ["explanation.json", "report_data.json"]),
        ]
    normalized_workflow_type = "what_if_prediction" if workflow_type == "what_if_prediction" else "auto_repair"
    return {
        "title": "AI 分析路线图",
        "user_goal": str(user_goal or ""),
        "goal": str(user_goal or ""),
        "workflow_type": normalized_workflow_type,
        "task_type": task_type,
        "summary": "AI 已将自然语言目标拆解为一条可执行、可验证、可回溯的多 Agent 任务链。",
        "dataset_columns": [str(item) for item in dataset_profile.get("columns") or []],
        "steps": steps,
        "mermaid_code": _build_mermaid_code(steps),
    }

def _normalize_result(result: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return fallback
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    normalized_steps = []
    for index, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage") or item.get("status_stage") or "")
        inputs = _string_list(item.get("inputs")) or _string_list(item.get("depends_on"))
        outputs = _string_list(item.get("outputs")) or _string_list(item.get("expected_artifacts"))
        if stage == "quality_review" or "质检" in str(item.get("title") or item.get("agent") or ""):
            continue
        normalized_steps.append(
            {
                "step_id": str(item.get("step_id") or f"S{index}"),
                "agent": str(item.get("agent") or "Agent"),
                "title": str(item.get("title") or f"步骤 {index}"),
                "description": str(item.get("description") or ""),
                "stage": stage,
                "status_stage": stage,
                "inputs": inputs,
                "depends_on": inputs,
                "outputs": outputs,
                "expected_artifacts": outputs,
                "status_hint": str(item.get("status_hint") or stage),
            }
        )
    if not normalized_steps:
        normalized_steps = fallback["steps"]
    workflow_type = str(result.get("workflow_type") or fallback.get("workflow_type") or "auto_repair")
    if workflow_type not in {"auto_repair", "what_if_prediction"}:
        workflow_type = fallback.get("workflow_type", "auto_repair")
    user_goal = str(result.get("user_goal") or result.get("goal") or fallback.get("user_goal") or fallback.get("goal") or "")
    return {
        "title": str(result.get("title") or fallback.get("title") or "AI 分析路线图"),
        "user_goal": user_goal,
        "goal": user_goal,
        "workflow_type": workflow_type,
        "task_type": str(result.get("task_type") or fallback.get("task_type") or ""),
        "summary": str(result.get("summary") or fallback.get("summary") or "AI 已生成分析路线图。"),
        "dataset_columns": _string_list(result.get("dataset_columns")) or fallback.get("dataset_columns", []),
        "steps": normalized_steps,
        "mermaid_code": _valid_mermaid_code(result.get("mermaid_code")) or _build_mermaid_code(normalized_steps),
    }


def _valid_mermaid_code(value: Any) -> str:
    code = str(value or "").strip()
    if not code:
        return ""
    if code.startswith("flowchart") or code.startswith("graph"):
        return code
    return ""


def _build_mermaid_code(steps: list[dict[str, Any]]) -> str:
    lines = ["flowchart TD"]
    for index, step in enumerate(steps, start=1):
        step_id = _safe_mermaid_id(str(step.get("step_id") or f"S{index}"))
        title = _escape_mermaid_label(str(step.get("title") or f"步骤 {index}"))
        agent = _escape_mermaid_label(str(step.get("agent") or "Agent"))
        lines.append(f'  {step_id}["{index}. {title}<br/>{agent}"]')
    step_ids = [_safe_mermaid_id(str(step.get("step_id") or f"S{index}")) for index, step in enumerate(steps, start=1)]
    for previous, current in zip(step_ids, step_ids[1:]):
        lines.append(f"  {previous} --> {current}")
    return "\n".join(lines)


def _safe_mermaid_id(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum() or char == "_")
    return cleaned or "S"


def _escape_mermaid_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "'").replace("[", "(").replace("]", ")")


def _step(
    step_id: str,
    agent: str,
    title: str,
    description: str,
    status_stage: str,
    depends_on: list[str],
    expected_artifacts: list[str],
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "agent": agent,
        "title": title,
        "description": description,
        "stage": status_stage,
        "status_stage": status_stage,
        "inputs": depends_on,
        "depends_on": depends_on,
        "outputs": expected_artifacts,
        "expected_artifacts": expected_artifacts,
        "status_hint": status_stage,
    }


def _step_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("description") or item.get("name") or item.get("title") or "")
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item)]

