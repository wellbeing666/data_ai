import json
from datetime import datetime, timezone
from typing import Any

from app.agents.code_agent import (
    _enforce_matplotlib_chinese_font_setup,
    _enforce_runtime_constants,
    _extract_python_code,
    _validate_generated_script,
)
from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the Chart Code Refinement Agent of an AI-native data analysis workbench.

Return only a complete executable Python script. Do not output Markdown or explanations.

Your task is to modify the original analysis script according to a user instruction for one target chart.
Hard requirements:
- Preserve the original analytical meaning unless the instruction explicitly changes chart type, grouping, filtering, labels, sorting, or visible fields.
- Read only INPUT_FILE and files under OUTPUT_DIR.
- Write all generated artifacts under OUTPUT_DIR.
- Create or update PNG charts under OUTPUT_DIR / "charts".
- Keep analysis_result.json or prediction_result.json and report_data.json valid JSON.
- Append the refined chart path to the result charts list, or replace the target chart when safe.
- Use matplotlib Agg backend and configure Chinese fonts before creating figures.
- Do not import requests, subprocess, shutil, socket, scipy, sklearn, statsmodels, or any network/system libraries.
- Do not call eval, exec, os.system, or access paths outside INPUT_FILE and OUTPUT_DIR.
"""


def build_user_prompt(
    *,
    input_file: str,
    output_dir: str,
    original_script: str,
    target_chart_path: str,
    instruction: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    workflow_type: str,
) -> str:
    context = {
        "workflow_type": workflow_type,
        "target_chart_path": target_chart_path,
        "instruction": instruction,
        "dataset_profile": dataset_profile,
        "result_payload": result_payload,
    }
    return """Modify the chart generation code in the original script.

Use these exact constants at module level:
INPUT_FILE = Path(r{input_file!r})
OUTPUT_DIR = Path(r{output_dir!r})
CHARTS_DIR = OUTPUT_DIR / "charts"

The script must contain these exact path strings:
- {input_file}
- {output_dir}

Refinement context JSON:
{context}

Original script:
```python
{original_script}
```

