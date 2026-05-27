import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.sandbox.base import BaseSandboxExecutor
from app.sandbox.code_safety import validate_script_static_safety


JOB_ROOT = Path("storage/jobs")
RUNNER_PATH = Path(__file__).with_name("runner.py")
EXECUTION_RESULT_FILENAME = "execution_result.json"


class LocalSubprocessSandboxExecutor(BaseSandboxExecutor):
    def execute(
        self,
        generated_script_path: str,
        input_file: str,
        output_dir: str | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        source_script = _resolve_existing_file(generated_script_path, "generated_script.py")
        source_input = _resolve_existing_file(input_file, "input_file")
        job_id, job_dir, resolved_output_dir = _prepare_job_dir(output_dir)
        execution_result_path = job_dir / EXECUTION_RESULT_FILENAME
        sandbox_script = job_dir / "generated_script.py"

        shutil.copy2(source_script, sandbox_script)

        static_issues = validate_script_static_safety(
            script_path=sandbox_script,
            input_file=source_input,
            output_dir=resolved_output_dir,
        )
        if static_issues:
            result = _build_rejected_result(
                job_id=job_id,
                sandbox_script=sandbox_script,
                source_input=source_input,
                output_dir=resolved_output_dir,
                execution_result_path=execution_result_path,
                issues=static_issues,
            )
            _write_json(execution_result_path, result)
            return result

        result = _run_subprocess(
            job_id=job_id,
            job_dir=job_dir,
            sandbox_script=sandbox_script,
            source_input=source_input,
            output_dir=resolved_output_dir,
            execution_result_path=execution_result_path,
            timeout_seconds=timeout_seconds,
        )
        _write_json(execution_result_path, result)
        return result


def _resolve_existing_file(path_value: str, label: str) -> Path:
    path = Path(path_value).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} does not exist or is not a file: {path_value}",
        )
    return path


def _prepare_job_dir(output_dir: str | None) -> tuple[str, Path, Path]:
    job_root = JOB_ROOT.resolve()
    job_root.mkdir(parents=True, exist_ok=True)

    if output_dir:
        resolved_output_dir = Path(output_dir).resolve()
        if not _is_relative_to(resolved_output_dir, job_root):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="output_dir must be inside storage/jobs.",
            )
        if resolved_output_dir.parent != job_root:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="output_dir must be a direct child of storage/jobs/{job_id}.",
            )
        job_id = resolved_output_dir.name
        job_dir = resolved_output_dir
    else:
        job_id = uuid4().hex
        job_dir = job_root / job_id
        resolved_output_dir = job_dir

    job_dir.mkdir(parents=True, exist_ok=True)
    return job_id, job_dir, resolved_output_dir


def _run_subprocess(
    job_id: str,
    job_dir: Path,
    sandbox_script: Path,
    source_input: Path,
    output_dir: Path,
    execution_result_path: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    started_at = _utc_now()
    start_time = time.perf_counter()
    timed_out = False

    command = [
        sys.executable,
        str(RUNNER_PATH.resolve()),
        "--script",
        str(sandbox_script.resolve()),
        "--input-file",
        str(source_input.resolve()),
        "--output-dir",
        str(output_dir.resolve()),
        "--job-dir",
        str(job_dir.resolve()),
    ]
    runtime_tmp_dir = job_dir / ".runtime_tmp"
    runtime_tmp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "MPLCONFIGDIR": str(runtime_tmp_dir / "matplotlib"),
            "TMP": str(runtime_tmp_dir),
            "TEMP": str(runtime_tmp_dir),
            "TMPDIR": str(runtime_tmp_dir),
            "PYTHONIOENCODING": "utf-8",
        }
    )

    try:
        completed = subprocess.run(
            command,
            cwd=str(job_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        stdout = _decode_timeout_output(exc.stdout)
        stderr = _decode_timeout_output(exc.stderr)
        if stderr:
            stderr = f"{stderr}\nExecution timed out after {timeout_seconds} seconds."
        else:
            stderr = f"Execution timed out after {timeout_seconds} seconds."
    except Exception as exc:
        exit_code = None
        stdout = ""
        stderr = traceback.format_exc()
        return _build_result(
            job_id=job_id,
            success=False,
            timed_out=False,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            sandbox_script=sandbox_script,
            source_input=source_input,
            output_dir=output_dir,
            execution_result_path=execution_result_path,
            started_at=started_at,
            finished_at=_utc_now(),
            duration_ms=_elapsed_ms(start_time),
            error={
                "type": type(exc).__name__,
                "message": str(exc),
            },
        )

    success = exit_code == 0 and not timed_out
    return _build_result(
        job_id=job_id,
        success=success,
        timed_out=timed_out,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        sandbox_script=sandbox_script,
        source_input=source_input,
        output_dir=output_dir,
        execution_result_path=execution_result_path,
        started_at=started_at,
        finished_at=_utc_now(),
        duration_ms=_elapsed_ms(start_time),
        error=None
        if success
        else {
            "type": "ExecutionFailed",
            "message": "Script execution failed or timed out.",
        },
    )


def _build_rejected_result(
    job_id: str,
    sandbox_script: Path,
    source_input: Path,
    output_dir: Path,
    execution_result_path: Path,
    issues: list[str],
) -> dict[str, Any]:
    now = _utc_now()
    return _build_result(
        job_id=job_id,
        success=False,
        timed_out=False,
        exit_code=None,
        stdout="",
        stderr="Static safety validation failed.",
        sandbox_script=sandbox_script,
        source_input=source_input,
        output_dir=output_dir,
        execution_result_path=execution_result_path,
        started_at=now,
        finished_at=now,
        duration_ms=0,
        error={
            "type": "StaticSafetyValidationError",
            "message": "Generated script contains forbidden operations.",
            "issues": issues,
        },
    )


def _build_result(
    job_id: str,
    success: bool,
    timed_out: bool,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    sandbox_script: Path,
    source_input: Path,
    output_dir: Path,
    execution_result_path: Path,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "success": success,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "script_path": str(sandbox_script),
        "input_file": str(source_input),
        "output_dir": str(output_dir),
        "execution_result_path": str(execution_result_path),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "artifacts": _list_artifacts(output_dir, exclude={execution_result_path, sandbox_script}),
        "error": error,
    }


def _list_artifacts(output_dir: Path, exclude: set[Path]) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    resolved_exclude = {path.resolve() for path in exclude}

    if not output_dir.exists():
        return artifacts

    for path in sorted(output_dir.rglob("*")):
        if not path.is_file():
            continue
        resolved_path = path.resolve()
        if resolved_path in resolved_exclude:
            continue
        artifacts.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
            }
        )

    return artifacts


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(start_time: float) -> int:
    return int((time.perf_counter() - start_time) * 1000)


def _decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
