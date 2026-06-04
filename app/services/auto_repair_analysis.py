import json
import shutil
import traceback
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.agents.analysis_agent import create_analysis_plan
from app.agents.code_agent import CodeAgent, CodeGenerationError
from app.agents.controller_agent import create_controller_plan
from app.agents.data_understanding_agent import create_data_understanding
from app.agents.explanation_agent import create_explanation
from app.agents.quality_review_agent import create_quality_review
from app.sandbox.code_safety import validate_script_static_safety
from app.sandbox.local_executor import LocalSubprocessSandboxExecutor
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_reader import load_uploaded_dataset
from app.services.evidence_service import build_evidence_chain, merge_evidence_into_quality_review
from app.services.execution_log_service import create_event, write_execution_log
from app.services.job_control_service import JobCancelled, checkpoint_job_control
from app.services.rag_service import format_rag_context, get_rag_service
from app.services.report_service import generate_markdown_report
from app.services.validation_service import validate_job_outputs


JOB_ROOT = Path("storage/jobs")
MAX_RETRIES = 3
TERMINAL_STATUSES = {"success", "failed"}


def create_auto_repair_job_record(
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    effective_max_retries = _validate_max_retries(max_retries)
    job_id = uuid4().hex
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=False)
    events = [
        create_event("queued", "pending", "任务已创建，等待 Agent 流程启动。")
    ]
    return _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="pending",
        current_stage="queued",
        max_retries=effective_max_retries,
        attempts=[],
        events=events,
        timeout_seconds=timeout_seconds,
    )


def run_auto_repair_analysis_job_background(
    job_id: str,
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 60,
) -> None:
    try:
        run_auto_repair_analysis_job(
            dataset_id=dataset_id,
            user_goal=user_goal,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
            job_id=job_id,
        )
    except JobCancelled:
        job_dir = (JOB_ROOT / job_id).resolve()
        current_status = _read_json_if_exists(job_dir / "task_status.json") or {}
        events = _event_list(current_status.get("events"))
        events.append(create_event("cancelled", "cancelled", "分析任务已取消。"))
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="cancelled",
            current_stage="cancelled",
            max_retries=min(max_retries, MAX_RETRIES),
            attempts=_dict_list(current_status.get("attempts")),
            events=events,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:  # pragma: no cover - background safety net
        job_dir = (JOB_ROOT / job_id).resolve()
        current_status = _read_json_if_exists(job_dir / "task_status.json") or {}
        events = _event_list(current_status.get("events"))
        events.append(
            create_event(
                "failed",
                "failed",
                f"任务执行异常：{exc}",
            )
        )
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="failed",
            current_stage="failed",
            max_retries=min(max_retries, MAX_RETRIES),
            attempts=_dict_list(current_status.get("attempts")),
            events=events,
            timeout_seconds=timeout_seconds,
            error={
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=8),
            },
        )


def get_auto_repair_job_status(job_id: str) -> dict[str, Any]:
    if not job_id or Path(job_id).name != job_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid job_id.",
        )
    status_path = JOB_ROOT / job_id / "task_status.json"
    if not status_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job status not found.",
        )
    status_data = _read_json(status_path)
    return _normalize_status_payload(status_data)


def run_auto_repair_analysis_job(
    dataset_id: str,
    user_goal: str,
    max_retries: int = 3,
    timeout_seconds: int = 60,
    job_id: str | None = None,
) -> dict[str, Any]:
    effective_max_retries = _validate_max_retries(max_retries)
    job_id = job_id or uuid4().hex
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=bool(job_id))
    current_status = _read_json_if_exists(job_dir / "task_status.json") or {}
    events = _event_list(current_status.get("events"))
    if not events:
        events.append(create_event("queued", "pending", "任务已创建。"))

    def progress(stage: str, status_text: str, message: str) -> None:
        checkpoint_job_control(job_dir)
        events.append(create_event(stage, status_text, message))
        write_stage_snapshot(stage, "running" if status_text != "failed" else "failed")

    attempts: list[dict[str, Any]] = []
    final_result_path = None
    final_report_data_path = None
    final_validation_result_path = None
    explanation_path = None
    quality_review_path = None
    evidence_chain_path = None
    cleaning_report_path = None
    report_path = None
    pptx_path = None
    pptx_preview_path = None
    rag_retrieval_path = None
    rag_context: list[dict[str, Any]] = []

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
            max_retries=effective_max_retries,
            attempts=attempts,
            events=events,
            timeout_seconds=timeout_seconds,
            final_result_path=final_result_path,
            final_report_data_path=final_report_data_path,
            final_validation_result_path=final_validation_result_path,
            explanation_path=explanation_path,
            quality_review_path=quality_review_path,
            evidence_chain_path=evidence_chain_path,
            cleaning_report_path=cleaning_report_path,
            report_path=report_path,
            pptx_path=pptx_path,
            pptx_preview_path=pptx_preview_path,
            controller_plan_path=existing_job_file("controller_plan.json"),
            rag_retrieval_path=rag_retrieval_path or existing_job_file("rag_retrieval.json"),
            dataset_profile_path=existing_job_file("dataset_profile.json"),
            data_understanding_path=existing_job_file("data_understanding.json"),
            analysis_plan_path=existing_job_file("analysis_plan.json"),
        )

    progress("loading_dataset", "running", "正在读取上传数据并生成数据画像。")
    input_file, _df = load_uploaded_dataset(dataset_id)
    input_file = input_file.resolve()
    source_cleaning_report = input_file.parent / "cleaning_report.json"
    if source_cleaning_report.exists():
        cleaning_report_path = str(job_dir / "cleaning_report.json")
        shutil.copy2(source_cleaning_report, job_dir / "cleaning_report.json")
    dataset_profile = generate_dataset_profile(dataset_id)

    progress("rag_retrieval", "running", "RAG 正在检索全局业务知识库。")
    rag_search_result = get_rag_service().search(
        query=user_goal,
        dataset_profile=dataset_profile,
    )
    rag_context = format_rag_context(rag_search_result)
    rag_retrieval_path = str(job_dir / "rag_retrieval.json")
    _write_json(job_dir / "rag_retrieval.json", rag_search_result)
    events.append(
        create_event(
            "rag_retrieval",
            "success" if rag_context else "fallback",
            (
                f"RAG 命中 {len(rag_context)} 条业务知识片段。"
                if rag_context
                else "RAG 当前不可用或未命中，继续常规分析流程。"
            ),
        )
    )
    _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="running",
        current_stage="controller",
        max_retries=effective_max_retries,
        attempts=attempts,
        events=events,
        timeout_seconds=timeout_seconds,
        rag_retrieval_path=rag_retrieval_path,
    )

    progress("controller", "running", "主控 Agent 正在规划任务类型和执行步骤。")
    controller_plan = create_controller_plan(user_goal, dataset_profile, rag_context=rag_context)
    _write_json(job_dir / "controller_plan.json", controller_plan)
    _write_json(job_dir / "dataset_profile.json", dataset_profile)
    events.append(create_event("controller", "success", "主控 Agent 已生成任务计划。"))
    _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="running",
        current_stage="data_understanding",
        max_retries=effective_max_retries,
        attempts=attempts,
        events=events,
        timeout_seconds=timeout_seconds,
        controller_plan_path=str(job_dir / "controller_plan.json"),
        rag_retrieval_path=rag_retrieval_path,
        dataset_profile_path=str(job_dir / "dataset_profile.json"),
    )

    events.append(create_event("data_understanding", "running", "数据理解 Agent 正在识别字段语义。"))
    data_understanding = create_data_understanding(
        user_goal,
        dataset_profile,
        rag_context=rag_context,
    )
    _write_json(job_dir / "data_understanding.json", data_understanding)
    events.append(create_event("data_understanding", "success", "数据理解 Agent 已完成字段识别。"))
    _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="running",
        current_stage="analysis",
        max_retries=effective_max_retries,
        attempts=attempts,
        events=events,
        timeout_seconds=timeout_seconds,
        controller_plan_path=str(job_dir / "controller_plan.json"),
        rag_retrieval_path=rag_retrieval_path,
        dataset_profile_path=str(job_dir / "dataset_profile.json"),
        data_understanding_path=str(job_dir / "data_understanding.json"),
    )

    events.append(create_event("analysis", "running", "分析 Agent 正在选择分析方法和图表方案。"))
    analysis_plan = create_analysis_plan(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        data_understanding_result=data_understanding,
        controller_plan=controller_plan,
        rag_context=rag_context,
    )
    _write_json(job_dir / "analysis_plan.json", analysis_plan)
    events.append(create_event("analysis", "success", "分析 Agent 已生成分析计划。"))
    _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value="running",
        current_stage="code_generation",
        max_retries=effective_max_retries,
        attempts=attempts,
        events=events,
        timeout_seconds=timeout_seconds,
        controller_plan_path=str(job_dir / "controller_plan.json"),
        rag_retrieval_path=rag_retrieval_path,
        dataset_profile_path=str(job_dir / "dataset_profile.json"),
        data_understanding_path=str(job_dir / "data_understanding.json"),
        analysis_plan_path=str(job_dir / "analysis_plan.json"),
    )

    code_agent = CodeAgent()
    sandbox_executor = LocalSubprocessSandboxExecutor()
    previous_execution_result = None
    previous_validation_result = None
    total_attempts = effective_max_retries + 1
    status_value = "failed"

    for attempt in range(1, total_attempts + 1):
        checkpoint_job_control(job_dir)
        events.append(
            create_event(
                "code_generation",
                "running",
                f"代码 Agent 正在生成第 {attempt} 次分析脚本。",
                attempt=attempt,
            )
        )
        write_stage_snapshot("code_generation")
        script_path = job_dir / f"generated_script_attempt_{attempt}.py.txt"
        _clear_attempt_outputs(job_dir)
        safety_attempt_path = job_dir / f"code_safety_result_attempt_{attempt}.json"
        execution_attempt_path = job_dir / f"execution_result_attempt_{attempt}.json"
        validation_attempt_path = job_dir / f"validation_result_attempt_{attempt}.json"
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
        write_stage_snapshot("code_generation")
        try:
            script_code = code_agent.generate_script(
                input_file=str(input_file),
                output_dir=str(job_dir),
                analysis_plan=analysis_plan,
                dataset_profile=dataset_profile,
                attempt=attempt,
                previous_execution_result=previous_execution_result,
                previous_validation_result=previous_validation_result,
            )
        except CodeGenerationError as exc:
            script_path.write_text(_diagnostic_generation_failure_script(str(exc)), encoding="utf-8")
            safety_result = {
                "passed": False,
                "issues": ["Code generation failed before static safety validation."],
            }
            _write_json(job_dir / "code_safety_result.json", safety_result)
            shutil.copy2(job_dir / "code_safety_result.json", safety_attempt_path)
            execution_result = _build_code_generation_failure_result(
                job_id=job_id,
                script_path=script_path,
                input_file=input_file,
                output_dir=job_dir,
                error_message=str(exc),
            )
            _write_json(job_dir / "execution_result.json", execution_result)
            shutil.copy2(job_dir / "execution_result.json", execution_attempt_path)
            events.append(
                create_event(
                    "code_generation",
                    "failed",
                    f"代码 Agent 第 {attempt} 次生成未通过，将继续交给 LLM 修复。",
                    attempt=attempt,
                )
            )
            events.append(
                create_event(
                    "validation",
                    "running",
                    f"验证 Agent 正在整理第 {attempt} 次生成失败信息。",
                    attempt=attempt,
                )
            )
            write_stage_snapshot("validation")
            validation_result = validate_job_outputs(job_id)
            shutil.copy2(job_dir / "validation_result.json", validation_attempt_path)
            should_retry = bool(validation_result["should_retry"])
            attempt_result.update(
                {
                    "passed": False,
                    "should_retry": should_retry,
                    "severity": str(validation_result["severity"]),
                    "safety_issues": safety_result["issues"],
                }
            )
            previous_execution_result = execution_result
            previous_validation_result = validation_result
            status_value = "failed"
            events.append(
                create_event(
                    "validation",
                    "failed",
                    f"验证 Agent 已记录第 {attempt} 次代码生成失败。",
                    attempt=attempt,
                )
            )
            _write_progress(
                job_dir=job_dir,
                job_id=job_id,
                dataset_id=dataset_id,
                user_goal=user_goal,
                status_value="running" if should_retry else "failed",
                current_stage="repair" if should_retry else "failed",
                max_retries=effective_max_retries,
                attempts=attempts,
                events=events,
                timeout_seconds=timeout_seconds,
                controller_plan_path=str(job_dir / "controller_plan.json"),
                dataset_profile_path=str(job_dir / "dataset_profile.json"),
                data_understanding_path=str(job_dir / "data_understanding.json"),
                analysis_plan_path=str(job_dir / "analysis_plan.json"),
            )
            if not should_retry:
                break
            events.append(
                create_event(
                    "repair",
                    "retrying",
                    "代码生成失败信息已交给 LLM，下一轮继续修复而不是规则兜底。",
                    attempt=attempt,
                )
            )
            write_stage_snapshot("repair")
            continue
        script_path.write_text(script_code, encoding="utf-8")
        events.append(
            create_event(
                "code_generation",
                "success",
                f"代码 Agent 已生成第 {attempt} 次 Python 脚本。",
                attempt=attempt,
            )
        )
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="running",
            current_stage="code_safety",
            max_retries=effective_max_retries,
            attempts=attempts,
            events=events,
            timeout_seconds=timeout_seconds,
            controller_plan_path=str(job_dir / "controller_plan.json"),
            dataset_profile_path=str(job_dir / "dataset_profile.json"),
            data_understanding_path=str(job_dir / "data_understanding.json"),
            analysis_plan_path=str(job_dir / "analysis_plan.json"),
        )

        events.append(
            create_event(
                "code_safety",
                "running",
                f"正在对第 {attempt} 次脚本进行静态安全检查。",
                attempt=attempt,
            )
        )
        write_stage_snapshot("code_safety")
        static_safety_issues = validate_script_static_safety(
            script_path=script_path,
            input_file=input_file,
            output_dir=job_dir,
        )
        safety_result = {
            "passed": not bool(static_safety_issues),
            "issues": static_safety_issues,
        }
        _write_json(job_dir / "code_safety_result.json", safety_result)
        shutil.copy2(job_dir / "code_safety_result.json", safety_attempt_path)
        events.append(
            create_event(
                "code_safety",
                "success" if safety_result["passed"] else "failed",
                "静态安全检查通过。" if safety_result["passed"] else "静态安全检查失败，准备进入修复循环。",
                attempt=attempt,
            )
        )
        write_stage_snapshot("code_safety")

        if static_safety_issues:
            execution_result = _build_static_safety_failure_result(
                job_id=job_id,
                script_path=script_path,
                input_file=input_file,
                output_dir=job_dir,
                issues=static_safety_issues,
            )
            _write_json(job_dir / "execution_result.json", execution_result)
            shutil.copy2(job_dir / "execution_result.json", execution_attempt_path)

            events.append(
                create_event(
                    "validation",
                    "running",
                    f"验证 Agent 正在检查第 {attempt} 次安全失败结果。",
                    attempt=attempt,
                )
            )
            write_stage_snapshot("validation")
            validation_result = validate_job_outputs(job_id)
            shutil.copy2(job_dir / "validation_result.json", validation_attempt_path)

            should_retry = bool(validation_result["should_retry"])
            attempt_result.update(
                {
                    "passed": False,
                    "should_retry": should_retry,
                    "severity": str(validation_result["severity"]),
                    "safety_issues": static_safety_issues,
                }
            )
            previous_execution_result = execution_result
            previous_validation_result = validation_result
            status_value = "failed"
            events.append(
                create_event(
                    "validation",
                    "failed",
                    f"验证 Agent 已记录第 {attempt} 次安全失败结果。",
                    attempt=attempt,
                )
            )
            _write_progress(
                job_dir=job_dir,
                job_id=job_id,
                dataset_id=dataset_id,
                user_goal=user_goal,
                status_value="running" if should_retry else "failed",
                current_stage="repair" if should_retry else "failed",
                max_retries=effective_max_retries,
                attempts=attempts,
                events=events,
                timeout_seconds=timeout_seconds,
                controller_plan_path=str(job_dir / "controller_plan.json"),
                dataset_profile_path=str(job_dir / "dataset_profile.json"),
                data_understanding_path=str(job_dir / "data_understanding.json"),
                analysis_plan_path=str(job_dir / "analysis_plan.json"),
            )
            if not should_retry:
                break
            events.append(
                create_event(
                    "repair",
                    "retrying",
                    "已将失败原因交给代码 Agent，准备重新生成脚本。",
                    attempt=attempt,
                )
            )
            write_stage_snapshot("repair")
            continue

        events.append(
            create_event(
                "sandbox",
                "running",
                f"沙箱正在执行第 {attempt} 次脚本。",
                attempt=attempt,
            )
        )
        write_stage_snapshot("sandbox")
        execution_result = sandbox_executor.execute(
            generated_script_path=str(script_path),
            input_file=str(input_file),
            output_dir=str(job_dir),
            timeout_seconds=timeout_seconds,
        )
        shutil.copy2(job_dir / "execution_result.json", execution_attempt_path)
        events.append(
            create_event(
                "sandbox",
                "success" if execution_result.get("success") else "failed",
                f"沙箱已完成第 {attempt} 次执行。",
                attempt=attempt,
            )
        )
        write_stage_snapshot("sandbox")
        checkpoint_job_control(job_dir)

        events.append(
            create_event(
                "validation",
                "running",
                f"验证 Agent 正在检查第 {attempt} 次产物。",
                attempt=attempt,
            )
        )
        write_stage_snapshot("validation")
        validation_result = validate_job_outputs(job_id)
        shutil.copy2(job_dir / "validation_result.json", validation_attempt_path)

        attempt_result.update(
            {
                "passed": bool(validation_result["passed"]),
                "should_retry": bool(validation_result["should_retry"]),
                "severity": str(validation_result["severity"]),
            }
        )
        events.append(
            create_event(
                "validation",
                "success" if validation_result["passed"] else "failed",
                f"验证 Agent 已完成第 {attempt} 次检查。",
                attempt=attempt,
            )
        )
        write_stage_snapshot("validation")

        previous_execution_result = execution_result
        previous_validation_result = validation_result

        if validation_result["passed"]:
            status_value = "success"
            _write_progress(
                job_dir=job_dir,
                job_id=job_id,
                dataset_id=dataset_id,
                user_goal=user_goal,
                status_value="running",
                current_stage="explanation",
                max_retries=effective_max_retries,
                attempts=attempts,
                events=events,
                timeout_seconds=timeout_seconds,
                controller_plan_path=str(job_dir / "controller_plan.json"),
                dataset_profile_path=str(job_dir / "dataset_profile.json"),
                data_understanding_path=str(job_dir / "data_understanding.json"),
                analysis_plan_path=str(job_dir / "analysis_plan.json"),
            )
            break

        if not validation_result["should_retry"]:
            status_value = "failed"
            _write_progress(
                job_dir=job_dir,
                job_id=job_id,
                dataset_id=dataset_id,
                user_goal=user_goal,
                status_value="failed",
                current_stage="failed",
                max_retries=effective_max_retries,
                attempts=attempts,
                events=events,
                timeout_seconds=timeout_seconds,
                controller_plan_path=str(job_dir / "controller_plan.json"),
                dataset_profile_path=str(job_dir / "dataset_profile.json"),
                data_understanding_path=str(job_dir / "data_understanding.json"),
                analysis_plan_path=str(job_dir / "analysis_plan.json"),
            )
            break
        events.append(
            create_event(
                "repair",
                "retrying",
                "验证未通过，系统将 stderr、验证结果和修复建议交给代码 Agent 重试。",
                attempt=attempt,
            )
        )
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="running",
            current_stage="repair",
            max_retries=effective_max_retries,
            attempts=attempts,
            events=events,
            timeout_seconds=timeout_seconds,
            controller_plan_path=str(job_dir / "controller_plan.json"),
            dataset_profile_path=str(job_dir / "dataset_profile.json"),
            data_understanding_path=str(job_dir / "data_understanding.json"),
            analysis_plan_path=str(job_dir / "analysis_plan.json"),
        )

    final_result_path = (
        str(job_dir / "analysis_result.json")
        if (job_dir / "analysis_result.json").exists()
        else None
    )
    final_report_data_path = (
        str(job_dir / "report_data.json")
        if (job_dir / "report_data.json").exists()
        else None
    )
    final_validation_result_path = (
        str(job_dir / "validation_result.json")
        if (job_dir / "validation_result.json").exists()
        else None
    )
    if status_value == "success" and final_result_path:
        events.append(create_event("explanation", "running", "解释 Agent 正在生成结论和 PPT 大纲。"))
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="running",
            current_stage="explanation",
            max_retries=effective_max_retries,
            attempts=attempts,
            events=events,
            timeout_seconds=timeout_seconds,
            final_result_path=final_result_path,
            final_report_data_path=final_report_data_path,
            final_validation_result_path=final_validation_result_path,
            controller_plan_path=str(job_dir / "controller_plan.json"),
            dataset_profile_path=str(job_dir / "dataset_profile.json"),
            data_understanding_path=str(job_dir / "data_understanding.json"),
            analysis_plan_path=str(job_dir / "analysis_plan.json"),
        )
        analysis_result_data = _read_json(Path(final_result_path))
        chart_paths = _collect_chart_paths(job_dir, analysis_result_data)
        explanation = create_explanation(
            user_goal=user_goal,
            dataset_profile=dataset_profile,
            analysis_result=analysis_result_data,
            chart_paths=chart_paths,
            limitations=_string_list(analysis_plan.get("limitations")),
            rag_context=rag_context,
        )
        explanation_path = str(job_dir / "explanation.json")
        _write_json(job_dir / "explanation.json", explanation)
        evidence_chain = build_evidence_chain(
            job_dir=job_dir,
            explanation=explanation,
            result_payload=analysis_result_data,
            report_data=_read_json_if_exists(job_dir / "report_data.json") or {},
            chart_paths=chart_paths,
        )
        evidence_chain_path = str(job_dir / "evidence_chain.json")
        events.append(create_event("explanation", "success", "解释 Agent 已生成结论和 PPT 大纲。"))

        events.append(create_event("quality_review", "running", "质检 Agent 正在审查结论证据链和风险表述。"))
        _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value="running",
            current_stage="quality_review",
            max_retries=effective_max_retries,
            attempts=attempts,
            events=events,
            timeout_seconds=timeout_seconds,
            final_result_path=final_result_path,
            final_report_data_path=final_report_data_path,
            final_validation_result_path=final_validation_result_path,
            explanation_path=explanation_path,
            evidence_chain_path=evidence_chain_path,
            cleaning_report_path=cleaning_report_path,
            controller_plan_path=str(job_dir / "controller_plan.json"),
            rag_retrieval_path=rag_retrieval_path,
            dataset_profile_path=str(job_dir / "dataset_profile.json"),
            data_understanding_path=str(job_dir / "data_understanding.json"),
            analysis_plan_path=str(job_dir / "analysis_plan.json"),
        )
        validation_payload = _read_json_if_exists(Path(final_validation_result_path)) if final_validation_result_path else None
        quality_review = create_quality_review(
            user_goal=user_goal,
            dataset_profile=dataset_profile,
            result_payload=analysis_result_data,
            explanation=explanation,
            validation_result=validation_payload or {},
            chart_paths=chart_paths,
            workflow_type="auto_repair",
        )
        quality_review = merge_evidence_into_quality_review(quality_review, evidence_chain)
        quality_review_path = str(job_dir / "quality_review.json")
        _write_json(job_dir / "quality_review.json", quality_review)
        events.append(create_event(
            "quality_review",
            "success" if quality_review.get("passed") else "warning",
            "质检 Agent 已完成结论审查。",
        ))
        report_result = generate_markdown_report(final_result_path, chart_paths, include_pptx=True)
        report_path = report_result.get("report_path")
        pptx_path = report_result.get("pptx_path")
        pptx_preview_path = report_result.get("pptx_preview_path")
        events.append(create_event("report", "success", "报告和 PPTX 已生成。"))

    events.append(
        create_event(
            "success" if status_value == "success" else "failed",
            status_value,
            "分析任务已完成。" if status_value == "success" else "分析任务执行失败。",
        )
    )

    result = {
        "job_id": job_id,
        "status": status_value,
        "attempts": attempts,
        "final_result_path": final_result_path,
        "final_report_data_path": final_report_data_path,
        "final_validation_result_path": final_validation_result_path,
        "job_dir": str(job_dir),
        "controller_plan_path": str(job_dir / "controller_plan.json"),
        "rag_retrieval_path": rag_retrieval_path,
        "dataset_profile_path": str(job_dir / "dataset_profile.json"),
        "data_understanding_path": str(job_dir / "data_understanding.json"),
        "analysis_plan_path": str(job_dir / "analysis_plan.json"),
        "explanation_path": explanation_path,
        "quality_review_path": quality_review_path,
        "evidence_chain_path": evidence_chain_path,
        "cleaning_report_path": cleaning_report_path,
        "report_path": report_path,
        "pptx_path": pptx_path,
        "pptx_preview_path": pptx_preview_path,
        "effective_max_retries": effective_max_retries,
    }
    return _write_progress(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        status_value=status_value,
        current_stage=status_value,
        max_retries=effective_max_retries,
        attempts=attempts,
        events=events,
        timeout_seconds=timeout_seconds,
        final_result_path=final_result_path,
        final_report_data_path=final_report_data_path,
        final_validation_result_path=final_validation_result_path,
        explanation_path=explanation_path,
        quality_review_path=quality_review_path,
        evidence_chain_path=evidence_chain_path,
        cleaning_report_path=cleaning_report_path,
        report_path=report_path,
        pptx_path=pptx_path,
        pptx_preview_path=pptx_preview_path,
        controller_plan_path=str(job_dir / "controller_plan.json"),
        dataset_profile_path=str(job_dir / "dataset_profile.json"),
        data_understanding_path=str(job_dir / "data_understanding.json"),
        analysis_plan_path=str(job_dir / "analysis_plan.json"),
    )


def _write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        data = json.load(source)
    return data if isinstance(data, dict) else {}


def _collect_chart_paths(job_dir: Path, analysis_result: dict[str, Any]) -> list[str]:
    charts = analysis_result.get("charts")
    chart_paths = [str(path) for path in charts] if isinstance(charts, list) else []
    if chart_paths:
        return chart_paths

    charts_dir = job_dir / "charts"
    if not charts_dir.exists():
        return []
    return [str(path) for path in sorted(charts_dir.glob("*.png"))]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _validate_max_retries(max_retries: int) -> int:
    return max(0, min(int(max_retries), MAX_RETRIES))


def _write_progress(
    *,
    job_dir: Path,
    job_id: str,
    dataset_id: str,
    user_goal: str,
    status_value: str,
    current_stage: str,
    max_retries: int,
    attempts: list[dict[str, Any]],
    events: list[dict[str, Any]],
    timeout_seconds: int,
    final_result_path: str | None = None,
    final_report_data_path: str | None = None,
    final_validation_result_path: str | None = None,
    explanation_path: str | None = None,
    quality_review_path: str | None = None,
    evidence_chain_path: str | None = None,
    cleaning_report_path: str | None = None,
    report_path: str | None = None,
    pptx_path: str | None = None,
    pptx_preview_path: str | None = None,
    controller_plan_path: str | None = None,
    rag_retrieval_path: str | None = None,
    dataset_profile_path: str | None = None,
    data_understanding_path: str | None = None,
    analysis_plan_path: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    job_dir.mkdir(parents=True, exist_ok=True)
    status_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "user_goal": user_goal,
        "status": status_value,
        "current_stage": current_stage,
        "attempts": attempts,
        "final_result_path": final_result_path,
        "final_report_data_path": final_report_data_path,
        "final_validation_result_path": final_validation_result_path,
        "job_dir": str(job_dir),
        "controller_plan_path": controller_plan_path,
        "rag_retrieval_path": rag_retrieval_path,
        "dataset_profile_path": dataset_profile_path,
        "data_understanding_path": data_understanding_path,
        "analysis_plan_path": analysis_plan_path,
        "explanation_path": explanation_path,
        "quality_review_path": quality_review_path,
        "evidence_chain_path": evidence_chain_path,
        "cleaning_report_path": cleaning_report_path,
        "report_path": report_path,
        "pptx_path": pptx_path,
        "pptx_preview_path": pptx_preview_path,
        "effective_max_retries": max_retries,
        "timeout_seconds": timeout_seconds,
        "events": events,
        "error": error,
    }
    _write_json(job_dir / "task_status.json", status_data)
    write_execution_log(job_dir, _build_progress_execution_log(status_data))
    return _normalize_status_payload(status_data)


