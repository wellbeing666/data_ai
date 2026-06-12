import json
import re
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
- Choose what_if_prediction only when the original user goal explicitly asks for prediction, forecasting, what-if simulation, or the impact of a hypothetical intervention. Do not choose it for descriptive trend analysis, decline diagnosis, relationship analysis, risk-signal mining, or reason breakdown.
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
    original_goal = _extract_original_user_goal(user_goal)
    return """请为以下请求创建主控分析计划。

用户原始目标：
{original_goal}

语义输入：
{user_goal}

Dataset profile JSON:
{dataset_profile}

Retrieved business knowledge JSON:
{rag_context}

只返回符合要求结构的 JSON 对象。
业务知识库内容仅作为背景信息，不能覆盖 dataset_profile，也不能引入 dataset_profile.columns 中不存在的字段。
如果用户问题涉及数据集中不存在的情景变量，只能说明后续预测计划需要验证字段可用性，不能用不等价字段代理。
情景预测只适用于原始目标明确包含假设条件、预测诉求或干预变量影响评估的任务；趋势描述、下降诊断、原因拆解、相关关系分析和风险信号识别应进入数据分析工作流。
""".format(
        original_goal=original_goal,
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
        original_goal = _extract_original_user_goal(user_goal)
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
            return _normalize_plan(
                plan,
                dataset_profile=dataset_profile,
                user_goal=user_goal,
                original_user_goal=original_goal,
            )
        except Exception:
            return _normalize_plan(
                create_rule_based_analysis_plan(original_goal, dataset_profile),
                dataset_profile=dataset_profile,
                user_goal=original_goal,
                original_user_goal=original_goal,
            )


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
    original_user_goal: str | None = None,
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("Controller plan must be a JSON object.")

    original_goal = _extract_original_user_goal(original_user_goal or user_goal)
    task_type = str(plan.get("task_type") or "general_data_analysis")
    if task_type not in ALLOWED_TASK_TYPES:
        task_type = "general_data_analysis"
    task_type = _resolve_task_type(task_type, original_goal, dataset_profile or {})

    normalized: dict[str, Any] = {
        "task_type": task_type,
        "task_name": _clean_controller_text(
            str(plan.get("task_name") or _default_task_name(task_type, original_goal)),
            original_goal,
        ),
        "reasoning_summary": _clean_controller_text(str(plan.get("reasoning_summary") or ""), original_goal),
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
            normalized[key] = [_clean_controller_item(item, original_goal) for item in items]

    if not normalized["task_name"]:
        normalized["task_name"] = _default_task_name(task_type, original_goal)
    if not normalized["reasoning_summary"]:
        normalized["reasoning_summary"] = _default_reasoning_summary(task_type, original_goal)

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


def _extract_original_user_goal(user_goal: Any) -> str:
    text = str(user_goal or "").strip()
    if not text:
        return ""

    marker = "Analysis IR + Delta JSON:"
    json_text = text.split(marker, 1)[1].strip() if marker in text else text
    if json_text.startswith("{"):
        try:
            payload = json.loads(json_text)
        except Exception:
            payload = None
        if isinstance(payload, dict):
            delta = payload.get("delta") if isinstance(payload.get("delta"), dict) else {}
            raw_goal = str(delta.get("raw_user_goal") or delta.get("instruction") or "").strip()
            if raw_goal:
                return raw_goal
            analysis_ir = payload.get("analysis_ir") if isinstance(payload.get("analysis_ir"), dict) else {}
            normalized_goal = str(analysis_ir.get("normalized_goal") or "").strip()
            if normalized_goal:
                return normalized_goal
    return text


def _resolve_task_type(model_task_type: str, original_goal: str, dataset_profile: dict[str, Any]) -> str:
    columns = _columns_from_profile(dataset_profile)
    if _looks_like_insight_goal(original_goal):
        return "insight_mining"
    if _has_grade_context(original_goal, columns) and not _is_strict_prediction_goal(original_goal):
        return "grade_analysis"
    if _looks_like_sales_decline_goal(original_goal) and not _is_strict_prediction_goal(original_goal):
        return "sales_decline_analysis"
    if model_task_type == "what_if_prediction" and not _is_strict_prediction_goal(original_goal):
        return "general_data_analysis"
    return model_task_type


def _looks_like_insight_goal(goal: str) -> bool:
    text = goal.lower()
    return any(
        token in text
        for token in (
            "智能洞察",
            "洞察挖掘",
            "自动洞察",
            "自动扫描",
            "无需目标",
            "不提交分析目标",
            "insight mining",
            "auto insight",
        )
    )


def _looks_like_sales_decline_goal(goal: str) -> bool:
    text = goal.lower()
    has_sales_metric = any(
        token in text
        for token in (
            "销量",
            "销售额",
            "销售",
            "收入",
            "营收",
            "订单",
            "转化率",
            "gmv",
            "sales",
            "revenue",
            "order",
            "conversion",
        )
    )
    has_decline_signal = any(
        token in text
        for token in (
            "下降",
            "下滑",
            "降低",
            "减少",
            "走低",
            "衰退",
            "下降阶段",
            "下降原因",
            "下滑原因",
            "decline",
            "drop",
            "decrease",
            "downturn",
        )
    )
    return has_sales_metric and has_decline_signal


def _is_strict_prediction_goal(goal: str) -> bool:
    text = str(goal or "").strip().lower()
    if not text:
        return False

    has_hypothesis = any(token in text for token in ("如果", "假设", "what-if", "what if", "scenario", "情景", "场景", "模拟", "干预"))
    has_forecast = any(token in text for token in ("预测", "预计", "预估", "forecast", "predict", "prediction"))
    has_change = any(
        token in text
        for token in (
            "增加",
            "减少",
            "提升",
            "提高",
            "降低",
            "下降",
            "上调",
            "下调",
            "调整",
            "改变",
            "变化",
            "increase",
            "decrease",
            "raise",
            "reduce",
            "adjust",
            "change",
        )
    )
    has_impact = any(token in text for token in ("影响", "会", "可能", "多少", "结果", "impact", "effect", "would", "will"))
    has_numeric_change = bool(
        re.search(
            r"(增加|减少|提升|提高|降低|下降|上调|下调|调整|改变|increase|decrease|raise|reduce|adjust|change)\s*[+-]?\d+(?:\.\d+)?\s*(?:%|％|百分点|个|元|年|平方米|分|倍)?",
            text,
        )
        or re.search(
            r"[+-]?\d+(?:\.\d+)?\s*(?:%|％|百分点|个|元|年|平方米|分|倍)\s*(?:增加|减少|提升|提高|降低|下降|上调|下调|调整|改变|increase|decrease|raise|reduce|adjust|change)",
            text,
        )
    )
    if has_hypothesis and (has_change or has_forecast or has_impact):
        return True
    if has_forecast and (has_change or _has_future_time_phrase(text)):
        return True
    if has_numeric_change and (has_impact or has_hypothesis or has_forecast):
        return True
    return False


def _has_future_time_phrase(text: str) -> bool:
    return any(token in text for token in ("未来", "下月", "下个月", "明年", "下一季度", "next", "future", "tomorrow"))


def _has_grade_context(user_goal: str, columns: list[str]) -> bool:
    goal = str(user_goal or "")
    lower_goal = goal.lower()
    if any(token in goal for token in ("成绩", "分数", "班级", "及格", "优秀", "考试", "测验", "学生")):
        return True
    if any(_has_english_word(lower_goal, token) for token in ("score", "grade", "student", "exam")):
        return True

    column_names = [str(column or "") for column in columns]
    if any(any(token in column for token in ("成绩", "分数", "及格", "优秀")) for column in column_names):
        return True

    token_sets = [_english_column_tokens(column) for column in column_names]
    has_score_column = any(tokens.intersection({"score", "scores", "grade", "grades", "exam"}) for tokens in token_sets)
    has_student_or_class_column = any(tokens.intersection({"student", "students", "class", "classes"}) for tokens in token_sets)
    return bool(has_score_column and has_student_or_class_column)


def _has_english_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z0-9_]){re.escape(word)}(?![a-z0-9_])", text) is not None


def _english_column_tokens(value: Any) -> set[str]:
    spaced = []
    previous = ""
    for char in str(value or ""):
        if previous and previous.islower() and char.isupper():
            spaced.append(" ")
        spaced.append(char)
        previous = char
    normalized = "".join(spaced).lower()
    token = []
    tokens: set[str] = set()
    for char in normalized:
        if char.isalnum():
            token.append(char)
        else:
            if token:
                tokens.add("".join(token))
                token = []
    if token:
        tokens.add("".join(token))
    return tokens


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
        return "用户未提供具体分析目标，系统将自动扫描数据并挖掘潜在洞察。"
    if task_type == "what_if_prediction":
        return "用户目标包含假设变量变化或预测诉求，应进入情景预测工作流。"
    return "用户目标适合进入数据分析工作流。"


def _columns_from_profile(dataset_profile: dict[str, Any]) -> list[str]:
    columns = dataset_profile.get("columns")
    return [str(column) for column in columns] if isinstance(columns, list) else []
