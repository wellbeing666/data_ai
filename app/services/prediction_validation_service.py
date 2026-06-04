import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status


JOB_ROOT = Path("storage/jobs")
VALIDATION_RESULT_FILENAME = "prediction_validation_result.json"
REQUIRED_KEYS = {
    "task_type",
    "scenario_summary",
    "target_metric",
    "intervention",
    "entity_dimension",
    "top_impacted_entities",
    "baseline_summary",
    "predicted_summary",
    "model_info",
    "limitations",
    "charts",
}


def validate_prediction_outputs(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id)
    issues: list[dict[str, str | None]] = []
    repair_suggestions: list[dict[str, str]] = []

    execution_result = _load_json(job_dir / "execution_result.json", issues, repair_suggestions)
    prediction_result = _load_json(job_dir / "prediction_result.json", issues, repair_suggestions)
    report_data = _load_json(job_dir / "report_data.json", issues, repair_suggestions)

    if execution_result and execution_result.get("success") is not True:
        _issue(issues, "execution_failed", "critical", "Prediction script did not execute successfully.", "execution_result.json")
        _suggest(repair_suggestions, "Fix stderr and regenerate the prediction script.")

    is_unsupported_result = False
    if isinstance(prediction_result, dict):
        normalized_prediction, changed = _normalize_prediction_result(prediction_result)
        if changed:
            prediction_result = normalized_prediction
            _write_json(job_dir / "prediction_result.json", prediction_result)
            if isinstance(report_data, dict):
                report_data = _sync_report_data_with_prediction(report_data, prediction_result)
                _write_json(job_dir / "report_data.json", report_data)
        is_unsupported_result = _is_unsupported_prediction_result(prediction_result)
        _validate_prediction_result(prediction_result, issues, repair_suggestions)
        if is_unsupported_result:
            _validate_missed_transformable_intervention(job_dir, prediction_result, issues, repair_suggestions)
    if not isinstance(report_data, dict):
        _issue(issues, "invalid_report_data", "high", "report_data.json must be a JSON object.", "report_data.json")

    _validate_charts(job_dir, issues, repair_suggestions, require_chart=not is_unsupported_result)

    severity = _overall_severity(issues)
    should_retry = severity in {"critical", "high"}
    result = {
        "passed": not should_retry,
        "issues": issues,
        "severity": severity,
        "repair_suggestions": _dedupe(repair_suggestions),
        "should_retry": should_retry,
    }
    _write_json(job_dir / VALIDATION_RESULT_FILENAME, result)
    _write_json(job_dir / "validation_result.json", result)
    return result


