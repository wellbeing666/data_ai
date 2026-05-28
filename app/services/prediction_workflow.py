import json
import shutil
import traceback
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.agents.hypothesis_agent import create_hypothesis_plan
from app.agents.prediction_agent import create_prediction_plan
from app.agents.prediction_code_agent import PredictionCodeAgent
from app.agents.prediction_explanation_agent import create_prediction_explanation
from app.sandbox.code_safety import validate_script_static_safety
from app.sandbox.local_executor import LocalSubprocessSandboxExecutor
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_reader import load_uploaded_dataset
from app.services.execution_log_service import create_event, write_execution_log
from app.services.prediction_validation_service import validate_prediction_outputs
from app.services.rag_service import format_rag_context, get_rag_service


JOB_ROOT = Path("storage/jobs")
MAX_RETRIES = 3


def create_prediction_job_record(
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    effective_max_retries = _validate_max_retries(max_retries)
    job_id = uuid4().hex
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=False)
    events = [create_event("queued", "pending", "情景预测任务已创建，等待流程启动。")]
    return _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="pending",
        current_stage="queued",
        attempts=[],
        events=events,
        max_retries=effective_max_retries,
        timeout_seconds=timeout_seconds,
    )


def run_prediction_job_background(
    job_id: str,
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 90,
) -> None:
    try:
        run_prediction_job(
            dataset_id=dataset_id,
            user_goal=user_goal,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
        )
    except Exception as exc:  # pragma: no cover
        job_dir = (JOB_ROOT / job_id).resolve()
        current_status = _read_json_if_exists(job_dir / "prediction_task_status.json") or {}
        events = _event_list(current_status.get("events"))
        events.append(create_event("failed", "failed", f"情景预测任务执行异常：{exc}"))
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="failed",
            current_stage="failed",
            attempts=_dict_list(current_status.get("attempts")),
            events=events,
            max_retries=min(max_retries, MAX_RETRIES),
            timeout_seconds=timeout_seconds,
            error={
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=8),
            },
        )


def get_prediction_job_status(job_id: str) -> dict[str, Any]:
    if not job_id or Path(job_id).name != job_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job_id.")
    status_path = JOB_ROOT / job_id / "prediction_task_status.json"
    if not status_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prediction job status not found.")
    return _normalize_status_payload(_read_json(status_path))


def get_prediction_job_log(job_id: str) -> dict[str, Any]:
    status_data = get_prediction_job_status(job_id)
    return _build_execution_log(status_data)


