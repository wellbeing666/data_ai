from pathlib import Path
import tempfile
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.sandbox.code_safety import validate_source_static_safety  # noqa: E402


def _check(source: str) -> list[str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_file = root / "input.xlsx"
        output_dir = root / "job"
        input_file.write_text("x", encoding="utf-8")
        output_dir.mkdir()
        return validate_source_static_safety(
            source=source,
            input_file=input_file,
            output_dir=output_dir,
        )


def test_forbidden_imports_and_calls():
    source = """
import socket
import requests
import subprocess
import shutil
import os
os.system("echo unsafe")
eval("1 + 1")
exec("x = 1")
"""
    issues = _check(source)
    assert "Forbidden import: socket" in issues
    assert "Forbidden import: requests" in issues
    assert "Forbidden import: subprocess" in issues
    assert "Forbidden import: shutil" in issues
    assert "Forbidden call: os.system" in issues
    assert "Forbidden call: eval" in issues
    assert "Forbidden call: exec" in issues


def test_forbidden_absolute_open_and_home():
    source = r'''
from pathlib import Path
import pandas as pd
open("/etc/passwd")
open("C:\Windows\win.ini")
pd.read_csv("/etc/passwd")
Path.home()
Path("/etc/passwd").read_text()
'''
    issues = _check(source)
    assert any("Forbidden open() absolute path" in issue for issue in issues)
    assert any("Forbidden absolute path literal" in issue for issue in issues)
    assert "Forbidden call: Path.home" in issues
    assert any("outside input_file/output_dir" in issue for issue in issues)


def test_allows_input_and_output_dir_access():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_file = root / "input.xlsx"
        output_dir = root / "job"
        input_file.write_text("x", encoding="utf-8")
        output_dir.mkdir()
        source = f'''
from pathlib import Path
INPUT_FILE = Path(r"{input_file}")
OUTPUT_DIR = Path(r"{output_dir}")
CHARTS_DIR = OUTPUT_DIR / "charts"
data = INPUT_FILE.read_bytes()
CHARTS_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "analysis_result.json").open("w", encoding="utf-8")
'''
        issues = validate_source_static_safety(
            source=source,
            input_file=input_file,
            output_dir=output_dir,
        )
        assert issues == []


def test_allows_sklearn_imports_for_prediction_scripts():
    source = """
from sklearn.linear_model import LinearRegression
from sklearn.tree import DecisionTreeRegressor
model = LinearRegression()
tree = DecisionTreeRegressor(max_depth=3)
"""
    assert _check(source) == []


def test_rejects_path_outside_output_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        input_file = root / "input.xlsx"
        output_dir = root / "job"
        outside = root / "outside" / "result.json"
        input_file.write_text("x", encoding="utf-8")
        output_dir.mkdir()
        source = f'''
from pathlib import Path
BAD_PATH = Path(r"{outside}")
BAD_PATH.open("w", encoding="utf-8")
'''
        issues = validate_source_static_safety(
            source=source,
            input_file=input_file,
            output_dir=output_dir,
        )
        assert any("outside input_file/output_dir" in issue for issue in issues)


if __name__ == "__main__":
    test_forbidden_imports_and_calls()
    test_forbidden_absolute_open_and_home()
    test_allows_input_and_output_dir_access()
    test_allows_sklearn_imports_for_prediction_scripts()
    test_rejects_path_outside_output_dir()
    print("Code safety tests passed.")
