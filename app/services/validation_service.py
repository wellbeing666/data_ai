import json
import math
import re
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status


JOB_ROOT = Path("storage/jobs")
VALIDATION_RESULT_FILENAME = "validation_result.json"
SEVERITY_ORDER = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}
METRIC_KEYWORDS = (
    "average",
    "avg",
    "count",
    "excellent_rate",
    "max",
    "mean",
    "metric",
    "min",
    "pass_rate",
    "rate",
    "ratio",
    "score",
    "total",
    "value",
)
METRIC_TOKENS = {
    "average",
    "avg",
    "count",
    "max",
    "mean",
    "metric",
    "min",
    "rate",
    "ratio",
    "score",
    "total",
    "value",
}
SKIP_METRIC_PATH_KEYS = {
    "repair_context",
    "previous_execution_result",
    "previous_validation_result",
    "artifacts",
}
CONCLUSION_KEYS = {
    "chart_explanations",
    "conclusion",
    "conclusions",
    "findings",
    "insights",
    "key_findings",
    "recommendations",
    "summary",
}
DATA_KEYS = {
    "data",
    "metrics",
    "result",
    "results",
    "summary",
    "tables",
}


def validate_job_outputs(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id)
    issues: list[dict[str, str | None]] = []
    repair_suggestions: list[dict[str, str]] = []

    execution_result = _load_required_json(
        job_dir / "execution_result.json",
        "execution_result",
        issues,
        repair_suggestions,
    )
    analysis_result = _load_required_json(
        job_dir / "analysis_result.json",
        "analysis_result",
        issues,
        repair_suggestions,
    )
    report_data = _load_required_json(
        job_dir / "report_data.json",
        "report_data",
        issues,
        repair_suggestions,
    )
    controller_plan = _load_optional_json(job_dir / "controller_plan.json")

    _validate_execution_result(execution_result, issues, repair_suggestions)
    _validate_chart_artifacts(job_dir, issues, repair_suggestions)

    if analysis_result is not None:
        _validate_task_consistency(
            controller_plan=controller_plan,
            analysis_result=analysis_result,
            issues=issues,
            repair_suggestions=repair_suggestions,
        )
        _validate_metric_values(
            data=analysis_result,
            source_name="analysis_result.json",
            issues=issues,
            repair_suggestions=repair_suggestions,
        )

    if report_data is not None:
        _validate_metric_values(
            data=report_data,
            source_name="report_data.json",
            issues=issues,
            repair_suggestions=repair_suggestions,
        )

    if analysis_result is not None and report_data is not None:
        _validate_conclusion_support(
            analysis_result=analysis_result,
            report_data=report_data,
            issues=issues,
            repair_suggestions=repair_suggestions,
        )

    severity = _overall_severity(issues)
    should_retry = SEVERITY_ORDER[severity] >= SEVERITY_ORDER["high"]
    passed = severity in {"none", "low", "medium"} and not should_retry

    result = {
        "passed": passed,
        "issues": issues,
        "severity": severity,
        "repair_suggestions": _dedupe_suggestions(repair_suggestions),
        "should_retry": should_retry,
    }

    _write_json(job_dir / VALIDATION_RESULT_FILENAME, result)
    return result


def _get_job_dir(job_id: str) -> Path:
    if not job_id or Path(job_id).name != job_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id.",
        )

    job_dir = JOB_ROOT / job_id
    if not job_dir.exists() or not job_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    return job_dir