def run_prediction_job(
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 90,
    job_id: str | None = None,
) -> dict[str, Any]:
    effective_max_retries = _validate_max_retries(max_retries)
    job_id = job_id or uuid4().hex
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=bool(job_id))
    events = _event_list((_read_json_if_exists(job_dir / "prediction_task_status.json") or {}).get("events"))
    if not events:
        events.append(create_event("queued", "pending", "情景预测任务已创建。"))

    attempts: list[dict[str, Any]] = []
    final_prediction_result_path = None
    final_report_data_path = None
    final_validation_result_path = None
    prediction_explanation_path = None

    def progress(stage: str, message: str) -> None:
        events.append(create_event(stage, "running", message))
        write_stage_snapshot(stage)

    def existing_job_file(filename: str) -> str | None:
        path = job_dir / filename
        return str(path) if path.exists() else None

    def write_stage_snapshot(stage: str, status_value: str = "running") -> None:
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value=status_value,
            current_stage=stage,
            attempts=attempts,
            events=events,
            max_retries=effective_max_retries,
            timeout_seconds=timeout_seconds,
            final_prediction_result_path=final_prediction_result_path,
            final_report_data_path=final_report_data_path,
            final_validation_result_path=final_validation_result_path,
            prediction_explanation_path=prediction_explanation_path,
            dataset_profile_path=existing_job_file("dataset_profile.json"),
            rag_retrieval_path=existing_job_file("rag_retrieval.json"),
            hypothesis_plan_path=existing_job_file("hypothesis_plan.json"),
            prediction_plan_path=existing_job_file("prediction_plan.json"),
        )

    progress("loading_dataset", "正在读取上传数据并生成数据画像。")
    input_file, _df = load_uploaded_dataset(dataset_id)
    input_file = input_file.resolve()
    dataset_profile = generate_dataset_profile(dataset_id)
    _write_json(job_dir / "dataset_profile.json", dataset_profile)

    progress("rag_retrieval", "RAG 正在检索预测相关业务知识。")
    rag_search_result = get_rag_service().search(query=user_goal, dataset_profile=dataset_profile, task_type="what_if_prediction")
    rag_context = format_rag_context(rag_search_result)
    _write_json(job_dir / "rag_retrieval.json", rag_search_result)
    events.append(
        create_event(
            "rag_retrieval",
            "success" if rag_context else "fallback",
            f"RAG 命中 {len(rag_context)} 条预测相关知识。" if rag_context else "RAG 当前不可用或未命中，继续预测流程。",
        )
    )

    progress("hypothesis", "假设解析 Agent 正在解析干预变量、目标指标和对象维度。")
    hypothesis_plan = create_hypothesis_plan(user_goal, dataset_profile, rag_context=rag_context)
    _write_json(job_dir / "hypothesis_plan.json", hypothesis_plan)
    events.append(create_event("hypothesis", "success", "假设解析 Agent 已生成结构化假设。"))

    progress("prediction_plan", "预测 Agent 正在选择建模或模拟方案。")
    prediction_plan = create_prediction_plan(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        hypothesis_plan=hypothesis_plan,
        rag_context=rag_context,
    )
    _write_json(job_dir / "prediction_plan.json", prediction_plan)
    events.append(create_event("prediction_plan", "success", "预测 Agent 已生成预测计划。"))

    code_agent = PredictionCodeAgent()
    sandbox_executor = LocalSubprocessSandboxExecutor()
    previous_execution_result = None
    previous_validation_result = None
    total_attempts = effective_max_retries + 1
    status_value = "failed"

    for attempt in range(1, total_attempts + 1):
        events.append(create_event("code_generation", "running", f"预测 Code Agent 正在生成第 {attempt} 次脚本。", attempt=attempt))
        write_stage_snapshot("code_generation")
        script_path = job_dir / f"generated_prediction_script_attempt_{attempt}.py"
        script_code = code_agent.generate_script(
            input_file=str(input_file),
            output_dir=str(job_dir),
            dataset_profile=dataset_profile,
            hypothesis_plan=hypothesis_plan,
            prediction_plan=prediction_plan,
            attempt=attempt,
            previous_execution_result=previous_execution_result,
            previous_validation_result=previous_validation_result,
        )
        script_path.write_text(script_code, encoding="utf-8")
        _clear_attempt_outputs(job_dir)
        safety_attempt_path = job_dir / f"prediction_code_safety_result_attempt_{attempt}.json"
        execution_attempt_path = job_dir / f"prediction_execution_result_attempt_{attempt}.json"
        validation_attempt_path = job_dir / f"prediction_validation_result_attempt_{attempt}.json"
        attempt_result = {
            "attempt": attempt,
            "script_path": str(script_path),
            "safety_result_path": str(safety_attempt_path),
            "execution_result_path": str(execution_attempt_path),
            "validation_result_path": str(validation_attempt_path),
            "passed": False,
            "should_retry": True,
            "severity": "unknown",
        }
        attempts.append(attempt_result)
        events.append(create_event("code_generation", "success", f"预测 Code Agent 已生成第 {attempt} 次脚本。", attempt=attempt))
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="running",
            current_stage="code_safety",
            attempts=attempts,
            events=events,
            max_retries=effective_max_retries,
            timeout_seconds=timeout_seconds,
            dataset_profile_path=str(job_dir / "dataset_profile.json"),
            rag_retrieval_path=str(job_dir / "rag_retrieval.json"),
            hypothesis_plan_path=str(job_dir / "hypothesis_plan.json"),
            prediction_plan_path=str(job_dir / "prediction_plan.json"),
        )

        events.append(create_event("code_safety", "running", f"正在对第 {attempt} 次预测脚本进行静态安全检查。", attempt=attempt))
        write_stage_snapshot("code_safety")
        safety_issues = validate_script_static_safety(script_path=script_path, input_file=input_file, output_dir=job_dir)
        safety_result = {"passed": not bool(safety_issues), "issues": safety_issues}
        _write_json(safety_attempt_path, safety_result)
        events.append(create_event("code_safety", "success" if safety_result["passed"] else "failed", "静态安全检查通过。" if safety_result["passed"] else "静态安全检查失败，准备进入修复循环。", attempt=attempt))
        if safety_issues:
            execution_result = _static_safety_failure(job_id, script_path, input_file, job_dir, safety_issues)
            _write_json(job_dir / "execution_result.json", execution_result)
            shutil.copy2(job_dir / "execution_result.json", execution_attempt_path)
            events.append(create_event("validation", "running", f"预测验证 Agent 正在检查第 {attempt} 次安全失败结果。", attempt=attempt))
            write_stage_snapshot("validation")
            validation_result = validate_prediction_outputs(job_id)
            shutil.copy2(job_dir / "prediction_validation_result.json", validation_attempt_path)
            attempt_result.update(
                {
                    "passed": False,
                    "should_retry": bool(validation_result["should_retry"]),
                    "severity": str(validation_result["severity"]),
                    "safety_issues": safety_issues,
                }
            )
            previous_execution_result = execution_result
            previous_validation_result = validation_result
            if not validation_result["should_retry"]:
                break
            continue

        events.append(create_event("sandbox", "running", f"沙箱正在执行第 {attempt} 次预测脚本。", attempt=attempt))
        write_stage_snapshot("sandbox")
        execution_result = sandbox_executor.execute(
            generated_script_path=str(script_path),
            input_file=str(input_file),
            output_dir=str(job_dir),
            timeout_seconds=timeout_seconds,
        )
        shutil.copy2(job_dir / "execution_result.json", execution_attempt_path)
        events.append(create_event("sandbox", "success" if execution_result.get("success") else "failed", "沙箱已完成预测脚本执行。", attempt=attempt))

        events.append(create_event("validation", "running", f"预测验证 Agent 正在检查第 {attempt} 次产物。", attempt=attempt))
        write_stage_snapshot("validation")
        validation_result = validate_prediction_outputs(job_id)
        shutil.copy2(job_dir / "prediction_validation_result.json", validation_attempt_path)
        attempt_result.update(
            {
                "passed": bool(validation_result["passed"]),
                "should_retry": bool(validation_result["should_retry"]),
                "severity": str(validation_result["severity"]),
            }
        )
        previous_execution_result = execution_result
        previous_validation_result = validation_result
        events.append(create_event("validation", "success" if validation_result["passed"] else "failed", "预测验证 Agent 已完成产物检查。", attempt=attempt))
        if validation_result["passed"]:
            status_value = "success"
            break
        if not validation_result["should_retry"]:
            break
        events.append(create_event("repair", "retrying", "预测产物未通过，准备把错误和修复建议交给预测 Code Agent。", attempt=attempt))

    final_prediction_result_path = str(job_dir / "prediction_result.json") if (job_dir / "prediction_result.json").exists() else None
    final_report_data_path = str(job_dir / "report_data.json") if (job_dir / "report_data.json").exists() else None
    final_validation_result_path = str(job_dir / "prediction_validation_result.json") if (job_dir / "prediction_validation_result.json").exists() else None

    if status_value == "success" and final_prediction_result_path:
        progress("explanation", "预测解释 Agent 正在生成业务结论。")
        prediction_result = _read_json(Path(final_prediction_result_path))
        chart_paths = prediction_result.get("charts") if isinstance(prediction_result.get("charts"), list) else []
        explanation = create_prediction_explanation(
            user_goal=user_goal,
            prediction_result=prediction_result,
            chart_paths=[str(path) for path in chart_paths],
            rag_context=rag_context,
        )
        prediction_explanation_path = str(job_dir / "prediction_explanation.json")
        _write_json(job_dir / "prediction_explanation.json", explanation)
        events.append(create_event("explanation", "success", "预测解释 Agent 已生成结论。"))

    events.append(create_event("success" if status_value == "success" else "failed", status_value, "情景预测任务已完成。" if status_value == "success" else "情景预测任务失败。"))
    return _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value=status_value,
        current_stage=status_value,
        attempts=attempts,
        events=events,
        max_retries=effective_max_retries,
        timeout_seconds=timeout_seconds,
        final_prediction_result_path=final_prediction_result_path,
        final_report_data_path=final_report_data_path,
        final_validation_result_path=final_validation_result_path,
        prediction_explanation_path=prediction_explanation_path,
        dataset_profile_path=str(job_dir / "dataset_profile.json"),
        rag_retrieval_path=str(job_dir / "rag_retrieval.json"),
        hypothesis_plan_path=str(job_dir / "hypothesis_plan.json"),
        prediction_plan_path=str(job_dir / "prediction_plan.json"),
    )


