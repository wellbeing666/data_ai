from __future__ import annotations

import json
from typing import Any

from app.agents.analysis_ir_schema import FollowUpIRPatch, IRFilter
from app.services.llm_client import get_llm_client


SYSTEM_PROMPT = """你是图形刷选即问题 Agent。
用户在图表上圈选柱子、点、时间窗或异常区域。你需要把 selection_spec 转成 followup_ir_patch.json：包括筛选条件、上下文问题、证据需求。
不要凭空创造数据，只能根据 Analysis IR、现有产物和 selection_spec 推断可追问的问题。
返回合法 JSON，不要 Markdown。
"""


def create_selection_followup_patch(
    selection_spec: dict[str, Any],
    analysis_ir: dict[str, Any] | None = None,
    artifacts: dict[str, Any] | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    fallback = _rule_based_patch(selection_spec, analysis_ir or {})
    try:
        client = llm_client or get_llm_client()
        payload = {
            "selection_spec": selection_spec,
            "analysis_ir": analysis_ir or {},
            "available_artifacts": sorted((artifacts or {}).keys()),
            "required_schema": FollowUpIRPatch.model_json_schema(),
            "fallback_reference": fallback,
        }
        raw = client.chat_json(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, indent=2)},
            ],
            temperature=0.1,
        )
        if isinstance(raw, dict):
            patch = {**fallback, **raw}
            patch["selection_spec"] = selection_spec
            patch["question"] = str(patch.get("question") or fallback["question"]).strip()[:500]
            patch["filters"] = _normalize_filters(patch.get("filters")) or fallback.get("filters", [])
            patch["evidence_requirements"] = _string_list(patch.get("evidence_requirements")) or fallback.get("evidence_requirements", [])
            return FollowUpIRPatch.model_validate(patch).model_dump(mode="json")
    except Exception:
        return fallback
    return fallback


def _rule_based_patch(selection_spec: dict[str, Any], analysis_ir: dict[str, Any]) -> dict[str, Any]:
    chart_title = str(selection_spec.get("chart_title") or selection_spec.get("title") or "被圈选区域")
    metric_names = [str(item.get("name") or item.get("source_column") or "") for item in analysis_ir.get("metrics", []) if isinstance(item, dict)]
    dimension_names = [str(item.get("name") or item.get("source_column") or "") for item in analysis_ir.get("dimensions", []) if isinstance(item, dict)]
    metric = next((item for item in metric_names if item), "关键指标")
    dimension = next((item for item in dimension_names if item), "相关维度")
    selected_label = _selection_label(selection_spec)
    question = f"为什么{chart_title}中{selected_label}的{metric}表现值得关注？请按{dimension}拆解可能原因和证据。"
    filters = []
    for key in ("x_value", "category", "series", "time_start", "time_end"):
        value = selection_spec.get(key)
        if value in (None, ""):
            continue
        field = dimension if key in {"x_value", "category", "series"} else str((analysis_ir.get("time_window") or {}).get("field") or "")
        if field:
            filters.append(IRFilter(field=field, operator="contains" if key != "time_start" and key != "time_end" else key, value=value, description="由图形刷选动作自动生成").model_dump(mode="json"))
    return FollowUpIRPatch(
        question=question,
        selection_spec=selection_spec,
        filters=filters,
        context={
            "source": "chart_brush",
            "chart_path": selection_spec.get("chart_path"),
            "selection_label": selected_label,
            "semantic_source": "analysis_ir + selection_delta",
        },
        evidence_requirements=[
            "对比圈选区域与全量/未圈选区域的指标差异。",
            "检查相关维度、时间窗和样本量是否支撑该追问。",
            "原因类回答必须使用可能原因或相关信号表述。",
        ],
    ).model_dump(mode="json")


def _selection_label(selection_spec: dict[str, Any]) -> str:
    labels = _string_list(selection_spec.get("labels"))
    if labels:
        return "、".join(labels[:5])
    if selection_spec.get("time_start") or selection_spec.get("time_end"):
        return f"{selection_spec.get('time_start', '起点')}到{selection_spec.get('time_end', '终点')}的时间窗"
    ratios = [selection_spec.get(key) for key in ("ratio_x0", "ratio_y0", "ratio_x1", "ratio_y1")]
    if all(isinstance(item, (int, float)) for item in ratios):
        return f"图中横向 {float(ratios[0]):.0%}-{float(ratios[2]):.0%}、纵向 {float(ratios[1]):.0%}-{float(ratios[3]):.0%} 的刷选区域"
    return "被圈选的数据点或异常区间"


def _normalize_filters(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value[:12]:
        if isinstance(item, dict):
            result.append(IRFilter.model_validate(item).model_dump(mode="json"))
    return result


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []
