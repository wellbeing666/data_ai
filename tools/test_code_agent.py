from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.code_agent import CodeAgent  # noqa: E402


INPUT_FILE = r"C:\workspace\data.xlsx"
OUTPUT_DIR = r"C:\workspace\storage\jobs\job1"

DATASET_PROFILE = {
    "columns": ["class", "score"],
    "numeric_summary": {"score": {"min": 60, "max": 95, "mean": 80}},
}

ANALYSIS_PLAN = {
    "analysis_goal": "Summarize scores by class",
    "grouping_dimensions": ["class"],
    "metrics": ["score"],
    "chart_plan": [],
}


VALID_SCRIPT = f'''import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

INPUT_FILE = Path(r"{INPUT_FILE}")
OUTPUT_DIR = Path(r"{OUTPUT_DIR}")
CHARTS_DIR = OUTPUT_DIR / "charts"

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    suffix = INPUT_FILE.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(INPUT_FILE)
    elif suffix in [".xlsx", ".xls"]:
        df = pd.read_excel(INPUT_FILE)
    else:
        raise ValueError("unsupported")
    chart_path = CHARTS_DIR / "chart.png"
    plt.figure()
    plt.plot([1, 2], [1, 2])
    plt.savefig(chart_path)
    plt.close()
    payload = {{"success": True, "rows": len(df), "charts": [str(chart_path)]}}
    with (OUTPUT_DIR / "analysis_result.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    with (OUTPUT_DIR / "report_data.json").open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)

if __name__ == "__main__":
    main()
'''


class FakeLLMClient:
    def __init__(self, content=None, error=None):
        self.content = content
        self.error = error
        self.last_messages = None

    def chat(self, messages, temperature=0.2):
        self.last_messages = messages
        if self.error is not None:
            raise self.error
        return self.content


def test_uses_llm_python_script():
    llm = FakeLLMClient(content=VALID_SCRIPT)
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan=ANALYSIS_PLAN,
        dataset_profile=DATASET_PROFILE,
        attempt=1,
    )
    assert script == VALID_SCRIPT.strip()
    assert llm.last_messages[0]["role"] == "system"


def test_strips_markdown_fence():
    llm = FakeLLMClient(content=f"```python\n{VALID_SCRIPT}\n```")
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan=ANALYSIS_PLAN,
        dataset_profile=DATASET_PROFILE,
        attempt=1,
    )
    assert script.startswith("import json")
    assert "```" not in script


def test_disallowed_import_falls_back_to_rule_based_script():
    bad_script = VALID_SCRIPT.replace("import json", "import requests")
    llm = FakeLLMClient(content=bad_script)
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan=ANALYSIS_PLAN,
        dataset_profile=DATASET_PROFILE,
        attempt=1,
    )
    assert "Current rule-based CodeAgent" not in script
    assert "CLASS_COLUMN = 'class'" in script
    assert "SCORE_COLUMN = 'score'" in script


def test_rule_based_script_does_not_write_repair_context_to_outputs():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan=ANALYSIS_PLAN,
        dataset_profile=DATASET_PROFILE,
        attempt=2,
        previous_execution_result={"duration_ms": 1234},
        previous_validation_result={"should_retry": True},
    )
    assert '"repair_context"' not in script
    assert "REPAIR_CONTEXT" in script


if __name__ == "__main__":
    test_uses_llm_python_script()
    test_strips_markdown_fence()
    test_disallowed_import_falls_back_to_rule_based_script()
    test_rule_based_script_does_not_write_repair_context_to_outputs()
    print("CodeAgent tests passed.")