def _write_progress(
    *,
    job_dir: Path,
    job_id: str,
    dataset_id: str,
    user_goal: str,
    status_value: str,
    current_stage: str,
    attempts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    max_retries: int,
    timeout_seconds: int,
    final_prediction_result_path: str | None = None,
    final_report_data_path: str | None = None,
    final_validation_result_path: str | None = None,
    prediction_explanation_path: str | None = None,
    dataset_profile_path: str | None = None,
    rag_retrieval_path: str | None = None,
    hypothesis_plan_path: str | None = None,
    prediction_plan_path: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "user_goal": user_goal,
        "status": status_value,
        "current_stage": current_stage,
        "attempts": attempts,
        "final_prediction_result_path": final_prediction_result_path,
        "final_report_data_path": final_report_data_path,
        "final_validation_result_path": final_validation_result_path,
        "job_dir": str(job_dir),
        "dataset_profile_path": dataset_profile_path,
        "rag_retrieval_path": rag_retrieval_path,
        "hypothesis_plan_path": hypothesis_plan_path,
        "prediction_plan_path": prediction_plan_path,
        "prediction_explanation_path": prediction_explanation_path,
        "effective_max_retries": max_retries,
        "timeout_seconds": timeout_seconds,
        "events": events,
        "error": error,
    }
    _write_json(job_dir / "prediction_task_status.json", status_data)
    write_execution_log(job_dir, _build_execution_log(status_data))
    return _normalize_status_payload(status_data)