def _normalize_prediction_result(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    normalized = dict(data)
    changed = False

    entities = normalized.get("top_impacted_entities")
    if isinstance(entities, list):
        normalized_entities = []
        for index, item in enumerate(entities):
            normalized_item = _normalize_entity_item(item, index)
            normalized_entities.append(normalized_item)
            if normalized_item != item:
                changed = True
        normalized["top_impacted_entities"] = normalized_entities

    if not isinstance(normalized.get("model_info"), dict):
        normalized["model_info"] = {"method": "unknown"}
        changed = True
    elif not normalized["model_info"].get("method"):
        normalized["model_info"] = {**normalized["model_info"], "method": "unknown"}
        changed = True

    return normalized, changed


def _normalize_entity_item(item: Any, index: int) -> dict[str, Any]:
    if isinstance(item, dict):
        normalized = dict(item)
    else:
        normalized = {"entity": f"对象{index + 1}"}

    entity = str(normalized.get("entity") or f"对象{index + 1}")
    baseline = _safe_float(normalized.get("baseline_value"), 0.0)
    predicted = _safe_float(normalized.get("predicted_value"), baseline)
    absolute_change = _safe_float(normalized.get("absolute_change"), predicted - baseline)
    if "predicted_value" not in normalized and "absolute_change" in normalized:
        predicted = baseline + absolute_change
    if "absolute_change" not in normalized:
        absolute_change = predicted - baseline
    percent_change = _safe_float(
        normalized.get("percent_change"),
        absolute_change / baseline if abs(baseline) > 1e-9 else 0.0,
    )
    direction = str(normalized.get("direction") or ("增加" if absolute_change >= 0 else "降低"))
    explanation = str(normalized.get("explanation") or "").strip()
    if not explanation:
        explanation = f"该对象在当前情景下预测值{direction}约 {abs(absolute_change):,.2f}，该结果来自模型模拟估计，需结合业务背景验证。"

    normalized.update(
        {
            "entity": entity,
            "baseline_value": baseline,
            "predicted_value": predicted,
            "absolute_change": absolute_change,
            "percent_change": percent_change,
            "direction": direction,
            "explanation": explanation,
        }
    )
    return normalized


def _sync_report_data_with_prediction(report_data: dict[str, Any], prediction_result: dict[str, Any]) -> dict[str, Any]:
    synced = dict(report_data)
    if "top_impacted_entities" in prediction_result:
        synced["top_impacted_entities"] = prediction_result["top_impacted_entities"]
    if "model_info" in prediction_result:
        synced["model_info"] = prediction_result["model_info"]
    if "charts" in prediction_result:
        synced["charts"] = prediction_result["charts"]
    if "limitations" in prediction_result:
        synced["limitations"] = prediction_result["limitations"]
    return synced


def _validate_prediction_result(
    data: dict[str, Any],
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    if _is_unsupported_prediction_result(data):
        _validate_unsupported_prediction_result(data, issues, repair_suggestions)
        return

    missing = sorted(REQUIRED_KEYS - set(data.keys()))
    if missing:
        _issue(issues, "missing_prediction_keys", "critical", f"Missing keys: {', '.join(missing)}", "prediction_result.json")
        _suggest(repair_suggestions, "Write prediction_result.json with the required what-if prediction schema.")
    if data.get("task_type") != "what_if_prediction":
        _issue(issues, "invalid_task_type", "critical", "task_type must be what_if_prediction.", "prediction_result.json")
    entities = data.get("top_impacted_entities")
    if not isinstance(entities, list) or not entities:
        _issue(issues, "empty_top_impacted_entities", "high", "top_impacted_entities must be a non-empty list.", "prediction_result.json")
        _suggest(repair_suggestions, "Rank at least one impacted entity or write an overall row.")
    else:
        for index, item in enumerate(entities[:10]):
            if not isinstance(item, dict):
                _issue(issues, "invalid_entity_item", "high", f"Entity item {index} must be an object.", "prediction_result.json")
                continue
            for key in ("entity", "baseline_value", "predicted_value", "absolute_change", "percent_change", "direction", "explanation"):
                if key not in item:
                    _issue(issues, "missing_entity_field", "medium", f"Entity item {index} missing {key}.", "prediction_result.json")
    model_info = data.get("model_info")
    if not isinstance(model_info, dict) or not model_info.get("method"):
        _issue(issues, "missing_model_info", "medium", "model_info.method should explain the model or fallback used.", "prediction_result.json")



def _is_unsupported_prediction_result(data: dict[str, Any]) -> bool:
    model_info = data.get("model_info") if isinstance(data.get("model_info"), dict) else {}
    method = str(model_info.get("method") or "")
    return data.get("status") == "unsupported" or method == "unsupported_missing_required_column"


def _validate_unsupported_prediction_result(
    data: dict[str, Any],
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    required = {"task_type", "status", "scenario_summary", "target_metric", "intervention", "baseline_summary", "predicted_summary", "model_info", "limitations", "charts", "unsupported_reason"}
    missing = sorted(required - set(data.keys()))
    if missing:
        _issue(issues, "missing_unsupported_keys", "critical", f"Missing keys: {', '.join(missing)}", "prediction_result.json")
        _suggest(repair_suggestions, "Write an unsupported prediction_result.json with unsupported_reason and baseline summary.")
    if data.get("task_type") != "what_if_prediction":
        _issue(issues, "invalid_task_type", "critical", "task_type must be what_if_prediction.", "prediction_result.json")
    if data.get("status") != "unsupported":
        _issue(issues, "invalid_unsupported_status", "high", "Unsupported prediction results must set status to unsupported.", "prediction_result.json")
    if not str(data.get("unsupported_reason") or "").strip():
        _issue(issues, "missing_unsupported_reason", "high", "unsupported_reason must explain which required field is absent.", "prediction_result.json")
    intervention = data.get("intervention") if isinstance(data.get("intervention"), dict) else {}
    if str(intervention.get("column") or "").strip():
        _issue(issues, "unsupported_has_intervention_column", "high", "Unsupported result must not assign a substitute intervention column.", "prediction_result.json")
    charts = data.get("charts")
    if not isinstance(charts, list):
        _issue(issues, "invalid_unsupported_charts", "medium", "Unsupported prediction results should set charts to an array; an empty array is allowed when no numeric chart can be generated.", "prediction_result.json")
    if not str(data.get("no_chart_reason") or data.get("chart_notice") or "").strip() and charts == []:
        _issue(issues, "missing_no_chart_reason", "medium", "Unsupported prediction results without charts should explain why no chart is generated.", "prediction_result.json")
    model_info = data.get("model_info") if isinstance(data.get("model_info"), dict) else {}
    if model_info.get("method") != "unsupported_missing_required_column":
        _issue(issues, "invalid_unsupported_model_method", "medium", "model_info.method should be unsupported_missing_required_column.", "prediction_result.json")


def _validate_missed_transformable_intervention(
    job_dir: Path,
    data: dict[str, Any],
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    dataset_profile = _read_json_if_exists(job_dir / "dataset_profile.json") or {}
    hypothesis_plan = _read_json_if_exists(job_dir / "hypothesis_plan.json") or {}
    prediction_plan = _read_json_if_exists(job_dir / "prediction_plan.json") or {}
    columns = [str(column) for column in dataset_profile.get("columns", [])] if isinstance(dataset_profile, dict) else []
    text = " ".join(
        [
            json.dumps(hypothesis_plan, ensure_ascii=False),
            json.dumps(prediction_plan, ensure_ascii=False),
            str(data.get("scenario_summary") or ""),
            str(data.get("unsupported_reason") or ""),
        ]
    ).lower()

    if not (_mentions_house_age(text) and _has_price_target(columns) and _has_house_age_source(columns)):
        return

    _issue(
        issues,
        "missed_transformable_intervention",
        "high",
        "当前数据包含房价目标和可转换的房龄来源字段，不能将房龄情景误判为缺少字段。",
        "prediction_result.json",
    )
    _suggest(
        repair_suggestions,
        "将房龄映射为 HouseAge；若没有 HouseAge 但存在 YearBuilt/BuiltYear，则按建造年份反向变化执行模拟，并重新生成预测图表。",
    )


def _read_json_if_exists(path: Path) -> Any | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _mentions_house_age(text: str) -> bool:
    return any(token in text for token in ("房龄", "房屋年龄", "建筑年龄", "楼龄", "house age", "building age"))


def _has_price_target(columns: list[str]) -> bool:
    return any(column.lower() == "saleprice" or column in {"房价", "总价", "售价", "价格"} for column in columns)


def _has_house_age_source(columns: list[str]) -> bool:
    return any(
        column.lower().replace("_", "") in {"houseage", "buildingage", "yearbuilt", "builtyear"}
        or column in {"房龄", "房屋年龄", "建筑年龄", "楼龄", "建成年份", "建造年份", "建筑年份"}
        for column in columns
    )


def _validate_charts(
    job_dir: Path,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
    *,
    require_chart: bool = True,
) -> None:
    charts_dir = job_dir / "charts"
    charts = list(charts_dir.glob("*.png")) if charts_dir.exists() else []
    existing_charts = [path for path in charts if path.is_file() and path.stat().st_size > 0]
    if not existing_charts and require_chart:
        _issue(issues, "missing_chart", "high", "No PNG chart generated under charts/.", str(charts_dir))
        _suggest(repair_suggestions, "Generate at least one meaningful PNG chart under output_dir/charts for supported prediction scenarios.")


def _load_json(
    path: Path,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> Any | None:
    if not path.exists():
        _issue(issues, "missing_artifact", "critical", f"Missing required artifact: {path.name}.", str(path))
        _suggest(repair_suggestions, f"Regenerate the script so it writes {path.name}.")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _issue(issues, "invalid_json", "critical", f"{path.name} is not valid JSON: {exc}", str(path))
        return None


def _get_job_dir(job_id: str) -> Path:
    if not job_id or Path(job_id).name != job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id.")
    job_dir = JOB_ROOT / job_id
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job_dir


def _safe_float(value: Any, default: float) -> float:
    try:
        if value in (None, ""):
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _issue(
    issues: list[dict[str, str | None]],
    issue_type: str,
    severity: str,
    message: str,
    location: str | None = None,
) -> None:
    issues.append({"issue_type": issue_type, "severity": severity, "message": message, "location": location})


def _suggest(suggestions: list[dict[str, str]], message: str) -> None:
    suggestions.append({"target_agent": "prediction_code_agent", "message": message})


def _overall_severity(issues: list[dict[str, str | None]]) -> str:
    order = {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    if not issues:
        return "none"
    return max((str(issue.get("severity", "none")) for issue in issues), key=lambda item: order.get(item, 0))


def _dedupe(suggestions: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    deduped = []
    for item in suggestions:
        key = (item["target_agent"], item["message"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
