import json
from datetime import datetime, timezone
from pathlib import Path
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
- Only regenerate the target chart requested by target_chart_path. Do not overwrite, delete, or restyle unrelated charts.
- Preserve the original analytical meaning unless the instruction explicitly changes chart type, grouping, filtering, labels, sorting, or visible fields.
- Use the target chart filename and title as important context. For example, a filename containing region/channel/category/trend should keep that chart's matching dimension or trend meaning.
- Prefer saving the refined chart with the same filename as target_chart_path under OUTPUT_DIR / "charts".
- Read only INPUT_FILE and files under OUTPUT_DIR.
- Write all generated artifacts under OUTPUT_DIR.
- Create or update PNG charts under OUTPUT_DIR / "charts".
- Keep analysis_result.json or prediction_result.json and report_data.json valid JSON if you touch them.
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
        "target_chart_filename": Path(str(target_chart_path)).name,
        "instruction": instruction,
        "dataset_profile": dataset_profile,
        "result_payload": result_payload,
        "execution_scope": "single_target_chart_only",
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
    target_name = Path(str(target_chart_path).replace("\\", "/")).name or (
        "refined_chart_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + ".png"
    )
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
TARGET_CHART_NAME = {target_name!r}
RESULT_FILENAME = {result_filename!r}


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


def _load_input_frame():
    suffix = INPUT_FILE.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(INPUT_FILE)
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(INPUT_FILE)
    return pd.DataFrame()


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