def _build_execution_log(status_data: dict[str, Any]) -> dict[str, Any]:
    attempts = _dict_list(status_data.get("attempts"))
    execution_results = []
    validation_results = []
    generated_paths = []
    for attempt in attempts:
        script_path = str(attempt.get("script_path") or "")
        if script_path:
            generated_paths.append(script_path)
        execution = _read_json_if_exists(Path(str(attempt.get("execution_result_path") or "")))
        if execution:
            execution_results.append({"attempt": attempt.get("attempt"), "path": attempt.get("execution_result_path"), **execution})
        validation = _read_json_if_exists(Path(str(attempt.get("validation_result_path") or "")))
        if validation:
            validation_results.append({"attempt": attempt.get("attempt"), "path": attempt.get("validation_result_path"), **validation})
    return {
        "job_id": str(status_data.get("job_id") or ""),
        "dataset_id": status_data.get("dataset_id"),
        "status": str(status_data.get("status") or "pending"),
        "workflow_type": "what_if_prediction",
        "user_goal": str(status_data.get("user_goal") or ""),
        "prediction_plan": _read_json_if_exists(Path(str(status_data.get("prediction_plan_path") or ""))),
        "generated_python_code_paths": generated_paths,
        "execution_results": execution_results,
        "validation_results": validation_results,
        "retry_count": max(0, len(attempts) - 1),
        "max_retries": int(status_data.get("effective_max_retries") or 0),
        "artifacts": {
            "prediction_result": status_data.get("final_prediction_result_path"),
            "report_data": status_data.get("final_report_data_path"),
            "validation_result": status_data.get("final_validation_result_path"),
            "prediction_explanation": status_data.get("prediction_explanation_path"),
        },
        "events": _event_list(status_data.get("events")),
    }


