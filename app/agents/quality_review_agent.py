import json
import re
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


RESULT_KEYS = [
    "passed",
    "risk_level",
    "issues",
    "checked_items",
    "revised_summary",
    "safe_language_suggestions",
    "missing_evidence",
]

SYSTEM_PROMPT = """You are the Quality Review / Rebuttal Agent of an AI-native data analysis workbench.

Your job is to challenge the generated conclusion before it reaches the user.
Return only one valid JSON object. All user-facing text must be Simplified Chinese.

Check:
- Whether conclusions are supported by analysis_result or prediction_result.
- Whether correlation is overstated as causation.
- Whether important fields or data quality issues were ignored.
- Whether chart choice and generated artifacts match the task.
- Whether sample size or uncertainty should be mentioned.

Required schema:
{
  "passed": true,
  "risk_level": "low|medium|high",
  "issues": [
    {"issue_type": "string", "severity": "low|medium|high", "finding": "问题", "evidence": "依据", "suggestion": "建议"}
  ],
  "checked_items": [
    {"name": "检查项", "status": "pass|warning|fail", "detail": "说明"}
  ],
  "revised_summary": "更稳健的结论摘要",
  "safe_language_suggestions": [],
  "missing_evidence": []
}
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    explanation: dict[str, Any],
    validation_result: dict[str, Any],
    chart_paths: list[str],
    workflow_type: str,
) -> str:
    return """Review this workflow result.

Workflow type:
{workflow_type}

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Analysis or prediction result JSON:
{result_payload}

Explanation JSON:
{explanation}

Validation result JSON:
{validation_result}

Chart paths JSON:
{chart_paths}

