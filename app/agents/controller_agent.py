import json
from typing import Any

from app.agents.master_agent import create_rule_based_analysis_plan
from app.services.llm_client import LLMClient, get_llm_client


ALLOWED_TASK_TYPES = {
    "grade_analysis",
    "sales_decline_analysis",
    "general_data_analysis",
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
- Choose general_data_analysis when the goal does not clearly match the two specialized task types.
- Use only columns that appear in the dataset profile when filling required_columns and charts.
- Keep reasoning_summary concise and factual.
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """Create a controller analysis plan for this request.

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Retrieved business knowledge JSON:
{rag_context}

Return only the JSON object with the required schema.
The retrieved business knowledge is background only. It must not override dataset_profile and must not introduce columns that do not exist in dataset_profile.columns.
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
            return _normalize_plan(plan)
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


def _normalize_plan(plan: Any) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise ValueError("Controller plan must be a JSON object.")

    normalized: dict[str, Any] = {
        "task_type": str(plan.get("task_type") or "general_data_analysis"),
        "task_name": str(plan.get("task_name") or "General data analysis"),
        "reasoning_summary": str(plan.get("reasoning_summary") or ""),
        "steps": [],
        "required_columns": [],
        "analysis_methods": [],
        "charts": [],
        "expected_artifacts": [],
        "risks": [],
    }

    if normalized["task_type"] not in ALLOWED_TASK_TYPES:
        normalized["task_type"] = "general_data_analysis"

    for key in LIST_KEYS:
        value = plan.get(key)
        normalized[key] = value if isinstance(value, list) else []

    return {key: normalized[key] for key in PLAN_KEYS}