def _to_numeric_columns(frame):
    for column in frame.columns:
        if pd.api.types.is_numeric_dtype(frame[column]):
            continue
        converted = pd.to_numeric(frame[column], errors="coerce")
        if converted.notna().sum() >= max(1, len(frame) // 3):
            frame[column] = converted
    return frame


def _contains_any(text, words):
    lowered = str(text).lower()
    return any(str(word).lower() in lowered for word in words)


def _find_column(frame, word_groups):
    columns = list(frame.columns)
    for words in word_groups:
        for column in columns:
            if _contains_any(column, words):
                return column
    return ""


def _metric_column(frame):
    numeric_columns = [column for column in frame.columns if pd.api.types.is_numeric_dtype(frame[column])]
    if not numeric_columns:
        return ""
    preferred_groups = [
        ["销量", "sales", "销售量"],
        ["销售额", "revenue", "amount", "gmv"],
        ["平均", "mean", "avg"],
        ["数量", "count", "订单", "orders"],
        ["值", "value", "metric"],
    ]
    matched = _find_column(frame[numeric_columns], preferred_groups)
    return matched or numeric_columns[0]


def _date_column(frame):
    return _find_column(frame, [["日期", "date", "时间", "time"], ["月份", "month", "月"]])


def _dimension_column(frame):
    target_text = f"{{TARGET_CHART_PATH}} {{INSTRUCTION}}"
    candidates = []
    if _contains_any(target_text, ["地区", "区域", "region", "area"]):
        candidates.append(["地区", "区域", "region", "area"])
    if _contains_any(target_text, ["渠道", "channel"]):
        candidates.append(["渠道", "channel"])
    if _contains_any(target_text, ["商品类别", "品类", "类别", "category"]):
        candidates.append(["商品类别", "品类", "类别", "category"])
    if _contains_any(target_text, ["商品", "产品", "product"]):
        candidates.append(["商品", "产品", "product"])
    if _contains_any(target_text, ["班级", "class"]):
        candidates.append(["班级", "class"])
    candidates.extend([
        ["地区", "区域", "region", "area"],
        ["渠道", "channel"],
        ["商品类别", "品类", "类别", "category"],
        ["商品", "产品", "product"],
        ["班级", "class"],
    ])
    return _find_column(frame, candidates)


def _wants_trend():
    return _contains_any(
        f"{{TARGET_CHART_PATH}} {{INSTRUCTION}}",
        ["trend", "趋势", "时间", "日期", "月份", "环比", "同比", "变化率", "峰谷", "下降最快", "反弹"],
    )


def _chart_kind():
    if _contains_any(INSTRUCTION, ["折线", "line", "环比", "同比", "趋势", "变化率"]):
        return "line"
    if _contains_any(INSTRUCTION, ["散点", "scatter"]):
        return "scatter"
    if _contains_any(INSTRUCTION, ["横向", "条形", "barh"]):
        return "barh"
    return "bar"


def _limit_rows(frame):
    if _contains_any(INSTRUCTION, ["前 10", "前10", "top 10", "top10", "关键"]):
        return frame.head(10)
    return frame.head(30)


def _plot_trend(frame, metric):
    date_col = _date_column(frame)
    if not date_col or not metric:
        return False
    working = frame[[date_col, metric]].copy().dropna(subset=[metric])
    if working.empty:
        return False
    parsed = pd.to_datetime(working[date_col], errors="coerce")
    if parsed.notna().sum() > 0:
        working[date_col] = parsed.fillna(working[date_col])
    trend = working.groupby(date_col, dropna=False)[metric].sum().reset_index().sort_values(date_col)
    if trend.empty:
        return False
    x_values = trend[date_col].astype(str)
    y_values = trend[metric]
    if _contains_any(INSTRUCTION, ["同比", "环比", "变化率"]):
        y_values = y_values.pct_change() * 100
        ylabel = f"{{metric}}变化率(%)"
        title = f"{{metric}}变化率趋势"
    else:
        ylabel = str(metric)
        title = f"{{metric}}趋势"
    plt.plot(x_values, y_values, marker="o")
    plt.title(title)
    plt.xlabel(str(date_col))
    plt.ylabel(ylabel)
    plt.xticks(rotation=35, ha="right")
    if _contains_any(INSTRUCTION, ["峰谷", "最高", "最低", "最低点", "最高点"]):
        valid = pd.to_numeric(y_values, errors="coerce")
        if valid.notna().any():
            max_idx = valid.idxmax()
            min_idx = valid.idxmin()
            for idx, label in [(max_idx, "最高"), (min_idx, "最低")]:
                plt.scatter([x_values.loc[idx]], [y_values.loc[idx]])
                plt.annotate(f"{{label}}: {{y_values.loc[idx]:.2f}}", (x_values.loc[idx], y_values.loc[idx]), textcoords="offset points", xytext=(0, 8), ha="center")
    if _contains_any(INSTRUCTION, ["下降最快", "下降最大", "下滑最快"]):
        valid = pd.to_numeric(trend[metric], errors="coerce")
        diffs = valid.diff()
        if diffs.notna().any():
            drop_idx = diffs.idxmin()
            if pd.notna(diffs.loc[drop_idx]) and drop_idx > 0:
                prev_idx = drop_idx - 1
                plt.axvspan(prev_idx - 0.15, drop_idx + 0.15, alpha=0.18)
                plt.annotate(f"下降最快: {{diffs.loc[drop_idx]:.2f}}", (x_values.loc[drop_idx], trend[metric].loc[drop_idx]), textcoords="offset points", xytext=(0, -18), ha="center")
    return True


def _plot_dimension(frame, metric):
    dimension = _dimension_column(frame)
    if not dimension or not metric:
        return False
    grouped = frame[[dimension, metric]].copy().dropna(subset=[dimension, metric])
    if grouped.empty:
        return False
    grouped[dimension] = grouped[dimension].astype(str)
    summary = grouped.groupby(dimension, dropna=False)[metric].sum().reset_index()
    ascending = _contains_any(INSTRUCTION, ["升序", "从低到高", "最低"])
    if _contains_any(INSTRUCTION, ["排序", "排行", "最高", "最大", "top", "前"]):
        summary = summary.sort_values(metric, ascending=ascending)
    summary = _limit_rows(summary)
    kind = _chart_kind()
    x_values = summary[dimension]
    y_values = summary[metric]
    if kind == "line":
        plt.plot(x_values, y_values, marker="o")
        plt.xticks(rotation=35, ha="right")
    elif kind == "scatter":
        plt.scatter(range(len(summary)), y_values)
        plt.xticks(range(len(summary)), x_values, rotation=35, ha="right")
    elif kind == "barh":
        plt.barh(x_values, y_values)
    else:
        plt.bar(x_values, y_values)
        plt.xticks(rotation=35, ha="right")
    plt.title(f"按{{dimension}}对比{{metric}}")
    plt.xlabel(str(dimension))
    plt.ylabel(str(metric))
    if _contains_any(INSTRUCTION, ["数值标签", "显示数值", "标注"]):
        if kind == "barh":
            for index, value in enumerate(y_values):
                plt.text(value, index, f"{{value:.2f}}", va="center")
        else:
            for index, value in enumerate(y_values):
                plt.text(index, value, f"{{value:.2f}}", ha="center", va="bottom", fontsize=8)
    if _contains_any(INSTRUCTION, ["限制", "口径", "说明"]):
        plt.figtext(0.01, 0.01, "说明：图表基于当前数据和已选指标生成，结论需结合业务口径进一步验证。", fontsize=9)
    return True


def _plot_from_result_payload():
    result_payload = _read_json(OUTPUT_DIR / RESULT_FILENAME)
    report_payload = _read_json(OUTPUT_DIR / "report_data.json")
    rows = _rows_from_payload(result_payload) or _rows_from_payload(report_payload)
    if not rows:
        return False
    frame = _to_numeric_columns(pd.DataFrame(rows))
    metric = _metric_column(frame)
    return _plot_dimension(frame, metric)


def _update_payloads(chart_entry):
    for filename in [RESULT_FILENAME, "report_data.json"]:
        path = OUTPUT_DIR / filename
        payload = _read_json(path)
        if not payload:
            continue
        charts = payload.get("charts")
        if not isinstance(charts, list):
            charts = []
        if chart_entry not in charts:
            charts.append(chart_entry)
        payload["charts"] = charts
        refinements = payload.get("chart_refinements")
        if not isinstance(refinements, list):
            refinements = []
        refinements.append({{"target_chart_path": TARGET_CHART_PATH, "instruction": INSTRUCTION, "chart_path": chart_entry}})
        payload["chart_refinements"] = refinements
        _write_json(path, payload)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    _configure_fonts()

    chart_path = CHARTS_DIR / TARGET_CHART_NAME
    plt.figure(figsize=(10, 5.8))
    plotted = False
    try:
        frame = _to_numeric_columns(_load_input_frame())
        metric = _metric_column(frame)
        if not frame.empty:
            if _wants_trend():
                plotted = _plot_trend(frame, metric)
            if not plotted:
                plotted = _plot_dimension(frame, metric)
        if not plotted:
            plotted = _plot_from_result_payload()
    except Exception as exc:
        plt.text(0.5, 0.52, "图表调整未能读取到足够数据", ha="center", va="center")
        plt.text(0.5, 0.44, str(exc)[:120], ha="center", va="center", fontsize=9)
        plt.axis("off")
        plotted = True
    if not plotted:
        plt.text(0.5, 0.5, "当前结果缺少可绘制的数据", ha="center", va="center")
        plt.axis("off")
    plt.tight_layout()
    plt.savefig(chart_path, dpi=160, bbox_inches="tight")
    plt.close()
    _update_payloads(str(chart_path))


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
