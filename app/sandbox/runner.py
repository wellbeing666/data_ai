import argparse
import builtins
import os
import runpy
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--job-dir", required=True)
    args = parser.parse_args()

    script_path = Path(args.script).resolve()
    input_file = Path(args.input_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    job_dir = Path(args.job_dir).resolve()

    if not _is_relative_to(output_dir, job_dir):
        raise PermissionError("output_dir must be inside job_dir")

    _install_write_guards(job_dir)

    os.environ["SANDBOX_INPUT_FILE"] = str(input_file)
    os.environ["SANDBOX_OUTPUT_DIR"] = str(output_dir)
    os.environ["SANDBOX_JOB_DIR"] = str(job_dir)

    import sys

    sys.argv = [str(script_path), str(input_file), str(output_dir)]
    runpy.run_path(str(script_path), run_name="__main__")


def _install_write_guards(job_dir: Path) -> None:
    original_open = builtins.open
    original_os_makedirs = os.makedirs
    original_os_mkdir = os.mkdir

    def guarded_open(file, mode="r", *args, **kwargs):
        if _is_write_mode(mode):
            _ensure_path_inside_job(file, job_dir)
        return original_open(file, mode, *args, **kwargs)

    def guarded_makedirs(name, mode=0o777, exist_ok=False):
        _ensure_path_inside_job(name, job_dir)
        return original_os_makedirs(name, mode=mode, exist_ok=exist_ok)

    def guarded_mkdir(path, mode=0o777, *, dir_fd=None):
        _ensure_path_inside_job(path, job_dir)
        if dir_fd is not None:
            raise PermissionError("dir_fd is not allowed in sandbox")
        return original_os_mkdir(path, mode=mode)

    builtins.open = guarded_open
    os.makedirs = guarded_makedirs
    os.mkdir = guarded_mkdir

    _patch_pathlib_open(job_dir)
    _patch_deletion_calls(job_dir)


def _patch_pathlib_open(job_dir: Path) -> None:
    original_path_open = Path.open
    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_touch = Path.touch
    original_mkdir = Path.mkdir

    def guarded_path_open(self, mode="r", *args, **kwargs):
        if _is_write_mode(mode):
            _ensure_path_inside_job(self, job_dir)
        return original_path_open(self, mode, *args, **kwargs)

    def guarded_write_text(self, *args, **kwargs):
        _ensure_path_inside_job(self, job_dir)
        return original_write_text(self, *args, **kwargs)

    def guarded_write_bytes(self, *args, **kwargs):
        _ensure_path_inside_job(self, job_dir)
        return original_write_bytes(self, *args, **kwargs)

    def guarded_touch(self, *args, **kwargs):
        _ensure_path_inside_job(self, job_dir)
        return original_touch(self, *args, **kwargs)

    def guarded_mkdir(self, *args, **kwargs):
        _ensure_path_inside_job(self, job_dir)
        return original_mkdir(self, *args, **kwargs)

    Path.open = guarded_path_open
    Path.write_text = guarded_write_text
    Path.write_bytes = guarded_write_bytes
    Path.touch = guarded_touch
    Path.mkdir = guarded_mkdir


def _patch_deletion_calls(job_dir: Path) -> None:
    original_os_remove = os.remove
    original_os_unlink = os.unlink
    original_os_rmdir = os.rmdir
    original_path_unlink = Path.unlink
    original_path_rmdir = Path.rmdir

    def guarded_os_remove(path, *, dir_fd=None):
        if dir_fd is not None:
            raise PermissionError("dir_fd is not allowed in sandbox")
        _ensure_path_inside_job(path, job_dir)
        return original_os_remove(path)

    def guarded_os_unlink(path, *, dir_fd=None):
        if dir_fd is not None:
            raise PermissionError("dir_fd is not allowed in sandbox")
        _ensure_path_inside_job(path, job_dir)
        return original_os_unlink(path)

    def guarded_os_rmdir(path, *, dir_fd=None):
        if dir_fd is not None:
            raise PermissionError("dir_fd is not allowed in sandbox")
        _ensure_path_inside_job(path, job_dir)
        return original_os_rmdir(path)

    def guarded_path_unlink(self, *args, **kwargs):
        _ensure_path_inside_job(self, job_dir)
        return original_path_unlink(self, *args, **kwargs)

    def guarded_path_rmdir(self, *args, **kwargs):
        _ensure_path_inside_job(self, job_dir)
        return original_path_rmdir(self, *args, **kwargs)

    os.remove = guarded_os_remove
    os.unlink = guarded_os_unlink
    os.rmdir = guarded_os_rmdir

    Path.unlink = guarded_path_unlink
    Path.rmdir = guarded_path_rmdir


def _is_write_mode(mode: str) -> bool:
    return any(flag in mode for flag in ("w", "a", "x", "+"))


def _ensure_path_inside_job(path_like, job_dir: Path) -> None:
    path = Path(path_like).resolve()
    if not _is_relative_to(path, job_dir):
        raise PermissionError(f"Write outside job_dir is not allowed: {path}")


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    main()
