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

    if isinstance(prediction_result, dict):
        _validate_prediction_result(prediction_result, issues, repair_suggestions)
    if not isinstance(report_data, dict):
        _issue(issues, "invalid_report_data", "high", "report_data.json must be a JSON object.", "report_data.json")

    _validate_charts(job_dir, issues, repair_suggestions)

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


def _validate_prediction_result(
    data: dict[str, Any],
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
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


def _validate_charts(
    job_dir: Path,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    charts_dir = job_dir / "charts"
    charts = list(charts_dir.glob("*.png")) if charts_dir.exists() else []
    if not [path for path in charts if path.is_file() and path.stat().st_size > 0]:
        _issue(issues, "missing_chart", "high", "No PNG chart generated under charts/.", str(charts_dir))
        _suggest(repair_suggestions, "Generate at least one PNG chart under output_dir/charts.")


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
