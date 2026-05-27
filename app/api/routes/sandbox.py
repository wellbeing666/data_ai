from fastapi import APIRouter

from app.sandbox.local_executor import LocalSubprocessSandboxExecutor
from app.schemas.sandbox import SandboxExecutionRequest, SandboxExecutionResponse


router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


@router.post("/execute", response_model=SandboxExecutionResponse)
def execute_generated_script(
    request: SandboxExecutionRequest,
) -> SandboxExecutionResponse:
    executor = LocalSubprocessSandboxExecutor()
    result = executor.execute(
        generated_script_path=request.generated_script_path,
        input_file=request.input_file,
        output_dir=request.output_dir,
        timeout_seconds=request.timeout_seconds,
    )
    return SandboxExecutionResponse(**result)