Return only the full updated Python script. The script must define main() and call it under if __name__ == "__main__".
""".format(
        input_file=input_file,
        output_dir=output_dir,
        context=json.dumps(context, ensure_ascii=False, indent=2),
        original_script=original_script,
    )


class ChartCodeRefinerAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def refine_script(
        self,
        *,
        input_file: str,
        output_dir: str,
        original_script: str,
        target_chart_path: str,
        instruction: str,
        dataset_profile: dict[str, Any],
        result_payload: dict[str, Any],
        workflow_type: str,
    ) -> str:
        try:
            content = self.llm_client.chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            input_file=input_file,
                            output_dir=output_dir,
                            original_script=original_script,
                            target_chart_path=target_chart_path,
                            instruction=instruction,
                            dataset_profile=dataset_profile,
                            result_payload=result_payload,
                            workflow_type=workflow_type,
                        ),
                    },
                ],
                temperature=0.1,
            )
            script = _extract_python_code(content)
            script = _enforce_runtime_constants(script, input_file=input_file, output_dir=output_dir)
            script = _enforce_matplotlib_chinese_font_setup(script)
            _validate_generated_script(script, input_file=input_file, output_dir=output_dir)
            return script
        except Exception:
            return build_rule_based_chart_refinement_script(
                input_file=input_file,
                output_dir=output_dir,
                instruction=instruction,
                target_chart_path=target_chart_path,
                workflow_type=workflow_type,
            )


def build_rule_based_chart_refinement_script(
    *,
    input_file: str,
    output_dir: str,
    instruction: str,
    target_chart_path: str,
    workflow_type: str,
) -> str:
    result_filename = "prediction_result.json" if workflow_type == "what_if_prediction" else "analysis_result.json"
    refined_name = "refined_chart_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + ".png"
    return f'''import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

INPUT_FILE = Path(r"{input_file}")
OUTPUT_DIR = Path(r"{output_dir}")
CHARTS_DIR = OUTPUT_DIR / "charts"
INSTRUCTION = {instruction!r}
TARGET_CHART_PATH = {target_chart_path!r}
RESULT_FILENAME = {result_filename!r}
REFINED_CHART_NAME = {refined_name!r}


def _configure_fonts():
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def _read_json(path):
    if not path.exists():
        return {{}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {{}}
    return data if isinstance(data, dict) else {{}}


def _write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _rows_from_payload(payload):
    for key in ["summary", "top_impacted_entities", "data", "rows"]:
        value = payload.get(key)
        if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
            return value
    nested = payload.get("analysis_summary")
    if isinstance(nested, dict):
        rows = []
        for key, value in nested.items():
            if isinstance(value, dict):
                row = {{"项目": key}}
                row.update(value)
                rows.append(row)
        if rows:
            return rows
    return []


def _choose_columns(frame):
    if frame.empty:
        return None, None
    text_columns = [column for column in frame.columns if not pd.api.types.is_numeric_dtype(frame[column])]
    numeric_columns = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    if not numeric_columns:
        for column in frame.columns:
            converted = pd.to_numeric(frame[column], errors="coerce")
            if converted.notna().sum() > 0:
                frame[column] = converted
                numeric_columns.append(column)
    x_column = text_columns[0] if text_columns else frame.columns[0]
    y_column = numeric_columns[0] if numeric_columns else None
    return x_column, y_column


def _chart_type():
    lowered = INSTRUCTION.lower()
    if "折线" in INSTRUCTION or "line" in lowered:
        return "line"
    if "散点" in INSTRUCTION or "scatter" in lowered:
        return "scatter"
    if "横向" in INSTRUCTION:
        return "barh"
    return "bar"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    _configure_fonts()

    result_path = OUTPUT_DIR / RESULT_FILENAME
    report_path = OUTPUT_DIR / "report_data.json"
    result_payload = _read_json(result_path)
    report_payload = _read_json(report_path)
    rows = _rows_from_payload(result_payload) or _rows_from_payload(report_payload)

    if not rows:
        suffix = INPUT_FILE.suffix.lower()
        if suffix == ".csv":
            df = pd.read_csv(INPUT_FILE)
        elif suffix in [".xlsx", ".xls"]:
            df = pd.read_excel(INPUT_FILE)
        else:
            df = pd.DataFrame()
        rows = df.head(30).to_dict(orient="records")

    frame = pd.DataFrame(rows)
    for column in frame.columns:
        numeric = pd.to_numeric(frame[column], errors="coerce")
        if numeric.notna().sum() >= max(1, len(frame) // 3):
            frame[column] = numeric
    x_column, y_column = _choose_columns(frame)
    chart_path = CHARTS_DIR / REFINED_CHART_NAME

    plt.figure(figsize=(10, 5.8))
    if x_column is None or y_column is None or frame.empty:
        plt.text(0.5, 0.5, "当前结果缺少可绘制的数据", ha="center", va="center")
        plt.axis("off")
    else:
        chart_frame = frame[[x_column, y_column]].dropna().head(30)
        chart_frame[x_column] = chart_frame[x_column].astype(str)
        kind = _chart_type()
        if kind == "line":
            plt.plot(chart_frame[x_column], chart_frame[y_column], marker="o")
        elif kind == "scatter":
            plt.scatter(range(len(chart_frame)), chart_frame[y_column])
            plt.xticks(range(len(chart_frame)), chart_frame[x_column], rotation=35, ha="right")
        elif kind == "barh":
            plt.barh(chart_frame[x_column], chart_frame[y_column])
        else:
            plt.bar(chart_frame[x_column], chart_frame[y_column])
            plt.xticks(rotation=35, ha="right")
        plt.title("按要求调整后的图表")
        plt.xlabel(str(x_column))
        plt.ylabel(str(y_column))
        plt.tight_layout()
    plt.savefig(chart_path, dpi=160, bbox_inches="tight")
    plt.close()

    chart_entry = str(chart_path)
    for payload in [result_payload, report_payload]:
        charts = payload.get("charts")
        if not isinstance(charts, list):
            charts = []
        charts.append(chart_entry)
        payload["charts"] = charts
        refinements = payload.get("chart_refinements")
        if not isinstance(refinements, list):
            refinements = []
        refinements.append({{"target_chart_path": TARGET_CHART_PATH, "instruction": INSTRUCTION, "chart_path": chart_entry}})
        payload["chart_refinements"] = refinements

    _write_json(result_path, result_payload)
    _write_json(report_path, report_payload)


if __name__ == "__main__":
    main()
'''


def create_refined_chart_script(
    *,
    input_file: str,
    output_dir: str,
    original_script: str,
    target_chart_path: str,
    instruction: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    workflow_type: str,
    llm_client: LLMClient | None = None,
) -> str:
    return ChartCodeRefinerAgent(llm_client=llm_client).refine_script(
        input_file=input_file,
        output_dir=output_dir,
        original_script=original_script,
        target_chart_path=target_chart_path,
        instruction=instruction,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        workflow_type=workflow_type,
    )
