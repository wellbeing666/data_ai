import json
import ast
import re
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


ALLOWED_IMPORT_ROOTS = {
    "pandas",
    "numpy",
    "matplotlib",
    "seaborn",
    "duckdb",
    "json",
    "os",
    "pathlib",
}

SYSTEM_PROMPT = """You are the Code Agent of an AI-native data analysis workbench.

Return only executable Python code. Do not output markdown, code fences, comments outside code, or explanation.

Hard requirements:
- Use only these libraries: pandas, numpy, matplotlib, seaborn, duckdb, json, os, pathlib.
- The code must read INPUT_FILE.
- The code must write all outputs under OUTPUT_DIR.
- The code must create OUTPUT_DIR / "analysis_result.json".
- The code must create OUTPUT_DIR / "report_data.json".
- The code must create at least one PNG chart under OUTPUT_DIR / "charts".
- The code must support CSV, XLSX, and XLS input files.
- The code must handle Chinese column names by treating all column names as strings and preserving UTF-8 JSON output.
- Do not write repair context, previous execution logs, validation logs, stderr, artifact lists, duration_ms, or size_bytes into analysis_result.json or report_data.json.
- Use matplotlib Agg backend before importing pyplot.
- Never read or write outside INPUT_FILE and OUTPUT_DIR.
"""


def build_user_prompt(
    input_file: str,
    output_dir: str,
    dataset_profile: dict[str, Any],
    analysis_plan: dict[str, Any],
    attempt: int,
    previous_execution_result: dict[str, Any] | None,
    previous_validation_result: dict[str, Any] | None,
) -> str:
    context = {
        "attempt": attempt,
        "previous_execution_result": previous_execution_result,
        "previous_validation_result": previous_validation_result,
        "previous_stderr": (previous_execution_result or {}).get("stderr")
        if previous_execution_result
        else None,
        "previous_repair_suggestions": (previous_validation_result or {}).get(
            "repair_suggestions"
        )
        if previous_validation_result
        else None,
    }
    return """Generate a complete Python analysis script.

Use these exact constants:
INPUT_FILE = Path(r{input_file!r})
OUTPUT_DIR = Path(r{output_dir!r})
CHARTS_DIR = OUTPUT_DIR / "charts"

Dataset profile JSON:
{dataset_profile}

Analysis plan JSON:
{analysis_plan}

Repair context JSON:
{context}

If this is attempt 2 or later, fix the previous error using previous_stderr,
previous_validation_result, and previous_repair_suggestions. Do not repeat unsafe
operations or missing-artifact mistakes from earlier attempts.

Return only Python code. The script must define main() and call it under if __name__ == "__main__".
""".format(
        input_file=input_file,
        output_dir=output_dir,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        analysis_plan=json.dumps(analysis_plan, ensure_ascii=False, indent=2),
        context=json.dumps(context, ensure_ascii=False, indent=2),
    )


class CodeAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.rule_based_agent = RuleBasedCodeAgent()

    def generate_script(
        self,
        input_file: str,
        output_dir: str,
        analysis_plan: dict[str, Any],
        dataset_profile: dict[str, Any],
        attempt: int,
        previous_execution_result: dict[str, Any] | None = None,
        previous_validation_result: dict[str, Any] | None = None,
    ) -> str:
        try:
            script = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            input_file=input_file,
                            output_dir=output_dir,
                            dataset_profile=dataset_profile,
                            analysis_plan=analysis_plan,
                            attempt=attempt,
                            previous_execution_result=previous_execution_result,
                            previous_validation_result=previous_validation_result,
                        ),
                    },
                ],
                temperature=0.1,
            )
            script = _extract_python_code(script)
            _validate_generated_script(script, input_file=input_file, output_dir=output_dir)
            return script
        except Exception:
            return self.rule_based_agent.generate_script(
                input_file=input_file,
                output_dir=output_dir,
                analysis_plan=_to_rule_based_plan(analysis_plan, dataset_profile),
                dataset_profile=dataset_profile,
                attempt=attempt,
                previous_execution_result=previous_execution_result,
                previous_validation_result=previous_validation_result,
            )


