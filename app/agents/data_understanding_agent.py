import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SEMANTIC_TYPES = {
    "date",
    "metric",
    "dimension",
    "identifier",
    "text",
    "unknown",
}

RESULT_KEYS = [
    "columns",
    "date_columns",
    "target_columns",
    "dimension_columns",
    "numeric_columns",
    "quality_issues",
    "suitability_score",
    "warnings",
]


SYSTEM_PROMPT = """You are the Data Understanding Agent of an AI-native data analysis workbench.

Your job is to infer column semantics from the user's analysis goal and dataset profile.

You must return only one valid JSON object. Do not output markdown, code fences, comments, or extra explanation.
Never invent columns. You may only mention field names that exist in dataset_profile.columns.

The JSON object must contain exactly these keys:
{
  "columns": [
    {
      "name": "field name",
      "semantic_type": "date|metric|dimension|identifier|text|unknown",
      "business_meaning": "business meaning of the field",
      "confidence": 0.0
    }
  ],
  "date_columns": [],
  "target_columns": [],
  "dimension_columns": [],
  "numeric_columns": [],
  "quality_issues": [],
  "suitability_score": 0.0,
  "warnings": []
}

Guidance:
- date means date, datetime, month, year, week, or time period fields.
- metric means numeric measures that can be aggregated or compared.
- dimension means categorical fields used for grouping, filtering, or segmentation.
- identifier means IDs, names, codes, keys, order numbers, student numbers, or unique identifiers.
- text means free-form notes or long text.
- unknown means the profile is insufficient to infer semantics.
- target_columns should contain fields most relevant to the user's goal.
- Use confidence between 0.0 and 1.0.
- Keep warnings and quality_issues concise and factual.
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """Understand this dataset for the requested analysis.

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Retrieved business knowledge JSON:
{rag_context}

Return only the JSON object with the required schema. Do not mention any field that is not in dataset_profile.columns.
The retrieved business knowledge may help infer business meaning, but it must not add or rename fields.
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
    )


class DataUnderstandingAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def understand(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        rag_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(user_goal, dataset_profile, rag_context),
                    },
                ],
                temperature=0.1,
            )
            return _normalize_result(result, user_goal, dataset_profile)
        except Exception:
            return create_rule_based_data_understanding(user_goal, dataset_profile)


