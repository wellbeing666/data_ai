import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the Prediction Planning Agent for a what-if simulation workflow.

Create a practical prediction/simulation plan from the user goal, dataset profile, and parsed hypothesis.
Return only one valid JSON object. Do not output markdown or explanation.
Use only fields that exist in dataset_profile.columns.

Required schema:
{
  "task_type": "what_if_prediction",
  "prediction_goal": "...",
  "target_metric": "",
  "intervention": {
    "variable": "",
    "column": "",
    "change_type": "relative|absolute|weight_shift|unknown",
    "change_value": 0.0,
    "unit": ""
  },
  "entity_dimension": "",
  "feature_columns": [],
  "model_candidates": [],
  "fallback_strategy": "...",
  "charts": [],
  "limitations": []
}

Use cautious language. Prediction estimates are not causal proof.
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    hypothesis_plan: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """Create a prediction plan.

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Hypothesis plan JSON:
{hypothesis_plan}

Retrieved business knowledge JSON:
{rag_context}

Use only dataset_profile.columns for target_metric, intervention.column, entity_dimension, and feature_columns.
If the request uses a unit such as 平方米, keep it in intervention.unit.
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        hypothesis_plan=json.dumps(hypothesis_plan, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
    )


class PredictionAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def create_plan(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        hypothesis_plan: dict[str, Any],
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
                            hypothesis_plan=hypothesis_plan,
                            rag_context=rag_context,
                        ),
                    },
                ],
                temperature=0.1,
            )
            return _normalize(result, user_goal, dataset_profile, hypothesis_plan)
        except Exception:
            return create_rule_based_prediction_plan(user_goal, dataset_profile, hypothesis_plan)


def create_prediction_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
    hypothesis_plan: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return PredictionAgent(llm_client=llm_client).create_plan(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        hypothesis_plan=hypothesis_plan,
        rag_context=rag_context,
    )


def create_rule_based_prediction_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
    hypothesis_plan: dict[str, Any],
) -> dict[str, Any]:
    columns = _columns(dataset_profile)
    numeric = [str(column) for column in dataset_profile.get("numeric_summary", {}).keys()]
    target = _existing(hypothesis_plan.get("target_metric", {}).get("matched_column"), columns)
    if not target:
        target = _choose_target(user_goal, numeric, columns)
    intervention_column = _existing(
        hypothesis_plan.get("intervention", {}).get("matched_column"), columns
    )
    if not intervention_column or (_is_identifier_column(intervention_column) and _mentions_area_change(user_goal)):
        intervention_column = _choose_intervention(user_goal, numeric, columns, target)
    entity = _existing(hypothesis_plan.get("entity_dimension", {}).get("matched_column"), columns)
    if not entity:
        entity = _choose_dimension(user_goal, dataset_profile, columns)

    feature_columns = [column for column in numeric if column != target and not _is_identifier_column(column)]
    if intervention_column and intervention_column not in feature_columns and intervention_column != target:
        feature_columns.insert(0, intervention_column)

    limitations = []
    if not target:
        limitations.append("No numeric target metric was identified; the script must use rule-based simulation.")
    if not intervention_column:
        limitations.append("No matching intervention column was identified; use a scenario-level heuristic if needed.")
    if not entity:
        limitations.append("No entity dimension was identified; rank the whole dataset or inferred categories when possible.")

    hypothesis_intervention = hypothesis_plan.get("intervention") if isinstance(hypothesis_plan.get("intervention"), dict) else {}
    return {
        "task_type": "what_if_prediction",
        "prediction_goal": user_goal,
        "target_metric": target,
        "intervention": {
            "variable": str(hypothesis_intervention.get("variable") or ""),
            "column": intervention_column,
            "change_type": str(hypothesis_intervention.get("change_type") or "unknown"),
            "change_value": float(hypothesis_intervention.get("change_value") or 0.0),
            "unit": str(hypothesis_intervention.get("unit") or ""),
        },
        "entity_dimension": entity,
        "feature_columns": feature_columns[:12],
        "model_candidates": ["ridge_regression", "linear_regression", "rule_based_simulation"],
        "fallback_strategy": "Use rule-based simulation when sklearn is unavailable, sample size is too small, or required fields are missing.",
        "charts": ["change_summary_bar", "baseline_vs_predicted_scatter"],
        "limitations": limitations,
    }


def _normalize(
    result: Any,
    user_goal: str,
    dataset_profile: dict[str, Any],
    hypothesis_plan: dict[str, Any],
) -> dict[str, Any]:
    fallback = create_rule_based_prediction_plan(user_goal, dataset_profile, hypothesis_plan)
    if not isinstance(result, dict):
        return fallback
    columns = set(_columns(dataset_profile))
    intervention = result.get("intervention") if isinstance(result.get("intervention"), dict) else {}
    normalized = {
        **fallback,
        "prediction_goal": str(result.get("prediction_goal") or fallback["prediction_goal"]),
        "target_metric": _existing(result.get("target_metric"), columns) or fallback["target_metric"],
        "entity_dimension": _existing(result.get("entity_dimension"), columns) or fallback["entity_dimension"],
        "feature_columns": _filter_existing(result.get("feature_columns"), columns) or fallback["feature_columns"],
        "model_candidates": _strings(result.get("model_candidates")) or fallback["model_candidates"],
        "fallback_strategy": str(result.get("fallback_strategy") or fallback["fallback_strategy"]),
        "charts": _strings(result.get("charts")) or fallback["charts"],
        "limitations": _strings(result.get("limitations")) or fallback["limitations"],
    }
    normalized["feature_columns"] = [
        column
        for column in normalized["feature_columns"]
        if column != normalized["target_metric"] and not _is_identifier_column(column)
    ]
    normalized["intervention"] = {
        **fallback["intervention"],
        "variable": str(intervention.get("variable") or fallback["intervention"]["variable"]),
        "column": _existing(intervention.get("column"), columns) or fallback["intervention"]["column"],
        "change_type": str(intervention.get("change_type") or fallback["intervention"]["change_type"]),
        "change_value": _safe_float(intervention.get("change_value"), fallback["intervention"]["change_value"]),
        "unit": str(intervention.get("unit") or fallback["intervention"].get("unit") or ""),
    }
    normalized["task_type"] = "what_if_prediction"
    return normalized


def _choose_target(user_goal: str, numeric: list[str], columns: list[str]) -> str:
    for keyword in ("总价", "房价", "售价", "价格", "SalePrice", "saleprice"):
        if keyword.lower() in user_goal.lower():
            column = _choose_existing_by_alias(columns, ["SalePrice", "房价", "总价", "售价", "价格", "Price"], numeric_required=True, numeric_columns=numeric)
            if column:
                return column
    for keyword in ("销量", "销售量", "销售额", "不及格率", "及格率", "优秀率", "成绩", "分数"):
        if keyword in user_goal:
            for column in columns:
                if keyword in column or (keyword == "不及格率" and ("成绩" in column or "分数" in column)):
                    return column
    for column in numeric:
        if not _is_identifier_column(column):
            return column
    return numeric[0] if numeric else ""


def _mentions_area_change(user_goal: str) -> bool:
    lowered = user_goal.lower()
    return any(keyword in user_goal for keyword in ("面积", "平方米", "平米", "㎡")) or any(keyword in lowered for keyword in ("area", "m2", "m^2"))


def _choose_intervention(user_goal: str, numeric: list[str], columns: list[str], target: str) -> str:
    lowered = user_goal.lower()
    if any(keyword in user_goal for keyword in ("面积", "平方米", "平米", "㎡")) or any(keyword in lowered for keyword in ("area", "m2", "m^2")):
        column = _choose_existing_by_alias(
            columns,
            ["GrLivArea", "LivingArea", "TotalBsmtSF", "1stFlrSF", "2ndFlrSF", "LotArea", "GarageArea", "面积", "Area", "SF"],
            numeric_required=True,
            numeric_columns=numeric,
        )
        if column and column != target:
            return column
    for column in numeric:
        if column != target and not _is_identifier_column(column):
            return column
    return ""


def _choose_dimension(user_goal: str, dataset_profile: dict[str, Any], columns: list[str]) -> str:
    if any(keyword in user_goal for keyword in ("某套房", "房屋", "房子", "住宅", "房源")):
        column = _choose_existing_by_alias(columns, ["Id", "房屋编号", "编号", "house_id", "ID", "id"])
        if column:
            return column
    for keyword in ("商品", "产品", "SKU", "班级", "区域", "渠道", "品类"):
        if keyword in user_goal:
            for column in columns:
                if keyword.lower() in column.lower():
                    return column
    text_summary = dataset_profile.get("text_summary", {})
    if isinstance(text_summary, dict) and text_summary:
        return next(iter(text_summary.keys()), "")
    for column in columns:
        if _is_identifier_column(column):
            return column
    return ""


def _choose_existing_by_alias(
    columns: list[str],
    aliases: list[str],
    numeric_required: bool = False,
    numeric_columns: list[str] | None = None,
) -> str:
    numeric_set = set(numeric_columns or [])
    for alias in aliases:
        for column in columns:
            if alias.lower() == column.lower() and (not numeric_required or column in numeric_set):
                return column
    for alias in aliases:
        for column in columns:
            if alias.lower() in column.lower() and (not numeric_required or column in numeric_set):
                return column
    return ""


def _is_identifier_column(column: str) -> bool:
    text = str(column).strip().lower()
    return text in {"id", "编号", "序号", "房屋编号", "house_id", "row_id"} or text.endswith("_id")


def _columns(dataset_profile: dict[str, Any]) -> list[str]:
    return [str(column) for column in dataset_profile.get("columns", [])]


def _existing(value: Any, columns: set[str] | list[str]) -> str:
    value = str(value or "")
    return value if value in set(columns) else ""


def _filter_existing(value: Any, columns: set[str]) -> list[str]:
    return [str(item) for item in value if str(item) in columns] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if item is not None] if isinstance(value, list) else []


def _safe_float(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)