def _normalize_status_payload(data: dict[str, Any]) -> dict[str, Any]:
    job_dir = Path(str(data.get("job_dir") or ""))
    if job_dir.exists():
        data = {
            **data,
            "dataset_profile_path": _existing_or_none(data.get("dataset_profile_path"), job_dir / "dataset_profile.json"),
            "rag_retrieval_path": _existing_or_none(data.get("rag_retrieval_path"), job_dir / "rag_retrieval.json"),
            "hypothesis_plan_path": _existing_or_none(data.get("hypothesis_plan_path"), job_dir / "hypothesis_plan.json"),
            "prediction_plan_path": _existing_or_none(data.get("prediction_plan_path"), job_dir / "prediction_plan.json"),
            "prediction_explanation_path": _existing_or_none(data.get("prediction_explanation_path"), job_dir / "prediction_explanation.json"),
            "final_prediction_result_path": _existing_or_none(data.get("final_prediction_result_path"), job_dir / "prediction_result.json"),
            "final_report_data_path": _existing_or_none(data.get("final_report_data_path"), job_dir / "report_data.json"),
            "final_validation_result_path": _existing_or_none(data.get("final_validation_result_path"), job_dir / "prediction_validation_result.json"),
        }
    return {
        "job_id": str(data.get("job_id") or ""),
        "status": str(data.get("status") or "pending"),
        "current_stage": str(data.get("current_stage") or "pending"),
        "attempts": _dict_list(data.get("attempts")),
        "final_prediction_result_path": data.get("final_prediction_result_path"),
        "final_report_data_path": data.get("final_report_data_path"),
        "final_validation_result_path": data.get("final_validation_result_path"),
        "job_dir": str(data.get("job_dir") or ""),
        "dataset_profile_path": data.get("dataset_profile_path"),
        "rag_retrieval_path": data.get("rag_retrieval_path"),
        "hypothesis_plan_path": data.get("hypothesis_plan_path"),
        "prediction_plan_path": data.get("prediction_plan_path"),
        "prediction_explanation_path": data.get("prediction_explanation_path"),
        "effective_max_retries": data.get("effective_max_retries"),
        "events": _event_list(data.get("events")),
        "error": data.get("error") if isinstance(data.get("error"), dict) else None,
    }


def _clear_attempt_outputs(job_dir: Path) -> None:
    for filename in ("prediction_result.json", "report_data.json", "execution_result.json", "validation_result.json", "prediction_validation_result.json"):
        path = job_dir / filename
        if path.exists() and path.is_file():
            path.unlink()
    charts_dir = job_dir / "charts"
    if charts_dir.exists():
        shutil.rmtree(charts_dir)


def _static_safety_failure(job_id: str, script_path: Path, input_file: Path, output_dir: Path, issues: list[str]) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "success": False,
        "timed_out": False,
        "exit_code": None,
        "stdout": "",
        "stderr": "Static safety validation failed before execution.",
        "script_path": str(script_path),
        "input_file": str(input_file),
        "output_dir": str(output_dir),
        "error": {"type": "StaticSafetyValidationError", "message": "Generated prediction script is unsafe.", "issues": issues},
    }


def _validate_max_retries(max_retries: int) -> int:
    return max(0, min(int(max_retries), MAX_RETRIES))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not str(path) or not path.exists() or not path.is_file():
        return None
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def _event_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _existing_or_none(value: Any, fallback_path: Path) -> str | None:
    if isinstance(value, str) and value:
        return value
    return str(fallback_path) if fallback_path.exists() else None
