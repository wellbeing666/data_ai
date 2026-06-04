import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


CHART_TYPES = {"bar", "line", "scatter", "box", "pie", "heatmap"}

RESULT_KEYS = [
    "task_type",
    "analysis_goal",
    "methods",
    "grouping_dimensions",
    "metrics",
    "chart_plan",
    "statistical_checks",
    "limitations",
]


SYSTEM_PROMPT = """You are the Analysis Agent of an AI-native data analysis workbench.

Your job is to turn the user goal, dataset profile, data understanding result, and controller plan into a practical analysis plan.

You must return only one valid JSON object. Do not output markdown, code fences, comments, or extra explanation.
You may only use field names that exist in dataset_profile.columns. Never invent columns.
All user-facing text in methods, titles, statistical_checks and limitations must be Simplified Chinese.

For sales decline reason analysis, output possible reasons only. Do not claim confirmed causality or deterministic cause-and-effect.
If the data fields are insufficient for the requested analysis, explain that in limitations.

The JSON object must contain exactly these keys:
{
  "task_type": "grade_analysis|sales_decline_analysis|general_data_analysis",
  "analysis_goal": "...",
  "methods": [],
  "grouping_dimensions": [],
  "metrics": [],
  "chart_plan": [
    {
      "chart_type": "bar|line|scatter|box|pie|heatmap",
      "title": "...",
      "x": "...",
      "y": "...",
      "group_by": "..."
    }
  ],
  "statistical_checks": [],
  "limitations": []
}

Guidance:
- methods should be analysis operations such as aggregation, trend comparison, distribution check, correlation screening, segment comparison, or quality check.
- grouping_dimensions should contain categorical or date fields used for grouping.
- metrics should contain numeric fields used as measures or targets.
- chart_plan must only reference existing fields, or use an empty string when a field is unavailable.
- statistical_checks should be feasible with the available dataset profile.
- limitations should be explicit when date, metric, or dimension fields are missing.
- Write Chinese strings such as “按月份趋势对比”, “按维度分组拆解”, “仅能识别相关信号”.
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    data_understanding_result: dict[str, Any],
    controller_plan: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """请为本次请求生成分析计划 JSON。

用户目标：
{user_goal}

数据画像 JSON：
{dataset_profile}

数据理解结果 JSON：
{data_understanding_result}

主控计划 JSON：
{controller_plan}

检索到的业务知识 JSON：
{rag_context}

请只返回符合 schema 的 JSON 对象。只能使用 dataset_profile.columns 中存在的字段名。
检索到的业务知识只作为方法和术语参考，不能覆盖真实数据画像，也不能引入不存在字段。所有面向用户的文本必须使用中文。
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        data_understanding_result=json.dumps(
            data_understanding_result, ensure_ascii=False, indent=2
        ),
        controller_plan=json.dumps(controller_plan, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
    )


class AnalysisAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def create_plan(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        data_understanding_result: dict[str, Any],
        controller_plan: dict[str, Any],
        rag_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            user_goal=user_goal,
                            dataset_profile=dataset_profile,
                            data_understanding_result=data_understanding_result,
                            controller_plan=controller_plan,
                            rag_context=rag_context,
                        ),
                    },
                ],
                temperature=0.1,
            )
            return _normalize_result(
                result=result,
                user_goal=user_goal,
                dataset_profile=dataset_profile,
                data_understanding_result=data_understanding_result,
                controller_plan=controller_plan,
            )
        except Exception:
            return create_rule_based_analysis_plan(
                user_goal=user_goal,
                dataset_profile=dataset_profile,
                data_understanding_result=data_understanding_result,
                controller_plan=controller_plan,
            )


def create_analysis_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
    data_understanding_result: dict[str, Any],
    controller_plan: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return AnalysisAgent(llm_client=llm_client).create_plan(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        data_understanding_result=data_understanding_result,
        controller_plan=controller_plan,
        rag_context=rag_context,
    )


