from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.services.llm_client import get_llm_client


DEBATE_SYSTEM_PROMPT = """你是 AI 原生数据分析工作台的 Debate Matrix 编排器。
你需要在内部模拟两个 Agent 的 2~3 轮辩论：
A：激进的商业洞察 Agent。尽量从图表 JSON、分析结果和数据摘要中提炼最有冲击力的商业结论、策略机会和风险预警。
B：严谨的统计质检 Agent。强力挑刺，指出样本量、分组偏差、相关不等于因果、时间跨度、缺失值和统计不确定性。
最后输出双方共识：既要有商业深度，也必须保留统计边界。

要求：
1. 不要要求重跑代码，除非产物明显缺失；重点做结论文案层面的辩论、收敛和修饰。
2. 对销售下降、影响因素、策略建议等，只能写“可能原因、相关信号、待验证线索”，不能写成确定因果。
3. 返回合法 JSON 对象，不要输出 Markdown 代码块。
4. debate_rounds 需要包含 A 和 B 的简短发言；final_consensus 需要可直接交给解释 Agent 使用。

返回格式：
{
  "debate_rounds": [
    {"round": 1, "aggressive_business_agent": "...", "statistical_qc_agent": "..."}
  ],
  "consensus_findings": ["..."],
  "consensus_recommendations": ["..."],
  "statistical_guardrails": ["..."],
  "phrasing_revisions": [{"risky_claim": "...", "safer_claim": "..."}],
  "final_consensus": "..."
}
"""


def create_debate_reflection(
    *,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    report_data: dict[str, Any] | None = None,
    chart_paths: list[str] | None = None,
    validation_result: dict[str, Any] | None = None,
    limitations: list[str] | None = None,
    workflow_type: str = "auto_repair",
    max_rounds: int = 3,
) -> dict[str, Any]:
    payload = {
        "user_goal": user_goal,
        "workflow_type": workflow_type,
        "dataset_profile": _compact(dataset_profile),
        "result_payload": _compact(result_payload),
        "report_data": _compact(report_data or {}),
        "chart_paths": chart_paths or [],
        "validation_result": _compact(validation_result or {}),
        "existing_limitations": limitations or [],
        "requested_rounds": max(2, min(max_rounds, 3)),
    }
    fallback = _fallback_debate(payload)
    try:
        result = get_llm_client().chat_json(
            messages=[
                {"role": "system", "content": DEBATE_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
            temperature=0.2,
        )
    except Exception:
        return fallback
    if not isinstance(result, dict):
        return fallback
    return _normalize_debate_result(result, fallback)


def _normalize_debate_result(result: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    debate_rounds = _dict_list(result.get("debate_rounds"))[:3] or fallback["debate_rounds"]
    consensus_findings = _string_list(result.get("consensus_findings"))[:8] or fallback["consensus_findings"]
    consensus_recommendations = _string_list(result.get("consensus_recommendations"))[:8] or fallback["consensus_recommendations"]
    statistical_guardrails = _string_list(result.get("statistical_guardrails"))[:8] or fallback["statistical_guardrails"]
    phrasing_revisions = _dict_list(result.get("phrasing_revisions"))[:6] or fallback["phrasing_revisions"]
    final_consensus = str(result.get("final_consensus") or fallback["final_consensus"]).strip()
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "debate_rounds": debate_rounds,
        "consensus_findings": consensus_findings,
        "consensus_recommendations": consensus_recommendations,
        "statistical_guardrails": statistical_guardrails,
        "phrasing_revisions": phrasing_revisions,
        "final_consensus": final_consensus,
        "source": "llm" if result else "fallback",
    }


def _fallback_debate(payload: dict[str, Any]) -> dict[str, Any]:
    result_payload = payload.get("result_payload") if isinstance(payload.get("result_payload"), dict) else {}
    summary_items = _extract_summary_items(result_payload)
    strongest = summary_items[0] if summary_items else "当前结果提供了可用于业务复核的结构化信号。"
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "debate_rounds": [
            {
                "round": 1,
                "aggressive_business_agent": f"最值得强调的商业信号是：{strongest} 应把它转化为可执行的运营假设。",
                "statistical_qc_agent": "该信号需要保留样本量、时间跨度和观察性数据限制，不能直接写成确定因果。",
            },
            {
                "round": 2,
                "aggressive_business_agent": "报告应优先呈现高差异、高贡献或持续趋势的结论，并给出明确下一步。",
                "statistical_qc_agent": "所有建议应表述为复核、验证、实验或进一步拆解，避免过度承诺。",
            },
        ],
        "consensus_findings": summary_items[:5] or ["当前分析已形成若干可复核的业务信号。"],
        "consensus_recommendations": [
            "优先围绕高影响、高置信的信号开展业务复核。",
            "对关键分组补充样本量、时间跨度和外部业务事件信息。",
            "将结论转化为可验证假设，采用 A/B 实验、分层对比或后续追踪验证。",
        ],
        "statistical_guardrails": [
            "观察性数据不能直接证明因果关系。",
            "样本量较小或时间跨度较短时，结论需要降级为待验证线索。",
            "分组差异可能受促销、价格、库存、渠道组合或缺失值影响。",
        ],
        "phrasing_revisions": [
            {"risky_claim": "A 导致 B", "safer_claim": "A 与 B 存在相关信号，可能是影响 B 的候选因素之一"},
            {"risky_claim": "必须立即调整策略", "safer_claim": "建议优先复核并设计小流量实验验证策略有效性"},
        ],
        "final_consensus": "报告应突出高价值业务信号，同时明确样本、时间跨度和相关性边界，把结论定位为可行动、可验证的业务假设。",
        "source": "fallback",
    }


def _extract_summary_items(result_payload: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for key in ("insights", "key_findings", "findings", "summary"):
        value = result_payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    text = item.get("title") or item.get("description") or item.get("finding") or item.get("summary")
                else:
                    text = item
                if text:
                    items.append(str(text).strip())
        elif isinstance(value, str) and value.strip():
            items.append(value.strip())
    if not items:
        for key, value in result_payload.items():
            if isinstance(value, (str, int, float)) and str(value).strip():
                items.append(f"{key}: {value}")
            if len(items) >= 5:
                break
    deduped: list[str] = []
    for item in items:
        if item and item not in deduped:
            deduped.append(item[:260])
    return deduped


def _compact(value: Any, *, depth: int = 0, max_depth: int = 4, max_items: int = 10, max_string: int = 1000) -> Any:
    if depth >= max_depth:
        return _short(value, max_string=180)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                result["__truncated__"] = True
                break
            result[str(key)] = _compact(item, depth=depth + 1, max_depth=max_depth, max_items=max_items, max_string=max_string)
        return result
    if isinstance(value, list):
        result = [_compact(item, depth=depth + 1, max_depth=max_depth, max_items=max_items, max_string=max_string) for item in value[:max_items]]
        if len(value) > max_items:
            result.append({"__truncated__": True, "total_items": len(value)})
        return result
    return _short(value, max_string=max_string)


def _short(value: Any, *, max_string: int = 1000) -> Any:
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    return text if len(text) <= max_string else text[:max_string] + "..."


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item or "").strip()]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