def _load_required_json(
    path: Path,
    artifact_name: str,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> Any | None:
    if not path.exists():
        _add_issue(
            issues,
            issue_type="missing_artifact",
            severity="critical",
            message=f"Missing required artifact: {path.name}.",
            location=str(path),
        )
        _add_suggestion(
            repair_suggestions,
            f"Please regenerate the script so it writes {path.name} into output_dir.",
        )
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _add_issue(
            issues,
            issue_type="invalid_json",
            severity="critical",
            message=f"{artifact_name} is not valid JSON: {exc}",
            location=str(path),
        )
        _add_suggestion(
            repair_suggestions,
            f"Please ensure {path.name} is written with json.dump and valid UTF-8 JSON.",
        )
        return None


def _load_optional_json(path: Path) -> Any | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _deep_get(data: dict[str, Any], keys: list[str]) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _validate_execution_result(
    execution_result: Any | None,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    if execution_result is None:
        return

    if not isinstance(execution_result, dict):
        _add_issue(
            issues,
            issue_type="invalid_execution_result",
            severity="critical",
            message="execution_result.json must be a JSON object.",
            location="execution_result.json",
        )
        return

    if execution_result.get("timed_out") is True:
        _add_issue(
            issues,
            issue_type="execution_timeout",
            severity="critical",
            message="Generated script timed out.",
            location="execution_result.json",
        )
        _add_suggestion(
            repair_suggestions,
            "Please simplify the script, reduce expensive loops, and keep execution under the timeout.",
        )

    if execution_result.get("success") is not True or execution_result.get("exit_code") != 0:
        error = execution_result.get("error")
        error_type = error.get("type") if isinstance(error, dict) else ""
        if error_type == "EnvironmentInterrupted":
            _add_issue(
                issues,
                issue_type="environment_interrupted",
                severity="critical",
                message="Sandbox execution was interrupted by the runtime environment.",
                location="execution_result.json",
            )
            _add_suggestion(
                repair_suggestions,
                "Please retry the same script because the failure was caused by the runtime environment.",
                target_agent="sandbox",
            )
            return

        _add_issue(
            issues,
            issue_type="execution_failed",
            severity="critical",
            message="Generated script did not execute successfully.",
            location="execution_result.json",
        )
        _add_suggestion(
            repair_suggestions,
            "Please inspect stderr, fix the runtime error, and regenerate the Python script.",
        )


def _validate_task_consistency(
    controller_plan: Any | None,
    analysis_result: Any,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    if not isinstance(controller_plan, dict) or not isinstance(analysis_result, dict):
        return

    expected_task_type = str(controller_plan.get("task_type") or "")
    actual_task_type = str(
        analysis_result.get("task_type")
        or analysis_result.get("analysis_type")
        or _deep_get(analysis_result, ["analysis_plan", "task_type"])
        or ""
    )
    if not expected_task_type:
        return
    if not actual_task_type:
        _add_issue(
            issues,
            issue_type="missing_task_type",
            severity="critical",
            message="analysis_result.json must include task_type matching controller_plan.json.",
            location="analysis_result.json",
        )
        _add_suggestion(
            repair_suggestions,
            "Please include the controller-selected task_type in analysis_result.json.",
        )
        return
    if expected_task_type == actual_task_type:
        return
    if expected_task_type == "what_if_prediction":
        return

    _add_issue(
        issues,
        issue_type="task_type_mismatch",
        severity="critical",
        message=(
            "analysis_result.json task_type does not match controller_plan.json: "
            f"expected {expected_task_type}, got {actual_task_type}."
        ),
        location="analysis_result.json",
    )
    _add_suggestion(
        repair_suggestions,
        "Please regenerate the script for the controller-selected task type and do not reuse an unrelated analysis template.",
    )


def _validate_chart_artifacts(
    job_dir: Path,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    charts_dir = job_dir / "charts"
    chart_paths = list(charts_dir.glob("*.png")) if charts_dir.exists() else []
    valid_charts = [path for path in chart_paths if path.is_file() and path.stat().st_size > 0]

    if not valid_charts:
        _add_issue(
            issues,
            issue_type="missing_chart",
            severity="high",
            message="No PNG chart was generated under charts/.",
            location=str(charts_dir),
        )
        _add_suggestion(
            repair_suggestions,
            "Please generate at least one PNG chart and save it under output_dir/charts.",
        )


def _validate_metric_values(
    data: Any,
    source_name: str,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    for path, key, value in _walk_json(data):
        if _is_skipped_metric_path(path):
            continue
        if not _looks_like_metric_key(key):
            continue

        if _is_optional_statistic_value(key, value):
            continue

        if value is None or value == "":
            _add_issue(
                issues,
                issue_type="empty_metric",
                severity="high",
                message=f"Metric value is empty at {path}.",
                location=source_name,
            )
            continue

        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            _add_issue(
                issues,
                issue_type="invalid_metric",
                severity="high",
                message=f"Metric value is NaN or Infinity at {path}.",
                location=source_name,
            )
            continue

        if isinstance(value, (int, float)):
            normalized_key = key.lower()
            if "count" in normalized_key and value < 0:
                _add_issue(
                    issues,
                    issue_type="abnormal_metric",
                    severity="high",
                    message=f"Count metric is negative at {path}.",
                    location=source_name,
                )
            if ("rate" in normalized_key or "ratio" in normalized_key) and not (0 <= value <= 1):
                _add_issue(
                    issues,
                    issue_type="abnormal_metric",
                    severity="high",
                    message=f"Rate or ratio metric is outside [0, 1] at {path}.",
                    location=source_name,
                )
            if "score" in normalized_key and not (0 <= value <= 100):
                _add_issue(
                    issues,
                    issue_type="abnormal_metric",
                    severity="medium",
                    message=f"Score metric is outside the usual [0, 100] range at {path}.",
                    location=source_name,
                )

    if any(issue["issue_type"] in {"empty_metric", "invalid_metric", "abnormal_metric"} for issue in issues):
        _add_suggestion(
            repair_suggestions,
            "Please clean numeric columns with pandas.to_numeric(errors='coerce'), drop invalid rows, and avoid writing NaN/Infinity into result JSON.",
        )


def _validate_conclusion_support(
    analysis_result: Any,
    report_data: Any,
    issues: list[dict[str, str | None]],
    repair_suggestions: list[dict[str, str]],
) -> None:
    conclusion_items = _collect_conclusion_items(report_data)
    if not conclusion_items:
        return

    if not _has_analysis_data(analysis_result):
        _add_issue(
            issues,
            issue_type="unsupported_conclusion",
            severity="high",
            message="report_data contains conclusions or findings, but analysis_result has no supporting data.",
            location="report_data.json",
        )
        _add_suggestion(
            repair_suggestions,
            "Please include supporting tables, metrics, or summary data in analysis_result.json before writing conclusions.",
        )
        return

    unsupported_objects = [
        item
        for item in conclusion_items
        if isinstance(item, dict) and not _has_evidence_field(item)
    ]
    if unsupported_objects:
        _add_issue(
            issues,
            issue_type="weak_conclusion_support",
            severity="medium",
            message="Some conclusion objects do not include evidence, source, or data_reference fields.",
            location="report_data.json",
        )
        _add_suggestion(
            repair_suggestions,
            "Please add evidence, source_metric, or data_reference fields for each key finding or conclusion.",
        )


def _walk_json(data: Any, path: str = "$") -> list[tuple[str, str, Any]]:
    items: list[tuple[str, str, Any]] = []
    if isinstance(data, dict):
        for key, value in data.items():
            child_path = f"{path}.{key}"
            items.append((child_path, str(key), value))
            items.extend(_walk_json(value, child_path))
    elif isinstance(data, list):
        for index, value in enumerate(data):
            items.extend(_walk_json(value, f"{path}[{index}]"))
    return items


def _looks_like_metric_key(key: str) -> bool:
    normalized_key = key.lower()
    if normalized_key in METRIC_KEYWORDS:
        return True
    return bool(set(_metric_key_tokens(normalized_key)) & METRIC_TOKENS)


def _is_optional_statistic_value(key: str, value: Any) -> bool:
    if not _is_optional_statistic_key(key):
        return False
    if value is None or value == "":
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and value.strip().lower() in {"nan", "none", "null", "n/a", "not_calculated"}:
        return True
    return False


def _is_optional_statistic_key(key: str) -> bool:
    normalized_key = key.lower().replace("-", "_")
    tokens = _metric_key_tokens(normalized_key)
    token_text = "_".join(tokens)
    return token_text in {
        "p_value",
        "p_value_approx",
        "pvalue",
        "pvalue_approx",
        "q_value",
        "q_value_approx",
    }


def _metric_key_tokens(key: str) -> list[str]:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    return [token.lower() for token in re.split(r"[^A-Za-z0-9]+", normalized) if token]


def _is_skipped_metric_path(path: str) -> bool:
    path_keys = set(re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)", path))
    return bool(path_keys & SKIP_METRIC_PATH_KEYS)


def _collect_conclusion_items(report_data: Any) -> list[Any]:
    items: list[Any] = []
    if isinstance(report_data, dict):
        for key, value in report_data.items():
            if key in CONCLUSION_KEYS and value:
                if isinstance(value, list):
                    items.extend(value)
                else:
                    items.append(value)
            if isinstance(value, (dict, list)):
                items.extend(_collect_conclusion_items(value))
    elif isinstance(report_data, list):
        for value in report_data:
            items.extend(_collect_conclusion_items(value))
    return items


def _has_analysis_data(analysis_result: Any) -> bool:
    if isinstance(analysis_result, dict):
        for key in DATA_KEYS:
            value = analysis_result.get(key)
            if isinstance(value, list) and value:
                return True
            if isinstance(value, dict) and value:
                return True
        return any(isinstance(value, (int, float)) for _, _, value in _walk_json(analysis_result))
    return False


def _has_evidence_field(item: dict[str, Any]) -> bool:
    evidence_keys = {"data_reference", "evidence", "source", "source_metric"}
    return any(item.get(key) for key in evidence_keys)


def _overall_severity(issues: list[dict[str, str | None]]) -> str:
    if not issues:
        return "none"
    return max(
        (str(issue["severity"]) for issue in issues),
        key=lambda severity: SEVERITY_ORDER.get(severity, 0),
    )


def _add_issue(
    issues: list[dict[str, str | None]],
    issue_type: str,
    severity: str,
    message: str,
    location: str | None = None,
) -> None:
    issues.append(
        {
            "issue_type": issue_type,
            "severity": severity,
            "message": message,
            "location": location,
        }
    )


def _add_suggestion(
    repair_suggestions: list[dict[str, str]],
    message: str,
    target_agent: str = "code_agent",
) -> None:
    repair_suggestions.append(
        {
            "target_agent": target_agent,
            "message": message,
        }
    )


def _dedupe_suggestions(suggestions: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    deduped = []
    for suggestion in suggestions:
        key = (suggestion["target_agent"], suggestion["message"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(suggestion)
    return deduped


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)