def _normalize_status_payload(data: dict[str, Any]) -> dict[str, Any]:
    job_dir = Path(str(data.get("job_dir") or ""))
    if job_dir and job_dir.exists():
        data = {
            **data,
            "controller_plan_path": _existing_or_none(data.get("controller_plan_path"), job_dir / "controller_plan.json"),
            "rag_retrieval_path": _existing_or_none(data.get("rag_retrieval_path"), job_dir / "rag_retrieval.json"),
            "dataset_profile_path": _existing_or_none(data.get("dataset_profile_path"), job_dir / "dataset_profile.json"),
            "data_understanding_path": _existing_or_none(data.get("data_understanding_path"), job_dir / "data_understanding.json"),
            "analysis_plan_path": _existing_or_none(data.get("analysis_plan_path"), job_dir / "analysis_plan.json"),
            "explanation_path": _existing_or_none(data.get("explanation_path"), job_dir / "explanation.json"),
            "quality_review_path": _existing_or_none(data.get("quality_review_path"), job_dir / "quality_review.json"),
            "evidence_chain_path": _existing_or_none(data.get("evidence_chain_path"), job_dir / "evidence_chain.json"),
            "cleaning_report_path": _existing_or_none(data.get("cleaning_report_path"), job_dir / "cleaning_report.json"),
            "report_path": _existing_or_none(data.get("report_path"), job_dir / "report.md"),
            "pptx_path": _existing_or_none(data.get("pptx_path"), job_dir / "report.pptx"),
            "pptx_preview_path": _existing_or_none(data.get("pptx_preview_path"), job_dir / "pptx_preview.json"),
            "final_result_path": _existing_or_none(data.get("final_result_path"), job_dir / "analysis_result.json"),
            "final_report_data_path": _existing_or_none(data.get("final_report_data_path"), job_dir / "report_data.json"),
            "final_validation_result_path": _existing_or_none(data.get("final_validation_result_path"), job_dir / "validation_result.json"),
        }
    return {
        "job_id": str(data.get("job_id") or ""),
        "status": str(data.get("status") or "pending"),
        "current_stage": str(data.get("current_stage") or data.get("status") or "pending"),
        "attempts": _dict_list(data.get("attempts")),
        "final_result_path": data.get("final_result_path"),
        "final_report_data_path": data.get("final_report_data_path"),
        "final_validation_result_path": data.get("final_validation_result_path"),
        "job_dir": str(data.get("job_dir") or ""),
        "controller_plan_path": data.get("controller_plan_path"),
        "rag_retrieval_path": data.get("rag_retrieval_path"),
        "dataset_profile_path": data.get("dataset_profile_path"),
        "data_understanding_path": data.get("data_understanding_path"),
        "analysis_plan_path": data.get("analysis_plan_path"),
        "explanation_path": data.get("explanation_path"),
        "quality_review_path": data.get("quality_review_path"),
        "evidence_chain_path": data.get("evidence_chain_path"),
        "cleaning_report_path": data.get("cleaning_report_path"),
        "report_path": data.get("report_path"),
        "pptx_path": data.get("pptx_path"),
        "pptx_preview_path": data.get("pptx_preview_path"),
        "effective_max_retries": data.get("effective_max_retries"),
        "events": _event_list(data.get("events")),
        "error": data.get("error") if isinstance(data.get("error"), dict) else None,
    }


