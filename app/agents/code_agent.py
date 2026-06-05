import json
import ast
import re
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


LLM_ONLY_ATTEMPTS = 3
SALES_DECLINE_EARLY_FALLBACK_ATTEMPT = 2

ALLOWED_IMPORT_ROOTS = {
    "pandas",
    "numpy",
    "matplotlib",
    "seaborn",
    "duckdb",
    "json",
    "math",
    "os",
    "pathlib",
    "warnings",
    "sys",
}

SYSTEM_PROMPT = """You are the Code Agent of an AI-native data analysis workbench.

Return only executable Python code. Do not output markdown, code fences, comments outside code, or explanation.

Hard requirements:
- Use only these libraries: pandas, numpy, matplotlib, seaborn, duckdb, json, math, os, pathlib, warnings.
- The code must read INPUT_FILE.
- The code must write all outputs under OUTPUT_DIR.
- The code must create OUTPUT_DIR / "analysis_result.json".
- The code must create OUTPUT_DIR / "report_data.json".
- The code must create at least one PNG chart under OUTPUT_DIR / "charts".
- analysis_result.json must include task_type equal to Analysis plan JSON task_type.
- The code must support CSV, XLSX, and XLS input files.
- The code must handle Chinese column names by treating all column names as strings and preserving UTF-8 JSON output.
- Do not write repair context, previous execution logs, validation logs, stderr, artifact lists, duration_ms, or size_bytes into analysis_result.json or report_data.json.
- Use matplotlib Agg backend before importing pyplot.
- Configure matplotlib Chinese fonts before creating charts so Chinese labels render correctly. Use font_manager when available and set plt.rcParams["font.sans-serif"] plus plt.rcParams["axes.unicode_minus"] = False.
- Use Chinese visible chart text for chart titles, axis labels, legends, and annotations.
- If the requested advanced analysis is risky or a previous attempt failed, produce a simpler but valid task-aligned analysis instead of crashing.
- Prefer robust pandas operations: coerce numeric columns, drop invalid rows for calculations, cap chart categories to Top 20, and always save at least one PNG chart.
- Do not import sklearn, scipy, statsmodels, requests, subprocess, or shutil.
- Do not import any library that is not explicitly listed above. In particular, avoid sklearn/scipy/statsmodels even for feature importance or statistical tests; use pandas/numpy approximations instead.
- The generated code must contain literal assignments for the exact INPUT_FILE and OUTPUT_DIR constants provided in the user prompt. Do not compute, omit, rename, or replace these paths.
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

You must copy the INPUT_FILE and OUTPUT_DIR assignments above into the script exactly.
The generated source must contain these exact path strings:
- {input_file}
- {output_dir}
Do not derive these paths from cwd, environment variables, command-line arguments, or relative paths.

Dataset profile JSON:
{dataset_profile}

Analysis plan JSON:
{analysis_plan}

Repair context JSON:
{context}

If this is attempt 2 or later, fix the previous error using previous_stderr,
previous_validation_result, and previous_repair_suggestions. Do not repeat unsafe
operations or missing-artifact mistakes from earlier attempts.

Chinese chart requirements:
- Configure matplotlib Chinese fonts before any figure is created.
- Use Chinese visible text in chart titles, axis labels, legends, and annotations when the analysis goal is Chinese.
- Do not rely on the default DejaVu Sans font for Chinese text.

Reliability requirements:
- Keep analysis_result.task_type exactly equal to analysis_plan.task_type.
- If a complex method fails, fall back inside the generated script to a basic profile / grouped summary that still writes analysis_result.json, report_data.json, and charts/*.png.
- Treat validation feedback as mandatory. If validation reported missing artifacts, the repaired script must write those artifacts before exiting.
- Use only the allowed imports from the system prompt. If you need unsupported statistical/modeling functionality, replace it with pandas/numpy logic.

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
            script = _enforce_runtime_constants(
                script,
                input_file=input_file,
                output_dir=output_dir,
            )
            script = _enforce_matplotlib_chinese_font_setup(script)
            _validate_generated_script(script, input_file=input_file, output_dir=output_dir)
            return script
        except Exception as exc:
            if _should_use_sales_decline_fallback(analysis_plan, attempt, previous_execution_result, previous_validation_result):
                return self.rule_based_agent.generate_script(
                    input_file=input_file,
                    output_dir=output_dir,
                    analysis_plan=_to_rule_based_plan(analysis_plan, dataset_profile),
                    dataset_profile=dataset_profile,
                    attempt=attempt,
                    previous_execution_result=previous_execution_result,
                    previous_validation_result=previous_validation_result,
                )
            if attempt <= LLM_ONLY_ATTEMPTS:
                raise CodeGenerationError(
                    f"LLM code generation failed on attempt {attempt}: {exc}"
                ) from exc
            return self.rule_based_agent.generate_script(
                input_file=input_file,
                output_dir=output_dir,
                analysis_plan=_to_rule_based_plan(analysis_plan, dataset_profile),
                dataset_profile=dataset_profile,
                attempt=attempt,
                previous_execution_result=previous_execution_result,
                previous_validation_result=previous_validation_result,
            )


def _should_use_sales_decline_fallback(
    analysis_plan: dict[str, Any],
    attempt: int,
    previous_execution_result: dict[str, Any] | None,
    previous_validation_result: dict[str, Any] | None,
) -> bool:
    task_type = str(analysis_plan.get("task_type") or "")
    if task_type != "sales_decline_analysis":
        return False
    if attempt < SALES_DECLINE_EARLY_FALLBACK_ATTEMPT:
        return False
    return previous_execution_result is not None or previous_validation_result is not None


class CodeGenerationError(RuntimeError):
    pass


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
        if task_type == "sales_decline_analysis":
            return self._generate_sales_decline_script(
                input_file=input_file,
                output_dir=output_dir,
                analysis_plan=analysis_plan,
                dataset_profile=dataset_profile,
            )
        if task_type != "grade_analysis":
            return self._generate_general_analysis_script(
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

    def _generate_sales_decline_script(
        self,
        input_file: str,
        output_dir: str,
        analysis_plan: dict[str, Any],
        dataset_profile: dict[str, Any],
    ) -> str:
        columns = [str(column) for column in dataset_profile.get("columns") or []]
        numeric_summary = dataset_profile.get("numeric_summary") if isinstance(dataset_profile.get("numeric_summary"), dict) else {}
        metric = _find_column(columns, ("销量", "销售额", "收入", "gmv", "sales", "revenue", "amount", "订单"))
        if not metric:
            metrics = [item for item in analysis_plan.get("metrics") or [] if str(item) in columns]
            metric = str(metrics[0]) if metrics else next((col for col in columns if col in numeric_summary), columns[0] if columns else "")
        date_col = _find_column(columns, ("日期", "时间", "月份", "年月", "date", "month", "time", "day"))
        dimensions = [str(item) for item in analysis_plan.get("grouping_dimensions") or [] if str(item) in columns and str(item) != metric]
        if not dimensions:
            dimensions = [col for col in columns if col != metric and col != date_col and col not in numeric_summary][:3]
        return f'''import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
import pandas as pd

INPUT_FILE = Path(r"{input_file}")
OUTPUT_DIR = Path(r"{output_dir}")
CHARTS_DIR = OUTPUT_DIR / "charts"
TASK_TYPE = "sales_decline_analysis"
METRIC_COLUMN = {metric!r}
DATE_COLUMN = {date_col!r}
DIMENSION_COLUMNS = {dimensions!r}


def _configure_generated_chart_fonts():
    available_fonts = {{font.name for font in font_manager.fontManager.ttflist}}
    preferred_fonts = ["Noto Sans CJK SC", "Noto Sans CJK JP", "Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    font_name = next((font for font in preferred_fonts if font in available_fonts), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [font_name]
    plt.rcParams["axes.unicode_minus"] = False


def _read_input(path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        for encoding in ("utf-8", "utf-8-sig", "gbk"):
            try:
                return pd.read_csv(path, encoding=encoding)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(path)
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    raise ValueError("unsupported input file")


def _safe_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def _save_line_chart(monthly):
    chart_path = CHARTS_DIR / "sales_decline_trend.png"
    plt.figure(figsize=(9, 4.8))
    if len(monthly) > 0:
        plt.plot(monthly["period"].astype(str), monthly["value"], marker="o")
    else:
        plt.plot(["无有效日期"], [0], marker="o")
    plt.title("销量/销售指标趋势")
    plt.xlabel("时间")
    plt.ylabel(METRIC_COLUMN or "指标")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    plt.close()
    return str(chart_path)


def _save_contribution_chart(contribution, dim):
    chart_path = CHARTS_DIR / f"contribution_{{dim}}.png"
    plt.figure(figsize=(9, 4.8))
    if len(contribution) > 0:
        plot_df = contribution.head(12).sort_values("change")
        plt.barh(plot_df[dim].astype(str), plot_df["change"])
    else:
        plt.barh(["无有效分组"], [0])
    plt.title(f"{{dim}} 下降贡献")
    plt.xlabel("变化量")
    plt.ylabel(dim)
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    plt.close()
    return str(chart_path)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    _configure_generated_chart_fonts()
    df = _read_input(INPUT_FILE)
    df.columns = [str(col).strip() for col in df.columns]
    if not METRIC_COLUMN or METRIC_COLUMN not in df.columns:
        numeric_candidates = []
        for col in df.columns:
            values = _safe_numeric(df[col])
            if values.notna().sum() >= max(3, len(df) * 0.4):
                numeric_candidates.append(col)
        metric = numeric_candidates[0] if numeric_candidates else df.columns[0]
    else:
        metric = METRIC_COLUMN
    df["__metric__"] = _safe_numeric(df[metric]).fillna(0)
    charts = []
    findings = []
    limitations = ["当前自动脚本用于降低重复修复次数，输出为稳健的趋势和分组相关信号，不能证明确定因果。"]
    trend = {{}}
    if DATE_COLUMN and DATE_COLUMN in df.columns:
        parsed = pd.to_datetime(df[DATE_COLUMN], errors="coerce")
        temp = df.copy()
        temp["__period__"] = parsed.dt.to_period("M").astype(str)
        temp = temp[parsed.notna()]
        if len(temp) > 0:
            monthly = temp.groupby("__period__")["__metric__"].sum().reset_index().rename(columns={{"__period__": "period", "__metric__": "value"}}).sort_values("period")
        else:
            monthly = pd.DataFrame(columns=["period", "value"])
    else:
        monthly = pd.DataFrame({{"period": ["全量"], "value": [float(df["__metric__"].sum())]}})
        limitations.append("未识别到可靠日期字段，因此无法完成严格时间趋势拆解。")
    if len(monthly) >= 2:
        first_value = float(monthly["value"].iloc[0])
        last_value = float(monthly["value"].iloc[-1])
        delta = last_value - first_value
        delta_pct = (delta / abs(first_value) * 100) if abs(first_value) > 1e-12 else None
        trend = {{"start_period": str(monthly["period"].iloc[0]), "end_period": str(monthly["period"].iloc[-1]), "start_value": first_value, "end_value": last_value, "delta": delta, "delta_pct": delta_pct}}
        if delta_pct is not None:
            findings.append(f"从 {{trend['start_period']}} 到 {{trend['end_period']}}，{{metric}} 变化约 {{delta_pct:+.2f}}%，属于需要重点复核的趋势信号。")
        else:
            findings.append(f"从 {{trend['start_period']}} 到 {{trend['end_period']}}，{{metric}} 变化量为 {{delta:+.3g}}。")
    else:
        trend = {{"total_value": float(df["__metric__"].sum())}}
        findings.append(f"当前数据可统计 {{metric}} 全量合计，但时间点不足，无法判断连续下降趋势。")
    charts.append(_save_line_chart(monthly))
    contribution_tables = {{}}
    if len(monthly) >= 2 and DATE_COLUMN and DATE_COLUMN in df.columns:
        start_period = str(monthly["period"].iloc[0])
        end_period = str(monthly["period"].iloc[-1])
        parsed = pd.to_datetime(df[DATE_COLUMN], errors="coerce")
        work = df.copy()
        work["__period__"] = parsed.dt.to_period("M").astype(str)
        for dim in DIMENSION_COLUMNS[:3]:
            if dim not in work.columns:
                continue
            pivot = work[work["__period__"].isin([start_period, end_period])].groupby([dim, "__period__"])["__metric__"].sum().unstack(fill_value=0)
            if start_period not in pivot.columns:
                pivot[start_period] = 0
            if end_period not in pivot.columns:
                pivot[end_period] = 0
            contribution = pivot.reset_index()
            contribution["start_value"] = contribution[start_period]
            contribution["end_value"] = contribution[end_period]
            contribution["change"] = contribution["end_value"] - contribution["start_value"]
            contribution["change_pct"] = contribution.apply(lambda row: (row["change"] / abs(row["start_value"]) * 100) if abs(row["start_value"]) > 1e-12 else None, axis=1)
            contribution = contribution[[dim, "start_value", "end_value", "change", "change_pct"]].sort_values("change")
            contribution_tables[dim] = contribution.head(20).to_dict(orient="records")
            charts.append(_save_contribution_chart(contribution, dim))
            if len(contribution) > 0:
                worst = contribution.iloc[0]
                findings.append(f"{{dim}} 维度中，{{worst[dim]}} 的 {{metric}} 变化量最低（{{worst['change']:+.3g}}），可能是优先排查分组。")
    if not contribution_tables:
        for dim in DIMENSION_COLUMNS[:2]:
            if dim not in df.columns:
                continue
            grouped = df.groupby(dim)["__metric__"].sum().reset_index().sort_values("__metric__", ascending=False).head(20)
            contribution_tables[dim] = grouped.rename(columns={{"__metric__": "value"}}).to_dict(orient="records")
    result = {{
        "success": True,
        "task_type": TASK_TYPE,
        "analysis_type": TASK_TYPE,
        "metric_column": metric,
        "date_column": DATE_COLUMN,
        "dimension_columns": DIMENSION_COLUMNS,
        "rows": int(len(df)),
        "trend": trend,
        "findings": findings,
        "key_findings": findings,
        "contribution_tables": contribution_tables,
        "charts": charts,
        "chart_paths": charts,
        "limitations": limitations,
        "recommendations": [
            "优先复核下降贡献最大的地区、渠道或品类，检查库存、价格、活动、投放和竞品变化。",
            "补充外部业务事件和更长时间跨度数据，以验证当前下降信号是否持续。",
            "把高风险分组转化为可验证假设，设计小规模运营实验或专项复盘。",
        ],
    }}
    with (OUTPUT_DIR / "analysis_result.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with (OUTPUT_DIR / "report_data.json").open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
'''

    def _generate_general_analysis_script(
        self,
        input_file: str,
        output_dir: str,
        analysis_plan: dict[str, Any],
        dataset_profile: dict[str, Any],
    ) -> str:
        task_type = str(analysis_plan.get("task_type") or "general_data_analysis")
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
TASK_TYPE = {task_type!r}


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


def configure_matplotlib():
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def first_existing(candidates, columns):
    allowed = set(str(column) for column in columns)
    if isinstance(candidates, list):
        for item in candidates:
            name = str(item)
            if name in allowed:
                return name
    return ""


def choose_metric(df):
    metric = first_existing(ANALYSIS_PLAN.get("metrics"), df.columns)
    if metric and pd.to_numeric(df[metric], errors="coerce").notna().sum() > 0:
        return metric
    profile_numeric = list((DATASET_PROFILE.get("numeric_summary") or {{}}).keys())
    metric = first_existing(profile_numeric, df.columns)
    if metric:
        return metric
    for column in df.columns:
        if pd.to_numeric(df[column], errors="coerce").notna().sum() > 0:
            return str(column)
    return ""


def choose_dimension(df, metric):
    dimension = first_existing(ANALYSIS_PLAN.get("grouping_dimensions"), df.columns)
    if dimension and dimension != metric:
        return dimension
    for column in df.columns:
        if str(column) == metric:
            continue
        series = df[column]
        if series.dtype == object or str(series.dtype).startswith("category"):
            unique_count = series.nunique(dropna=True)
            if 1 < unique_count <= 30:
                return str(column)
    return ""


def clean_json_value(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        return value.item()
    return value


def build_numeric_summary(df):
    rows = []
    numeric_columns = []
    for column in df.columns:
        numeric = pd.to_numeric(df[column], errors="coerce")
        if numeric.notna().sum() == 0:
            continue
        numeric_columns.append(str(column))
        rows.append({{
            "field": str(column),
            "count": int(numeric.notna().sum()),
            "mean": round(float(numeric.mean()), 6),
            "min": round(float(numeric.min()), 6),
            "max": round(float(numeric.max()), 6),
            "missing_count": int(numeric.isna().sum()),
        }})
    return rows, numeric_columns


def save_missing_chart(df):
    missing = df.isna().sum().sort_values(ascending=False).head(20)
    if missing.empty:
        missing = pd.Series([0], index=["无字段"])
    chart_path = CHARTS_DIR / "missing_values_top20.png"
    width = max(8, min(16, len(missing) * 0.6))
    fig, ax = plt.subplots(figsize=(width, 5))
    ax.bar(missing.index.astype(str), missing.values, color="#2563eb")
    ax.set_title("缺失值统计 Top 20")
    ax.set_xlabel("字段")
    ax.set_ylabel("缺失数量")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=160)
    plt.close(fig)
    return str(chart_path)


def save_group_metric_chart(df, dimension, metric):
    if not dimension or not metric:
        return ""
    work = pd.DataFrame({{
        "dimension": df[dimension].astype(str),
        "metric": pd.to_numeric(df[metric], errors="coerce"),
    }}).dropna(subset=["metric"])
    work = work[work["dimension"].ne("")]
    work = work[work["dimension"].str.lower().ne("nan")]
    if work.empty:
        return ""
    grouped = (
        work.groupby("dimension")["metric"]
        .mean()
        .sort_values(ascending=False)
        .head(20)
    )
    chart_path = CHARTS_DIR / "group_metric_mean_top20.png"
    width = max(8, min(18, len(grouped) * 0.75))
    fig, ax = plt.subplots(figsize=(width, 5))
    ax.bar(grouped.index.astype(str), grouped.values, color="#0f766e")
    ax.set_title(f"{{dimension}} 分组的 {{metric}} 均值 Top 20")
    ax.set_xlabel(dimension)
    ax.set_ylabel(f"{{metric}} 均值")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(chart_path, dpi=160)
    plt.close(fig)
    return str(chart_path)


def build_group_summary(df, dimension, metric):
    if not dimension or not metric:
        return []
    work = pd.DataFrame({{
        "dimension": df[dimension].astype(str),
        "metric": pd.to_numeric(df[metric], errors="coerce"),
    }}).dropna(subset=["metric"])
    if work.empty:
        return []
    grouped = (
        work.groupby("dimension")["metric"]
        .agg(count="count", mean="mean", min="min", max="max")
        .reset_index()
        .sort_values("mean", ascending=False)
        .head(30)
    )
    return [
        {{
            "dimension_value": str(row["dimension"]),
            "count": int(row["count"]),
            "mean": round(float(row["mean"]), 6),
            "min": round(float(row["min"]), 6),
            "max": round(float(row["max"]), 6),
        }}
        for _, row in grouped.iterrows()
    ]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()
    df = load_dataset(INPUT_FILE)
    df.columns = [str(column).strip() for column in df.columns]

    metric = choose_metric(df)
    dimension = choose_dimension(df, metric)
    numeric_summary, numeric_columns = build_numeric_summary(df)
    group_summary = build_group_summary(df, dimension, metric)
    charts = [save_missing_chart(df)]
    group_chart = save_group_metric_chart(df, dimension, metric)
    if group_chart:
        charts.append(group_chart)

    sample_rows = [
        {{str(key): clean_json_value(value) for key, value in row.items()}}
        for row in df.head(10).astype(object).where(pd.notnull(df.head(10)), None).to_dict(orient="records")
    ]
    analysis_result = {{
        "success": True,
        "task_type": TASK_TYPE,
        "analysis_plan": ANALYSIS_PLAN,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "selected_metric": metric,
        "selected_dimension": dimension,
        "numeric_summary": numeric_summary,
        "group_summary": group_summary,
        "sample_rows": sample_rows,
        "charts": charts,
    }}
    report_data = {{
        "success": True,
        "title": ANALYSIS_PLAN.get("analysis_goal") or "通用数据分析报告",
        "summary": f"已完成基础数据画像、缺失值检查和{{'按 ' + dimension + ' 分组的 ' + metric + ' 对比' if dimension and metric else '可用字段概览'}}。",
        "tables": [
            {{"name": "numeric_summary", "rows": numeric_summary}},
            {{"name": "group_summary", "rows": group_summary}},
        ],
        "charts": [{{"title": "缺失值统计", "path": charts[0], "data_reference": "analysis_result.numeric_summary"}}]
        + ([{{"title": "分组指标均值", "path": group_chart, "data_reference": "analysis_result.group_summary"}}] if group_chart else []),
        "key_findings": [
            {{
                "title": "数据画像已完成",
                "description": f"数据包含 {{len(df)}} 行、{{len(df.columns)}} 列，识别到 {{len(numeric_columns)}} 个可数值化字段。",
                "evidence": "analysis_result.row_count / analysis_result.numeric_summary",
            }},
            {{
                "title": "主要分析字段",
                "description": f"当前兜底分析选择指标字段：{{metric or '未识别'}}；分组字段：{{dimension or '未识别'}}。",
                "evidence": "analysis_result.selected_metric / analysis_result.selected_dimension",
            }},
        ],
        "limitations": [
            "这是通用兜底分析结果，适合快速检查数据结构和主要分组差异；复杂统计关系仍建议使用 LLM 生成的专项分析脚本。",
        ],
    }}
    safe_write_json(OUTPUT_DIR / "analysis_result.json", analysis_result)
    safe_write_json(OUTPUT_DIR / "report_data.json", report_data)

if __name__ == "__main__":
    main()
'''



MATPLOTLIB_CHINESE_FONT_SETUP = """
def _configure_generated_chart_fonts():
    candidate_fonts = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "KaiTi",
        "FangSong",
        "Microsoft JhengHei",
        "PingFang SC",
        "Hiragino Sans GB",
        "Heiti SC",
        "Songti SC",
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Noto Sans CJK KR",
        "Source Han Sans SC",
        "Source Han Sans CN",
        "WenQuanYi Micro Hei",
        "WenQuanYi Zen Hei",
        "Arial Unicode MS",
    ]
    available_fonts = []
    for font_name in candidate_fonts:
        try:
            font_manager.findfont(font_name, fallback_to_default=False)
            available_fonts.append(font_name)
        except Exception:
            pass
    font_families = []
    for font_name in available_fonts + candidate_fonts + ["DejaVu Sans"]:
        if font_name not in font_families:
            font_families.append(font_name)
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = font_families
    plt.rcParams["axes.unicode_minus"] = False


