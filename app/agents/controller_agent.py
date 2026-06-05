import json
from typing import Any

from app.agents.master_agent import create_rule_based_analysis_plan
from app.services.llm_client import LLMClient, get_llm_client


ALLOWED_TASK_TYPES = {
    "grade_analysis",
    "sales_decline_analysis",
    "general_data_analysis",
    "what_if_prediction",
    "insight_mining",
}

PLAN_KEYS = [
    "task_type",
    "task_name",
    "reasoning_summary",
    "steps",
    "required_columns",
    "analysis_methods",
    "charts",
    "expected_artifacts",
    "risks",
]

LIST_KEYS = [
    "steps",
    "required_columns",
    "analysis_methods",
    "charts",
    "expected_artifacts",
    "risks",
]


SYSTEM_PROMPT = """You are the Controller Agent of an AI-native data analysis workbench.

Your job is to read the user's analysis goal and dataset profile, then create a structured analysis plan.

You must classify the task_type as exactly one of:
- grade_analysis
- sales_decline_analysis
- general_data_analysis
- what_if_prediction
- insight_mining

Return only one valid JSON object. Do not output markdown, code fences, comments, or extra explanation.
The JSON object must contain exactly these keys:
{
  "task_type": "...",
  "task_name": "...",
  "reasoning_summary": "...",
  "steps": [],
  "required_columns": [],
  "analysis_methods": [],
  "charts": [],
  "expected_artifacts": [],
  "risks": []
}

Guidance:
- Choose grade_analysis for score, exam, student, class, pass rate, excellent rate, or grade summary goals.
- Choose sales_decline_analysis for revenue, sales, GMV, order, conversion, customer, region, category, or time trend decline goals.
- Choose what_if_prediction for hypothetical, forecast, prediction, simulation, what-if, intervention, budget/weight adjustment, increase/decrease impact, or possible change goals.
- Choose insight_mining when the user explicitly asks for automatic insight discovery, no-goal analysis, autonomous scanning, potential pattern mining, or “智能洞察”.
- Choose general_data_analysis when the goal does not clearly match the specialized task types.
- Use only columns that appear in the dataset profile when filling required_columns and charts.
- Do not propose proxy substitution for an absent intervention variable. For example, do not replace a floor-level question with HouseStyle, and do not replace a subway/metro-station question with neighborhood or road-condition fields unless a direct transit-distance/station field exists.
- All user-facing text in task_name, reasoning_summary, steps, analysis_methods, charts, expected_artifacts, and risks must be Simplified Chinese.
- Keep reasoning_summary concise and factual.
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """请为以下请求创建主控分析计划。

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Retrieved business knowledge JSON:
{rag_context}

只返回符合要求结构的 JSON 对象。
业务知识库内容仅作为背景信息，不能覆盖 dataset_profile，也不能引入 dataset_profile.columns 中不存在的字段。
如果用户问题涉及数据集中不存在的情景变量，只能说明后续预测计划需要验证字段可用性，不能用不等价字段代理。
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
    )


class ControllerAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def create_plan(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        rag_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            plan = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(user_goal, dataset_profile, rag_context),
                    },
                ],
                temperature=0.1,
            )
            return _normalize_plan(plan, dataset_profile=dataset_profile, user_goal=user_goal)
        except Exception:
            return create_rule_based_analysis_plan(user_goal, dataset_profile)


def create_controller_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return ControllerAgent(llm_client=llm_client).create_plan(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        rag_context=rag_context,
    )


def _normalize_plan(
    plan: Any,
    dataset_profile: dict[str, Any] | None = None,
    user_goal: str = "",
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("Controller plan must be a JSON object.")

    task_type = str(plan.get("task_type") or "general_data_analysis")
    if task_type not in ALLOWED_TASK_TYPES:
        task_type = "general_data_analysis"

    normalized: dict[str, Any] = {
        "task_type": task_type,
        "task_name": _clean_controller_text(
            str(plan.get("task_name") or _default_task_name(task_type, user_goal)),
            user_goal,
        ),
        "reasoning_summary": _clean_controller_text(str(plan.get("reasoning_summary") or ""), user_goal),
        "steps": [],
        "required_columns": [],
        "analysis_methods": [],
        "charts": [],
        "expected_artifacts": [],
        "risks": [],
    }

    existing_columns = set(_columns_from_profile(dataset_profile or {}))
    for key in LIST_KEYS:
        value = plan.get(key)
        items = value if isinstance(value, list) else []
        if key == "required_columns":
            normalized[key] = [str(item) for item in items if str(item) in existing_columns]
        else:
            normalized[key] = [_clean_controller_item(item, user_goal) for item in items]

    if not normalized["task_name"]:
        normalized["task_name"] = _default_task_name(task_type, user_goal)
    if not normalized["reasoning_summary"]:
        normalized["reasoning_summary"] = _default_reasoning_summary(task_type, user_goal)

    return {key: normalized[key] for key in PLAN_KEYS}


def _clean_controller_item(value: Any, user_goal: str) -> Any:
    if isinstance(value, str):
        return _clean_controller_text(value, user_goal)
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            cleaned[key] = _clean_controller_text(item, user_goal) if isinstance(item, str) else item
        return cleaned
    return value


def _clean_controller_text(value: Any, user_goal: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    lower = text.lower()
    if "楼层" in user_goal and ("housestyle" in lower or "proxy" in lower or "代理" in text):
        return "用户希望预测楼层高低变化，但当前数据未提供房源所在楼层字段；后续情景预测会验证字段是否可用，不能用 HouseStyle 等建筑样式字段替代楼层。"
    if "地铁" in user_goal and ("proxy" in lower or "代理" in text or "condition" in lower or "neighborhood" in lower):
        return "用户希望预测新增地铁站或地铁距离变化的影响，但当前数据未提供地铁站、地铁距离或轨道交通可达性字段；后续情景预测会按字段可用性决定是否计算，不能用区域或道路条件字段替代地铁变量。"

    replacements = {
        "General data analysis": "通用数据分析",
        "What-if prediction": "情景预测",
        "Sales decline diagnosis": "销量下降诊断",
        "The goal asks about a hypothetical budget increase.": "用户提出了假设性变量变化问题，应进入情景预测流程。",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _default_task_name(task_type: str, user_goal: str) -> str:
    if task_type == "insight_mining":
        return "智能洞察挖掘"
    if task_type == "what_if_prediction":
        if "楼层" in user_goal:
            return "楼层调整对房价影响预测"
        if "地铁" in user_goal:
            return "地铁因素变化对房价影响预测"
        if "装修" in user_goal:
            return "装修等级变化对房价影响预测"
        if "房龄" in user_goal:
            return "房龄变化对房价影响预测"
        if "两居" in user_goal or "三居" in user_goal:
            return "卧室数量变化对房价影响预测"
        return "情景预测"
    if task_type == "grade_analysis":
        return "成绩数据分析"
    if task_type == "sales_decline_analysis":
        return "销量下降诊断"
    return "通用数据分析"


def _default_reasoning_summary(task_type: str, user_goal: str) -> str:
    if task_type == "insight_mining":
        return "智能洞察挖掘"
    if task_type == "what_if_prediction":
        return "用户目标包含假设变量变化或预测诉求，应进入情景预测工作流。"
    if task_type == "insight_mining":
        return "用户未提供具体分析目标，系统将自动扫描数据并挖掘潜在洞察。"
    return "用户目标适合进入数据分析工作流。"


def _columns_from_profile(dataset_profile: dict[str, Any]) -> list[str]:
    columns = dataset_profile.get("columns")
    return [str(column) for column in columns] if isinstance(columns, list) else []