def _build_progress_execution_log(status_data: dict[str, Any]) -> dict[str, Any]:
    attempts = _dict_list(status_data.get("attempts"))
    execution_results = []
    validation_results = []
    generated_python_code_paths = []

    for attempt in attempts:
        attempt_number = int(attempt.get("attempt") or 0)
        script_path = str(attempt.get("script_path") or "")
        if script_path:
            generated_python_code_paths.append(script_path)

        execution_path = Path(str(attempt.get("execution_result_path") or ""))
        execution_data = _read_json_if_exists(execution_path)
        if execution_data:
            execution_results.append(
                {
                    "attempt": attempt_number,
                    "path": str(execution_path),
                    "exit_code": execution_data.get("exit_code"),
                    "stdout": execution_data.get("stdout", ""),
                    "stderr": execution_data.get("stderr", ""),
                    "success": bool(execution_data.get("success")),
                    "timed_out": bool(execution_data.get("timed_out")),
                    "duration_ms": execution_data.get("duration_ms"),
                }
            )

        validation_path = Path(str(attempt.get("validation_result_path") or ""))
        validation_data = _read_json_if_exists(validation_path)
        if validation_data:
            validation_results.append(
                {
                    "attempt": attempt_number,
                    "path": str(validation_path),
                    "passed": bool(validation_data.get("passed")),
                    "severity": validation_data.get("severity", "unknown"),
                    "issues": validation_data.get("issues", []),
                    "repair_suggestions": validation_data.get("repair_suggestions", []),
                    "should_retry": bool(validation_data.get("should_retry")),
                }
            )

    return {
        "job_id": str(status_data.get("job_id") or ""),
        "dataset_id": status_data.get("dataset_id"),
        "status": str(status_data.get("status") or "pending"),
        "workflow_type": "auto_repair",
        "user_goal": str(status_data.get("user_goal") or ""),
        "analysis_plan": _read_json_if_exists(Path(str(status_data.get("analysis_plan_path") or ""))),
        "generated_python_code_paths": generated_python_code_paths,
        "executor_code_path": None,
        "execution_results": execution_results,
        "validation_results": validation_results,
        "retry_count": max(0, len(attempts) - 1),
        "max_retries": int(status_data.get("effective_max_retries") or 0),
        "artifacts": {
            "analysis_result": status_data.get("final_result_path"),
            "report_data": status_data.get("final_report_data_path"),
            "validation_result": status_data.get("final_validation_result_path"),
            "explanation": status_data.get("explanation_path"),
            "quality_review": status_data.get("quality_review_path"),
            "evidence_chain": status_data.get("evidence_chain_path"),
            "cleaning_report": status_data.get("cleaning_report_path"),
            "report": status_data.get("report_path"),
            "pptx": status_data.get("pptx_path"),
            "pptx_preview": status_data.get("pptx_preview_path"),
            "rag_retrieval": status_data.get("rag_retrieval_path"),
        },
        "events": _event_list(status_data.get("events")),
    }