class RuleBasedCodeAgent:
    def generate_script(
        self,
        input_file: str,
        output_dir: str,
        analysis_plan: dict[str, Any],
        dataset_profile: dict[str, Any],
        attempt: int,
        previous_execution_result: dict[str, Any] | None = None,
        previous_validation_result: dict[str, Any] | None = None,
    ) -> str:
        task_type = analysis_plan.get("task_type")
        if task_type != "grade_analysis":
            return self._generate_unsupported_task_script(
                input_file=input_file,
                output_dir=output_dir,
                analysis_plan=analysis_plan,
                dataset_profile=dataset_profile,
            )

        return self._generate_grade_analysis_script(
            input_file=input_file,
            output_dir=output_dir,
            analysis_plan=analysis_plan,
            dataset_profile=dataset_profile,
            attempt=attempt,
            previous_execution_result=previous_execution_result,
            previous_validation_result=previous_validation_result,
        )

    def _generate_grade_analysis_script(
        self,
        input_file: str,
        output_dir: str,
        analysis_plan: dict[str, Any],
        dataset_profile: dict[str, Any],
        attempt: int,
        previous_execution_result: dict[str, Any] | None,
        previous_validation_result: dict[str, Any] | None,
    ) -> str:
        class_column = _extract_required_column(analysis_plan, "class")
        score_column = _extract_required_column(analysis_plan, "score")
        name_column = _extract_required_column(analysis_plan, "name")

        context = {
            "attempt": attempt,
            "previous_execution_result": previous_execution_result,
            "previous_validation_result": previous_validation_result,
        }

        return f'''import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


INPUT_FILE = Path(r{input_file!r})
OUTPUT_DIR = Path(r{output_dir!r})
CHARTS_DIR = OUTPUT_DIR / "charts"
ANALYSIS_PLAN = json.loads({_json_string_literal(analysis_plan)})
DATASET_PROFILE = json.loads({_json_string_literal(dataset_profile)})
REPAIR_CONTEXT = json.loads({_json_string_literal(context)})
CLASS_COLUMN = {class_column!r}
SCORE_COLUMN = {score_column!r}
NAME_COLUMN = {name_column!r}
PASS_SCORE = 60
EXCELLENT_SCORE = 90


def safe_write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)


def load_dataset(input_file):
    suffix = input_file.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(input_file)
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(input_file)
    raise ValueError(f"Unsupported input file type: {{suffix}}")


def validate_columns(df, required_columns):
    missing = [column for column in required_columns if column and column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {{missing}}")


def write_error_result(error):
    payload = {{
        "success": False,
        "analysis_plan": ANALYSIS_PLAN,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "charts": [],
    }}
    safe_write_json(OUTPUT_DIR / "analysis_result.json", payload)
    safe_write_json(OUTPUT_DIR / "report_data.json", payload)


def configure_matplotlib():
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def save_bar_chart(summary, x_column, y_column, title, ylabel, output_path, percent=False):
    labels = summary[x_column].astype(str).tolist()
    values = summary[y_column].astype(float).tolist()
    plot_values = [value * 100 for value in values] if percent else values
    fig_width = max(8, min(16, len(labels) * 1.2))
    fig, ax = plt.subplots(figsize=(fig_width, 5))
    bars = ax.bar(labels, plot_values, color="#0f766e")
    ax.set_title(title)
    ax.set_xlabel(x_column)
    ax.set_ylabel(ylabel)
    if percent:
        ax.set_ylim(0, 105)
    suffix = "%" if percent else ""
    ax.bar_label(bars, labels=[f"{{value:.2f}}{{suffix}}" for value in plot_values], padding=3, fontsize=9)
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if not CLASS_COLUMN or not SCORE_COLUMN:
            raise ValueError("Analysis plan must provide class and score columns.")

        df = load_dataset(INPUT_FILE)
        df = df.rename(columns=lambda column: str(column).strip())
        validate_columns(df, [CLASS_COLUMN, SCORE_COLUMN])

        work_df = pd.DataFrame({{
            "class_name": df[CLASS_COLUMN].astype(str).str.strip(),
            "score": pd.to_numeric(df[SCORE_COLUMN], errors="coerce"),
        }})
        work_df = work_df.dropna(subset=["score"])
        work_df = work_df[work_df["class_name"].ne("")]
        work_df = work_df[work_df["class_name"].str.lower().ne("nan")]

        if work_df.empty:
            raise ValueError("No valid class and score rows found.")

        grouped = work_df.groupby("class_name", sort=True)["score"]
        summary = grouped.agg(
            student_count="count",
            average_score="mean",
            max_score="max",
            min_score="min",
        ).reset_index()
        summary["pass_rate"] = summary["class_name"].map(
            grouped.apply(lambda scores: float((scores >= PASS_SCORE).mean()))
        )
        summary["excellent_rate"] = summary["class_name"].map(
            grouped.apply(lambda scores: float((scores >= EXCELLENT_SCORE).mean()))
        )
        summary["average_score"] = summary["average_score"].round(2)
        summary["max_score"] = summary["max_score"].round(2)
        summary["min_score"] = summary["min_score"].round(2)
        summary["pass_rate"] = summary["pass_rate"].round(4)
        summary["excellent_rate"] = summary["excellent_rate"].round(4)

        configure_matplotlib()
        average_chart = CHARTS_DIR / "class_average_score.png"
        pass_rate_chart = CHARTS_DIR / "class_pass_rate.png"
        save_bar_chart(summary, "class_name", "average_score", "班级平均分", "平均分", average_chart)
        save_bar_chart(summary, "class_name", "pass_rate", "班级及格率", "及格率（%）", pass_rate_chart, percent=True)

        summary_records = summary.to_dict(orient="records")
        charts = [str(average_chart), str(pass_rate_chart)]
        analysis_result = {{
            "success": True,
            "task_type": "grade_analysis",
            "analysis_plan": ANALYSIS_PLAN,
            "fields": {{
                "class_field": CLASS_COLUMN,
                "name_field": NAME_COLUMN,
                "score_field": SCORE_COLUMN,
            }},
            "thresholds": {{
                "pass_score": PASS_SCORE,
                "excellent_score": EXCELLENT_SCORE,
            }},
            "summary": summary_records,
            "charts": charts,
        }}
        report_data = {{
            "success": True,
            "title": "成绩按班级统计分析",
            "summary": "已按班级生成成绩统计结果和图表。",
            "tables": [
                {{
                    "name": "class_summary",
                    "rows": summary_records,
                }}
            ],
            "charts": [
                {{
                    "title": "班级平均分",
                    "path": str(average_chart),
                    "data_reference": "analysis_result.summary.average_score",
                }},
                {{
                    "title": "班级及格率",
                    "path": str(pass_rate_chart),
                    "data_reference": "analysis_result.summary.pass_rate",
                }},
            ],
            "key_findings": [
                {{
                    "title": "班级成绩统计已完成",
                    "description": "各班人数、平均分、最高分、最低分、及格率和优秀率已生成。",
                    "evidence": "analysis_result.summary",
                }}
            ],
            "notes": [],
        }}
        safe_write_json(OUTPUT_DIR / "analysis_result.json", analysis_result)
        safe_write_json(OUTPUT_DIR / "report_data.json", report_data)
    except Exception as error:
        write_error_result(error)
        raise


if __name__ == "__main__":
    main()
'''

    def _generate_unsupported_task_script(
        self,
        input_file: str,
        output_dir: str,
        analysis_plan: dict[str, Any],
        dataset_profile: dict[str, Any],
    ) -> str:
        return f'''import json
from pathlib import Path

OUTPUT_DIR = Path(r{output_dir!r})
ANALYSIS_PLAN = json.loads({_json_string_literal(analysis_plan)})
DATASET_PROFILE = json.loads({_json_string_literal(dataset_profile)})

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {{
        "success": False,
        "error_type": "UnsupportedTaskType",
        "error_message": "Current rule-based CodeAgent only supports grade_analysis.",
        "analysis_plan": ANALYSIS_PLAN,
        "charts": [],
    }}
    with (OUTPUT_DIR / "analysis_result.json").open("w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
    with (OUTPUT_DIR / "report_data.json").open("w", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2)
    raise RuntimeError(payload["error_message"])

if __name__ == "__main__":
    main()
'''


