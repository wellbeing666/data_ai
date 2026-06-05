from __future__ import annotations

import json
import re
from typing import Any

from app.agents.analysis_ir_schema import AnalysisIR, IRChartIntent, IRDependency, IRFieldRef, IRFilter, IRMetric, IRTimeWindow, normalize_ir_payload
from app.services.llm_client import get_llm_client


SYSTEM_PROMPT = """你是 Analysis IR 编译器，不是业务分析 Agent。
你的任务是把用户自然语言分析目标编译为强类型 analysis_ir.json，供后续 Controller、Analysis、Code、Dashboard、Follow-up、PPT 统一消费。
要求：
1. 只使用 dataset_profile 中真实存在的字段，不能编造列名。
2. 明确实体、粒度、指标、过滤条件、时间窗、候选方法、图表意图、假设、证据需求和输出产物依赖关系。
3. 涉及原因、影响、预测时必须保留谨慎表述边界，不能把相关性写成确定因果。
4. 返回合法 JSON 对象，不要输出 Markdown。
"""


def create_analysis_ir(
    user_goal: str,
    dataset_profile: dict[str, Any],
    preflight: dict[str, Any] | None = None,
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    fallback = _rule_based_ir(user_goal, dataset_profile, preflight=preflight, rag_context=rag_context)
    client = llm_client
    try:
        if client is None:
            client = get_llm_client()
        payload = {
            "user_goal": user_goal,
            "dataset_profile": _compact_profile(dataset_profile),
            "preflight": preflight or {},
            "retrieved_business_knowledge": rag_context or [],
            "required_schema": AnalysisIR.model_json_schema(),
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
            normalized = _sanitize_ir(raw, user_goal, dataset_profile, fallback)
            return normalize_ir_payload(normalized)
    except Exception:
        return fallback
    return fallback


def render_analysis_ir_for_agent(analysis_ir: dict[str, Any] | None, delta: dict[str, Any] | None = None) -> str:
    """Render IR + local delta as the single semantic input consumed by downstream agents."""
    if not analysis_ir:
        return str((delta or {}).get("raw_user_goal") or (delta or {}).get("instruction") or (delta or {}).get("question") or "")
    payload = {
        "contract": "Use Analysis IR as the semantic source of truth. Apply delta only as a local interaction override; do not reinterpret the original goal independently.",
        "analysis_ir": analysis_ir,
        "delta": delta or {},
    }
    return "Analysis IR + Delta JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def _sanitize_ir(raw: dict[str, Any], user_goal: str, dataset_profile: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    columns = set(_columns(dataset_profile))
    result = {**fallback, **raw}
    result["normalized_goal"] = str(result.get("normalized_goal") or user_goal).strip()[:2000]
    result["task_type"] = _safe_task_type(str(result.get("task_type") or fallback.get("task_type") or "general_data_analysis"))
    result["entities"] = _filter_field_refs(result.get("entities"), columns) or fallback.get("entities", [])
    result["dimensions"] = _filter_field_refs(result.get("dimensions"), columns) or fallback.get("dimensions", [])
    result["metrics"] = _filter_metrics(result.get("metrics"), columns) or fallback.get("metrics", [])
    result["filters"] = _filter_filters(result.get("filters"), columns)
    result["chart_intents"] = _filter_chart_intents(result.get("chart_intents"), columns) or fallback.get("chart_intents", [])
    time_window = result.get("time_window") if isinstance(result.get("time_window"), dict) else {}
    if str(time_window.get("field") or "") not in columns:
        time_window = fallback.get("time_window", {})
    result["time_window"] = time_window
    result["grain"] = _string_list(result.get("grain")) or fallback.get("grain", [])
    result["candidate_methods"] = _string_list(result.get("candidate_methods")) or fallback.get("candidate_methods", [])
    result["hypotheses"] = _string_list(result.get("hypotheses"))[:12] or fallback.get("hypotheses", [])
    result["evidence_requirements"] = _string_list(result.get("evidence_requirements"))[:16] or fallback.get("evidence_requirements", [])
    result["guardrails"] = _string_list(result.get("guardrails"))[:12] or fallback.get("guardrails", [])
    result["open_questions"] = _string_list(result.get("open_questions"))[:8]
    result["output_dependencies"] = _normalize_dependencies(result.get("output_dependencies")) or fallback.get("output_dependencies", [])
    result["source"] = {**(fallback.get("source") if isinstance(fallback.get("source"), dict) else {}), **(result.get("source") if isinstance(result.get("source"), dict) else {})}
    return result


def _rule_based_ir(
    user_goal: str,
    dataset_profile: dict[str, Any],
    preflight: dict[str, Any] | None = None,
    rag_context: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    columns = _columns(dataset_profile)
    numeric_columns = list((dataset_profile.get("numeric_summary") or {}).keys())
    text_columns = list((dataset_profile.get("text_summary") or {}).keys())
    goal = str(user_goal or "").strip()
    date_cols = [col for col in columns if _looks_like_date(col)]
    metric_cols = _goal_matched_columns(goal, numeric_columns) or numeric_columns[:3]
    dimension_cols = _goal_matched_columns(goal, text_columns) or text_columns[:4]
    entity_cols = [col for col in dimension_cols if _looks_like_entity(col)] or dimension_cols[:1]
    task_type = _infer_task_type(goal)
    metrics = [
        IRMetric(
            name=col,
            source_column=col,
            aggregation="sum" if _metric_prefers_sum(col, goal) else "mean",
            direction=_metric_direction(col),
            business_definition=f"基于字段“{col}”计算核心指标。",
            evidence_required=["分组统计表", "图表趋势或对比", "样本量/缺失值说明"],
        ).model_dump(mode="json")
        for col in metric_cols
    ]
    dimensions = [
        IRFieldRef(name=col, role="dimension", source_column=col, confidence=0.72, description=f"用于拆解指标的维度字段：{col}").model_dump(mode="json")
        for col in dimension_cols
    ]
    entities = [
        IRFieldRef(name=col, role="entity", source_column=col, confidence=0.68, description=f"分析对象或业务实体字段：{col}").model_dump(mode="json")
        for col in entity_cols
    ]
    time_window = IRTimeWindow(field=date_cols[0] if date_cols else "", granularity="month" if date_cols else "", description="从目标或日期字段中推断出的时间窗口，未明确时按全量数据处理。").model_dump(mode="json")
    methods = _candidate_methods(task_type, goal, bool(date_cols), bool(dimension_cols))
    chart_intents = _default_chart_intents(metric_cols, dimension_cols, date_cols, goal)
    evidence = [
        "必须引用实际产物中的数值、分组表或图表路径。",
        "原因类问题只输出相关信号、可能原因或待验证线索。",
        "说明数据缺失、样本量和口径限制。",
    ]
    if preflight and isinstance(preflight.get("clarifying_questions"), list):
        evidence.append("保留 preflight 阶段的澄清问题和用户选择口径。")
    if rag_context:
        evidence.append("优先遵守 RAG 命中的业务指标定义和谨慎表述约束。")
    return AnalysisIR(
        task_type=task_type,
        normalized_goal=goal,
        semantic_digest=_semantic_digest(goal, metric_cols, dimension_cols, date_cols),
        entities=entities,
        grain=_string_list([*(date_cols[:1] or []), *dimension_cols[:3]]) or ["全量数据"],
        metrics=metrics,
        dimensions=dimensions,
        time_window=time_window,
        filters=[],
        candidate_methods=methods,
        chart_intents=chart_intents,
        hypotheses=_default_hypotheses(task_type, goal, metric_cols, dimension_cols),
        evidence_requirements=evidence,
        output_dependencies=_default_dependencies(task_type),
        guardrails=[
            "后续 Agent 必须消费 analysis_ir.json + delta，不要各自重新解释原始自然语言。",
            "字段名必须来自 dataset_profile.columns。",
            "相关性不等于因果，预测不等于承诺。",
        ],
        open_questions=_string_list((preflight or {}).get("clarifying_questions"))[:3],
        source={
            "compiler": "rule_based_fallback_or_llm_sanitized",
            "row_count": dataset_profile.get("row_count"),
            "column_count": dataset_profile.get("column_count"),
            "rag_context_count": len(rag_context or []),
        },
    ).model_dump(mode="json")


def _compact_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        "columns": _columns(profile),
        "row_count": profile.get("row_count"),
        "column_count": profile.get("column_count"),
        "dtypes": profile.get("dtypes") or {},
        "missing_values": profile.get("missing_values") or {},
        "numeric_summary": profile.get("numeric_summary") or {},
        "text_summary_keys": list((profile.get("text_summary") or {}).keys()),
        "sample_rows": (profile.get("sample_rows") or [])[:5],
    }


def _columns(profile: dict[str, Any]) -> list[str]:
    return [str(item) for item in profile.get("columns", []) if str(item).strip()]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _safe_task_type(value: str) -> str:
    text = value.strip() or "general_data_analysis"
    allowed = {"general_data_analysis", "sales_decline_analysis", "grade_analysis", "what_if_prediction", "insight_mining"}
    return text if text in allowed else "general_data_analysis"


def _infer_task_type(goal: str) -> str:
    text = goal.lower()
    if any(word in goal for word in ("如果", "预测", "预计", "情景", "增加", "减少")) and any(word in goal for word in ("会", "可能", "预测", "预计", "影响")):
        return "what_if_prediction"
    if any(word in goal for word in ("成绩", "班级", "及格率", "优秀率")):
        return "grade_analysis"
    if any(word in goal for word in ("下降", "下滑", "衰退", "原因")) and any(word in goal for word in ("销量", "销售额", "订单")):
        return "sales_decline_analysis"
    if "insight" in text or "智能洞察" in goal or "自动扫描" in goal:
        return "insight_mining"
    return "general_data_analysis"


def _goal_matched_columns(goal: str, columns: list[str]) -> list[str]:
    direct = [col for col in columns if col and col in goal]
    if direct:
        return direct[:6]
    aliases = {
        "销量": ["sales", "volume", "数量"],
        "销售额": ["revenue", "amount", "gmv"],
        "地区": ["region", "area", "省", "城市"],
        "渠道": ["channel", "来源"],
        "商品": ["product", "sku", "品类", "类别"],
        "日期": ["date", "month", "月份", "时间"],
        "成绩": ["score", "分数"],
    }
    result: list[str] = []
    lower_goal = goal.lower()
    for col in columns:
        lower_col = col.lower()
        for cn, keys in aliases.items():
            if cn in goal or any(key in lower_goal for key in keys):
                if cn in col or any(key in lower_col for key in keys):
                    result.append(col)
                    break
    return result[:6]


def _looks_like_date(column: str) -> bool:
    text = column.lower()
    return any(token in text for token in ("date", "time", "month", "year", "day", "日期", "时间", "月份", "年月", "年", "月"))


def _looks_like_entity(column: str) -> bool:
    text = column.lower()
    return any(token in text for token in ("商品", "产品", "门店", "客户", "用户", "班级", "学生", "物料", "区域", "地区", "product", "store", "customer", "class", "sku", "id"))


def _metric_prefers_sum(column: str, goal: str) -> bool:
    text = f"{column} {goal}".lower()
    return any(token in text for token in ("销量", "销售额", "订单", "人数", "数量", "总", "sum", "sales", "revenue", "amount", "count"))


def _metric_direction(column: str) -> str:
    text = column.lower()
    if any(token in text for token in ("退货", "缺陷", "不良", "风险", "成本", "时长", "等待", "响应", "率分", "risk", "defect", "cost", "duration", "time")):
        return "lower_is_better"
    return "higher_is_better"


def _candidate_methods(task_type: str, goal: str, has_time: bool, has_dimension: bool) -> list[str]:
    methods = []
    if has_time:
        methods.append("time_series_trend")
    if has_dimension:
        methods.append("group_comparison")
        methods.append("dimension_breakdown")
    if task_type == "sales_decline_analysis":
        methods.extend(["period_over_period_change", "contribution_decomposition", "anomaly_detection"])
    elif task_type == "what_if_prediction":
        methods.extend(["hypothesis_parsing", "feature_based_simulation", "model_candidate_comparison"])
    elif task_type == "grade_analysis":
        methods.extend(["class_summary_statistics", "pass_excellent_rate_calculation"])
    else:
        methods.extend(["descriptive_statistics", "outlier_scan"])
    return list(dict.fromkeys(methods))


def _default_chart_intents(metric_cols: list[str], dimension_cols: list[str], date_cols: list[str], goal: str) -> list[dict[str, Any]]:
    intents: list[IRChartIntent] = []
    metric = metric_cols[0] if metric_cols else ""
    if date_cols and metric:
        intents.append(IRChartIntent(chart_type="line", purpose="展示时间趋势", x=date_cols[0], y=metric, group_by=dimension_cols[0] if dimension_cols else "", title=f"{metric}趋势"))
    if dimension_cols and metric:
        intents.append(IRChartIntent(chart_type="bar", purpose="展示维度对比", x=dimension_cols[0], y=metric, group_by="", title=f"按{dimension_cols[0]}对比{metric}"))
    if not intents:
        intents.append(IRChartIntent(chart_type="table", purpose="展示关键统计摘要", x=dimension_cols[0] if dimension_cols else "", y=metric, title="关键指标摘要"))
    return [item.model_dump(mode="json") for item in intents[:4]]


def _default_hypotheses(task_type: str, goal: str, metric_cols: list[str], dimension_cols: list[str]) -> list[str]:
    metric = metric_cols[0] if metric_cols else "目标指标"
    dimension = dimension_cols[0] if dimension_cols else "关键维度"
    if task_type == "what_if_prediction":
        return ["用户提出的干预变量可能与目标指标存在历史相关关系，需要用现有数据估计变化方向。"]
    if task_type == "sales_decline_analysis":
        return [f"{metric}的下降可能在时间、{dimension}或渠道结构上存在可解释差异，但需要证据验证。"]
    return [f"{metric}在不同{dimension}之间可能存在差异，需要用分组统计和图表验证。"]


def _default_dependencies(task_type: str) -> list[dict[str, Any]]:
    deps = [
        IRDependency(artifact="controller_plan.json", depends_on=["analysis_ir.json"], purpose="只负责工作流分流，不重新解释用户目标。"),
        IRDependency(artifact="analysis_plan.json", depends_on=["analysis_ir.json", "data_understanding.json"], purpose="选择方法和图表时复用 IR 的指标、粒度和证据需求。"),
        IRDependency(artifact="analysis_result.json", depends_on=["analysis_plan.json", "generated_script.py"], purpose="产出统计表和图表。"),
        IRDependency(artifact="dashboard_config.json", depends_on=["analysis_ir.json", "analysis_result.json"], purpose="生成可筛选看板。"),
        IRDependency(artifact="followup_ir_patch.json", depends_on=["analysis_ir.json", "用户文本或图形刷选 delta"], purpose="把追问转成局部语义补丁。"),
        IRDependency(artifact="report.pptx", depends_on=["analysis_ir.json", "explanation.json", "charts"], purpose="PPT 复用同一口径。"),
    ]
    if task_type == "what_if_prediction":
        deps.insert(2, IRDependency(artifact="prediction_plan.json", depends_on=["analysis_ir.json", "hypothesis_plan.json"], purpose="预测计划复用 IR 的目标、干预和证据边界。"))
    return [item.model_dump(mode="json") for item in deps]


def _semantic_digest(goal: str, metrics: list[str], dimensions: list[str], dates: list[str]) -> str:
    parts = [f"目标：{goal or '未提供'}"]
    if metrics:
        parts.append("指标：" + "、".join(metrics[:4]))
    if dimensions:
        parts.append("维度：" + "、".join(dimensions[:4]))
    if dates:
        parts.append("时间：" + "、".join(dates[:2]))
    return "；".join(parts)


def _filter_field_refs(value: Any, columns: set[str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return refs
    for item in value:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_column") or item.get("field") or item.get("name") or "")
        if source in columns:
            payload = {**item, "name": str(item.get("name") or source), "source_column": source}
            refs.append(IRFieldRef.model_validate(payload).model_dump(mode="json"))
    return refs[:12]


def _filter_metrics(value: Any, columns: set[str]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return metrics
    for item in value:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source_column") or item.get("field") or item.get("name") or "")
        if source in columns:
            payload = {**item, "name": str(item.get("name") or source), "source_column": source}
            metrics.append(IRMetric.model_validate(payload).model_dump(mode="json"))
    return metrics[:8]


def _filter_filters(value: Any, columns: set[str]) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return filters
    for item in value:
        if isinstance(item, dict) and str(item.get("field") or "") in columns:
            filters.append(IRFilter.model_validate(item).model_dump(mode="json"))
    return filters[:12]


def _filter_chart_intents(value: Any, columns: set[str]) -> list[dict[str, Any]]:
    intents: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return intents
    for item in value:
        if not isinstance(item, dict):
            continue
        payload = dict(item)
        for key in ("x", "y", "group_by"):
            if payload.get(key) and str(payload.get(key)) not in columns:
                payload[key] = ""
        intents.append(IRChartIntent.model_validate(payload).model_dump(mode="json"))
    return intents[:8]


def _normalize_dependencies(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value[:12]:
        if isinstance(item, dict):
            result.append(IRDependency.model_validate(item).model_dump(mode="json"))
    return result
