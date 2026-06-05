import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SIDECAR_FILENAMES = {
    "anomalies": "anomaly_scan.json",
    "next_step_suggestions": "next_steps.json",
    "significance_tests": "significance_tests.json",
    "dashboard_config": "dashboard_config.json",
}


def create_postprocess_sidecars(
    *,
    job_dir: Path | str,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    report_data: dict[str, Any] | None = None,
    chart_paths: list[str] | None = None,
    validation_result: dict[str, Any] | None = None,
    debate_reflection: dict[str, Any] | None = None,
    workflow_type: str = "auto_repair",
) -> dict[str, str]:
    """Generate optional post-processing sidecar artifacts after the main chain succeeds.

    These artifacts deliberately hang off the job directory instead of changing the linear
    controller -> analysis -> code -> sandbox -> validation -> explanation trunk.
    """
    job_path = Path(job_dir)
    job_path.mkdir(parents=True, exist_ok=True)
    safe_report_data = report_data if isinstance(report_data, dict) else {}
    safe_chart_paths = [str(item) for item in (chart_paths or []) if str(item or "").strip()]
    safe_validation = validation_result if isinstance(validation_result, dict) else {}
    safe_debate = debate_reflection if isinstance(debate_reflection, dict) else {}

    anomalies = create_anomaly_scan(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        validation_result=safe_validation,
    )
    significance = create_significance_tests(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        validation_result=safe_validation,
        debate_reflection=safe_debate,
    )
    next_steps = create_next_step_suggestions(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        report_data=safe_report_data,
        debate_reflection=safe_debate,
        significance_tests=significance,
    )
    dashboard = create_dashboard_config(
        job_dir=job_path,
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        report_data=safe_report_data,
        chart_paths=safe_chart_paths,
        anomalies=anomalies,
        next_steps=next_steps,
        workflow_type=workflow_type,
    )

    payloads = {
        "anomalies": anomalies,
        "next_step_suggestions": next_steps,
        "significance_tests": significance,
        "dashboard_config": dashboard,
    }
    sidecar_results: dict[str, str] = {}
    for key, payload in payloads.items():
        filename = SIDECAR_FILENAMES[key]
        path = job_path / filename
        _write_json(path, payload)
        sidecar_results[key] = str(path)
    return sidecar_results


