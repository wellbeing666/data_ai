from typing import Any

from pydantic import BaseModel, Field


class SandboxExecutionRequest(BaseModel):
    generated_script_path: str = Field(..., min_length=1)
    input_file: str = Field(..., min_length=1)
    output_dir: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=300)


class SandboxArtifact(BaseModel):
    path: str
    size_bytes: int


class SandboxExecutionResponse(BaseModel):
    job_id: str
    success: bool
    timed_out: bool
    exit_code: int | None
    stdout: str
    stderr: str
    script_path: str
    input_file: str
    output_dir: str
    execution_result_path: str
    started_at: str
    finished_at: str
    duration_ms: int
    artifacts: list[SandboxArtifact]
    error: dict[str, Any] | None = None