def create_rule_based_analysis_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
    data_understanding_result: dict[str, Any],
    controller_plan: dict[str, Any],
) -> dict[str, Any]:
    task_type = str(controller_plan.get("task_type") or "general_data_analysis")
    metrics = _existing_metric_names(
        data_understanding_result.get("target_columns"),
        dataset_profile,
        data_understanding_result,
    )
    if not metrics:
        metrics = _existing_metric_names(
            data_understanding_result.get("numeric_columns"),
            dataset_profile,
            data_understanding_result,
        )
    if not metrics:
        metrics = _existing_names(
            data_understanding_result.get("numeric_columns"),
            dataset_profile,
        )

    dimensions = _existing_names(
        data_understanding_result.get("dimension_columns")
        or data_understanding_result.get("date_columns"),
        dataset_profile,
    )
    date_columns = _existing_names(data_understanding_result.get("date_columns"), dataset_profile)
    limitations = _field_limitations(metrics, dimensions, date_columns, task_type)

    if task_type == "grade_analysis":
        methods = [
            "按班级或可用维度进行分组统计。",
            "计算成绩类指标的人数、平均值、最高值、最低值、及格率和优秀率。",
            "比较不同分组的成绩分布差异。",
        ]
        checks = [
            "检查成绩字段的缺失值。",
            "确认选中的成绩指标可以转换为数值。",
            "检查各分组样本量是否足够支撑对比。",
        ]
        chart_plan = _grade_chart_plan(metrics, dimensions)
    elif task_type == "sales_decline_analysis":
        methods = [
            "按可用时间字段比较核心指标趋势。",
            "按地区、渠道、商品类别等可用维度拆解指标变化，识别可能相关信号。",
            "检查下降或波动是否集中在特定分组。",
        ]
        checks = [
            "检查目标指标的缺失值。",
            "检查是否存在可用于趋势对比的日期字段。",
            "分组变化只能作为可能原因或相关信号，不能写成确定因果。",
        ]
        chart_plan = _sales_decline_chart_plan(metrics, dimensions, date_columns)
        _ensure_causal_limitation(limitations)
    else:
        methods = [
            "汇总可用数值指标的总体水平。",
            "按可用维度比较指标差异。",
            "检查缺失值和基础分布特征。",
        ]
        checks = [
            "按字段检查缺失值。",
            "聚合前确认数值字段可正常计算。",
        ]
        chart_plan = _general_chart_plan(metrics, dimensions)

    return {
        "task_type": task_type,
        "analysis_goal": user_goal,
        "methods": methods,
        "grouping_dimensions": dimensions,
        "metrics": metrics,
        "chart_plan": chart_plan,
        "statistical_checks": checks,
        "limitations": limitations,
    }


