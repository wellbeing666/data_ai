from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.code_agent import CodeAgent, CodeGenerationError  # noqa: E402


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


def test_injects_missing_runtime_constants():
    llm_script = "\n".join(
        line
        for line in VALID_SCRIPT.splitlines()
        if not line.startswith(("INPUT_FILE =", "OUTPUT_DIR =", "CHARTS_DIR ="))
    )
    llm = FakeLLMClient(content=llm_script)
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan=ANALYSIS_PLAN,
        dataset_profile=DATASET_PROFILE,
        attempt=1,
    )

    assert f'INPUT_FILE = Path(r"{INPUT_FILE}")' in script
    assert f'OUTPUT_DIR = Path(r"{OUTPUT_DIR}")' in script
    assert 'CHARTS_DIR = OUTPUT_DIR / "charts"' in script


def test_rewrites_wrong_runtime_constants():
    wrong_script = VALID_SCRIPT.replace(INPUT_FILE, r"C:\wrong\input.csv").replace(
        OUTPUT_DIR,
        r"C:\wrong\job",
    )
    llm = FakeLLMClient(content=wrong_script)
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan=ANALYSIS_PLAN,
        dataset_profile=DATASET_PROFILE,
        attempt=1,
    )

    assert f'INPUT_FILE = Path(r"{INPUT_FILE}")' in script
    assert f'OUTPUT_DIR = Path(r"{OUTPUT_DIR}")' in script
    assert r"C:\wrong\input.csv" not in script
    assert r"C:\wrong\job" not in script



def test_injects_chinese_matplotlib_font_setup_for_llm_script():
    chinese_script = VALID_SCRIPT.replace(
        'plt.plot([1, 2], [1, 2])',
        'plt.title("按OverallQual分组SalePrice分布")\n    plt.xlabel("总体质量")\n    plt.ylabel("房价")\n    plt.plot([1, 2], [1, 2])',
    )
    llm = FakeLLMClient(content=chinese_script)
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan=ANALYSIS_PLAN,
        dataset_profile=DATASET_PROFILE,
        attempt=1,
    )

    assert "font.sans-serif" in script
    assert "axes.unicode_minus" in script
    assert "from matplotlib import font_manager" in script
    assert "_configure_generated_chart_fonts()" in script

def test_disallowed_import_falls_back_to_rule_based_script():
    bad_script = VALID_SCRIPT.replace("import json", "import requests")
    llm = FakeLLMClient(content=bad_script)
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan={**ANALYSIS_PLAN, "task_type": "grade_analysis"},
        dataset_profile=DATASET_PROFILE,
        attempt=4,
    )
    assert "Current rule-based CodeAgent" not in script
    assert "CLASS_COLUMN = 'class'" in script
    assert "SCORE_COLUMN = 'score'" in script


def test_llm_generation_error_before_attempt_four_does_not_fallback():
    bad_script = VALID_SCRIPT.replace("import json", "import requests")
    llm = FakeLLMClient(content=bad_script)
    try:
        CodeAgent(llm_client=llm).generate_script(
            input_file=INPUT_FILE,
            output_dir=OUTPUT_DIR,
            analysis_plan={**ANALYSIS_PLAN, "task_type": "grade_analysis"},
            dataset_profile=DATASET_PROFILE,
            attempt=1,
        )
    except CodeGenerationError:
        return
    raise AssertionError("Expected CodeGenerationError before rule fallback is allowed.")


def test_rule_based_script_does_not_write_repair_context_to_outputs():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan={**ANALYSIS_PLAN, "task_type": "grade_analysis"},
        dataset_profile=DATASET_PROFILE,
        attempt=4,
        previous_execution_result={"duration_ms": 1234},
        previous_validation_result={"should_retry": True},
    )
    assert '"repair_context"' not in script
    assert "REPAIR_CONTEXT" in script


def test_general_fallback_does_not_use_grade_template_for_house_price_task():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    script = CodeAgent(llm_client=llm).generate_script(
        input_file=INPUT_FILE,
        output_dir=OUTPUT_DIR,
        analysis_plan={
            "task_type": "general_data_analysis",
            "analysis_goal": "哪些因素和房价关系最明显？",
            "grouping_dimensions": ["Neighborhood"],
            "metrics": ["SalePrice"],
            "chart_plan": [],
        },
        dataset_profile={
            "columns": ["Neighborhood", "SalePrice", "OverallQual"],
            "numeric_summary": {"SalePrice": {}, "OverallQual": {}},
        },
        attempt=4,
        previous_execution_result={"success": False},
        previous_validation_result={"should_retry": True},
    )

    assert 'TASK_TYPE = \'general_data_analysis\'' in script
    assert "class_average_score" not in script
    assert "班级平均分" not in script
    assert "grade_analysis" not in script
    assert "group_metric_mean_top20.png" in script


if __name__ == "__main__":
    test_uses_llm_python_script()
    test_strips_markdown_fence()
    test_injects_missing_runtime_constants()
    test_rewrites_wrong_runtime_constants()
    test_injects_chinese_matplotlib_font_setup_for_llm_script()
    test_disallowed_import_falls_back_to_rule_based_script()
    test_llm_generation_error_before_attempt_four_does_not_fallback()
    test_rule_based_script_does_not_write_repair_context_to_outputs()
    test_general_fallback_does_not_use_grade_template_for_house_price_task()
    print("CodeAgent tests passed.")

