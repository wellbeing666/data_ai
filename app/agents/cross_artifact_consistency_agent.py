import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONSISTENCY_REPORT_FILENAME = "consistency_report.json"
SUGGESTED_REWRITES_FILENAME = "suggested_rewrites.json"


def create_cross_artifact_consistency_report(
    *,
    job_dir: Path | str,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    report_data: dict[str, Any] | None = None,
    dashboard: dict[str, Any] | None = None,
    chart_paths: list[str] | None = None,
    validation_result: dict[str, Any] | None = None,
    debate_reflection: dict[str, Any] | None = None,
    workflow_type: str = "auto_repair",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Check consistency across generated artifacts without re-analyzing raw data.

    This agent deliberately treats the generated artifacts as its input surface. It does
    not load the original dataset rows; instead it scans semantic products such as
    explanation.json, report_data.json, dashboard widgets, PPT outline, quality review,
    evidence chain, chart captions and follow-up answers.
    """
    job_path = Path(job_dir)
    artifacts = _load_artifact_bundle(
        job_path=job_path,
        report_data=report_data,
        dashboard=dashboard,
        validation_result=validation_result,
        debate_reflection=debate_reflection,
    )
    canonical = _canonical_context(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        artifacts=artifacts,
        chart_paths=chart_paths or [],
        workflow_type=workflow_type,
    )
    texts = _artifact_texts(artifacts, chart_paths or [])

    checks = [
        _check_artifact_coverage(artifacts),
        _check_date_range(canonical, texts),
        _check_metric_scope(canonical, dataset_profile, texts),
        _check_sample_scope(canonical, texts),
        _check_unit_and_baseline(canonical, texts),
        _check_direction_consistency(canonical, texts),
        _check_dashboard_alignment(canonical, artifacts),
    ]
    checks = [check for check in checks if check]
    rewrites = _suggest_rewrites(checks, canonical)
    risk_level = _overall_risk(checks)
    passed = all(str(check.get("status")) == "pass" for check in checks)
    report = {
        "schema_version": "1.0",
        "agent": "Cross Artifact Consistency Agent",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "user_goal": user_goal,
        "workflow_type": workflow_type,
        "passed": passed,
        "risk_level": risk_level,
        "canonical_context": canonical,
        "artifact_inventory": {name: _artifact_inventory_item(value) for name, value in artifacts.items()},
        "checks": checks,
        "inconsistent_claims": [check for check in checks if str(check.get("status")) != "pass"],
        "summary": _summary(passed, risk_level, checks),
        "limitations": [
            "该 Agent 只扫描已生成产物的一致性，不重新读取原始数据或重新计算指标。",
            "对自然语言文本的日期、单位和方向识别采用规则提取，复杂隐含口径仍建议人工复核。",
        ],
    }
    return report, rewrites


def write_cross_artifact_consistency_outputs(
    *,
    job_dir: Path | str,
    report: dict[str, Any],
    suggested_rewrites: list[dict[str, Any]],
) -> dict[str, str]:
    job_path = Path(job_dir)
    report_path = job_path / CONSISTENCY_REPORT_FILENAME
    rewrites_path = job_path / SUGGESTED_REWRITES_FILENAME
    _write_json(report_path, report)
    _write_json(rewrites_path, {"agent": "Cross Artifact Consistency Agent", "suggested_rewrites": suggested_rewrites})
    return {"consistency_report": str(report_path), "suggested_rewrites": str(rewrites_path)}


def _load_artifact_bundle(
    *,
    job_path: Path,
    report_data: dict[str, Any] | None,
    dashboard: dict[str, Any] | None,
    validation_result: dict[str, Any] | None,
    debate_reflection: dict[str, Any] | None,
) -> dict[str, Any]:
    bundle: dict[str, Any] = {}
    for filename in (
        "analysis_ir.json",
        "dataset_profile.json",
        "analysis_result.json",
        "prediction_result.json",
        "explanation.json",
        "prediction_explanation.json",
        "quality_review.json",
        "evidence_chain.json",
        "pptx_preview.json",
        "report_data.json",
        "dashboard_config.json",
        "validation_result.json",
        "prediction_validation_result.json",
        "debate_reflection.json",
    ):
        value = _read_json_if_exists(job_path / filename)
        if value:
            bundle[filename] = value
    if report_data:
        bundle["report_data.json"] = report_data
    if dashboard:
        bundle["dashboard_config.json"] = dashboard
    if validation_result:
        bundle["validation_result.json"] = validation_result
    if debate_reflection:
        bundle["debate_reflection.json"] = debate_reflection
    report_text = _read_text_if_exists(job_path / "report.md")
    if report_text:
        bundle["report.md"] = report_text
    followups_dir = job_path / "followups"
    if followups_dir.exists():
        followups = []
        for path in sorted(followups_dir.glob("followup_*.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:20]:
            value = _read_json_if_exists(path)
            if value:
                followups.append(value)
        if followups:
            bundle["followups"] = followups
    return bundle


def _canonical_context(
    *,
    user_goal: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    artifacts: dict[str, Any],
    chart_paths: list[str],
    workflow_type: str,
) -> dict[str, Any]:
    analysis_ir = artifacts.get("analysis_ir.json") if isinstance(artifacts.get("analysis_ir.json"), dict) else {}
    metrics = _canonical_metrics(analysis_ir, result_payload, dataset_profile)
    dimensions = _canonical_dimensions(analysis_ir, dataset_profile)
    time_window = analysis_ir.get("time_window") if isinstance(analysis_ir, dict) and isinstance(analysis_ir.get("time_window"), dict) else {}
    filters = analysis_ir.get("filters") if isinstance(analysis_ir, dict) and isinstance(analysis_ir.get("filters"), list) else []
    intervention = result_payload.get("intervention") if isinstance(result_payload.get("intervention"), dict) else {}
    return {
        "goal": user_goal,
        "workflow_type": workflow_type,
        "task_type": str(result_payload.get("task_type") or (analysis_ir or {}).get("task_type") or ""),
        "row_count": _safe_int(dataset_profile.get("row_count")),
        "column_count": _safe_int(dataset_profile.get("column_count")) or len(_string_list(dataset_profile.get("columns"))),
        "metrics": metrics,
        "dimensions": dimensions,
        "time_window": {
            "field": str(time_window.get("field") or ""),
            "start": str(time_window.get("start") or ""),
            "end": str(time_window.get("end") or ""),
        },
        "filters": filters,
        "intervention": intervention,
        "chart_count": len(chart_paths),
        "chart_captions": [_chart_caption(path) for path in chart_paths],
    }


def _canonical_metrics(analysis_ir: Any, result_payload: dict[str, Any], dataset_profile: dict[str, Any]) -> list[str]:
    metrics: list[str] = []
    if isinstance(analysis_ir, dict):
        for item in _as_list(analysis_ir.get("metrics")):
            if isinstance(item, dict):
                for key in ("source_column", "name", "label"):
                    value = str(item.get(key) or "").strip()
                    if value:
                        metrics.append(value)
            elif str(item or "").strip():
                metrics.append(str(item).strip())
    for key in ("target_metric", "metric"):
        value = str(result_payload.get(key) or "").strip()
        if value:
            metrics.append(value)
    numeric_summary = dataset_profile.get("numeric_summary") if isinstance(dataset_profile.get("numeric_summary"), dict) else {}
    if not metrics:
        metrics.extend(str(key) for key in numeric_summary.keys())
    return _dedupe(metrics)


def _canonical_dimensions(analysis_ir: Any, dataset_profile: dict[str, Any]) -> list[str]:
    dimensions: list[str] = []
    if isinstance(analysis_ir, dict):
        for item in _as_list(analysis_ir.get("dimensions")):
            if isinstance(item, dict):
                for key in ("source_column", "name", "label"):
                    value = str(item.get(key) or "").strip()
                    if value:
                        dimensions.append(value)
            elif str(item or "").strip():
                dimensions.append(str(item).strip())
    text_summary = dataset_profile.get("text_summary") if isinstance(dataset_profile.get("text_summary"), dict) else {}
    if not dimensions:
        dimensions.extend(str(key) for key in text_summary.keys())
    return _dedupe(dimensions)


def _artifact_texts(artifacts: dict[str, Any], chart_paths: list[str]) -> list[dict[str, str]]:
    texts: list[dict[str, str]] = []
    for name, value in artifacts.items():
        _collect_texts(name, value, texts)
    for index, path in enumerate(chart_paths):
        texts.append({"artifact": "chart_caption", "field": f"charts[{index}]", "text": _chart_caption(path)})
    return [item for item in texts if item.get("text")]


def _collect_texts(artifact: str, value: Any, output: list[dict[str, str]], field: str = "$", depth: int = 0) -> None:
    if depth > 5:
        return
    if isinstance(value, str):
        text = _clip(value, 1000)
        if text:
            output.append({"artifact": artifact, "field": field, "text": text})
        return
    if isinstance(value, (int, float, bool)) or value is None:
        return
    if isinstance(value, list):
        for index, item in enumerate(value[:30]):
            _collect_texts(artifact, item, output, f"{field}[{index}]", depth + 1)
        return
    if isinstance(value, dict):
        preferred = {"summary", "title", "description", "text", "answer", "question", "finding", "recommendation", "limitation", "bullet", "revised_summary"}
        for key, item in value.items():
            next_field = f"{field}.{key}"
            if isinstance(item, str) and (str(key) in preferred or len(item) >= 12):
                _collect_texts(artifact, item, output, next_field, depth + 1)
            elif isinstance(item, (dict, list)):
                _collect_texts(artifact, item, output, next_field, depth + 1)


def _check_artifact_coverage(artifacts: dict[str, Any]) -> dict[str, Any]:
    expected_any = ["explanation.json", "prediction_explanation.json", "report_data.json", "dashboard_config.json", "quality_review.json", "evidence_chain.json"]
    present = [name for name in expected_any if artifacts.get(name)]
    status = "pass" if len(present) >= 3 else "warning"
    return _check(
        "artifact_coverage",
        status,
        "artifact_inventory",
        "已扫描主要分析产物。" if status == "pass" else "可扫描产物较少，跨产物一致性检查覆盖不足。",
        [", ".join(present) or "未找到核心产物"],
        "确保 explanation、report_data、dashboard_config、quality_review 等产物完成后再复核。",
        "low",
    )


def _check_date_range(canonical: dict[str, Any], texts: list[dict[str, str]]) -> dict[str, Any]:
    time_window = canonical.get("time_window") if isinstance(canonical.get("time_window"), dict) else {}
    canonical_months = _months_from_range(str(time_window.get("start") or ""), str(time_window.get("end") or ""))
    mentions = _date_mentions(texts)
    if canonical_months:
        conflicts = [item for item in mentions if item["month"] and item["month"] not in canonical_months]
        if conflicts:
            return _check(
                "date_range_conflict",
                "warning",
                "date_range",
                "部分产物提到的月份不在 Analysis IR 锁定的时间窗内。",
                [f"{item['artifact']} {item['field']} -> {item['month']}" for item in conflicts[:5]],
                f"统一写为 {canonical_months[0]} 至 {canonical_months[-1]}，或明确说明该日期来自辅助背景。",
                "medium",
            )
        return _check("date_range_consistent", "pass", "date_range", "日期范围与 Analysis IR 时间窗一致或未发现冲突。", [], "", "low")
    unique_months = sorted({item["month"] for item in mentions if item.get("month")})
    if len(unique_months) >= 4:
        return _check(
            "date_range_unanchored",
            "warning",
            "date_range",
            "产物中出现多个日期，但 Analysis IR 未提供明确时间窗。",
            unique_months[:8],
            "建议在 Analysis IR 或报告开头写清分析时间范围。",
            "low",
        )
    return _check("date_range_not_applicable", "pass", "date_range", "未发现需要复核的日期范围冲突。", [], "", "low")


def _check_metric_scope(canonical: dict[str, Any], dataset_profile: dict[str, Any], texts: list[dict[str, str]]) -> dict[str, Any]:
    canonical_metrics = set(_normalize_token(item) for item in _string_list(canonical.get("metrics")) if item)
    if not canonical_metrics:
        return _check("metric_scope_no_anchor", "warning", "metric_scope", "未识别到统一核心指标，难以检查跨产物指标口径。", [], "建议在 Analysis IR 中明确 metrics。", "low")
    candidate_metrics = set(_normalize_token(item) for item in _known_metric_names(dataset_profile) if item)
    candidate_metrics.update(_normalize_token(item) for item in ["销量", "销售额", "收入", "利润", "成本", "退货率", "转化率", "不良率", "成绩", "房价", "响应时长", "排队时间"])
    candidate_metrics.discard("")
    unknown_mentions: list[str] = []
    for item in texts:
        normalized_text = _normalize_token(item["text"])
        for metric in candidate_metrics:
            if metric and metric in normalized_text and metric not in canonical_metrics:
                unknown_mentions.append(f"{item['artifact']} {item['field']} 提到 {metric}")
    unknown_mentions = _dedupe(unknown_mentions)
    if unknown_mentions:
        return _check(
            "metric_scope_drift",
            "warning",
            "metric_scope",
            "部分产物提到了非核心指标，可能造成指标口径漂移。",
            unknown_mentions[:6],
            f"将核心指标统一为 {', '.join(_string_list(canonical.get('metrics'))[:4])}；如保留辅助指标，需要明确其为补充参考。",
            "medium",
        )
    return _check("metric_scope_consistent", "pass", "metric_scope", "未发现核心指标口径漂移。", [], "", "low")


def _check_sample_scope(canonical: dict[str, Any], texts: list[dict[str, str]]) -> dict[str, Any]:
    row_count = _safe_int(canonical.get("row_count"))
    if not row_count:
        return _check("sample_scope_no_anchor", "warning", "sample_scope", "缺少 dataset_profile.row_count，无法核对样本行数口径。", [], "建议在数据画像中保留 row_count。", "low")
    mismatches: list[str] = []
    pattern_a = re.compile(r"(?:样本|数据|记录|行数|当前数据|当前记录).{0,12}?(\d{1,7})\s*行")
    pattern_b = re.compile(r"(\d{1,7})\s*行.{0,12}?(?:样本|数据|记录)")
    for item in texts:
        text = item["text"]
        for match in list(pattern_a.finditer(text)) + list(pattern_b.finditer(text)):
            number = int(match.group(1))
            context = text[max(0, match.start() - 12): match.end() + 12]
            if "前" in context or "Top" in context or "展示" in context:
                continue
            if number != row_count:
                mismatches.append(f"{item['artifact']} {item['field']} 写作 {number} 行，数据画像为 {row_count} 行")
    if mismatches:
        return _check(
            "sample_scope_conflict",
            "warning",
            "sample_scope",
            "部分产物中的样本行数与 dataset_profile 不一致。",
            _dedupe(mismatches)[:5],
            f"统一样本口径为 {row_count} 行；若页面只展示筛选后的行数，应写明“当前筛选命中”。",
            "medium",
        )
    return _check("sample_scope_consistent", "pass", "sample_scope", "未发现样本行数口径冲突。", [], "", "low")


def _check_unit_and_baseline(canonical: dict[str, Any], texts: list[dict[str, str]]) -> dict[str, Any]:
    intervention = canonical.get("intervention") if isinstance(canonical.get("intervention"), dict) else {}
    if not intervention:
        return _check("unit_baseline_not_applicable", "pass", "unit_and_baseline", "本轮不是情景预测或未提供干预变量，暂不检查干预单位。", [], "", "low")
    change_type = str(intervention.get("change_type") or "")
    change_value = intervention.get("change_value")
    variable = str(intervention.get("column") or intervention.get("variable") or "干预变量")
    conflicts: list[str] = []
    if change_type == "absolute" and change_value not in (None, ""):
        value_text = str(int(change_value)) if isinstance(change_value, (int, float)) and float(change_value).is_integer() else str(change_value)
        for item in texts:
            text = item["text"]
            if variable and variable in text and f"{value_text}%" in text:
                conflicts.append(f"{item['artifact']} {item['field']} 将绝对增量 {value_text} 写成百分比。")
    if conflicts:
        return _check(
            "unit_baseline_conflict",
            "fail",
            "unit_and_baseline",
            "情景预测干预单位存在冲突：绝对增量被写成百分比。",
            conflicts[:5],
            f"统一写为“{variable} 增加 {change_value}”，不要写作“{change_value}%”。",
            "high",
        )
    return _check("unit_baseline_consistent", "pass", "unit_and_baseline", "未发现干预单位或涨跌幅基准冲突。", [], "", "low")


def _check_direction_consistency(canonical: dict[str, Any], texts: list[dict[str, str]]) -> dict[str, Any]:
    important = [item for item in texts if item["artifact"] in {"explanation.json", "prediction_explanation.json", "report_data.json", "report.md", "pptx_preview.json"}]
    metric_tokens = [_normalize_token(item) for item in _string_list(canonical.get("metrics"))]
    direction_mentions: dict[str, set[str]] = {}
    for item in important:
        text = item["text"]
        normalized = _normalize_token(text)
        if metric_tokens and not any(token and token in normalized for token in metric_tokens):
            continue
        has_down = any(token in text for token in ("下降", "降低", "下滑", "减少", "decline", "decrease"))
        has_up = any(token in text for token in ("上升", "增长", "提升", "增加", "increase", "growth"))
        if has_down or has_up:
            key = f"{item['artifact']} {item['field']}"
            direction_mentions[key] = set()
            if has_down:
                direction_mentions[key].add("down")
            if has_up:
                direction_mentions[key].add("up")
    all_directions = set().union(*direction_mentions.values()) if direction_mentions else set()
    if {"up", "down"}.issubset(all_directions):
        evidence = [f"{key}: {','.join(sorted(value))}" for key, value in direction_mentions.items()]
        return _check(
            "direction_conflict_possible",
            "warning",
            "direction_consistency",
            "核心产物同时出现上升和下降方向表述，可能是总体与分组口径未写清。",
            evidence[:6],
            "补充“总体趋势”“分组局部变化”“预测变化方向”等限定词，避免读者理解为冲突结论。",
            "medium",
        )
    return _check("direction_consistent", "pass", "direction_consistency", "未发现核心方向表述冲突。", [], "", "low")


def _check_dashboard_alignment(canonical: dict[str, Any], artifacts: dict[str, Any]) -> dict[str, Any]:
    dashboard = artifacts.get("dashboard_config.json") if isinstance(artifacts.get("dashboard_config.json"), dict) else {}
    widgets = dashboard.get("widgets") if isinstance(dashboard.get("widgets"), list) else []
    if not widgets:
        return _check("dashboard_not_available", "warning", "dashboard_alignment", "未找到 Dashboard widgets，无法检查看板与报告口径一致性。", [], "分析完成后建议刷新或重跑 Dashboard 生成 Agent。", "low")
    metric_tokens = [_normalize_token(item) for item in _string_list(canonical.get("metrics"))]
    widget_text = _normalize_token(" ".join(str(widget.get("title") or "") + " " + str(widget.get("description") or "") for widget in widgets if isinstance(widget, dict)))
    if metric_tokens and not any(token and token in widget_text for token in metric_tokens):
        return _check(
            "dashboard_metric_alignment_warning",
            "warning",
            "dashboard_alignment",
            "Dashboard 标题与描述未显式包含核心指标，用户可能误解监控口径。",
            [f"核心指标：{', '.join(_string_list(canonical.get('metrics'))[:4])}"],
            "在关键 widget 标题或描述中写明核心指标及其聚合方式。",
            "low",
        )
    return _check("dashboard_aligned", "pass", "dashboard_alignment", "Dashboard widgets 与核心指标口径基本一致。", [], "", "low")


def _suggest_rewrites(checks: list[dict[str, Any]], canonical: dict[str, Any]) -> list[dict[str, Any]]:
    rewrites: list[dict[str, Any]] = []
    metric_text = "、".join(_string_list(canonical.get("metrics"))[:4]) or "核心指标"
    row_count = _safe_int(canonical.get("row_count"))
    time_window = canonical.get("time_window") if isinstance(canonical.get("time_window"), dict) else {}
    range_text = _range_label(str(time_window.get("start") or ""), str(time_window.get("end") or ""))
    canonical_sentence = f"本轮分析口径：时间范围{range_text or '以 Analysis IR 为准'}，核心指标为 {metric_text}，样本量为 {row_count or '数据画像记录数'} 行。"
    for check in checks:
        if str(check.get("status")) == "pass":
            continue
        evidence = _string_list(check.get("evidence"))
        rewrites.append(
            {
                "artifact": str(check.get("topic") or "multi_artifact"),
                "field": str(check.get("check_id") or "consistency_check"),
                "current_text": evidence[0] if evidence else str(check.get("finding") or ""),
                "suggested_text": canonical_sentence,
                "rationale": str(check.get("suggested_action") or "统一多产物中的业务口径。"),
            }
        )
    return rewrites[:10]


def _check(check_id: str, status: str, topic: str, finding: str, evidence: list[str], suggested_action: str, severity: str) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": status,
        "severity": severity,
        "topic": topic,
        "finding": finding,
        "evidence": evidence,
        "suggested_action": suggested_action,
    }


def _overall_risk(checks: list[dict[str, Any]]) -> str:
    severities = {str(check.get("severity") or "low") for check in checks if str(check.get("status")) != "pass"}
    if "high" in severities:
        return "high"
    if "medium" in severities:
        return "medium"
    if "low" in severities:
        return "low"
    return "low"


def _summary(passed: bool, risk_level: str, checks: list[dict[str, Any]]) -> str:
    issue_count = len([check for check in checks if str(check.get("status")) != "pass"])
    if passed:
        return "跨产物口径一致性检查通过，未发现日期范围、指标、样本量、单位或 Dashboard 口径冲突。"
    return f"跨产物口径一致性检查发现 {issue_count} 个需复核点，最高风险级别为 {risk_level}。建议优先查看 suggested_rewrites.json。"


def _date_mentions(texts: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    patterns = [
        re.compile(r"(20\d{2})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?"),
        re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月"),
    ]
    for item in texts:
        for pattern in patterns:
            for match in pattern.finditer(item["text"]):
                year = int(match.group(1))
                month = int(match.group(2))
                if 1 <= month <= 12:
                    result.append({"artifact": item["artifact"], "field": item["field"], "month": f"{year:04d}-{month:02d}"})
    return result


def _months_from_range(start: str, end: str) -> list[str]:
    start_month = _month_from_text(start)
    end_month = _month_from_text(end) or start_month
    if not start_month:
        return []
    sy, sm = [int(part) for part in start_month.split("-")]
    ey, em = [int(part) for part in end_month.split("-")]
    months: list[str] = []
    year, month = sy, sm
    for _ in range(72):
        months.append(f"{year:04d}-{month:02d}")
        if year == ey and month == em:
            break
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def _month_from_text(value: str) -> str:
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})", str(value or ""))
    if not match:
        return ""
    month = int(match.group(2))
    if not 1 <= month <= 12:
        return ""
    return f"{int(match.group(1)):04d}-{month:02d}"


def _range_label(start: str, end: str) -> str:
    months = _months_from_range(start, end)
    if not months:
        return ""
    return months[0] if len(months) == 1 else f"{months[0]} 至 {months[-1]}"


def _known_metric_names(dataset_profile: dict[str, Any]) -> list[str]:
    metrics = []
    numeric_summary = dataset_profile.get("numeric_summary") if isinstance(dataset_profile.get("numeric_summary"), dict) else {}
    metrics.extend(str(key) for key in numeric_summary.keys())
    columns = _string_list(dataset_profile.get("columns"))
    metric_keywords = ("率", "量", "额", "价", "分", "数", "时长", "时间", "成本", "收入", "利润", "销量", "销售")
    metrics.extend(column for column in columns if any(keyword in column for keyword in metric_keywords))
    return _dedupe(metrics)


def _normalize_token(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "").lower())


def _artifact_inventory_item(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"type": "object", "keys": list(value.keys())[:12]}
    if isinstance(value, list):
        return {"type": "array", "items": len(value)}
    if isinstance(value, str):
        return {"type": "text", "length": len(value)}
    return {"type": type(value).__name__}


def _chart_caption(path: str) -> str:
    filename = Path(str(path)).name
    stem = re.sub(r"\.[^.]+$", "", filename)
    return re.sub(r"[_\-]+", " ", stem).strip() or filename


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _clip(value: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_text_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
