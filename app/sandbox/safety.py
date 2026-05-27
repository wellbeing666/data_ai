from pathlib import Path

from app.sandbox.code_safety import validate_script_static_safety as _validate


def validate_script_static_safety(script_path: Path) -> list[str]:
    return _validate(script_path)
