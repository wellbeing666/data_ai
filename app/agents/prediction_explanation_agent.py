import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the Prediction Explanation Agent.

Explain what-if prediction results in cautious business language.
Return only one valid JSON object. Do not output markdown.
Never claim certain causality. Use words like "可能", "显示", "估计", "需要进一步验证".

Required schema:
{
  "summary": "...",
  "key_findings": [],
  "top_impacted_entities": [],
  "recommendations": [],
  "limitations": [],
  "ppt_outline": []
}
"""


def build_user_prompt(
    user_goal: str,
    prediction_result: dict[str, Any],
    chart_paths: list[str],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """Create a cautious explanation for this what-if prediction.

User goal:
{user_goal}

Prediction result JSON:
{prediction_result}

Chart paths JSON:
{chart_paths}

Retrieved business knowledge JSON:
{rag_context}
""".format(
        user_goal=user_goal,
        prediction_result=json.dumps(prediction_result, ensure_ascii=False, indent=2),
        chart_paths=json.dumps(chart_paths, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
    )


class PredictionExplanationAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def explain(
        self,
        user_goal: str,
        prediction_result: dict[str, Any],
        chart_paths: list[str],
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
                            prediction_result=prediction_result,
                            chart_paths=chart_paths,
                            rag_context=rag_context,
                        ),
                    },
                ],
                temperature=0.1,
            )
            return _normalize(result, prediction_result)
        except Exception:
            return create_template_prediction_explanation(user_goal, prediction_result, chart_paths)


def create_prediction_explanation(
    user_goal: str,
    prediction_result: dict[str, Any],
    chart_paths: list[str],
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return PredictionExplanationAgent(llm_client=llm_client).explain(
        user_goal=user_goal,
        prediction_result=prediction_result,
        chart_paths=chart_paths,
        rag_context=rag_context,
    )


def create_template_prediction_explanation(
    user_goal: str,
    prediction_result: dict[str, Any],
    chart_paths: list[str],
) -> dict[str, Any]:
    top_entities = prediction_result.get("top_impacted_entities")
    top_entities = top_entities if isinstance(top_entities, list) else []
    target = prediction_result.get("target_metric") or "目标指标"
    summary = (
        f"在“{user_goal}”这一假设下，系统基于当前数据估计 {target} 可能出现变化。"
        "该结果是模拟预测，不代表确定因果。"
    )
    findings = []
    for item in top_entities[:5]:
        if isinstance(item, dict):
            findings.append(
                f"{item.get('entity', '对象')} 预测变化约为 {item.get('absolute_change', '-')}"
                f"（{item.get('direction', 'unknown')}）。"
            )
    if not findings:
        findings.append("当前数据可用于生成整体层面的情景模拟，但对象级排序信息有限。")
    limitations = prediction_result.get("limitations")
    limitations = limitations if isinstance(limitations, list) else []
    return {
        "summary": summary,
        "key_findings": findings,
        "top_impacted_entities": top_entities[:10],
        "recommendations": [
            "优先复盘预测变化较大的对象，并结合业务背景进行验证。",
            "将该预测作为情景参考，不应直接视为确定因果结论。",
        ],
        "limitations": limitations,
        "ppt_outline": [
            {"title": "情景假设", "bullets": [str(prediction_result.get("scenario_summary", user_goal))], "chart": ""},
            {"title": "预测变化 Top 对象", "bullets": findings[:3], "chart": chart_paths[0] if chart_paths else ""},
            {"title": "模型与限制", "bullets": limitations[:4], "chart": ""},
        ],
    }


def _normalize(result: Any, prediction_result: dict[str, Any]) -> dict[str, Any]:
    fallback = create_template_prediction_explanation("", prediction_result, prediction_result.get("charts") or [])
    if not isinstance(result, dict):
        return fallback
    return {
        "summary": str(result.get("summary") or fallback["summary"]),
        "key_findings": _strings(result.get("key_findings")) or fallback["key_findings"],
        "top_impacted_entities": result.get("top_impacted_entities") if isinstance(result.get("top_impacted_entities"), list) else fallback["top_impacted_entities"],
        "recommendations": _strings(result.get("recommendations")) or fallback["recommendations"],
        "limitations": _strings(result.get("limitations")) or fallback["limitations"],
        "ppt_outline": result.get("ppt_outline") if isinstance(result.get("ppt_outline"), list) else fallback["ppt_outline"],
    }


def _strings(value: Any) -> list[str]:
    return [str(item) for item in value if item is not None] if isinstance(value, list) else []