def create_data_understanding(
    user_goal: str,
    dataset_profile: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return DataUnderstandingAgent(llm_client=llm_client).understand(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        rag_context=rag_context,
    )


def create_rule_based_data_understanding(
    user_goal: str,
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    profile_columns = _profile_columns(dataset_profile)
    column_items = [_rule_column_item(column, dataset_profile) for column in profile_columns]

    date_columns = [
        item["name"] for item in column_items if item["semantic_type"] == "date"
    ]
    numeric_columns = list(dataset_profile.get("numeric_summary", {}).keys())
    numeric_columns = _filter_existing_names(numeric_columns, profile_columns)
    dimension_columns = [
        item["name"] for item in column_items if item["semantic_type"] == "dimension"
    ]
    target_columns = _detect_target_columns(user_goal, column_items, numeric_columns)
    quality_issues = _detect_quality_issues(dataset_profile, profile_columns)
    warnings = _detect_warnings(user_goal, date_columns, numeric_columns, target_columns)

    return {
        "columns": column_items,
        "date_columns": date_columns,
        "target_columns": target_columns,
        "dimension_columns": dimension_columns,
        "numeric_columns": numeric_columns,
        "quality_issues": quality_issues,
        "suitability_score": _calculate_suitability_score(
            profile_columns=profile_columns,
            target_columns=target_columns,
            quality_issues=quality_issues,
        ),
        "warnings": warnings,
    }


def _normalize_result(
    result: Any,
    user_goal: str,
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Data understanding result must be a JSON object.")

    profile_columns = _profile_columns(dataset_profile)
    allowed_columns = set(profile_columns)
    rule_based = create_rule_based_data_understanding(user_goal, dataset_profile)
    normalized_columns = []
    seen_columns = set()

    raw_columns = result.get("columns")
    if isinstance(raw_columns, list):
        for item in raw_columns:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "")
            if name not in allowed_columns or name in seen_columns:
                continue
            semantic_type = str(item.get("semantic_type") or "unknown")
            if semantic_type not in SEMANTIC_TYPES:
                semantic_type = "unknown"
            normalized_columns.append(
                {
                    "name": name,
                    "semantic_type": semantic_type,
                    "business_meaning": str(item.get("business_meaning") or ""),
                    "confidence": _clamp_float(item.get("confidence"), 0.0, 1.0),
                }
            )
            seen_columns.add(name)

    rule_columns_by_name = {item["name"]: item for item in rule_based["columns"]}
    for column in profile_columns:
        if column not in seen_columns:
            normalized_columns.append(rule_columns_by_name[column])

    normalized = {
        "columns": normalized_columns,
        "date_columns": _filter_existing_names(result.get("date_columns"), profile_columns),
        "target_columns": _filter_existing_names(
            result.get("target_columns"), profile_columns
        ),
        "dimension_columns": _filter_existing_names(
            result.get("dimension_columns"), profile_columns
        ),
        "numeric_columns": _filter_existing_names(
            result.get("numeric_columns"), profile_columns
        ),
        "quality_issues": result.get("quality_issues")
        if isinstance(result.get("quality_issues"), list)
        else [],
        "suitability_score": _clamp_float(result.get("suitability_score"), 0.0, 1.0),
        "warnings": result.get("warnings") if isinstance(result.get("warnings"), list) else [],
    }

    for key in ("date_columns", "target_columns", "dimension_columns", "numeric_columns"):
        if not normalized[key]:
            normalized[key] = rule_based[key]

    if normalized["suitability_score"] == 0.0:
        normalized["suitability_score"] = rule_based["suitability_score"]

    return {key: normalized[key] for key in RESULT_KEYS}


def _rule_column_item(column: str, dataset_profile: dict[str, Any]) -> dict[str, Any]:
    dtype = str(dataset_profile.get("dtypes", {}).get(column, "")).lower()
    column_lower = column.lower()
    semantic_type = _infer_semantic_type(column_lower, dtype, dataset_profile, column)

    return {
        "name": column,
        "semantic_type": semantic_type,
        "business_meaning": _infer_business_meaning(column, semantic_type),
        "confidence": _default_confidence(semantic_type),
    }


def _infer_semantic_type(
    column_lower: str,
    dtype: str,
    dataset_profile: dict[str, Any],
    column: str,
) -> str:
    if "datetime" in dtype or any(
        keyword in column_lower
        for keyword in ("date", "time", "month", "year", "day", "日期", "时间", "月份", "年份")
    ):
        return "date"

    if any(
        keyword in column_lower
        for keyword in ("id", "编号", "学号", "工号", "订单号", "code", "key", "name", "姓名")
    ):
        return "identifier"

    if column in dataset_profile.get("numeric_summary", {}):
        return "metric"

    unique_values = (
        dataset_profile.get("text_summary", {})
        .get(column, {})
        .get("unique_values", [])
    )
    if 0 < len(unique_values) <= 20:
        return "dimension"

    if "object" in dtype or "string" in dtype or "text" in dtype:
        return "text"

    return "unknown"


def _infer_business_meaning(column: str, semantic_type: str) -> str:
    meanings = {
        "date": "Time field for trend or period analysis.",
        "metric": "Numeric measure for aggregation, comparison, or target analysis.",
        "dimension": "Categorical field for grouping, filtering, or segmentation.",
        "identifier": "Identifier field used to distinguish records or entities.",
        "text": "Text field that may provide notes or descriptive context.",
        "unknown": "Field meaning is unclear from the available profile.",
    }
    return f"{column}: {meanings[semantic_type]}"


def _default_confidence(semantic_type: str) -> float:
    if semantic_type == "unknown":
        return 0.3
    return 0.75


def _detect_target_columns(
    user_goal: str,
    column_items: list[dict[str, Any]],
    numeric_columns: list[str],
) -> list[str]:
    goal_lower = user_goal.lower()
    matched = [
        item["name"]
        for item in column_items
        if item["name"].lower() in goal_lower
    ]
    if matched:
        return matched

    score_keywords = ("score", "grade", "成绩", "分数")
    sales_keywords = ("sales", "revenue", "gmv", "order", "销售", "销量", "收入")
    for keywords in (score_keywords, sales_keywords):
        if any(keyword in goal_lower for keyword in keywords):
            selected = [
                item["name"]
                for item in column_items
                if any(keyword in item["name"].lower() for keyword in keywords)
            ]
            if selected:
                return selected

    return numeric_columns[:1]


def _detect_quality_issues(
    dataset_profile: dict[str, Any],
    profile_columns: list[str],
) -> list[dict[str, Any]]:
    issues = []
    missing_values = dataset_profile.get("missing_values", {})
    for column in profile_columns:
        missing = missing_values.get(column, {})
        ratio = float(missing.get("ratio") or 0.0)
        if ratio > 0:
            issues.append(
                {
                    "column": column,
                    "issue_type": "missing_values",
                    "severity": "high" if ratio >= 0.2 else "medium",
                    "description": f"{column} has missing ratio {ratio:.2%}.",
                }
            )
    return issues


def _detect_warnings(
    user_goal: str,
    date_columns: list[str],
    numeric_columns: list[str],
    target_columns: list[str],
) -> list[str]:
    warnings = []
    goal_lower = user_goal.lower()
    if any(keyword in goal_lower for keyword in ("trend", "decline", "下降", "趋势")):
        if not date_columns:
            warnings.append("No date column was identified for trend analysis.")
    if not numeric_columns:
        warnings.append("No numeric columns were identified.")
    if not target_columns:
        warnings.append("No target columns were identified from the user goal.")
    return warnings


def _calculate_suitability_score(
    profile_columns: list[str],
    target_columns: list[str],
    quality_issues: list[dict[str, Any]],
) -> float:
    if not profile_columns:
        return 0.0

    score = 0.65
    if target_columns:
        score += 0.2
    score -= min(0.3, len(quality_issues) * 0.05)
    return round(_clamp_float(score, 0.0, 1.0), 2)


def _profile_columns(dataset_profile: dict[str, Any]) -> list[str]:
    return [str(column) for column in dataset_profile.get("columns", [])]


def _filter_existing_names(value: Any, profile_columns: list[str]) -> list[str]:
    if not isinstance(value, list):
        return []

    allowed = set(profile_columns)
    filtered = []
    seen = set()
    for item in value:
        name = str(item)
        if name in allowed and name not in seen:
            filtered.append(name)
            seen.add(name)
    return filtered


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))
