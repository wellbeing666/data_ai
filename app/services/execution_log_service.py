import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status


JOB_ROOT = Path("storage/jobs")
EXECUTION_LOG_FILENAME = "execution_log.json"


def create_event(
    stage: str,
    status_value: str,
    message: str,
    attempt: int | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "timestamp": _utc_now(),
        "stage": stage,
        "status": status_value,
        "message": message,
    }
    if attempt is not None:
        event["attempt"] = attempt
    return event


def write_fixed_template_execution_log(
    job_dir: Path,
    job_id: str,
    dataset_id: str,
    user_goal: str,
    analysis_plan: dict[str, Any],
    result_path: Path,
    chart_paths: list[str],
    executor_code_path: str,
) -> dict[str, Any]:
    log_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "status": "success",
        "workflow_type": "fixed_template",
        "user_goal": user_goal,
        "analysis_plan": analysis_plan,
        "generated_python_code_paths": [],
        "executor_code_path": executor_code_path,
        "execution_results": [],
        "validation_results": [],
        "retry_count": 0,
        "max_retries": 0,
        "artifacts": {
            "analysis_result": str(result_path),
            "charts": chart_paths,
        },
        "events": [
            create_event("planning", "success", "主控 Agent 已生成固定模板分析计划。"),
            create_event("running_code", "success", "系统使用内置成绩分析模板完成统计计算。"),
            create_event("validating", "success", "固定模板已生成 analysis_result.json 和图表文件。"),
            create_event("success", "success", "分析任务执行完成。"),
        ],
    }
    write_execution_log(job_dir, log_data)
    return log_data


def write_auto_repair_execution_log(
    job_dir: Path,
    job_id: str,
    dataset_id: str,
    user_goal: str,
    analysis_plan: dict[str, Any],
    attempts: list[dict[str, Any]],
    status_value: str,
    max_retries: int,
    final_result_path: str | None,
    final_report_data_path: str | None,
    final_validation_result_path: str | None,
) -> dict[str, Any]:
    execution_results = []
    validation_results = []
    generated_python_code_paths = []
    events = [
        create_event("planning", "success", "主控 Agent 已根据用户目标和数据画像生成分析计划。")
    ]

    for attempt in attempts:
        attempt_number = int(attempt["attempt"])
        script_path = str(attempt["script_path"])
        generated_python_code_paths.append(script_path)
        events.append(
            create_event(
                "code_generation",
                "success",
                f"代码 Agent 已生成第 {attempt_number} 次 Python 分析脚本。",
                attempt=attempt_number,
            )
        )

        execution_result = _load_json_if_exists(Path(str(attempt["execution_result_path"])))
        execution_results.append(
            {
                "attempt": attempt_number,
                "path": attempt["execution_result_path"],
                "exit_code": _get_value(execution_result, "exit_code"),
                "stdout": _get_value(execution_result, "stdout", ""),
                "stderr": _get_value(execution_result, "stderr", ""),
                "success": _get_value(execution_result, "success", False),
                "timed_out": _get_value(execution_result, "timed_out", False),
                "duration_ms": _get_value(execution_result, "duration_ms"),
                "error": _get_value(execution_result, "error"),
                "environment_retry_count": _get_value(execution_result, "environment_retry_count", 0),
                "environment_retries": _get_value(execution_result, "environment_retries", []),
            }
        )
        events.append(
            create_event(
                "running_code",
                "success" if execution_result and execution_result.get("success") else "failed",
                f"沙箱已完成第 {attempt_number} 次脚本执行。",
                attempt=attempt_number,
            )
        )

        validation_result = _load_json_if_exists(Path(str(attempt["validation_result_path"])))
        validation_results.append(
            {
                "attempt": attempt_number,
                "path": attempt["validation_result_path"],
                "passed": _get_value(validation_result, "passed", False),
                "severity": _get_value(validation_result, "severity", "unknown"),
                "issues": _get_value(validation_result, "issues", []),
                "repair_suggestions": _get_value(validation_result, "repair_suggestions", []),
                "should_retry": _get_value(validation_result, "should_retry", False),
            }
        )
        events.append(
            create_event(
                "validating",
                "success" if validation_result and validation_result.get("passed") else "failed",
                f"验证 Agent 已完成第 {attempt_number} 次产物检查。",
                attempt=attempt_number,
            )
        )

        if validation_result and validation_result.get("should_retry"):
            events.append(
                create_event(
                    "repair",
                    "retrying",
                    "验证未通过，系统将错误日志和修复建议交给代码 Agent 重新生成脚本。",
                    attempt=attempt_number,
                )
            )

    events.append(
        create_event(
            "success" if status_value == "success" else "failed",
            status_value,
            "分析任务执行完成。" if status_value == "success" else "分析任务执行失败。",
        )
    )

    log_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "status": status_value,
        "workflow_type": "auto_repair",
        "user_goal": user_goal,
        "analysis_plan": analysis_plan,
        "generated_python_code_paths": generated_python_code_paths,
        "execution_results": execution_results,
        "validation_results": validation_results,
        "retry_count": max(0, len(attempts) - 1),
        "max_retries": max_retries,
        "artifacts": {
            "analysis_result": final_result_path,
            "report_data": final_report_data_path,
            "validation_result": final_validation_result_path,
        },
        "events": events,
    }
    write_execution_log(job_dir, log_data)
    return log_data


def write_execution_log(job_dir: Path, log_data: dict[str, Any]) -> Path:
    log_path = job_dir / EXECUTION_LOG_FILENAME
    job_dir.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as output:
        json.dump(log_data, output, ensure_ascii=False, indent=2)
    return log_path


def get_execution_log(job_id: str) -> dict[str, Any]:
    job_dir = _get_job_dir(job_id)
    log_path = job_dir / EXECUTION_LOG_FILENAME

    if not log_path.exists() or not log_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Execution log not found.",
        )

    try:
        log_data = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"execution_log.json is not valid JSON: {exc}",
        ) from exc

    if not isinstance(log_data, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="execution_log.json must be a JSON object.",
        )

    return log_data


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


def _load_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _get_value(
    data: dict[str, Any] | None,
    key: str,
    default: Any = None,
) -> Any:
    if not data:
        return default
    return data.get(key, default)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
