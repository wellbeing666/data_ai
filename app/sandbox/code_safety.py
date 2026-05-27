import ast
import re
from pathlib import Path


FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "shutil",
    "socket",
    "subprocess",
}
FORBIDDEN_CALL_NAMES = {
    "eval",
    "exec",
}
FORBIDDEN_OS_CALLS = {
    "system",
}
PATH_ACCESS_CALLS = {
    "open",
    "Path",
    "pathlib.Path",
    "os.path.join",
}
PATH_METHOD_ACCESS_NAMES = {
    "open",
    "mkdir",
    "write_text",
    "write_bytes",
    "read_text",
    "read_bytes",
    "touch",
}


def validate_script_static_safety(
    script_path: Path,
    input_file: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> list[str]:
    source = script_path.read_text(encoding="utf-8")
    return validate_source_static_safety(
        source=source,
        input_file=input_file,
        output_dir=output_dir,
        filename=str(script_path),
    )


def validate_source_static_safety(
    source: str,
    input_file: str | Path | None = None,
    output_dir: str | Path | None = None,
    filename: str = "<generated_script>",
) -> list[str]:
    issues: list[str] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"Syntax error: {exc}"]

    allowed_input = Path(input_file).resolve() if input_file else None
    allowed_output = Path(output_dir).resolve() if output_dir else None

    constants = _collect_path_constants(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", maxsplit=1)[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    issues.append(f"Forbidden import: {alias.name}")

        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", maxsplit=1)[0]
            if root in FORBIDDEN_IMPORT_ROOTS:
                issues.append(f"Forbidden import: {node.module}")

        if isinstance(node, ast.Call):
            call_name = _get_call_name(node.func)
            if call_name in FORBIDDEN_CALL_NAMES:
                issues.append(f"Forbidden call: {call_name}")
            if call_name == "os.system":
                issues.append("Forbidden call: os.system")
            if call_name in {"Path.home", "pathlib.Path.home"}:
                issues.append(f"Forbidden call: {call_name}")

            _validate_absolute_literal_arguments(
                node=node,
                allowed_input=allowed_input,
                allowed_output=allowed_output,
                issues=issues,
            )
            _validate_path_method_access(
                node=node,
                constants=constants,
                allowed_input=allowed_input,
                allowed_output=allowed_output,
                issues=issues,
            )
            _validate_literal_path_access(
                node=node,
                call_name=call_name,
                constants=constants,
                allowed_input=allowed_input,
                allowed_output=allowed_output,
                issues=issues,
            )

    return _dedupe(issues)


def _validate_absolute_literal_arguments(
    node: ast.Call,
    allowed_input: Path | None,
    allowed_output: Path | None,
    issues: list[str],
) -> None:
    for arg in node.args:
        if not isinstance(arg, ast.Constant) or not isinstance(arg.value, str):
            continue
        if not _is_absolute_path_literal(arg.value):
            continue
        path = Path(arg.value).resolve()
        if not _is_allowed_path(path, allowed_input, allowed_output):
            issues.append(
                "Forbidden absolute path literal outside input_file/output_dir: "
                f"{path}"
            )


def _validate_path_method_access(
    node: ast.Call,
    constants: dict[str, Path],
    allowed_input: Path | None,
    allowed_output: Path | None,
    issues: list[str],
) -> None:
    if not isinstance(node.func, ast.Attribute):
        return
    if node.func.attr not in PATH_METHOD_ACCESS_NAMES:
        return

    path = _resolve_path_expr(node.func.value, constants)
    if path is not None and not _is_allowed_path(path, allowed_input, allowed_output):
        issues.append(
            "Forbidden path access outside input_file/output_dir: "
            f"{path}"
        )


def _validate_literal_path_access(
    node: ast.Call,
    call_name: str,
    constants: dict[str, Path],
    allowed_input: Path | None,
    allowed_output: Path | None,
    issues: list[str],
) -> None:
    if not node.args:
        return

    path = _resolve_path_expr(node.args[0], constants)
    if path is None:
        return

    if call_name == "open" and _is_forbidden_absolute_literal(node.args[0]):
        issues.append(f"Forbidden open() absolute path: {path}")
        return

    if call_name in PATH_ACCESS_CALLS or call_name.endswith(".open"):
        if not _is_allowed_path(path, allowed_input, allowed_output):
            issues.append(
                "Forbidden path access outside input_file/output_dir: "
                f"{path}"
            )


def _collect_path_constants(tree: ast.AST) -> dict[str, Path]:
    constants: dict[str, Path] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        path = _literal_path_from_expr(node.value, constants)
        if path is not None:
            constants[target.id] = path
    return constants


def _literal_path_from_expr(
    node: ast.AST,
    constants: dict[str, Path],
) -> Path | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        if _looks_like_path(node.value):
            return Path(node.value).resolve()
        return None

    if isinstance(node, ast.Name):
        return constants.get(node.id)

    if isinstance(node, ast.Call) and _get_call_name(node.func) in {"Path", "pathlib.Path"}:
        if node.args:
            return _literal_path_from_expr(node.args[0], constants)
        return None

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _literal_path_from_expr(node.left, constants)
        right = _literal_path_part(node.right)
        if left is not None and right is not None:
            return (left / right).resolve()

    return None


def _resolve_path_expr(
    node: ast.AST,
    constants: dict[str, Path],
) -> Path | None:
    path = _literal_path_from_expr(node, constants)
    if path is not None:
        return path

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return Path(node.value).resolve() if _looks_like_path(node.value) else None

    return None


def _literal_path_part(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _is_forbidden_absolute_literal(node: ast.AST) -> bool:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    return _is_absolute_path_literal(node.value)


def _is_absolute_path_literal(value: str) -> bool:
    return value.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", value) is not None


def _looks_like_path(value: str) -> bool:
    return (
        value.startswith("/")
        or re.match(r"^[A-Za-z]:[\\/]", value) is not None
        or "/" in value
        or "\\" in value
    )


def _is_allowed_path(
    path: Path,
    allowed_input: Path | None,
    allowed_output: Path | None,
) -> bool:
    resolved_path = path.resolve()
    if allowed_input is not None and resolved_path == allowed_input:
        return True
    if allowed_output is not None and _is_relative_to(resolved_path, allowed_output):
        return True
    return False


def _get_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = _get_call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr

    return ""


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _dedupe(issues: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for issue in issues:
        if issue in seen:
            continue
        seen.add(issue)
        deduped.append(issue)
    return deduped
