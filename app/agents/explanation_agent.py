import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


RESULT_KEYS = [
    "summary",
    "key_findings",
    "chart_explanations",
    "recommendations",
    "limitations",
    "ppt_outline",
]


SYSTEM_PROMPT = """You are the Explanation Agent of an AI-native data analysis workbench.

Your job is to turn analysis results into concise business-facing explanations and a PPT outline.

Return only one valid JSON object. Do not output markdown, code fences, comments, or extra explanation.

The JSON object must contain exactly these keys:
{
  "summary": "...",
  "key_findings": [],
  "chart_explanations": [],
  "recommendations": [],
  "limitations": [],
  "ppt_outline": [
    {
      "title": "...",
      "bullets": [],
      "chart": "optional chart path"
    }
  ]
}

Rules:
- For sales decline analysis, use cautious wording such as "possible", "shows", "is related to", or "may be associated with". Do not claim confirmed causality.
- For grade analysis, emphasize class differences, pass rate, and excellent rate when those metrics are available.
- Every chart path must come from the provided chart_paths list, or be an empty string.
- Limitations must include any provided limitations and any constraints visible in the analysis result.
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """Create an explanation JSON for this analysis.

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Analysis result JSON:
{analysis_result}

Chart paths JSON:
{chart_paths}

Limitations JSON:
{limitations}

Retrieved business knowledge JSON:
{rag_context}

Return only the JSON object with the required schema.
The retrieved business knowledge can guide terminology and recommendations, but conclusions must stay grounded in analysis_result and chart_paths.
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        analysis_result=json.dumps(analysis_result, ensure_ascii=False, indent=2),
        chart_paths=json.dumps(chart_paths, ensure_ascii=False, indent=2),
        limitations=json.dumps(limitations, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
    )


class ExplanationAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def explain(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        analysis_result: dict[str, Any],
        chart_paths: list[str],
        limitations: list[str],
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
                            analysis_result=analysis_result,
                            chart_paths=chart_paths,
                            limitations=limitations,
                            rag_context=rag_context,
                        ),
                    },
                ],
                temperature=0.1,
            )
            return _normalize_result(
                result=result,
                user_goal=user_goal,
                analysis_result=analysis_result,
                chart_paths=chart_paths,
                limitations=limitations,
            )
        except Exception:
            return create_template_explanation(
                user_goal=user_goal,
                analysis_result=analysis_result,
                chart_paths=chart_paths,
                limitations=limitations,
            )