def _existing_or_none(value: Any, fallback_path: Path) -> str | None:
    if isinstance(value, str) and value:
        return value
    return str(fallback_path) if fallback_path.exists() else None


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not str(path) or not path.exists() or not path.is_file():
        return None
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def _event_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _clear_attempt_outputs(job_dir: Path) -> None:
    for filename in (
        "analysis_result.json",
        "report_data.json",
        "execution_result.json",
        "validation_result.json",
    ):
        path = job_dir / filename
        if path.exists() and path.is_file():
            path.unlink()

    charts_dir = job_dir / "charts"
    if charts_dir.exists() and charts_dir.is_dir():
        shutil.rmtree(charts_dir)


def _diagnostic_generation_failure_script(error_message: str) -> str:
    return (
        "raise RuntimeError("
        + repr(f"Code generation failed before sandbox execution: {error_message}")
        + ")\n"
    )


def _build_code_generation_failure_result(
    job_id: str,
    script_path: Path,
    input_file: Path,
    output_dir: Path,
    error_message: str,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "success": False,
        "timed_out": False,
        "exit_code": None,
        "stdout": "",
        "stderr": error_message,
        "script_path": str(script_path),
        "input_file": str(input_file),
        "output_dir": str(output_dir),
        "execution_result_path": str(output_dir / "execution_result.json"),
        "artifacts": [],
        "error": {
            "type": "CodeGenerationError",
            "message": error_message,
        },
        "repair_context": {
            "failed_stage": "code_generation",
            "suggestion": "Regenerate a simpler valid script that writes analysis_result.json, report_data.json, and at least one chart.",
        },
    }


def _build_static_safety_failure_result(
    job_id: str,
    script_path: Path,
    input_file: Path,
    output_dir: Path,
    issues: list[str],
) -> dict[str, Any]:
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
        "execution_result_path": str(output_dir / "execution_result.json"),
        "artifacts": [],
        "error": {
            "type": "StaticSafetyValidationError",
            "message": "Generated script contains forbidden operations or path access.",
            "issues": issues,
        },
        "repair_context": {
            "target_agent": "code_agent",
            "message": "Regenerate the Python script without forbidden operations and only access input_file/output_dir.",
            "safety_issues": issues,
        },
    }