Return only the required JSON object.
""".format(
        workflow_type=workflow_type,
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        result_payload=json.dumps(result_payload, ensure_ascii=False, indent=2),
        explanation=json.dumps(explanation, ensure_ascii=False, indent=2),
        validation_result=json.dumps(validation_result, ensure_ascii=False, indent=2),
        chart_paths=json.dumps(chart_paths, ensure_ascii=False, indent=2),
    )


class QualityReviewAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def review(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        result_payload: dict[str, Any],
        explanation: dict[str, Any],
        validation_result: dict[str, Any],
        chart_paths: list[str],
        workflow_type: str = "auto_repair",
    ) -> dict[str, Any]:
        fallback = create_rule_based_quality_review(
            user_goal=user_goal,
            dataset_profile=dataset_profile,
            result_payload=result_payload,
            explanation=explanation,
            validation_result=validation_result,
            chart_paths=chart_paths,
            workflow_type=workflow_type,
        )
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            user_goal=user_goal,
                            dataset_profile=dataset_profile,
                            result_payload=result_payload,
                            explanation=explanation,
                            validation_result=validation_result,
                            chart_paths=chart_paths,
                            workflow_type=workflow_type,
                        ),
                    },
                ],
                temperature=0.1,
            )
            return _normalize_result(result, fallback)
        except Exception:
            return fallback


def create_quality_review(
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    explanation: dict[str, Any],
    validation_result: dict[str, Any],
    chart_paths: list[str],
    workflow_type: str = "auto_repair",
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return QualityReviewAgent(llm_client=llm_client).review(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        explanation=explanation,
        validation_result=validation_result,
        chart_paths=chart_paths,
        workflow_type=workflow_type,
    )


def create_rule_based_quality_review(
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    explanation: dict[str, Any],
    validation_result: dict[str, Any],
    chart_paths: list[str],
    workflow_type: str = "auto_repair",
) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    checked_items: list[dict[str, str]] = []
    summary = str(explanation.get("summary") or result_payload.get("summary") or result_payload.get("scenario_summary") or "")
    goal_text = str(user_goal or "")
    row_count = int(dataset_profile.get("row_count") or 0)

    validation_passed = bool(validation_result.get("passed", True))
    checked_items.append(
        {
            "name": "验证产物是否通过",
            "status": "pass" if validation_passed else "fail",
            "detail": "验证 Agent 已通过产物检查。" if validation_passed else "验证 Agent 报告产物仍存在问题。",
        }
    )
    if not validation_passed:
        issues.append(
            _issue(
                "validation_failed",
                "high",
                "验证 Agent 未通过最终产物检查。",
                "validation_result.passed=false",
                "优先查看 validation_result.json 中的问题并重新生成或修复结果。",
            )
        )

    if _contains_causal_overclaim(summary) and _needs_cautious_language(goal_text, workflow_type):
        issues.append(
            _issue(
                "correlation_as_causation",
                "high",
                "结论可能把相关性或预测关系写成确定因果。",
                "解释摘要中出现“导致、证明、必然、保证”等强因果词。",
                "改用“可能相关、显示出变化、历史数据下预计”等谨慎表述。",
            )
        )
        checked_items.append({"name": "因果表述", "status": "fail", "detail": "存在强因果或确定性表述。"})
    else:
        checked_items.append({"name": "因果表述", "status": "pass", "detail": "未发现明显因果过度表述。"})

    if row_count and row_count < 20:
        issues.append(
            _issue(
                "small_sample_size",
                "medium",
                f"样本量为 {row_count} 行，结论稳定性有限。",
                "dataset_profile.row_count",
                "在限制说明中补充样本量较小，建议扩大样本后复核。",
            )
        )
        checked_items.append({"name": "样本量", "status": "warning", "detail": f"当前样本量 {row_count} 行。"})
    else:
        checked_items.append({"name": "样本量", "status": "pass", "detail": "样本量未触发小样本警告。"})

    missing_fields = _missing_fields(dataset_profile)
    high_missing = [item for item in missing_fields if float(item.get("ratio") or 0.0) >= 0.2]
    if high_missing:
        issues.append(
            _issue(
                "high_missing_rate",
                "medium",
                "部分字段缺失率较高，可能影响结论可靠性。",
                "、".join(f"{item['column']}({float(item['ratio']):.0%})" for item in high_missing[:5]),
                "在报告限制中说明缺失字段，不要把缺失值直接解释为业务事实。",
            )
        )
        checked_items.append({"name": "数据质量", "status": "warning", "detail": "存在高缺失率字段。"})
    else:
        checked_items.append({"name": "数据质量", "status": "pass", "detail": "未发现高缺失率字段。"})

    if not chart_paths and result_payload.get("status") != "unsupported":
        issues.append(
            _issue(
                "missing_chart_artifact",
                "low",
                "未发现图表产物，演示和复核可读性较弱。",
                "chart_paths 为空。",
                "如果任务适合可视化，建议生成趋势、分组对比或分布图。",
            )
        )
        checked_items.append({"name": "图表产物", "status": "warning", "detail": "未发现可展示图表。"})
    else:
        checked_items.append({"name": "图表产物", "status": "pass", "detail": "已生成或无需生成图表。"})

    revised_summary = _make_cautious_summary(summary, workflow_type, goal_text)
    if not revised_summary:
        revised_summary = "当前结果已通过基础质检，建议结合图表、数据质量说明和业务背景谨慎解读。"

    risk_level = _risk_level(issues)
    return {
        "passed": risk_level != "high",
        "risk_level": risk_level,
        "issues": issues,
        "checked_items": checked_items,
        "revised_summary": revised_summary,
        "safe_language_suggestions": _safe_language_suggestions(workflow_type, goal_text),
        "missing_evidence": _missing_evidence_suggestions(issues),
    }


def _normalize_result(result: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return fallback
    issues = _normalize_issues(result.get("issues"))
    checked_items = _normalize_checked_items(result.get("checked_items")) or fallback["checked_items"]
    risk_level = str(result.get("risk_level") or fallback["risk_level"])
    if risk_level not in {"low", "medium", "high"}:
        risk_level = fallback["risk_level"]
    normalized = {
        "passed": bool(result.get("passed")) if result.get("passed") is not None else fallback["passed"],
        "risk_level": risk_level,
        "issues": issues,
        "checked_items": checked_items,
        "revised_summary": str(result.get("revised_summary") or fallback["revised_summary"]),
        "safe_language_suggestions": _string_list(result.get("safe_language_suggestions")) or fallback["safe_language_suggestions"],
        "missing_evidence": _string_list(result.get("missing_evidence")) or fallback["missing_evidence"],
    }
    if normalized["risk_level"] == "high":
        normalized["passed"] = False
    return {key: normalized[key] for key in RESULT_KEYS}


def _normalize_issues(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        severity = str(item.get("severity") or "low")
        if severity not in {"low", "medium", "high"}:
            severity = "low"
        result.append(
            {
                "issue_type": str(item.get("issue_type") or "quality_issue"),
                "severity": severity,
                "finding": str(item.get("finding") or ""),
                "evidence": str(item.get("evidence") or ""),
                "suggestion": str(item.get("suggestion") or ""),
            }
        )
    return result


def _normalize_checked_items(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "warning")
        if status not in {"pass", "warning", "fail"}:
            status = "warning"
        result.append({"name": str(item.get("name") or "检查项"), "status": status, "detail": str(item.get("detail") or "")})
    return result


def _issue(issue_type: str, severity: str, finding: str, evidence: str, suggestion: str) -> dict[str, str]:
    return {"issue_type": issue_type, "severity": severity, "finding": finding, "evidence": evidence, "suggestion": suggestion}


def _contains_causal_overclaim(text: str) -> bool:
    patterns = [r"导致", r"证明", r"必然", r"保证", r"确定", r"caused", r"prove", r"guarantee"]
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _needs_cautious_language(goal_text: str, workflow_type: str) -> bool:
    lowered = goal_text.lower()
    return workflow_type == "what_if_prediction" or any(token in lowered for token in ("下降", "原因", "影响", "预测", "if", "what"))


def _make_cautious_summary(summary: str, workflow_type: str, goal_text: str) -> str:
    text = str(summary or "").strip()
    if not text:
        return ""
    replacements = [
        ("导致", "可能与其变化有关"),
        ("证明", "显示出相关迹象"),
        ("必然", "可能"),
        ("保证", "预计"),
        ("确定", "当前数据下较可能"),
    ]
    for source, target in replacements:
        text = text.replace(source, target)
    if _needs_cautious_language(goal_text, workflow_type) and not any(token in text for token in ("可能", "预计", "显示", "建议", "不代表确定因果")):
        text = f"当前数据支持以下探索性判断：{text}。该结论不代表确定因果。"
    return text


def _safe_language_suggestions(workflow_type: str, goal_text: str) -> list[str]:
    suggestions = ["使用“可能、显示出、预计、建议复核”等谨慎表述。"]
    if _needs_cautious_language(goal_text, workflow_type):
        suggestions.append("避免使用“导致、证明、必然、保证”等强因果或确定性词语。")
    if workflow_type == "what_if_prediction":
        suggestions.append("说明预测基于历史数据和当前特征，不代表未来必然发生。")
    return suggestions


def _missing_evidence_suggestions(issues: list[dict[str, str]]) -> list[str]:
    result = []
    for issue in issues:
        if issue["issue_type"] == "missing_chart_artifact":
            result.append("需要补充至少一个趋势、分组对比或预测变化图表。")
        if issue["issue_type"] == "correlation_as_causation":
            result.append("需要用实验设计、外部业务证据或更严格模型支撑因果判断。")
    return result


def _risk_level(issues: list[dict[str, str]]) -> str:
    severities = {issue.get("severity") for issue in issues}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    return "low"


def _missing_fields(dataset_profile: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    missing_values = dataset_profile.get("missing_values") if isinstance(dataset_profile.get("missing_values"), dict) else {}
    for column, summary in missing_values.items():
        if not isinstance(summary, dict):
            continue
        count = int(summary.get("count") or 0)
        if count > 0:
            result.append({"column": str(column), "count": count, "ratio": float(summary.get("ratio") or 0.0)})
    return result


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