_configure_generated_chart_fonts()
""".strip()


CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def _contains_cjk(text: str) -> bool:
    return CJK_PATTERN.search(text) is not None


def _enforce_matplotlib_chinese_font_setup(script: str) -> str:
    if not _contains_cjk(script):
        return script
    if "_configure_generated_chart_fonts" in script and "font.sans-serif" in script:
        return script

    script = _ensure_matplotlib_chinese_font_imports(script)
    lines = script.splitlines()
    insert_at = _font_setup_insert_index(lines)
    block = MATPLOTLIB_CHINESE_FONT_SETUP.splitlines()
    if insert_at > 0 and lines[insert_at - 1].strip():
        block.insert(0, "")
    if insert_at < len(lines) and lines[insert_at].strip():
        block.append("")
    lines[insert_at:insert_at] = block
    return "\n".join(lines).strip()


def _ensure_matplotlib_chinese_font_imports(script: str) -> str:
    lines = script.splitlines()
    import_lines = []
    has_matplotlib_import = re.search(r"^\s*import\s+matplotlib\b", script, flags=re.MULTILINE) is not None
    has_pyplot_import = re.search(r"^\s*import\s+matplotlib\.pyplot\s+as\s+plt\b", script, flags=re.MULTILINE) is not None
    has_font_manager_import = re.search(
        r"^\s*(from\s+matplotlib\s+import\s+.*\bfont_manager\b|import\s+matplotlib\.font_manager\b)",
        script,
        flags=re.MULTILINE,
    ) is not None

    if not has_matplotlib_import:
        import_lines.append("import matplotlib")
    if "matplotlib.use(" not in script:
        import_lines.append('matplotlib.use("Agg")')
    if not has_font_manager_import:
        import_lines.append("from matplotlib import font_manager")
    if not has_pyplot_import:
        import_lines.append("import matplotlib.pyplot as plt")

    if not import_lines:
        return script

    insert_at = _runtime_constant_insert_index(lines)
    if insert_at > 0 and lines[insert_at - 1].strip():
        import_lines.insert(0, "")
    if insert_at < len(lines) and lines[insert_at].strip():
        import_lines.append("")
    lines[insert_at:insert_at] = import_lines
    return "\n".join(lines)


def _font_setup_insert_index(lines: list[str]) -> int:
    for index, line in enumerate(lines):
        if re.match(r"^(def|class)\s+", line):
            return index
    return len(lines)

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


def _enforce_runtime_constants(script: str, input_file: str, output_dir: str) -> str:
    script = _ensure_path_import(script.strip())
    lines = script.splitlines()
    constants = _runtime_constant_lines(input_file=input_file, output_dir=output_dir)
    updated_lines: list[str] = []
    seen: set[str] = set()

    for line in lines:
        match = re.match(r"^\s*(INPUT_FILE|OUTPUT_DIR|CHARTS_DIR)\s*=", line)
        if not match:
            updated_lines.append(line)
            continue

        name = match.group(1)
        if name in seen:
            continue
        updated_lines.append(constants[name])
        seen.add(name)

    missing = [name for name in ("INPUT_FILE", "OUTPUT_DIR", "CHARTS_DIR") if name not in seen]
    if missing:
        insert_at = _runtime_constant_insert_index(updated_lines)
        block = [constants[name] for name in missing]
        if insert_at > 0 and updated_lines[insert_at - 1].strip():
            block.insert(0, "")
        if insert_at < len(updated_lines) and updated_lines[insert_at].strip():
            block.append("")
        updated_lines[insert_at:insert_at] = block

    return "\n".join(updated_lines).strip()


def _ensure_path_import(script: str) -> str:
    if re.search(r"^\s*from\s+pathlib\s+import\s+.*\bPath\b", script, flags=re.MULTILINE):
        return script

    lines = script.splitlines()
    insert_at = 0
    if lines and lines[0].startswith("#!"):
        insert_at = 1
    if len(lines) > insert_at and re.search(r"coding[:=]\s*[-\w.]+", lines[insert_at]):
        insert_at += 1
    while len(lines) > insert_at and lines[insert_at].startswith("from __future__ import "):
        insert_at += 1

    lines.insert(insert_at, "from pathlib import Path")
    return "\n".join(lines)


def _runtime_constant_lines(input_file: str, output_dir: str) -> dict[str, str]:
    return {
        "INPUT_FILE": f'INPUT_FILE = Path(r"{_escape_raw_double_quoted_path(input_file)}")',
        "OUTPUT_DIR": f'OUTPUT_DIR = Path(r"{_escape_raw_double_quoted_path(output_dir)}")',
        "CHARTS_DIR": 'CHARTS_DIR = OUTPUT_DIR / "charts"',
    }


def _escape_raw_double_quoted_path(value: str) -> str:
    return value.replace('"', '\\"')


def _runtime_constant_insert_index(lines: list[str]) -> int:
    last_import_end: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            last_import_end = index + 1
            continue
        if last_import_end is not None and stripped == "":
            last_import_end = index + 1
            continue
        if last_import_end is not None:
            break
    return last_import_end or 0


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

    missing_paths = []
    if input_file not in script:
        missing_paths.append(f'INPUT_FILE = Path(r"{input_file}")')
    if output_dir not in script:
        missing_paths.append(f'OUTPUT_DIR = Path(r"{output_dir}")')
    if missing_paths:
        raise ValueError(
            "Generated script is missing the required runtime path constants: "
            + "; ".join(missing_paths)
        )

    if _contains_cjk(script):
        missing_font_fragments = [
            fragment
            for fragment in ("font.sans-serif", "axes.unicode_minus")
            if fragment not in script
        ]
        if missing_font_fragments:
            raise ValueError(
                "Generated script must configure Chinese matplotlib fonts: "
                + ", ".join(missing_font_fragments)
            )


def _validate_import_root(module_name: str) -> None:
    root = module_name.split(".", 1)[0]
    if root not in ALLOWED_IMPORT_ROOTS:
        raise ValueError(f"Generated script imports disallowed module: {module_name}")


def _to_rule_based_plan(
    analysis_plan: dict[str, Any],
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    task_type = str(analysis_plan.get("task_type") or "")
    if task_type and (task_type != "grade_analysis" or analysis_plan.get("required_columns")):
        return analysis_plan

    columns = [str(column) for column in dataset_profile.get("columns", [])]
    dimension_column = _first_existing(analysis_plan.get("grouping_dimensions"), columns)
    metric_column = _first_existing(analysis_plan.get("metrics"), columns)

    if metric_column is None:
        numeric_columns = list(dataset_profile.get("numeric_summary", {}).keys())
        metric_column = _first_existing(numeric_columns, columns)

    if dimension_column is None:
        dimension_column = _find_column(columns, ("班级", "class"))

    analysis_goal = str(analysis_plan.get("analysis_goal") or "")
    if not _looks_like_grade_plan(analysis_goal, dimension_column, metric_column):
        normalized_plan = dict(analysis_plan)
        normalized_plan["task_type"] = "general_data_analysis"
        if metric_column and not normalized_plan.get("metrics"):
            normalized_plan["metrics"] = [metric_column]
        if dimension_column and not normalized_plan.get("grouping_dimensions"):
            normalized_plan["grouping_dimensions"] = [dimension_column]
        return normalized_plan

    return {
        "task_type": "grade_analysis",
        "task_name": analysis_goal or "Grade analysis",
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
                "column_name": metric_column,
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


def _looks_like_grade_plan(
    analysis_goal: str,
    dimension_column: str | None,
    metric_column: str | None,
) -> bool:
    goal = analysis_goal.lower()
    if any(keyword in goal for keyword in ("成绩", "分数", "学生", "班级", "score", "grade", "student", "class")):
        return True
    dimension = str(dimension_column or "").lower()
    metric = str(metric_column or "").lower()
    return (
        any(keyword in dimension for keyword in ("班级", "class"))
        and any(keyword in metric for keyword in ("成绩", "分数", "score", "grade"))
    )


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