def create_anomaly_scan(
    *,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    validation_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row_count = _safe_int(dataset_profile.get("row_count"))
    issues: list[dict[str, Any]] = []
    now = _utc_now()

    missing_values = dataset_profile.get("missing_values")
    if isinstance(missing_values, dict):
        for column, summary in missing_values.items():
            if not isinstance(summary, dict):
                continue
            count = _safe_number(summary.get("count"))
            ratio = _safe_number(summary.get("ratio"))
            if count > 0:
                severity = "high" if ratio >= 0.2 else "medium" if ratio >= 0.05 else "low"
                issues.append(
                    {
                        "type": "missing_values",
                        "severity": severity,
                        "column": str(column),
                        "description": f"字段 {column} 存在 {int(count)} 个缺失值，占比约 {_fmt_percent(ratio)}。",
                        "suggestion": "建议在后续追问中验证缺失值处理方式对核心结论的影响。",
                    }
                )

    numeric_summary = dataset_profile.get("numeric_summary")
    if isinstance(numeric_summary, dict):
        for column, summary in numeric_summary.items():
            if not isinstance(summary, dict):
                continue
            minimum = _safe_number(summary.get("min"))
            maximum = _safe_number(summary.get("max"))
            mean = _safe_number(summary.get("mean"))
            if not mean or not math.isfinite(mean):
                continue
            spread_ratio = abs(maximum - minimum) / max(abs(mean), 1.0)
            if spread_ratio >= 5:
                issues.append(
                    {
                        "type": "wide_numeric_spread",
                        "severity": "medium" if spread_ratio < 15 else "high",
                        "column": str(column),
                        "description": f"字段 {column} 的最大最小差异约为均值的 {spread_ratio:.1f} 倍，可能存在长尾或异常值。",
                        "suggestion": "建议补充箱线图、分位数或剔除极端值后的稳健性分析。",
                    }
                )

    result_rows = _extract_primary_rows(result_payload)
    for item in _scan_result_row_extremes(result_rows)[:4]:
        issues.append(item)

    validation_issues = []
    if isinstance(validation_result, dict):
        raw_issues = validation_result.get("issues")
        if isinstance(raw_issues, list):
            validation_issues = [item for item in raw_issues if isinstance(item, dict)][:5]

    return {
        "agent": "Postprocess Anomaly Sidecar Agent",
        "generated_at": now,
        "user_goal": user_goal,
        "row_count": row_count,
        "risk_level": _overall_risk_level(issues, validation_issues),
        "anomalies": issues[:12],
        "validation_issues": validation_issues,
        "summary": _anomaly_summary(issues, validation_issues),
        "method_note": "该产物为主链成功后的横向后处理附件，不改变主分析结论；用于提示后续复核重点。",
    }


def create_significance_tests(
    *,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    validation_result: dict[str, Any] | None = None,
    debate_reflection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row_count = _safe_int(dataset_profile.get("row_count"))
    numeric_columns = _numeric_columns(dataset_profile)
    dimension_columns = _dimension_columns(dataset_profile)
    chart_count = len(_as_list(result_payload.get("charts")))
    tests: list[dict[str, Any]] = []

    if len(numeric_columns) >= 2:
        tests.append(
            {
                "name": "数值指标相关性复核",
                "status": "recommended",
                "target": numeric_columns[:4],
                "recommended_method": "Pearson/Spearman 相关系数 + 散点图复核",
                "interpretation_rule": "相关性只能作为线索，不能单独写成因果结论。",
            }
        )
    if dimension_columns and numeric_columns:
        tests.append(
            {
                "name": "分组差异显著性复核",
                "status": "recommended",
                "target": {"dimension": dimension_columns[:3], "metric": numeric_columns[:3]},
                "recommended_method": "ANOVA 或 Kruskal-Wallis；样本很小时改用描述统计。",
                "interpretation_rule": "若未做实验设计，应使用可能、相关、待验证等表述。",
            }
        )
    if row_count and row_count < 30:
        tests.append(
            {
                "name": "小样本稳健性提醒",
                "status": "warning",
                "target": {"row_count": row_count},
                "recommended_method": "Bootstrap 置信区间或合并更多周期样本。",
                "interpretation_rule": "样本量不足时不建议输出强判断。",
            }
        )
    if chart_count:
        tests.append(
            {
                "name": "图表证据一致性复核",
                "status": "available",
                "target": {"chart_count": chart_count},
                "recommended_method": "逐图核对标题、坐标轴、筛选口径和报告结论是否一致。",
                "interpretation_rule": "图表只显示数据模式，不能替代业务归因。",
            }
        )

    guardrails = _as_string_list((debate_reflection or {}).get("statistical_guardrails"))
    validation_passed = bool((validation_result or {}).get("passed")) if isinstance(validation_result, dict) else None
    return {
        "agent": "Postprocess Significance Sidecar Agent",
        "generated_at": _utc_now(),
        "user_goal": user_goal,
        "sample_profile": {
            "row_count": row_count,
            "numeric_columns": numeric_columns[:10],
            "dimension_columns": dimension_columns[:10],
            "validation_passed": validation_passed,
        },
        "tests": tests,
        "statistical_guardrails": guardrails,
        "limitations": _significance_limitations(row_count, numeric_columns, dimension_columns),
    }


def create_next_step_suggestions(
    *,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    report_data: dict[str, Any] | None = None,
    debate_reflection: dict[str, Any] | None = None,
    significance_tests: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dimensions = _dimension_columns(dataset_profile)
    metrics = _numeric_columns(dataset_profile)
    time_columns = _time_columns(dataset_profile)
    primary_metric = _pick_primary_metric(metrics, user_goal, result_payload)
    primary_dimension = _pick_primary_dimension(dimensions, user_goal)
    secondary_dimension = _pick_secondary_dimension(dimensions, primary_dimension)
    time_label = time_columns[0] if time_columns else "时间周期"
    question_candidates = [
        {
            "question": f"哪个{primary_dimension}对{primary_metric}的变化贡献最大？",
            "rationale": "优先把总体变化拆到最可行动的维度，便于定位主要影响来源。",
            "based_on": [primary_dimension, primary_metric],
            "confidence": 0.9,
        },
        {
            "question": f"是否存在{primary_dimension}和{secondary_dimension}的交互影响？",
            "rationale": "单维度排名可能掩盖组合差异，交叉分析能定位高风险组合。",
            "based_on": [primary_dimension, secondary_dimension, primary_metric],
            "confidence": 0.86,
        },
        {
            "question": f"{time_label}上{primary_metric}的异常波动集中在哪些节点？",
            "rationale": "趋势拐点通常比整体均值更适合触发业务复盘。",
            "based_on": [time_label, primary_metric],
            "confidence": 0.82,
        },
        {
            "question": f"剔除缺失值或异常值后，{primary_metric}相关结论是否仍然稳定？",
            "rationale": "主报告中的发现需要通过数据质量敏感性分析确认稳健性。",
            "based_on": [primary_metric, "缺失值", "异常值"],
            "confidence": 0.8,
        },
        {
            "question": "哪些建议动作最值得优先做 A/B 测试或小范围验证？",
            "rationale": "把一次性分析转为可验证行动，避免直接把相关性当成因果。",
            "based_on": ["建议动作", "统计限制", "业务验证"],
            "confidence": 0.78,
        },
    ]

    consensus = _as_string_list((debate_reflection or {}).get("consensus_findings"))[:3]
    tests = _as_list((significance_tests or {}).get("tests"))[:3]
    report_summary = _clip_text(str((report_data or {}).get("summary") or result_payload.get("summary") or ""), 300)
    return {
        "agent": "Postprocess Next-Step Suggestion Agent",
        "generated_at": _utc_now(),
        "user_goal": user_goal,
        "recommended_questions": _dedupe_questions(question_candidates)[:5],
        "context_summary": report_summary,
        "debate_consensus_used": consensus,
        "recommended_statistical_checks": tests,
        "usage_note": "前端会把这些问题展示在追问框上方，点击即可带入本轮任务上下文继续追问。",
    }


def create_dashboard_config(
    *,
    job_dir: Path,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    report_data: dict[str, Any] | None,
    chart_paths: list[str],
    anomalies: dict[str, Any] | None = None,
    next_steps: dict[str, Any] | None = None,
    workflow_type: str = "auto_repair",
) -> dict[str, Any]:
    row_count = _safe_int(dataset_profile.get("row_count"))
    column_count = _safe_int(dataset_profile.get("column_count")) or len(_as_string_list(dataset_profile.get("columns")))
    table_rows = _extract_primary_rows(result_payload) or _extract_report_table_rows(report_data or {})
    dashboard_id = f"dashboard_{job_dir.name}"
    chart_widgets = _chart_widgets(chart_paths)
    filters = _dashboard_filters(dataset_profile)
    kpis = [
        {
            "id": "kpi_rows",
            "type": "kpi",
            "title": "数据行数",
            "value": row_count,
            "unit": "行",
            "description": "当前分析数据集的记录数。",
        },
        {
            "id": "kpi_columns",
            "type": "kpi",
            "title": "字段数量",
            "value": column_count,
            "unit": "列",
            "description": "当前分析数据集的字段数。",
        },
        {
            "id": "kpi_charts",
            "type": "kpi",
            "title": "图表产物",
            "value": len(chart_paths),
            "unit": "张",
            "description": "本轮分析生成的可视化图表数量。",
        },
        {
            "id": "kpi_risk",
            "type": "kpi",
            "title": "复核风险",
            "value": str((anomalies or {}).get("risk_level") or "low"),
            "unit": "",
            "description": "来自异常扫描 sidecar 的风险提示。",
        },
    ]
    table_widget = {
        "id": "detail_table",
        "type": "table",
        "title": "明细表",
        "description": "从 analysis_result/report_data 中抽取的关键明细。",
        "columns": _table_columns(table_rows),
        "rows": table_rows[:50],
    }
    widgets: list[dict[str, Any]] = [*kpis, *chart_widgets, table_widget]
    layout = _default_dashboard_layout(widgets)
    return {
        "dashboard_id": dashboard_id,
        "title": "自动分析 Dashboard",
        "description": "分析完成后由 Dashboard Sidecar Agent 生成，可拖拽排序、设置刷新频率、筛选并保存。",
        "source_job_id": job_dir.name,
        "source_goal": user_goal,
        "workflow_type": workflow_type,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "refresh": {
            "enabled": False,
            "interval_seconds": 300,
            "last_refreshed_at": None,
            "api": f"/api/workflows/jobs/{job_dir.name}/dashboard/refresh",
        },
        "filters": filters,
        "layout": layout,
        "widgets": widgets,
        "recommended_questions": (next_steps or {}).get("recommended_questions", []),
        "sharing": {
            "share_token": "",
            "share_url": "",
            "embed_code": f'<iframe src="/api/workflows/jobs/{job_dir.name}/dashboard/embed" width="100%" height="720"></iframe>',
        },
        "permissions": {"can_save": True, "can_share": True, "can_embed": True},
    }


def _extract_primary_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [payload.get("summary"), payload.get("rows"), payload.get("data"), payload.get("top_impacted_entities")]
    analysis_summary = payload.get("analysis_summary")
    if isinstance(analysis_summary, dict):
        candidates.extend(analysis_summary.values())
    for value in candidates:
        rows = _rows_from_value(value)
        if rows:
            return rows
    return []


def _extract_report_table_rows(report_data: dict[str, Any]) -> list[dict[str, Any]]:
    tables = report_data.get("tables")
    if isinstance(tables, list):
        for table in tables:
            if isinstance(table, dict):
                rows = _rows_from_value(table.get("rows"))
                if rows:
                    return rows
    return []


def _rows_from_value(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        rows = [item for item in value if isinstance(item, dict)]
        if rows:
            return rows
    if isinstance(value, dict):
        nested = []
        for key, item in value.items():
            if isinstance(item, dict):
                row = {"name": key, **item}
                nested.append(row)
            elif isinstance(item, (int, float, str)):
                nested.append({"name": key, "value": item})
        if nested:
            return nested
    return []


def _scan_result_row_extremes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(rows) < 3:
        return []
    numeric_keys = []
    for row in rows:
        for key, value in row.items():
            if key not in numeric_keys and _is_number(value):
                numeric_keys.append(str(key))
    issues: list[dict[str, Any]] = []
    for key in numeric_keys[:4]:
        values = [_safe_number(row.get(key)) for row in rows if _is_number(row.get(key))]
        if len(values) < 3:
            continue
        mean = sum(values) / len(values)
        if not mean:
            continue
        high = max(values)
        low = min(values)
        ratio = abs(high - low) / max(abs(mean), 1.0)
        if ratio >= 1.5:
            issues.append(
                {
                    "type": "result_extreme_gap",
                    "severity": "medium" if ratio < 4 else "high",
                    "column": key,
                    "description": f"结果明细中 {key} 的最高值与最低值差异约为均值的 {ratio:.1f} 倍。",
                    "suggestion": "建议下钻查看造成极值差异的维度组合。",
                }
            )
    return issues


def _numeric_columns(dataset_profile: dict[str, Any]) -> list[str]:
    numeric_summary = dataset_profile.get("numeric_summary")
    if isinstance(numeric_summary, dict) and numeric_summary:
        return [str(key) for key in numeric_summary.keys()]
    columns = _as_string_list(dataset_profile.get("columns"))
    return [column for column in columns if any(token in column.lower() for token in ("sales", "amount", "score", "rate", "price", "销量", "销售", "金额", "成绩", "率", "时间", "数量"))]


def _dimension_columns(dataset_profile: dict[str, Any]) -> list[str]:
    text_summary = dataset_profile.get("text_summary")
    if isinstance(text_summary, dict) and text_summary:
        return [str(key) for key in text_summary.keys()]
    columns = _as_string_list(dataset_profile.get("columns"))
    excluded_tokens = ("id", "编号", "编码", "姓名", "名称", "备注")
    return [column for column in columns if not any(token in column.lower() for token in excluded_tokens)][:5]


def _time_columns(dataset_profile: dict[str, Any]) -> list[str]:
    columns = _as_string_list(dataset_profile.get("columns"))
    return [column for column in columns if re.search(r"日期|时间|月份|年月|date|month|time", column, re.IGNORECASE)]


def _pick_primary_metric(metrics: list[str], user_goal: str, result_payload: dict[str, Any]) -> str:
    if metrics:
        goal = user_goal.lower()
        for metric in metrics:
            if metric.lower() in goal or str(metric) in user_goal:
                return metric
        for preferred in ("销量", "销售额", "销售", "成绩", "不良率", "响应时长", "排队时间", "SalePrice"):
            for metric in metrics:
                if preferred.lower() in metric.lower() or preferred in metric:
                    return metric
        return metrics[0]
    rows = _extract_primary_rows(result_payload)
    for row in rows[:5]:
        for key, value in row.items():
            if _is_number(value):
                return str(key)
    return "核心指标"


def _pick_primary_dimension(dimensions: list[str], user_goal: str) -> str:
    for preferred in ("渠道", "地区", "区域", "商品类别", "品类", "班级", "部门", "生产线", "工序"):
        for dimension in dimensions:
            if preferred in dimension or dimension in user_goal:
                return dimension
    return dimensions[0] if dimensions else "关键维度"


def _pick_secondary_dimension(dimensions: list[str], primary_dimension: str) -> str:
    for dimension in dimensions:
        if dimension != primary_dimension:
            return dimension
    return "第二维度"


def _dashboard_filters(dataset_profile: dict[str, Any]) -> list[dict[str, Any]]:
    filters = []
    text_summary = dataset_profile.get("text_summary")
    if isinstance(text_summary, dict):
        for column, summary in list(text_summary.items())[:4]:
            options = ["全部"]
            if isinstance(summary, dict):
                values = summary.get("unique_values")
                if isinstance(values, list):
                    options.extend(str(value) for value in values[:20])
            filters.append({"id": f"filter_{len(filters) + 1}", "field": str(column), "label": str(column), "type": "select", "value": "全部", "options": options})
    if not filters:
        filters.append({"id": "filter_all", "field": "全局", "label": "全局筛选", "type": "text", "value": "", "options": []})
    return filters


def _chart_widgets(chart_paths: list[str]) -> list[dict[str, Any]]:
    widgets = []
    roles = ["trend", "comparison", "breakdown"]
    titles = {"trend": "趋势图", "comparison": "对比图", "breakdown": "结构拆解图"}
    for index, chart_path in enumerate(chart_paths[:3]):
        role = roles[min(index, len(roles) - 1)]
        widgets.append(
            {
                "id": f"chart_{index + 1}",
                "type": "chart",
                "chart_role": role,
                "title": titles[role],
                "chart_path": chart_path,
                "description": "沿用本轮分析生成的图表产物，可在图表结果页继续修改。",
            }
        )
    if not widgets:
        widgets.append(
            {
                "id": "chart_placeholder",
                "type": "chart",
                "chart_role": "placeholder",
                "title": "趋势图占位",
                "chart_path": "",
                "description": "当前任务尚未生成图表，可在后续刷新或重跑图表 Agent 后自动填充。",
            }
        )
    return widgets


def _default_dashboard_layout(widgets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    layout = []
    for index, widget in enumerate(widgets):
        widget_id = str(widget.get("id") or f"widget_{index + 1}")
        if widget.get("type") == "kpi":
            layout.append({"i": widget_id, "x": (index % 4) * 3, "y": 0, "w": 3, "h": 2})
        elif widget.get("type") == "chart":
            chart_index = sum(1 for item in layout if str(item.get("i", "")).startswith("chart_"))
            layout.append({"i": widget_id, "x": (chart_index % 2) * 6, "y": 3 + (chart_index // 2) * 4, "w": 6, "h": 4})
        else:
            layout.append({"i": widget_id, "x": 0, "y": 8 + index, "w": 12, "h": 4})
    return layout


def _table_columns(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows[:10]:
        for key in row.keys():
            if key not in seen:
                seen.append(str(key))
            if len(seen) >= 8:
                return seen
    return seen or ["暂无明细"]


def _dedupe_questions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for item in items:
        question = str(item.get("question") or "").strip()
        if not question or question in seen:
            continue
        seen.add(question)
        result.append(item)
    return result


def _overall_risk_level(issues: list[dict[str, Any]], validation_issues: list[dict[str, Any]]) -> str:
    high_count = sum(1 for item in issues if item.get("severity") == "high")
    medium_count = sum(1 for item in issues if item.get("severity") == "medium")
    if validation_issues or high_count >= 2:
        return "high"
    if high_count or medium_count >= 2:
        return "medium"
    return "low"


def _anomaly_summary(issues: list[dict[str, Any]], validation_issues: list[dict[str, Any]]) -> str:
    if not issues and not validation_issues:
        return "未发现需要优先处理的异常信号，可继续围绕业务问题下钻。"
    return f"发现 {len(issues)} 条数据/结果复核信号，验证阶段另有 {len(validation_issues)} 条提示。"


def _significance_limitations(row_count: int, numeric_columns: list[str], dimension_columns: list[str]) -> list[str]:
    limitations = []
    if row_count and row_count < 30:
        limitations.append("样本量低于 30，显著性检验结果容易不稳定。")
    if not numeric_columns:
        limitations.append("缺少明确数值指标，无法进行常规相关性或均值差异检验。")
    if not dimension_columns:
        limitations.append("缺少明确分组维度，暂不适合做分组差异显著性复核。")
    limitations.append("自动 sidecar 仅给出检验建议和风险提醒；如需正式显著性结论，应在脚本层加入可复现实验检验。")
    return limitations


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        if value is None:
            return 0.0
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _fmt_percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _clip_text(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    return clean if len(clean) <= limit else clean[:limit] + "..."


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
