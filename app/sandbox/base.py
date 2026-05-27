from abc import ABC, abstractmethod
from typing import Any


class BaseSandboxExecutor(ABC):
    @abstractmethod
    def execute(
        self,
        generated_script_path: str,
        input_file: str,
        output_dir: str | None = None,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        """Run a generated analysis script and return a structured execution result."""