def create_explanation(
    user_goal: str,
    dataset_profile: dict[str, Any],
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return ExplanationAgent(llm_client=llm_client).explain(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        analysis_result=analysis_result,
        chart_paths=chart_paths,
        limitations=limitations,
        rag_context=rag_context,
    )


def create_template_explanation(
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    task_type = str(analysis_result.get("task_type") or "")
    if task_type == "grade_analysis" or _looks_like_grade_goal(user_goal):
        return _grade_template_explanation(
            user_goal=user_goal,
            analysis_result=analysis_result,
            chart_paths=chart_paths,
            limitations=limitations,
        )
    if _looks_like_sales_decline_goal(user_goal):
        return _sales_decline_template_explanation(
            user_goal=user_goal,
            analysis_result=analysis_result,
            chart_paths=chart_paths,
            limitations=limitations,
        )
    return _general_template_explanation(
        user_goal=user_goal,
        analysis_result=analysis_result,
        chart_paths=chart_paths,
        limitations=limitations,
    )


def _normalize_result(
    result: Any,
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Explanation result must be a JSON object.")

    fallback = create_template_explanation(
        user_goal=user_goal,
        analysis_result=analysis_result,
        chart_paths=chart_paths,
        limitations=limitations,
    )
    normalized = {
        "summary": str(result.get("summary") or fallback["summary"]),
        "key_findings": _string_list(result.get("key_findings"))
        or fallback["key_findings"],
        "chart_explanations": _normalize_chart_explanations(
            result.get("chart_explanations"), chart_paths
        )
        or fallback["chart_explanations"],
        "recommendations": _string_list(result.get("recommendations"))
        or fallback["recommendations"],
        "limitations": _string_list(result.get("limitations")) or list(limitations),
        "ppt_outline": _normalize_ppt_outline(result.get("ppt_outline"), chart_paths)
        or fallback["ppt_outline"],
    }

    for limitation in limitations:
        if limitation not in normalized["limitations"]:
            normalized["limitations"].append(limitation)

    if _looks_like_sales_decline_goal(user_goal):
        _ensure_cautious_sales_language(normalized)

    if _looks_like_grade_goal(user_goal) or analysis_result.get("task_type") == "grade_analysis":
        _ensure_grade_focus(normalized, analysis_result)

    return {key: normalized[key] for key in RESULT_KEYS}


def _grade_template_explanation(
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    summary_rows = analysis_result.get("summary") if isinstance(analysis_result, dict) else []
    summary_rows = summary_rows if isinstance(summary_rows, list) else []
    best_average = _best_row(summary_rows, "average_score")
    best_pass_rate = _best_row(summary_rows, "pass_rate")
    best_excellent_rate = _best_row(summary_rows, "excellent_rate")

    key_findings = [
        "The analysis compares class-level score differences using average score, pass rate, and excellent rate.",
    ]
    if best_average:
        key_findings.append(
            f"{best_average.get('class_name')} shows the highest average score at {best_average.get('average_score')}."
        )
    if best_pass_rate:
        key_findings.append(
            f"{best_pass_rate.get('class_name')} shows the strongest pass rate at {best_pass_rate.get('pass_rate')}."
        )
    if best_excellent_rate:
        key_findings.append(
            f"{best_excellent_rate.get('class_name')} shows the strongest excellent rate at {best_excellent_rate.get('excellent_rate')}."
        )

    return {
        "summary": "This grade analysis highlights class differences, pass rate, and excellent rate based on the generated statistics.",
        "key_findings": key_findings,
        "chart_explanations": _default_chart_explanations(chart_paths),
        "recommendations": [
            "Review classes with lower average scores and pass rates for targeted support.",
            "Compare teaching practices from classes with stronger excellent rates.",
            "Inspect missing or invalid score records before making final decisions.",
        ],
        "limitations": list(limitations),
        "ppt_outline": [
            {
                "title": "Analysis Goal",
                "bullets": [user_goal, "Focus on class differences, pass rate, and excellent rate."],
                "chart": "",
            },
            {
                "title": "Class Score Comparison",
                "bullets": key_findings[:3],
                "chart": chart_paths[0] if chart_paths else "",
            },
            {
                "title": "Recommendations",
                "bullets": [
                    "Prioritize support for weaker classes.",
                    "Use pass rate and excellent rate together with average score.",
                ],
                "chart": chart_paths[1] if len(chart_paths) > 1 else "",
            },
        ],
    }


def _sales_decline_template_explanation(
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    cautious_limitation = (
        "The results show associations and possible reasons only; they do not prove confirmed causality."
    )
    merged_limitations = list(limitations)
    if cautious_limitation not in merged_limitations:
        merged_limitations.append(cautious_limitation)

    return {
        "summary": "The analysis shows patterns that may be related to the sales decline and should be treated as possible reasons.",
        "key_findings": [
            "The available metrics show changes that may be associated with the decline.",
            "Segment and trend views can indicate possible areas for follow-up.",
        ],
        "chart_explanations": _default_chart_explanations(chart_paths),
        "recommendations": [
            "Validate possible reasons with additional business context.",
            "Compare affected segments against stable or growing segments.",
            "Avoid treating correlation as confirmed causality without further evidence.",
        ],
        "limitations": merged_limitations,
        "ppt_outline": [
            {
                "title": "Possible Sales Decline Signals",
                "bullets": [
                    "Patterns shown in the data may be related to the decline.",
                    "The result should be read as possible causes, not proven causality.",
                ],
                "chart": chart_paths[0] if chart_paths else "",
            },
            {
                "title": "Recommended Follow-up",
                "bullets": [
                    "Validate with campaign, pricing, inventory, and channel context.",
                    "Run segment-level checks before deciding interventions.",
                ],
                "chart": "",
            },
        ],
    }


def _general_template_explanation(
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "summary": "The analysis summarizes the available dataset according to the user goal.",
        "key_findings": [
            "The generated artifacts contain summary statistics and chart outputs.",
        ],
        "chart_explanations": _default_chart_explanations(chart_paths),
        "recommendations": [
            "Review the generated tables and charts before making business decisions.",
            "Refine the analysis goal if more specific comparisons are needed.",
        ],
        "limitations": list(limitations),
        "ppt_outline": [
            {
                "title": "Analysis Summary",
                "bullets": [user_goal, "Review generated result tables and charts."],
                "chart": chart_paths[0] if chart_paths else "",
            }
        ],
    }


def _normalize_chart_explanations(value: Any, chart_paths: list[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    allowed = set(chart_paths)
    explanations = []
    for item in value:
        if isinstance(item, dict):
            chart = str(item.get("chart") or item.get("path") or "")
            explanations.append(
                {
                    "chart": chart if chart in allowed else "",
                    "explanation": str(item.get("explanation") or item.get("text") or ""),
                }
            )
        else:
            explanations.append({"chart": "", "explanation": str(item)})
    return explanations


def _normalize_ppt_outline(value: Any, chart_paths: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    allowed = set(chart_paths)
    outline = []
    for item in value:
        if not isinstance(item, dict):
            continue
        chart = str(item.get("chart") or "")
        outline.append(
            {
                "title": str(item.get("title") or ""),
                "bullets": _string_list(item.get("bullets")),
                "chart": chart if chart in allowed else "",
            }
        )
    return outline


def _default_chart_explanations(chart_paths: list[str]) -> list[dict[str, str]]:
    return [
        {
            "chart": chart_path,
            "explanation": "This chart visualizes one of the key analysis views generated by the workflow.",
        }
        for chart_path in chart_paths
    ]


def _ensure_cautious_sales_language(result: dict[str, Any]) -> None:
    caution = (
        "Sales decline statements are phrased as possible, shown, or related patterns rather than confirmed causality."
    )
    if caution not in result["limitations"]:
        result["limitations"].append(caution)
    if "possible" not in result["summary"].lower() and "may" not in result["summary"].lower():
        result["summary"] = f"{result['summary']} These should be treated as possible related signals."


def _ensure_grade_focus(result: dict[str, Any], analysis_result: dict[str, Any]) -> None:
    focus = "Grade analysis should be interpreted through class differences, pass rate, and excellent rate."
    if focus not in result["key_findings"]:
        result["key_findings"].insert(0, focus)


def _best_row(rows: list[Any], metric: str) -> dict[str, Any] | None:
    candidates = [row for row in rows if isinstance(row, dict) and row.get(metric) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda row: float(row.get(metric) or 0))


def _looks_like_grade_goal(user_goal: str) -> bool:
    goal = user_goal.lower()
    return any(keyword in goal for keyword in ("grade", "score", "class", "成绩", "分数", "班级"))


def _looks_like_sales_decline_goal(user_goal: str) -> bool:
    goal = user_goal.lower()
    return any(
        keyword in goal
        for keyword in ("sales decline", "revenue decline", "gmv decline", "销量下降", "销售下降", "收入下降")
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