def _extract_required_column(
    analysis_plan: dict[str, Any],
    semantic_name: str,
) -> str | None:
    for item in analysis_plan.get("required_columns", []):
        if item.get("semantic_name") == semantic_name:
            return item.get("column_name")
    return None


def _extract_python_code(content: str) -> str:
    stripped = content.strip()
    fenced_blocks = re.findall(
        r"```(?:python|py|PYTHON)?\s*(.*?)```",
        stripped,
        flags=re.DOTALL,
    )
    if fenced_blocks:
        return fenced_blocks[0].strip()
    return stripped


def _validate_generated_script(script: str, input_file: str, output_dir: str) -> None:
    if not script.strip():
        raise ValueError("Generated script is empty.")

    tree = ast.parse(script)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _validate_import_root(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                raise ValueError("Relative imports are not allowed in generated scripts.")
            _validate_import_root(node.module)

    required_fragments = [
        "INPUT_FILE",
        "OUTPUT_DIR",
        "analysis_result.json",
        "report_data.json",
        "charts",
    ]
    missing = [fragment for fragment in required_fragments if fragment not in script]
    if missing:
        raise ValueError(f"Generated script is missing required fragments: {missing}")

    if input_file not in script or output_dir not in script:
        raise ValueError("Generated script must embed the provided input_file and output_dir.")


def _validate_import_root(module_name: str) -> None:
    root = module_name.split(".", 1)[0]
    if root not in ALLOWED_IMPORT_ROOTS:
        raise ValueError(f"Generated script imports disallowed module: {module_name}")


def _to_rule_based_plan(
    analysis_plan: dict[str, Any],
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    if analysis_plan.get("task_type"):
        return analysis_plan

    columns = [str(column) for column in dataset_profile.get("columns", [])]
    dimension_column = _first_existing(analysis_plan.get("grouping_dimensions"), columns)
    score_column = _first_existing(analysis_plan.get("metrics"), columns)

    if score_column is None:
        numeric_columns = list(dataset_profile.get("numeric_summary", {}).keys())
        score_column = _first_existing(numeric_columns, columns)

    if dimension_column is None:
        dimension_column = _find_column(columns, ("班级", "class"))

    return {
        "task_type": "grade_analysis",
        "task_name": analysis_plan.get("analysis_goal") or "Grade analysis",
        "reasoning_summary": "Fallback rule-based code generation plan.",
        "steps": [],
        "required_columns": [
            {
                "semantic_name": "class",
                "column_name": dimension_column,
                "required": True,
                "reason": "Used for grouping.",
            },
            {
                "semantic_name": "score",
                "column_name": score_column,
                "required": True,
                "reason": "Used as numeric score metric.",
            },
            {
                "semantic_name": "name",
                "column_name": _find_column(columns, ("姓名", "name")),
                "required": False,
                "reason": "Optional identifier.",
            },
        ],
        "analysis_methods": [],
        "charts": [],
        "expected_artifacts": [],
        "risks": [],
    }


def _first_existing(value: Any, columns: list[str]) -> str | None:
    if not isinstance(value, list):
        return None
    allowed = set(columns)
    for item in value:
        name = str(item)
        if name in allowed:
            return name
    return None


def _find_column(columns: list[str], keywords: tuple[str, ...]) -> str | None:
    lowered_keywords = tuple(keyword.lower() for keyword in keywords)
    for column in columns:
        normalized_column = column.lower()
        if normalized_column in lowered_keywords:
            return column

    for column in columns:
        normalized_column = column.lower()
        if any(keyword in normalized_column for keyword in lowered_keywords):
            return column
    return None


def _json_string_literal(data: dict[str, Any]) -> str:
    json_text = json.dumps(data, ensure_ascii=False)
    return repr(json_text)
