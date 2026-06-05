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
All user-facing text must be Simplified Chinese.

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
- For sales decline analysis, use cautious Chinese wording such as “可能”“相关”“显示出信号”“需要进一步验证”. Do not claim confirmed causality.
- For grade analysis, emphasize class differences, pass rate, and excellent rate when those metrics are available.
- Every chart path must come from the provided chart_paths list, or be an empty string.
- Limitations must include any provided limitations and any constraints visible in the analysis result.
- If Debate Matrix context is provided, prefer its consensus_findings and statistical_guardrails when drafting final wording.
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
    rag_context: list[dict[str, Any]] | None = None,
    debate_context: dict[str, Any] | None = None,
) -> str:
    return """请为本次分析生成中文解释 JSON。

用户目标：
{user_goal}

数据画像 JSON：
{dataset_profile}

分析结果 JSON：
{analysis_result}

图表路径 JSON：
{chart_paths}

限制说明 JSON：
{limitations}

检索到的业务知识 JSON：
{rag_context}

Debate Matrix 动态辩论共识 JSON：
{debate_context}

请只返回符合 schema 的 JSON 对象。业务知识可用于术语和建议；Debate Matrix 可用于最终措辞、风险边界和优先建议；结论必须基于 analysis_result、chart_paths 和辩论共识。所有面向用户的文本必须使用中文。
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        analysis_result=json.dumps(analysis_result, ensure_ascii=False, indent=2),
        chart_paths=json.dumps(chart_paths, ensure_ascii=False, indent=2),
        limitations=json.dumps(limitations, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
        debate_context=json.dumps(debate_context or {}, ensure_ascii=False, indent=2),
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
        debate_context: dict[str, Any] | None = None,
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
                            debate_context=debate_context,
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
                debate_context=debate_context,
            )
        except Exception:
            return create_template_explanation(
                user_goal=user_goal,
                analysis_result=analysis_result,
                chart_paths=chart_paths,
                limitations=limitations,
                debate_context=debate_context,
            )


def create_explanation(
    user_goal: str,
    dataset_profile: dict[str, Any],
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
    rag_context: list[dict[str, Any]] | None = None,
    debate_context: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return ExplanationAgent(llm_client=llm_client).explain(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        analysis_result=analysis_result,
        chart_paths=chart_paths,
        limitations=limitations,
        rag_context=rag_context,
        debate_context=debate_context,
    )


def create_template_explanation(
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
    debate_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task_type = str(analysis_result.get("task_type") or "")
    result = None
    if task_type == "grade_analysis" or _looks_like_grade_goal(user_goal):
        result = _grade_template_explanation(user_goal, analysis_result, chart_paths, limitations)
    elif _looks_like_sales_decline_goal(user_goal):
        result = _sales_decline_template_explanation(user_goal, analysis_result, chart_paths, limitations)
    else:
        result = _general_template_explanation(user_goal, analysis_result, chart_paths, limitations)
    return _merge_debate_context(result, debate_context)


def _normalize_result(
    result: Any,
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
    debate_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Explanation result must be a JSON object.")

    fallback = create_template_explanation(
        user_goal=user_goal,
        analysis_result=analysis_result,
        chart_paths=chart_paths,
        limitations=limitations,
        debate_context=debate_context,
    )
    normalized = {
        "summary": _localize_text(str(result.get("summary") or fallback["summary"])),
        "key_findings": _string_list(result.get("key_findings")) or fallback["key_findings"],
        "chart_explanations": _normalize_chart_explanations(result.get("chart_explanations"), chart_paths) or fallback["chart_explanations"],
        "recommendations": _string_list(result.get("recommendations")) or fallback["recommendations"],
        "limitations": _string_list(result.get("limitations")) or _string_list(limitations),
        "ppt_outline": _normalize_ppt_outline(result.get("ppt_outline"), chart_paths) or fallback["ppt_outline"],
    }

    for limitation in _string_list(limitations):
        if limitation not in normalized["limitations"]:
            normalized["limitations"].append(limitation)

    if _looks_like_sales_decline_goal(user_goal):
        _ensure_cautious_sales_language(normalized)

    if _looks_like_grade_goal(user_goal) or analysis_result.get("task_type") == "grade_analysis":
        _ensure_grade_focus(normalized)

    normalized = _merge_debate_context(normalized, debate_context)
    return {key: normalized[key] for key in RESULT_KEYS}


def _merge_debate_context(explanation: dict[str, Any], debate_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(debate_context, dict) or not debate_context:
        return explanation
    merged = {**explanation}
    findings = _string_list(debate_context.get("consensus_findings"))
    recommendations = _string_list(debate_context.get("consensus_recommendations"))
    guardrails = _string_list(debate_context.get("statistical_guardrails"))
    final_consensus = str(debate_context.get("final_consensus") or "").strip()
    if final_consensus and final_consensus not in str(merged.get("summary") or ""):
        merged["summary"] = f"{merged.get('summary') or ''} {final_consensus}".strip()
    existing_findings = _string_list(merged.get("key_findings"))
    for item in findings:
        if item not in existing_findings:
            existing_findings.append(item)
    merged["key_findings"] = existing_findings[:8]
    existing_recommendations = _string_list(merged.get("recommendations"))
    for item in recommendations:
        if item not in existing_recommendations:
            existing_recommendations.append(item)
    merged["recommendations"] = existing_recommendations[:8]
    existing_limitations = _string_list(merged.get("limitations"))
    for item in guardrails:
        if item not in existing_limitations:
            existing_limitations.append(item)
    merged["limitations"] = existing_limitations[:8]
    return merged


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

    key_findings = ["本次成绩分析围绕班级差异、平均分、及格率和优秀率进行比较。"]
    if best_average:
        key_findings.append(f"{best_average.get('class_name')}的平均分最高，为 {best_average.get('average_score')}。")
    if best_pass_rate:
        key_findings.append(f"{best_pass_rate.get('class_name')}的及格率表现最好，为 {best_pass_rate.get('pass_rate')}。")
    if best_excellent_rate:
        key_findings.append(f"{best_excellent_rate.get('class_name')}的优秀率表现最好，为 {best_excellent_rate.get('excellent_rate')}。")

    return {
        "summary": "本次成绩分析基于已生成的统计结果，重点呈现各班级在平均分、及格率和优秀率上的差异。",
        "key_findings": key_findings,
        "chart_explanations": _default_chart_explanations(chart_paths),
        "recommendations": [
            "对平均分或及格率较低的班级开展针对性辅导。",
            "结合优秀率较高班级的教学做法，复盘可复制经验。",
            "在形成最终判断前，先核对缺失、异常或非数值成绩记录。",
        ],
        "limitations": _string_list(limitations),
        "ppt_outline": [
            {"title": "分析目标", "bullets": [user_goal, "重点关注班级差异、及格率和优秀率。"], "chart": ""},
            {"title": "班级成绩对比", "bullets": key_findings[:3], "chart": chart_paths[0] if chart_paths else ""},
            {"title": "建议动作", "bullets": ["优先支持薄弱班级。", "将平均分、及格率和优秀率结合解读。"], "chart": chart_paths[1] if len(chart_paths) > 1 else ""},
        ],
    }


def _sales_decline_template_explanation(
    user_goal: str,
    analysis_result: dict[str, Any],
    chart_paths: list[str],
    limitations: list[str],
) -> dict[str, Any]:
    cautious_limitation = "当前结果只能说明相关信号和可能原因，不能证明确定因果关系。"
    merged_limitations = _string_list(limitations)
    if cautious_limitation not in merged_limitations:
        merged_limitations.append(cautious_limitation)

    return {
        "summary": "本次分析识别出若干可能与销量下降相关的趋势和分组信号，建议将这些结果作为后续排查线索，而不是确定因果结论。",
        "key_findings": [
            "可用指标显示出与销量下降相关的变化信号。",
            "按时间、地区、渠道或商品类别的拆解结果可帮助定位优先排查方向。",
        ],
        "chart_explanations": _default_chart_explanations(chart_paths),
        "recommendations": [
            "结合促销、价格、库存、渠道运营等外部信息复核可能原因。",
            "将下降明显的分组与稳定或回升分组对比，寻找可验证差异。",
            "避免把相关性直接写成确定因果，必要时补充更长时间序列或实验数据。",
        ],
        "limitations": merged_limitations,
        "ppt_outline": [
            {
                "title": "销量下降相关信号",
                "bullets": ["数据中显示出可能相关的下降信号。", "结论应理解为待验证假设，而不是已证明原因。"],
                "chart": chart_paths[0] if chart_paths else "",
            },
            {
                "title": "建议排查方向",
                "bullets": ["结合活动、价格、库存和渠道上下文验证。", "先从下降幅度最大的分组开展复盘。"],
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
        "summary": "系统已根据分析目标汇总当前数据，并生成可用于解读的统计结果和图表。",
        "key_findings": ["已生成的产物包含关键统计结果、数据表和图表视图。"],
        "chart_explanations": _default_chart_explanations(chart_paths),
        "recommendations": [
            "在做业务决策前，结合原始数据和业务背景复核关键结论。",
            "如果需要更细的分组、时间范围或指标口径，可以继续细化分析目标。",
        ],
        "limitations": _string_list(limitations),
        "ppt_outline": [
            {"title": "分析摘要", "bullets": [user_goal, "查看生成的统计表和图表。"], "chart": chart_paths[0] if chart_paths else ""}
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
                    "explanation": _localize_text(str(item.get("explanation") or item.get("text") or "")),
                }
            )
        else:
            explanations.append({"chart": "", "explanation": _localize_text(str(item))})
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
                "title": _localize_text(str(item.get("title") or "")),
                "bullets": _string_list(item.get("bullets")),
                "chart": chart if chart in allowed else "",
            }
        )
    return outline


def _default_chart_explanations(chart_paths: list[str]) -> list[dict[str, str]]:
    return [
        {
            "chart": chart_path,
            "explanation": "该图展示了本次工作流生成的一个关键分析视图，可用于辅助理解趋势、对比或分布差异。",
        }
        for chart_path in chart_paths
    ]


def _ensure_cautious_sales_language(result: dict[str, Any]) -> None:
    caution = "销量下降相关结论均以可能、相关或信号形式表述，不代表已证明的确定因果。"
    if caution not in result["limitations"]:
        result["limitations"].append(caution)
    cautious_words = ("可能", "相关", "信号", "估计", "显示", "待验证")
    if not any(word in result["summary"] for word in cautious_words):
        result["summary"] = f"{result['summary']} 这些发现应作为可能相关信号，并结合更多业务证据验证。"


def _ensure_grade_focus(result: dict[str, Any]) -> None:
    focus = "成绩分析应结合班级差异、及格率和优秀率共同解读。"
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
    return any(keyword in goal for keyword in ("sales decline", "revenue decline", "gmv decline", "销量下降", "销售下降", "收入下降", "下降原因"))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_localize_text(str(item)) for item in value if item is not None and str(item).strip()]


def _localize_text(value: str) -> str:
    text = str(value or "").strip()
    translations = {
        "The analysis compares class-level score differences using average score, pass rate, and excellent rate.": "本次分析使用平均分、及格率和优秀率比较班级层面的成绩差异。",
        "This grade analysis highlights class differences, pass rate, and excellent rate based on the generated statistics.": "本次成绩分析基于已生成统计结果，重点呈现班级差异、及格率和优秀率。",
        "Review classes with lower average scores and pass rates for targeted support.": "对平均分或及格率较低的班级开展针对性支持。",
        "Compare teaching practices from classes with stronger excellent rates.": "复盘优秀率较高班级的教学做法。",
        "Inspect missing or invalid score records before making final decisions.": "形成最终判断前先核对缺失或异常成绩记录。",
        "The results show associations and possible reasons only; they do not prove confirmed causality.": "结果只能说明相关信号和可能原因，不能证明确定因果关系。",
        "The analysis shows patterns that may be related to the sales decline and should be treated as possible reasons.": "分析显示若干可能与销量下降相关的模式，应作为可能原因线索。",
        "The available metrics show changes that may be associated with the decline.": "可用指标显示出可能与下降相关的变化。",
        "Segment and trend views can indicate possible areas for follow-up.": "分组和趋势视图可指示后续排查方向。",
        "Validate possible reasons with additional business context.": "结合更多业务上下文验证可能原因。",
        "Compare affected segments against stable or growing segments.": "将受影响分组与稳定或增长分组进行对比。",
        "Avoid treating correlation as confirmed causality without further evidence.": "没有进一步证据时，不要把相关性当作确定因果。",
        "The analysis summarizes the available dataset according to the user goal.": "系统已根据用户目标汇总当前数据。",
        "The generated artifacts contain summary statistics and chart outputs.": "已生成的产物包含统计结果和图表输出。",
        "Review the generated tables and charts before making business decisions.": "做业务决策前请先复核生成的数据表和图表。",
        "Refine the analysis goal if more specific comparisons are needed.": "如需更具体的对比，请进一步细化分析目标。",
        "This chart visualizes one of the key analysis views generated by the workflow.": "该图展示了本次工作流生成的关键分析视图。",
        "Sales decline statements are phrased as possible, shown, or related patterns rather than confirmed causality.": "销量下降相关结论均以可能、显示或相关模式表述，不代表确定因果。",
        "These should be treated as possible related signals.": "这些发现应作为可能相关信号。",
        "Grade analysis should be interpreted through class differences, pass rate, and excellent rate.": "成绩分析应结合班级差异、及格率和优秀率共同解读。",
        "Analysis Goal": "分析目标",
        "Class Score Comparison": "班级成绩对比",
        "Recommendations": "建议动作",
        "Possible Sales Decline Signals": "销量下降相关信号",
        "Recommended Follow-up": "建议排查方向",
        "Analysis Summary": "分析摘要",
    }
    return translations.get(text, text)

