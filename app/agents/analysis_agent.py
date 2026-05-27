import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


CHART_TYPES = {"bar", "line", "scatter", "box", "pie", "heatmap"}

RESULT_KEYS = [
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

For sales decline reason analysis, output possible reasons only. Do not claim confirmed causality or deterministic cause-and-effect.
If the data fields are insufficient for the requested analysis, explain that in limitations.

The JSON object must contain exactly these keys:
{
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
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    data_understanding_result: dict[str, Any],
    controller_plan: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """Create an analysis plan for this request.

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Data understanding result JSON:
{data_understanding_result}

Controller plan JSON:
{controller_plan}

Retrieved business knowledge JSON:
{rag_context}

Return only the JSON object with the required schema. Use only field names from dataset_profile.columns.
The retrieved business knowledge is background for methods and terminology only. It must not override the actual dataset profile or introduce unavailable fields.
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
            "Group records by class or available dimensions.",
            "Calculate count, mean, min, max, pass rate, and excellent rate for score metrics.",
            "Compare score distributions across groups.",
        ]
        checks = [
            "Check missing values in score fields.",
            "Verify selected score metrics are numeric.",
            "Check whether grouping dimensions have enough records per group.",
        ]
        chart_plan = _grade_chart_plan(metrics, dimensions)
    elif task_type == "sales_decline_analysis":
        methods = [
            "Compare metric trends across available time periods.",
            "Segment metrics by available dimensions to identify possible decline contributors.",
            "Check whether changes are concentrated in specific groups.",
        ]
        checks = [
            "Check missing values in target metrics.",
            "Check whether a date field exists for trend comparison.",
            "Compare segment-level changes as possible reasons, not confirmed causality.",
        ]
        chart_plan = _sales_decline_chart_plan(metrics, dimensions, date_columns)
        _ensure_causal_limitation(limitations)
    else:
        methods = [
            "Summarize available numeric metrics.",
            "Compare metrics across available dimensions.",
            "Inspect missing values and basic distribution patterns.",
        ]
        checks = [
            "Check missing values by field.",
            "Verify numeric fields before aggregation.",
        ]
        chart_plan = _general_chart_plan(metrics, dimensions)

    return {
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
            "title": str(item.get("title") or ""),
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
            "title": "Average score by group",
            "x": dimension,
            "y": metric,
            "group_by": dimension,
        },
        {
            "chart_type": "box",
            "title": "Score distribution by group",
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
            "title": "Metric trend for possible decline detection",
            "x": date_column,
            "y": metric,
            "group_by": dimension,
        },
        {
            "chart_type": "bar",
            "title": "Metric comparison by segment",
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
            "title": "Metric comparison by dimension",
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
        limitations.append("No usable metric field was identified for quantitative analysis.")
    if not dimensions:
        limitations.append("No usable grouping dimension was identified for segment analysis.")
    if task_type == "sales_decline_analysis" and not date_columns:
        limitations.append("No date field was identified, so decline trends cannot be validated over time.")
    return limitations


def _ensure_causal_limitation(limitations: list[str]) -> None:
    message = (
        "Sales decline analysis can identify associations and possible reasons, "
        "but cannot prove confirmed causality from this dataset alone."
    )
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
    return [str(item) for item in value if item is not None]


def _profile_columns(dataset_profile: dict[str, Any]) -> list[str]:
    return [str(column) for column in dataset_profile.get("columns", [])]
