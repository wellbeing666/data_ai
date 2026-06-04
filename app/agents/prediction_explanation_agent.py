import json
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the Prediction Explanation Agent.

Explain what-if prediction results in cautious business language.
Return only one valid JSON object. Do not output markdown.
Never claim certain causality. Use words like "可能", "显示", "估计", "需要进一步验证".
All user-facing text must be Simplified Chinese. Translate any English limitations, model descriptions, and method explanations into Chinese before returning JSON.

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
    return """请用中文为以下情景预测结果生成谨慎解释。

User goal:
{user_goal}

Prediction result JSON:
{prediction_result}

Chart paths JSON:
{chart_paths}

Retrieved business knowledge JSON:
{rag_context}

输出 JSON 中 summary、key_findings、recommendations、limitations、ppt_outline 的 title 与 bullets 必须使用中文，不要夹杂英文说明。
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
        if prediction_result.get("status") == "unsupported":
            return create_template_prediction_explanation(user_goal, prediction_result, chart_paths)

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
    if prediction_result.get("status") == "unsupported":
        reason = _localize_text(str(prediction_result.get("unsupported_reason") or "当前数据缺少完成该情景预测所需的字段。"))
        limitations = prediction_result.get("limitations")
        limitations = _strings(limitations) if isinstance(limitations, list) else [reason]
        no_chart_reason = _localize_text(str(prediction_result.get("no_chart_reason") or prediction_result.get("chart_notice") or "当前缺少可计算的预测数值，因此图表模块无需生成图表。"))
        findings = [reason, "系统已停止情景模拟，避免把其他字段的模型结果解释为用户指定变量的影响。"]
        return {
            "summary": reason,
            "key_findings": findings,
            "top_impacted_entities": [],
            "recommendations": [
                "补充与情景变量对应的字段后重新运行预测。",
                "补充字段时应确认单位、时间口径和对象粒度与目标指标一致。",
            ],
            "limitations": [_localize_text(item) for item in limitations],
            "ppt_outline": [
                {"title": "情景预测无法计算", "bullets": [reason, no_chart_reason], "chart": chart_paths[0] if chart_paths else ""},
                {"title": "所需数据", "bullets": ["需要上传包含情景变量的字段，再进行模型模拟。"], "chart": ""},
            ],
        }

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
    limitations = _strings(limitations) if isinstance(limitations, list) else []
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
            {"title": "情景假设", "bullets": [_localize_text(str(prediction_result.get("scenario_summary", user_goal)))], "chart": ""},
            {"title": "预测变化 Top 对象", "bullets": findings[:3], "chart": chart_paths[0] if chart_paths else ""},
            {"title": "模型与限制", "bullets": limitations[:4], "chart": ""},
        ],
    }


def _normalize(result: Any, prediction_result: dict[str, Any]) -> dict[str, Any]:
    fallback = create_template_prediction_explanation("", prediction_result, prediction_result.get("charts") or [])
    if not isinstance(result, dict):
        return fallback
    return {
        "summary": _localize_text(str(result.get("summary") or fallback["summary"])),
        "key_findings": _strings(result.get("key_findings")) or fallback["key_findings"],
        "top_impacted_entities": result.get("top_impacted_entities") if isinstance(result.get("top_impacted_entities"), list) else fallback["top_impacted_entities"],
        "recommendations": _strings(result.get("recommendations")) or fallback["recommendations"],
        "limitations": _strings(result.get("limitations")) or fallback["limitations"],
        "ppt_outline": _normalize_ppt_outline(result.get("ppt_outline"), fallback["ppt_outline"]),
    }


def _normalize_ppt_outline(value: Any, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return fallback
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        bullets = _strings(item.get("bullets"))
        if not bullets:
            text = item.get("content") or item.get("description") or item.get("text")
            bullets = [_localize_text(str(text))] if text else []
        normalized.append(
            {
                "title": _localize_text(str(item.get("title") or f"第 {index + 1} 页")),
                "bullets": bullets,
                "chart": str(item.get("chart") or ""),
            }
        )
    return normalized or fallback


def _strings(value: Any) -> list[str]:
    return [_localize_text(str(item)) for item in value if item is not None] if isinstance(value, list) else []


def _localize_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    compact = " ".join(text.split())
    exact_replacements = {
        "No column representing floor level(楼层) exists in the dataset. Thus, the direct what-if intervention of changing floor from low to mid-high cannot be modeled. Predictions will be based on available features without this intervention.": "当前数据集中没有表示房源所在楼层高低的字段，因此无法直接模拟“从低层调整为中高层”这一情景。系统不会用其他不等价字段替代该变量。",
        "No numeric target metric was identified; prediction cannot be computed from the uploaded data.": "未识别到可用于预测的数值型目标指标，无法基于当前上传数据计算预测。",
        "No entity dimension was identified; only aggregate output can be shown when prediction is supported.": "未识别到对象维度；如果其他字段满足预测条件，只能展示总体汇总结果。",
    }
    if compact in exact_replacements:
        return exact_replacements[compact]
    replacements = [
        ("No column representing floor level", "当前数据集中没有表示楼层高低的字段"),
        ("the direct what-if intervention", "直接情景干预"),
        ("cannot be modeled", "无法建模"),
        ("Predictions will be based on available features without this intervention", "系统不会基于该缺失情景变量输出预测数值"),
        ("unsupported_missing_required_column", "缺少情景变量字段"),
        ("linear_regression", "线性回归"),
        ("ridge_regression", "岭回归"),
        ("rule_based_simulation", "规则化模拟"),
        ("random_forest", "随机森林"),
        ("What-if", "情景预测"),
    ]
    for source, target in replacements:
        text = text.replace(source, target)
    return text