def _normalize_result(
    result: Any,
    user_goal: str,
    dataset_profile: dict[str, Any],
    data_understanding_result: dict[str, Any],
    controller_plan: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Analysis plan must be a JSON object.")

    fallback = create_rule_based_analysis_plan(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        data_understanding_result=data_understanding_result,
        controller_plan=controller_plan,
    )
    task_type = str(controller_plan.get("task_type") or "")

    normalized = {
        "task_type": task_type or "general_data_analysis",
        "analysis_goal": str(result.get("analysis_goal") or user_goal),
        "methods": _string_list(result.get("methods")) or fallback["methods"],
        "grouping_dimensions": _existing_names(
            result.get("grouping_dimensions"), dataset_profile
        )
        or fallback["grouping_dimensions"],
        "metrics": _existing_metric_names(
            result.get("metrics"), dataset_profile, data_understanding_result
        )
        or fallback["metrics"],
        "chart_plan": _normalize_chart_plan(result.get("chart_plan"), dataset_profile),
        "statistical_checks": _string_list(result.get("statistical_checks"))
        or fallback["statistical_checks"],
        "limitations": _string_list(result.get("limitations")),
    }

    if not normalized["chart_plan"]:
        normalized["chart_plan"] = fallback["chart_plan"]

    if not normalized["limitations"]:
        normalized["limitations"] = fallback["limitations"]

    normalized["limitations"].extend(
        limitation
        for limitation in _field_limitations(
            metrics=normalized["metrics"],
            dimensions=normalized["grouping_dimensions"],
            date_columns=_existing_names(
                data_understanding_result.get("date_columns"), dataset_profile
            ),
            task_type=task_type,
        )
        if limitation not in normalized["limitations"]
    )

    if _needs_causal_caution(user_goal, task_type):
        _ensure_causal_limitation(normalized["limitations"])

    return {key: normalized[key] for key in RESULT_KEYS}


def _normalize_chart_plan(value: Any, dataset_profile: dict[str, Any]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []

    profile_columns = set(_profile_columns(dataset_profile))
    charts = []
    for item in value:
        if not isinstance(item, dict):
            continue
        chart_type = str(item.get("chart_type") or "bar")
        if chart_type not in CHART_TYPES:
            chart_type = "bar"
        chart = {
            "chart_type": chart_type,
            "title": _localize_text(str(item.get("title") or "")),
            "x": _field_or_empty(item.get("x"), profile_columns),
            "y": _field_or_empty(item.get("y"), profile_columns),
            "group_by": _field_or_empty(item.get("group_by"), profile_columns),
        }
        charts.append(chart)
    return charts


def _grade_chart_plan(metrics: list[str], dimensions: list[str]) -> list[dict[str, str]]:
    metric = metrics[0] if metrics else ""
    dimension = dimensions[0] if dimensions else ""
    return [
        {
            "chart_type": "bar",
            "title": "各分组平均成绩对比",
            "x": dimension,
            "y": metric,
            "group_by": dimension,
        },
        {
            "chart_type": "box",
            "title": "各分组成绩分布",
            "x": dimension,
            "y": metric,
            "group_by": dimension,
        },
    ]


def _sales_decline_chart_plan(
    metrics: list[str],
    dimensions: list[str],
    date_columns: list[str],
) -> list[dict[str, str]]:
    metric = metrics[0] if metrics else ""
    dimension = dimensions[0] if dimensions else ""
    date_column = date_columns[0] if date_columns else dimension
    return [
        {
            "chart_type": "line" if date_columns else "bar",
            "title": "核心指标趋势与下降信号",
            "x": date_column,
            "y": metric,
            "group_by": dimension,
        },
        {
            "chart_type": "bar",
            "title": "核心指标分组对比",
            "x": dimension,
            "y": metric,
            "group_by": dimension,
        },
    ]


def _general_chart_plan(metrics: list[str], dimensions: list[str]) -> list[dict[str, str]]:
    metric = metrics[0] if metrics else ""
    dimension = dimensions[0] if dimensions else ""
    return [
        {
            "chart_type": "bar",
            "title": "核心指标维度对比",
            "x": dimension,
            "y": metric,
            "group_by": dimension,
        }
    ]


def _field_limitations(
    metrics: list[str],
    dimensions: list[str],
    date_columns: list[str],
    task_type: str,
) -> list[str]:
    limitations = []
    if not metrics:
        limitations.append("未识别到可用于定量分析的指标字段。")
    if not dimensions:
        limitations.append("未识别到可用于分组对比的维度字段。")
    if task_type == "sales_decline_analysis" and not date_columns:
        limitations.append("未识别到日期字段，因此无法严格验证下降趋势的时间变化。")
    return limitations


def _ensure_causal_limitation(limitations: list[str]) -> None:
    message = "销量下降分析只能识别相关信号和可能原因，不能仅凭当前数据证明确定因果关系。"
    if message not in limitations:
        limitations.append(message)


def _needs_causal_caution(user_goal: str, task_type: str) -> bool:
    goal_lower = user_goal.lower()
    return task_type == "sales_decline_analysis" or any(
        keyword in goal_lower
        for keyword in ("decline", "reason", "cause", "why", "下降", "原因", "为什么")
    )


def _existing_names(value: Any, dataset_profile: dict[str, Any]) -> list[str]:
    if not isinstance(value, list):
        return []

    allowed = set(_profile_columns(dataset_profile))
    names = []
    seen = set()
    for item in value:
        name = str(item)
        if name in allowed and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def _existing_metric_names(
    value: Any,
    dataset_profile: dict[str, Any],
    data_understanding_result: dict[str, Any],
) -> list[str]:
    if not isinstance(value, list):
        return []

    allowed_metrics = set(dataset_profile.get("numeric_summary", {}).keys())
    for item in data_understanding_result.get("columns", []):
        if not isinstance(item, dict):
            continue
        if item.get("semantic_type") == "metric":
            allowed_metrics.add(str(item.get("name")))

    names = []
    seen = set()
    for item in value:
        name = str(item)
        if name in allowed_metrics and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def _field_or_empty(value: Any, profile_columns: set[str]) -> str:
    name = str(value or "")
    return name if name in profile_columns else ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_localize_text(str(item)) for item in value if item is not None and str(item).strip()]


def _localize_text(value: str) -> str:
    text = str(value or "").strip()
    translations = {
        "Group records by class or available dimensions.": "按班级或可用维度进行分组统计。",
        "Calculate count, mean, min, max, pass rate, and excellent rate for score metrics.": "计算成绩类指标的人数、平均值、最高值、最低值、及格率和优秀率。",
        "Compare score distributions across groups.": "比较不同分组的成绩分布差异。",
        "Check missing values in score fields.": "检查成绩字段的缺失值。",
        "Verify selected score metrics are numeric.": "确认选中的成绩指标可以转换为数值。",
        "Check whether grouping dimensions have enough records per group.": "检查各分组样本量是否足够支撑对比。",
        "Compare metric trends across available time periods.": "按可用时间字段比较核心指标趋势。",
        "Segment metrics by available dimensions to identify possible decline contributors.": "按可用维度拆解指标变化，识别可能相关信号。",
        "Check whether changes are concentrated in specific groups.": "检查下降或波动是否集中在特定分组。",
        "Check missing values in target metrics.": "检查目标指标的缺失值。",
        "Check whether a date field exists for trend comparison.": "检查是否存在可用于趋势对比的日期字段。",
        "Compare segment-level changes as possible reasons, not confirmed causality.": "分组变化只能作为可能原因或相关信号，不能写成确定因果。",
        "Summarize available numeric metrics.": "汇总可用数值指标的总体水平。",
        "Compare metrics across available dimensions.": "按可用维度比较指标差异。",
        "Inspect missing values and basic distribution patterns.": "检查缺失值和基础分布特征。",
        "Check missing values by field.": "按字段检查缺失值。",
        "Verify numeric fields before aggregation.": "聚合前确认数值字段可正常计算。",
        "No usable metric field was identified for quantitative analysis.": "未识别到可用于定量分析的指标字段。",
        "No usable grouping dimension was identified for segment analysis.": "未识别到可用于分组对比的维度字段。",
        "No date field was identified, so decline trends cannot be validated over time.": "未识别到日期字段，因此无法严格验证下降趋势的时间变化。",
        "Sales decline analysis can identify associations and possible reasons, but cannot prove confirmed causality from this dataset alone.": "销量下降分析只能识别相关信号和可能原因，不能仅凭当前数据证明确定因果关系。",
    }
    return translations.get(text, text)


def _profile_columns(dataset_profile: dict[str, Any]) -> list[str]:
    return [str(column) for column in dataset_profile.get("columns", [])]
