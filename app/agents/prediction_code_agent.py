import ast
import json
import re
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


LLM_ONLY_ATTEMPTS = 3

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
    "sklearn",
    "warnings",
}

SYSTEM_PROMPT = """You are the Prediction Code Agent for a what-if simulation workflow.

Return only executable Python code. Do not output markdown, code fences, or explanation.

Hard requirements:
- Use only these libraries: pandas, numpy, matplotlib, seaborn, duckdb, json, math, os, pathlib, sklearn, warnings.
- The code must read INPUT_FILE.
- The code must write all outputs under OUTPUT_DIR.
- The code must create OUTPUT_DIR / "prediction_result.json".
- The code must create OUTPUT_DIR / "report_data.json".
- For supported simulations, create meaningful PNG charts under OUTPUT_DIR / "charts". For unsupported scenarios caused by a missing intervention field, do not create a text-only PNG; leave charts empty and write no_chart_reason in the JSON outputs.
- The code must support CSV, XLSX, and XLS input files.
- If sklearn is unavailable or fields are insufficient, use a rule-based simulation fallback.
- Predictions are estimates, not causal proof.
- Configure matplotlib before creating charts so Chinese labels render correctly:
  plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "Arial Unicode MS", "DejaVu Sans"]
  plt.rcParams["axes.unicode_minus"] = False
- All visible chart text must be Chinese, including chart titles, axis labels, legends, annotations, and fallback labels.
- Translate common chart labels: Baseline=基准值, Predicted=预测值, Entity=对象, Value=指标值, Change=变化值, Predicted absolute change=预测绝对变化.
- Do not import any library that is not explicitly listed above.
- The generated code must contain literal assignments for the exact INPUT_FILE and OUTPUT_DIR constants provided in the user prompt. Do not compute, omit, rename, or replace these paths.
- Never read or write outside INPUT_FILE and OUTPUT_DIR.
- For absolute interventions, add the scenario amount to the intervention column; do not convert an absolute amount into a percentage multiplier.
- If the user states area in square meters/平方米/平米/㎡ and the dataset area column is in square feet such as GrLivArea, LotArea, TotalBsmtSF, 1stFlrSF, 2ndFlrSF, GarageArea, or another *SF column, convert 1 square meter to 10.76391041671 square feet before simulation.
- If the user asks about 房龄/房屋年龄/楼龄 and the dataset uses YearBuilt rather than a direct HouseAge column, simulate 房龄增加 by decreasing YearBuilt by the same number of years.
- Every item in top_impacted_entities must include entity, baseline_value, predicted_value, absolute_change, percent_change, direction, and explanation.
- If the chosen model yields identical marginal changes for all rows, do not draw a misleading Top 20 bar chart with duplicated values. Draw a single scenario summary chart and explain that the linear marginal effect is constant.
"""


def build_user_prompt(
    input_file: str,
    output_dir: str,
    dataset_profile: dict[str, Any],
    hypothesis_plan: dict[str, Any],
    prediction_plan: dict[str, Any],
    attempt: int,
    previous_execution_result: dict[str, Any] | None,
    previous_validation_result: dict[str, Any] | None,
) -> str:
    context = {
        "attempt": attempt,
        "previous_execution_result": previous_execution_result,
        "previous_validation_result": previous_validation_result,
        "previous_stderr": (previous_execution_result or {}).get("stderr"),
        "previous_repair_suggestions": (previous_validation_result or {}).get("repair_suggestions"),
    }
    return """Generate a complete Python what-if prediction script.

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

Hypothesis plan JSON:
{hypothesis_plan}

Prediction plan JSON:
{prediction_plan}

Repair context JSON:
{context}

Scenario calculation requirements:
- Use prediction_plan.target_metric as the target and prediction_plan.intervention.column as the intervention column when they exist.
- For absolute changes, add the scenario amount to the intervention column. For relative changes, multiply by 1 + change_value.
- Preserve the original unit from hypothesis_plan.intervention.unit. If the user asks for square meters/平方米/平米/㎡ and the selected dataset area field is GrLivArea or another square-foot field, convert to square feet using 10.76391041671.
- Put the actual scenario amount used in dataset units into model_info.scenario_change_in_data_units and include model_info.unit_conversion.
- For house price data, prefer SalePrice as target. For area scenarios prefer GrLivArea as intervention; for 房龄 scenarios prefer HouseAge when present, otherwise YearBuilt with inverse-year adjustment. Use Id as the house identifier when it exists.
- The result must answer the average total-price change and must not present unit-converted values in the wrong data unit.

Chinese chart requirements:
- Configure matplotlib Chinese font before any figure is created.
- Use Chinese visible text in every chart title, axis label, legend, and annotation.
- Do not use English chart titles such as "Top predicted changes" or "Baseline vs predicted".

Reliability requirements:
- If model training fails or fields are insufficient, fall back inside the script to a simple rule-based simulation.
- Treat validation feedback as mandatory. For supported scenarios, the repaired script must write prediction_result.json, report_data.json, and at least one meaningful PNG chart before exiting. For unsupported missing-field scenarios, do not create text-only PNG charts; write charts as an empty list and explain no_chart_reason.
- Prefer robust pandas operations, numeric coercion, Top 20 chart categories only when values are meaningfully different, and cautious limitations instead of crashing.
- Use only the allowed imports from the system prompt.

Return only Python code. The script must define main() and call it under if __name__ == "__main__".
""".format(
        input_file=input_file,
        output_dir=output_dir,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        hypothesis_plan=json.dumps(hypothesis_plan, ensure_ascii=False, indent=2),
        prediction_plan=json.dumps(prediction_plan, ensure_ascii=False, indent=2),
        context=json.dumps(context, ensure_ascii=False, indent=2),
    )


class PredictionCodeAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()
        self.rule_based_agent = RuleBasedPredictionCodeAgent()

    def generate_script(
        self,
        input_file: str,
        output_dir: str,
        dataset_profile: dict[str, Any],
        hypothesis_plan: dict[str, Any],
        prediction_plan: dict[str, Any],
        attempt: int,
        previous_execution_result: dict[str, Any] | None = None,
        previous_validation_result: dict[str, Any] | None = None,
    ) -> str:
        if _is_unsupported_prediction_plan(prediction_plan):
            if _unsupported_plan_is_transformable(dataset_profile, hypothesis_plan, prediction_plan):
                return self.rule_based_agent.generate_script(
                    input_file=input_file,
                    output_dir=output_dir,
                    dataset_profile=dataset_profile,
                    hypothesis_plan=hypothesis_plan,
                    prediction_plan=prediction_plan,
                )
            return self.rule_based_agent.generate_unsupported_script(
                input_file=input_file,
                output_dir=output_dir,
                dataset_profile=dataset_profile,
                hypothesis_plan=hypothesis_plan,
                prediction_plan=prediction_plan,
            )

        if _requires_deterministic_unit_aware_script(dataset_profile, hypothesis_plan, prediction_plan):
            return self.rule_based_agent.generate_script(
                input_file=input_file,
                output_dir=output_dir,
                dataset_profile=dataset_profile,
                hypothesis_plan=hypothesis_plan,
                prediction_plan=prediction_plan,
            )

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
                            hypothesis_plan=hypothesis_plan,
                            prediction_plan=prediction_plan,
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
            _validate_generated_script(script, input_file=input_file, output_dir=output_dir)
            return script
        except Exception as exc:
            if attempt <= LLM_ONLY_ATTEMPTS:
                raise PredictionCodeGenerationError(
                    f"LLM prediction code generation failed on attempt {attempt}: {exc}"
                ) from exc
            return self.rule_based_agent.generate_script(
                input_file=input_file,
                output_dir=output_dir,
                dataset_profile=dataset_profile,
                hypothesis_plan=hypothesis_plan,
                prediction_plan=prediction_plan,
            )


class PredictionCodeGenerationError(RuntimeError):
    pass


class RuleBasedPredictionCodeAgent:
    def generate_script(
        self,
        input_file: str,
        output_dir: str,
        dataset_profile: dict[str, Any],
        hypothesis_plan: dict[str, Any],
        prediction_plan: dict[str, Any],
    ) -> str:
        script = RULE_BASED_PREDICTION_SCRIPT_TEMPLATE
        script = script.replace("__INPUT_FILE__", _escape_raw_double_quoted_path(input_file))
        script = script.replace("__OUTPUT_DIR__", _escape_raw_double_quoted_path(output_dir))
        script = script.replace("__DATASET_PROFILE_JSON__", repr(json.dumps(dataset_profile, ensure_ascii=False)))
        script = script.replace("__HYPOTHESIS_PLAN_JSON__", repr(json.dumps(hypothesis_plan, ensure_ascii=False)))
        script = script.replace("__PREDICTION_PLAN_JSON__", repr(json.dumps(prediction_plan, ensure_ascii=False)))
        return script.strip()

    def generate_unsupported_script(
        self,
        input_file: str,
        output_dir: str,
        dataset_profile: dict[str, Any],
        hypothesis_plan: dict[str, Any],
        prediction_plan: dict[str, Any],
    ) -> str:
        script = UNSUPPORTED_PREDICTION_SCRIPT_TEMPLATE
        script = script.replace("__INPUT_FILE__", _escape_raw_double_quoted_path(input_file))
        script = script.replace("__OUTPUT_DIR__", _escape_raw_double_quoted_path(output_dir))
        script = script.replace("__DATASET_PROFILE_JSON__", repr(json.dumps(dataset_profile, ensure_ascii=False)))
        script = script.replace("__HYPOTHESIS_PLAN_JSON__", repr(json.dumps(hypothesis_plan, ensure_ascii=False)))
        script = script.replace("__PREDICTION_PLAN_JSON__", repr(json.dumps(prediction_plan, ensure_ascii=False)))
        return script.strip()


UNSUPPORTED_PREDICTION_SCRIPT_TEMPLATE = r'''
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt

INPUT_FILE = Path(r"__INPUT_FILE__")
OUTPUT_DIR = Path(r"__OUTPUT_DIR__")
CHARTS_DIR = OUTPUT_DIR / "charts"
DATASET_PROFILE = json.loads(__DATASET_PROFILE_JSON__)
HYPOTHESIS_PLAN = json.loads(__HYPOTHESIS_PLAN_JSON__)
PREDICTION_PLAN = json.loads(__PREDICTION_PLAN_JSON__)


def load_data(path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError("Unsupported input file type")


def clean_numeric(series):
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def choose_target(df):
    planned = str(PREDICTION_PLAN.get("target_metric") or "")
    if planned in df.columns:
        return planned
    matched = ""
    target_metric = HYPOTHESIS_PLAN.get("target_metric") if isinstance(HYPOTHESIS_PLAN.get("target_metric"), dict) else {}
    if isinstance(target_metric, dict):
        matched = str(target_metric.get("matched_column") or "")
    if matched in df.columns:
        return matched
    for name in ("SalePrice", "房价", "总价", "售价", "价格", "Price"):
        if name in df.columns and clean_numeric(df[name]).notna().any():
            return name
    numeric_columns = [column for column in df.columns if clean_numeric(df[column]).notna().any()]
    return numeric_columns[-1] if numeric_columns else ""


def unique_list(values):
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def baseline_summary(df, target):
    if not target or target not in df.columns:
        return {"count": int(len(df)), "mean": None, "median": None}
    series = clean_numeric(df[target]).dropna()
    if series.empty:
        return {"count": int(len(df)), "mean": None, "median": None}
    return {
        "count": int(series.shape[0]),
        "mean": round(float(series.mean()), 6),
        "median": round(float(series.median()), 6),
        "min": round(float(series.min()), 6),
        "max": round(float(series.max()), 6),
    }


def configure_matplotlib():
    warnings.filterwarnings("ignore", category=UserWarning)
    candidate_fonts = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
    ]
    available_fonts = []
    for font_name in candidate_fonts:
        try:
            font_manager.findfont(font_name, fallback_to_default=False)
            available_fonts.append(font_name)
        except Exception:
            pass
    plt.rcParams["font.sans-serif"] = available_fonts + candidate_fonts + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def create_unsupported_chart(df, target, unsupported_reason):
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()
    available_preview = "、".join([str(column) for column in df.columns[:8]])
    if len(df.columns) > 8:
        available_preview += " 等"
    target_text = target or "未识别"
    lines = [
        "无法计算该情景预测",
        f"目标指标：{target_text}",
        f"原因：{unsupported_reason}",
        "系统不会用不相关字段替代情景变量。",
        f"当前数据字段示例：{available_preview}",
    ]
    fig, ax = plt.subplots(figsize=(11, 5.6))
    ax.axis("off")
    ax.set_title("情景变量字段缺失说明", fontsize=18, pad=18)
    y = 0.82
    for index, line in enumerate(lines):
        size = 14 if index == 0 else 11
        weight = "bold" if index == 0 else "normal"
        ax.text(0.04, y, line, transform=ax.transAxes, fontsize=size, fontweight=weight, va="top", wrap=True)
        y -= 0.15 if index == 0 else 0.13
    ax.text(0.04, 0.08, "建议：补充与情景变量直接对应的字段后重新运行预测。", transform=ax.transAxes, fontsize=11, va="bottom")
    path = CHARTS_DIR / "unsupported_field_notice.png"
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return str(path)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()

    df = load_data(INPUT_FILE)
    df.columns = [str(column) for column in df.columns]
    target = choose_target(df)
    intervention = PREDICTION_PLAN.get("intervention") if isinstance(PREDICTION_PLAN.get("intervention"), dict) else {}
    unsupported_reason = str(PREDICTION_PLAN.get("unsupported_reason") or "").strip()
    if not unsupported_reason:
        raw_variable = str(intervention.get("variable") or intervention.get("column") or HYPOTHESIS_PLAN.get("scenario_summary") or PREDICTION_PLAN.get("prediction_goal") or "")
        unsupported_reason = f"当前数据集中没有与情景变量“{raw_variable}”对应的字段，无法计算该情景下的预测变化。"

    limitations = unique_list([
        unsupported_reason,
        "系统未使用其他不相关字段替代该情景变量，因此不会输出误导性的预测数值。",
        *list(PREDICTION_PLAN.get("limitations") or []),
        *list(HYPOTHESIS_PLAN.get("limitations") or []),
    ])
    no_chart_reason = "本次问题对应的情景变量字段缺失，无法生成基于预测数值的图表"
    chart_paths = []
    result = {
        "task_type": "what_if_prediction",
        "status": "unsupported",
        "scenario_summary": HYPOTHESIS_PLAN.get("scenario_summary") or PREDICTION_PLAN.get("prediction_goal", ""),
        "target_metric": target,
        "intervention": {
            **intervention,
            "column": "",
            "unsupported": True,
        },
        "entity_dimension": str(PREDICTION_PLAN.get("entity_dimension") or ""),
        "top_impacted_entities": [],
        "baseline_summary": baseline_summary(df, target),
        "predicted_summary": {
            "count": int(len(df)),
            "mean": None,
            "median": None,
            "mean_absolute_change": None,
            "median_absolute_change": None,
            "min_absolute_change": None,
            "max_absolute_change": None,
        },
        "model_info": {
            "method": "unsupported_missing_required_column",
            "target_column": target,
            "intervention_column": "",
            "reason": unsupported_reason,
            "available_columns": [str(column) for column in df.columns],
        },
        "limitations": limitations,
        "charts": chart_paths,
        "unsupported_reason": unsupported_reason,
        "no_chart_reason": no_chart_reason,
        "chart_notice": no_chart_reason,
    }
    report_data = {
        "summary": unsupported_reason,
        "key_findings": [
            {
                "finding": unsupported_reason,
                "evidence": "prediction_result.unsupported_reason",
            },
            {
                "finding": "已停止情景模拟，避免把不相关字段的模型结果解释为用户指定变量的影响。",
                "evidence": "prediction_result.model_info.method",
            },
        ],
        "top_impacted_entities": [],
        "model_info": result["model_info"],
        "recommendations": [
            "补充与情景变量对应的字段后重新运行情景预测。",
            "补充字段后应确认变量单位，并与目标指标在同一对象粒度下对应。",
        ],
        "limitations": limitations,
        "charts": chart_paths,
        "no_chart_reason": no_chart_reason,
        "chart_notice": no_chart_reason,
    }
    (OUTPUT_DIR / "prediction_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_DIR / "report_data.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
'''


RULE_BASED_PREDICTION_SCRIPT_TEMPLATE = r'''
import json
import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt

try:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LinearRegression, Ridge, RidgeCV
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
except Exception:
    ColumnTransformer = None
    SimpleImputer = None
    LinearRegression = None
    Ridge = None
    RidgeCV = None
    mean_absolute_error = None
    r2_score = None
    train_test_split = None
    Pipeline = None
    OneHotEncoder = None

INPUT_FILE = Path(r"__INPUT_FILE__")
OUTPUT_DIR = Path(r"__OUTPUT_DIR__")
CHARTS_DIR = OUTPUT_DIR / "charts"
DATASET_PROFILE = json.loads(__DATASET_PROFILE_JSON__)
HYPOTHESIS_PLAN = json.loads(__HYPOTHESIS_PLAN_JSON__)
PREDICTION_PLAN = json.loads(__PREDICTION_PLAN_JSON__)
SQUARE_METER_TO_SQUARE_FOOT = 10.76391041671


def load_data(path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    raise ValueError("Unsupported input file type")


def configure_matplotlib():
    candidate_fonts = [
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
    ]
    available_fonts = []
    for font_name in candidate_fonts:
        try:
            font_manager.findfont(font_name, fallback_to_default=False)
            available_fonts.append(font_name)
        except Exception:
            pass
    plt.rcParams["font.sans-serif"] = available_fonts + candidate_fonts + ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False


def safe_number(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def normalize_text(value):
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return " ".join(normalize_text(item) for item in value)
    return str(value or "")


def all_plan_text():
    return " ".join([
        normalize_text(HYPOTHESIS_PLAN),
        normalize_text(PREDICTION_PLAN),
        normalize_text(PREDICTION_PLAN.get("prediction_goal")),
        normalize_text(HYPOTHESIS_PLAN.get("scenario_summary")),
    ])


def get_nested(data, *keys, default=""):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def clean_numeric(series):
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def numeric_non_null_count(df, column):
    if column not in df.columns:
        return 0
    return int(clean_numeric(df[column]).notna().sum())


def is_identifier_column(column):
    text = str(column).strip().lower()
    return text in {"id", "编号", "序号", "房屋编号", "house_id", "row_id"} or text.endswith("_id")


def find_existing_column(df, value):
    text = str(value or "")
    return text if text in df.columns else ""


def choose_by_alias(df, aliases, numeric_required=False):
    lowered = [(column, str(column).lower()) for column in df.columns]
    for alias in aliases:
        alias_lower = alias.lower()
        for column, column_lower in lowered:
            if alias_lower == column_lower or alias_lower in column_lower:
                if not numeric_required or numeric_non_null_count(df, column) > 0:
                    return column
    return ""


def choose_target(df):
    planned = find_existing_column(df, PREDICTION_PLAN.get("target_metric"))
    if planned:
        return planned
    matched = find_existing_column(df, get_nested(HYPOTHESIS_PLAN, "target_metric", "matched_column"))
    if matched:
        return matched
    text = all_plan_text().lower()
    if any(keyword in text for keyword in ["房价", "总价", "售价", "saleprice", "price", "价格"]):
        target = choose_by_alias(df, ["SalePrice", "房价", "总价", "售价", "价格", "Price"], numeric_required=True)
        if target:
            return target
    target = choose_by_alias(df, ["销量", "销售量", "销售额", "成绩", "分数", "SalePrice", "Price"], numeric_required=True)
    if target:
        return target
    numeric_columns = [column for column in df.columns if numeric_non_null_count(df, column) > 0 and not is_identifier_column(column)]
    return numeric_columns[-1] if numeric_columns else ""


def choose_intervention(df, target):
    planned = find_existing_column(df, get_nested(PREDICTION_PLAN, "intervention", "column"))
    matched = find_existing_column(df, get_nested(HYPOTHESIS_PLAN, "intervention", "matched_column"))
    text = all_plan_text().lower()
    scenario_text = " ".join([
        normalize_text(PREDICTION_PLAN.get("prediction_goal")),
        normalize_text(HYPOTHESIS_PLAN.get("scenario_summary")),
        normalize_text(get_nested(PREDICTION_PLAN, "intervention", "variable")),
        normalize_text(get_nested(HYPOTHESIS_PLAN, "intervention", "variable")),
        normalize_text(get_nested(HYPOTHESIS_PLAN, "intervention", "raw_text")),
    ]).lower()
    if planned and planned != target and numeric_non_null_count(df, planned) > 0:
        return planned
    if matched and matched != target and numeric_non_null_count(df, matched) > 0:
        return matched
    quality_requested = any(keyword in scenario_text for keyword in ["装修", "精装修", "普通装修", "装修等级", "质量", "overallqual", "quality", "finish"])
    if quality_requested:
        quality_column = choose_by_alias(
            df,
            ["OverallQual", "OverallCond", "装修等级", "装修", "quality"],
            numeric_required=True,
        )
        if quality_column and quality_column != target:
            return quality_column
    if mentions_house_age_change():
        column = choose_by_alias(
            df,
            ["HouseAge", "house_age", "BuildingAge", "building_age", "房龄", "房屋年龄", "建筑年龄", "楼龄"],
            numeric_required=True,
        )
        if column and column != target:
            return column
        column = choose_by_alias(
            df,
            ["YearBuilt", "year_built", "BuiltYear", "Built_Year", "建成年份", "建造年份", "建筑年份"],
            numeric_required=True,
        )
        if column and column != target:
            return column
    if any(keyword in text for keyword in ["面积", "平方米", "平米", "grlivarea", "area", "㎡"]):
        column = choose_by_alias(
            df,
            ["GrLivArea", "LivingArea", "TotalBsmtSF", "1stFlrSF", "2ndFlrSF", "LotArea", "GarageArea", "面积", "Area", "SF"],
            numeric_required=True,
        )
        if column and column != target:
            return column
    if any(keyword in text for keyword in ["装修", "精装修", "普通装修", "装修等级", "质量", "overallqual", "quality", "finish"]):
        column = choose_by_alias(
            df,
            ["OverallQual", "KitchenQual", "ExterQual", "OverallCond", "装修等级", "装修", "quality"],
            numeric_required=True,
        )
        if column and column != target:
            return column
    if any(keyword in text for keyword in ["两居", "二居", "三居", "卧室", "居室", "户型", "bedroom"]):
        column = choose_by_alias(
            df,
            ["BedroomAbvGr", "Bedrooms", "Bedroom", "卧室数", "居室数", "居室", "户型", "TotRmsAbvGrd"],
            numeric_required=True,
        )
        if column and column != target:
            return column
    column = choose_by_alias(df, ["营销预算", "预算", "投放", "价格", "GrLivArea", "面积"], numeric_required=True)
    if column and column != target:
        return column
    for column in df.columns:
        if column != target and numeric_non_null_count(df, column) > 0 and not is_identifier_column(column):
            return column
    return ""


def choose_entity(df):
    planned = find_existing_column(df, PREDICTION_PLAN.get("entity_dimension"))
    if planned:
        return planned
    matched = find_existing_column(df, get_nested(HYPOTHESIS_PLAN, "entity_dimension", "matched_column"))
    if matched:
        return matched
    text = all_plan_text().lower()
    if any(keyword in text for keyword in ["同一套房", "某套房", "房屋", "房子", "住宅", "house"]):
        id_column = choose_by_alias(df, ["Id", "房屋编号", "编号", "house_id"])
        if id_column:
            return id_column
    if any(keyword in text for keyword in ["区域", "小区", "周边", "地段", "neighborhood"]):
        region_column = choose_by_alias(df, ["Neighborhood", "小区", "区域", "地区", "MSZoning", "Location"])
        if region_column:
            return region_column
    for column in df.columns:
        if is_identifier_column(column):
            return column
    for column in df.columns:
        series = df[column]
        if series.dtype == object or str(series.dtype).startswith("category"):
            unique_count = int(series.nunique(dropna=True))
            if 1 < unique_count <= max(50, len(df) // 2):
                return column
    return ""


def extract_requested_unit():
    intervention = HYPOTHESIS_PLAN.get("intervention") if isinstance(HYPOTHESIS_PLAN.get("intervention"), dict) else {}
    unit = str(intervention.get("unit") or get_nested(PREDICTION_PLAN, "intervention", "unit") or "")
    text = " ".join([unit, str(intervention.get("raw_text") or ""), all_plan_text()]).lower()
    if "%" in text:
        return "%"
    if any(token in text for token in ["平方米", "平米", "㎡", "m2", "m^2", "square meter"]):
        return "平方米"
    if any(token in text for token in ["平方英尺", "sqft", "sq ft", "square foot", "square feet"]):
        return "平方英尺"
    if any(token in text for token in ["装修", "精装修", "装修等级", "质量等级", "等级", "档", "quality", "finish"]):
        return "等级"
    if any(token in text for token in ["两居", "二居", "三居", "卧室", "居室", "户型", "bedroom", "bedrooms"]):
        return "间"
    if "年" in text or any(token in text for token in ["year", "years"]):
        return "年"
    normalized_unit = unit.lower()
    if unit in {"米", "公里", "千米"} or normalized_unit in {"m", "km"}:
        return "公里" if unit in {"公里", "千米"} or normalized_unit == "km" else "米"
    if any(token in text for token in ["公里", "千米", "km"]):
        return "公里"
    if any(token in text for token in ["米", "meter", "metre"]):
        return "米"
    return unit


def mentions_house_age_change():
    text = all_plan_text().lower()
    original = all_plan_text()
    return any(token in original for token in ["房龄", "房屋年龄", "建筑年龄", "楼龄"]) or any(
        token in text for token in ["house age", "building age"]
    )


def year_built_column_represents_age_inverse(column):
    normalized = str(column or "").strip().lower().replace("_", "")
    return normalized in {"yearbuilt", "builtyear"} or str(column or "") in {"建成年份", "建造年份", "建筑年份"}


def area_column_uses_square_feet(column):
    text = str(column or "")
    lowered = text.lower()
    known_square_foot_columns = {
        "grlivarea",
        "lotarea",
        "totalbsmtsf",
        "1stflrsf",
        "2ndflrsf",
        "lowqualfinsf",
        "bsmtfinsf1",
        "bsmtfinsf2",
        "bsmtunfsf",
        "garagearea",
        "wooddecksf",
        "openporchsf",
        "enclosedporch",
        "3ssnporch",
        "screenporch",
        "poolarea",
        "masvnrarea",
    }
    if lowered in known_square_foot_columns or lowered.endswith("sf") or "sqft" in lowered:
        return True
    if any(token in text for token in ["平方米", "平米", "㎡"]):
        return False
    return lowered in {"area", "livingarea", "grossarea"}


def distance_column_uses_kilometers(column):
    text = str(column or "")
    lowered = text.lower()
    return any(token in lowered for token in ["km", "kilometer", "kilometre"]) or any(token in text for token in ["公里", "千米"])


def distance_column_uses_meters(column):
    text = str(column or "")
    lowered = text.lower()
    if distance_column_uses_kilometers(column):
        return False
    return any(token in lowered for token in ["meter", "metre", "_m", "distance_m"]) or any(token in text for token in ["米", "距离"])


def scenario_change_info(intervention_col):
    intervention = PREDICTION_PLAN.get("intervention") if isinstance(PREDICTION_PLAN.get("intervention"), dict) else {}
    hypothesis_intervention = HYPOTHESIS_PLAN.get("intervention") if isinstance(HYPOTHESIS_PLAN.get("intervention"), dict) else {}
    change_type = str(intervention.get("change_type") or hypothesis_intervention.get("change_type") or "unknown")
    change_value = safe_number(intervention.get("change_value"), safe_number(hypothesis_intervention.get("change_value"), 0.0))
    requested_unit = extract_requested_unit()
    data_unit_change = change_value
    unit_conversion = "未做单位换算"

    if change_type in {"relative", "weight_shift"} or requested_unit == "%":
        return {
            "change_type": "relative",
            "change_value": change_value,
            "requested_unit": requested_unit or "%",
            "data_unit_change": change_value,
            "unit_conversion": "相对变化按 1 + change_value 乘数处理",
        }

    if change_type == "unknown" and abs(change_value) <= 1 and requested_unit not in {"平方米", "平方英尺", "年", "米", "公里", "等级", "间"}:
        return {
            "change_type": "relative",
            "change_value": change_value,
            "requested_unit": requested_unit or "%",
            "data_unit_change": change_value,
            "unit_conversion": "未识别明确单位，按相对变化处理",
        }

    if requested_unit == "年":
        if mentions_house_age_change() and year_built_column_represents_age_inverse(intervention_col):
            data_unit_change = -change_value
            unit_conversion = f"用户输入为房龄变化，数据字段 {intervention_col} 表示建造年份；房龄变化按建造年份反向调整。"
        elif mentions_house_age_change():
            unit_conversion = "用户输入为房龄变化，数据字段按房龄年数直接调整。"
        else:
            unit_conversion = "用户输入按年处理；若数据字段使用其他年份口径，请先统一字段含义。"
    elif requested_unit == "平方米" and area_column_uses_square_feet(intervention_col):
        data_unit_change = change_value * SQUARE_METER_TO_SQUARE_FOOT
        unit_conversion = "用户输入为平方米，数据面积字段按平方英尺口径换算，1 平方米 = 10.76391041671 平方英尺"
    elif requested_unit == "平方英尺":
        unit_conversion = "用户输入与数据面积字段同按平方英尺处理"
    elif requested_unit == "等级":
        if abs(change_value) <= 1e-12:
            data_unit_change = 1.0
        unit_conversion = "用户输入为装修或质量等级变化，按字段评分等级的绝对增减进行模拟。"
    elif requested_unit == "间":
        if abs(change_value) <= 1e-12:
            data_unit_change = 1.0
        unit_conversion = "用户输入为户型居室数量变化，按卧室数量字段的绝对增减进行模拟。"
    elif requested_unit == "米":
        if distance_column_uses_kilometers(intervention_col):
            data_unit_change = change_value / 1000.0
            unit_conversion = "用户输入为米，数据距离字段按公里口径换算，1 公里 = 1000 米"
        else:
            unit_conversion = "用户输入按米处理；若数据字段使用其他距离单位，请先统一单位"
    elif requested_unit == "公里":
        if distance_column_uses_meters(intervention_col):
            data_unit_change = change_value * 1000.0
            unit_conversion = "用户输入为公里，数据距离字段按米口径换算，1 公里 = 1000 米"
        else:
            unit_conversion = "用户输入按公里处理；若数据字段使用其他距离单位，请先统一单位"

    return {
        "change_type": "absolute",
        "change_value": change_value,
        "requested_unit": requested_unit,
        "data_unit_change": data_unit_change,
        "unit_conversion": unit_conversion,
    }


def build_model_columns(df, target, intervention_col):
    numeric_columns = []
    for column in df.columns:
        if column == target or is_identifier_column(column):
            continue
        if numeric_non_null_count(df, column) > 0:
            numeric_columns.append(column)
    if intervention_col and intervention_col in df.columns and intervention_col not in numeric_columns and intervention_col != target:
        numeric_columns.insert(0, intervention_col)

    categorical_columns = []
    for column in df.columns:
        if column == target or column in numeric_columns or is_identifier_column(column):
            continue
        series = df[column]
        unique_count = int(series.nunique(dropna=True))
        if (series.dtype == object or str(series.dtype).startswith("category")) and 1 < unique_count <= 80:
            categorical_columns.append(column)
    return numeric_columns, categorical_columns


def make_one_hot_encoder():
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def train_predictive_model(df, target, intervention_col):
    y = clean_numeric(df[target]) if target in df.columns else pd.Series([np.nan] * len(df), index=df.index)
    valid = y.notna()
    numeric_columns, categorical_columns = build_model_columns(df, target, intervention_col)
    feature_columns = numeric_columns + categorical_columns
    if not feature_columns or valid.sum() < 8 or RidgeCV is None or ColumnTransformer is None:
        return train_simple_fallback(df, target, intervention_col, y, numeric_columns)

    X = df.loc[:, feature_columns].copy()
    preprocess = ColumnTransformer(
        transformers=[
            ("num", SimpleImputer(strategy="median"), numeric_columns),
            ("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", make_one_hot_encoder())]), categorical_columns),
        ],
        remainder="drop",
    )
    model = Pipeline([
        ("preprocess", preprocess),
        ("model", RidgeCV(alphas=np.array([1.0, 10.0, 30.0, 100.0, 300.0, 1000.0]), cv=5)),
    ])
    metrics = {"mae": None, "r2": None, "validation_rows": 0}
    try:
        if valid.sum() >= 30 and train_test_split is not None:
            X_train, X_test, y_train, y_test = train_test_split(X.loc[valid], y.loc[valid], test_size=0.2, random_state=42)
            eval_model = Pipeline([
                ("preprocess", preprocess),
                ("model", Ridge(alpha=10.0 if Ridge is not None else 1.0)),
            ])
            eval_model.fit(X_train, y_train)
            y_pred = eval_model.predict(X_test)
            metrics = {
                "mae": round(float(mean_absolute_error(y_test, y_pred)), 6) if mean_absolute_error is not None else None,
                "r2": round(float(r2_score(y_test, y_pred)), 6) if r2_score is not None else None,
                "validation_rows": int(len(y_test)),
            }
        model.fit(X.loc[valid], y.loc[valid])
        baseline = pd.Series(model.predict(X), index=df.index)
        method = "ridge_regression_with_categorical_features"
        coefficient = None
        try:
            estimator = model.named_steps["model"]
            if intervention_col in numeric_columns and hasattr(estimator, "coef_"):
                coefficient = float(estimator.coef_[numeric_columns.index(intervention_col)])
        except Exception:
            coefficient = None
        return {
            "model": model,
            "feature_columns": feature_columns,
            "numeric_columns": numeric_columns,
            "categorical_columns": categorical_columns,
            "baseline": baseline,
            "method": method,
            "metrics": metrics,
            "coefficient_per_data_unit": coefficient,
        }
    except Exception:
        return train_simple_fallback(df, target, intervention_col, y, numeric_columns)


def train_simple_fallback(df, target, intervention_col, y, numeric_columns):
    baseline = y.fillna(y.median() if y.notna().any() else 0.0).astype(float)
    model = None
    method = "rule_based_simulation"
    coefficient = None
    feature_columns = list(numeric_columns or [])
    if intervention_col in df.columns and LinearRegression is not None and y.notna().sum() >= 8:
        try:
            x = clean_numeric(df[intervention_col]).fillna(clean_numeric(df[intervention_col]).median()).fillna(0.0).to_frame()
            model = LinearRegression().fit(x.loc[y.notna()], y.loc[y.notna()])
            baseline = pd.Series(model.predict(x), index=df.index)
            method = "linear_regression_single_feature"
            coefficient = float(model.coef_[0])
            feature_columns = [intervention_col]
        except Exception:
            pass
    return {
        "model": model,
        "feature_columns": feature_columns,
        "numeric_columns": feature_columns,
        "categorical_columns": [],
        "baseline": baseline,
        "method": method,
        "metrics": {"mae": None, "r2": None, "validation_rows": 0},
        "coefficient_per_data_unit": coefficient,
    }


def apply_scenario(df, intervention_col, change_info):
    scenario = df.copy()
    if not intervention_col or intervention_col not in scenario.columns:
        return scenario
    current = clean_numeric(scenario[intervention_col])
    if change_info["change_type"] == "relative":
        adjusted = current * (1.0 + safe_number(change_info["data_unit_change"], 0.0))
    else:
        adjusted = current + safe_number(change_info["data_unit_change"], 0.0)
    column_lower = str(intervention_col).lower()
    if column_lower == "overallqual" or intervention_col in {"OverallQual", "OverallCond"}:
        adjusted = adjusted.clip(lower=1, upper=10)
    if column_lower in {"bedroomabvgr", "bedrooms", "bedroom"} or any(token in str(intervention_col) for token in ["卧室", "居室"]):
        adjusted = adjusted.clip(lower=0)
    scenario[intervention_col] = adjusted
    return scenario


def predict_scenario(df, model_info, target, intervention_col, change_info):
    baseline = model_info["baseline"].astype(float)
    scenario_df = apply_scenario(df, intervention_col, change_info)
    feature_columns = model_info.get("feature_columns") or []
    model = model_info.get("model")
    predicted = None
    if model is not None and feature_columns:
        try:
            predicted = pd.Series(model.predict(scenario_df.loc[:, feature_columns]), index=df.index).astype(float)
        except Exception:
            predicted = None
    if predicted is None:
        coefficient = model_info.get("coefficient_per_data_unit")
        if coefficient is not None and change_info["change_type"] == "absolute":
            predicted = baseline + float(coefficient) * safe_number(change_info["data_unit_change"], 0.0)
        elif change_info["change_type"] == "relative":
            predicted = baseline * (1.0 + 0.3 * safe_number(change_info["data_unit_change"], 0.0))
        else:
            target_scale = float(baseline.abs().median()) if len(baseline) else 0.0
            predicted = baseline + target_scale * 0.01 * np.sign(safe_number(change_info["data_unit_change"], 0.0))
    return baseline, pd.Series(predicted, index=df.index).astype(float)


def changes_are_effectively_equal(changes):
    finite = pd.Series(changes).replace([np.inf, -np.inf], np.nan).dropna()
    if len(finite) <= 1:
        return True
    return float(finite.max() - finite.min()) <= max(1e-6, abs(float(finite.mean())) * 1e-9)


def entity_label(df, entity_col, index):
    if entity_col and entity_col in df.columns:
        value = df.at[index, entity_col]
        if str(entity_col).lower() == "id" or is_identifier_column(entity_col):
            return f"房屋{value}"
        return str(value)
    return f"记录{int(index) + 1}"


def build_impacted_entities(df, entity_col, baseline, predicted):
    changes = predicted - baseline
    if changes_are_effectively_equal(changes):
        base_mean = float(baseline.mean()) if len(baseline) else 0.0
        pred_mean = float(predicted.mean()) if len(predicted) else 0.0
        absolute_change = pred_mean - base_mean
        return pd.DataFrame([
            {
                "entity": "全体房屋平均" if any(str(c).lower() == "saleprice" for c in df.columns) else "整体平均",
                "_baseline": base_mean,
                "_predicted": pred_mean,
                "absolute_change": absolute_change,
                "percent_change": absolute_change / base_mean if abs(base_mean) > 1e-9 else 0.0,
                "direction": "增加" if absolute_change >= 0 else "降低",
                "explanation": "当前线性模型下，同一绝对情景变化对应相同的边际预测变化，因此以整体平均展示，避免重复展示多个完全相同的房屋条目。",
            }
        ])

    work = pd.DataFrame({"_baseline": baseline, "_predicted": predicted, "absolute_change": changes})
    if entity_col and entity_col in df.columns and not is_identifier_column(entity_col) and df[entity_col].nunique(dropna=True) <= 80:
        work["entity"] = df[entity_col].astype(str)
        grouped = work.groupby("entity", dropna=False)[["_baseline", "_predicted", "absolute_change"]].mean().reset_index()
    else:
        grouped = work.copy()
        grouped["entity"] = [entity_label(df, entity_col, index) for index in grouped.index]
    grouped["percent_change"] = np.where(grouped["_baseline"].abs() > 1e-9, grouped["absolute_change"] / grouped["_baseline"], 0.0)
    grouped["direction"] = np.where(grouped["absolute_change"] >= 0, "增加", "降低")
    grouped = grouped.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    grouped["_rank"] = grouped["absolute_change"].abs()
    return grouped.sort_values("_rank", ascending=False).head(20)


def result_item_from_row(row):
    absolute_change = float(row["absolute_change"])
    return {
        "entity": str(row["entity"]),
        "baseline_value": round(float(row["_baseline"]), 6),
        "predicted_value": round(float(row["_predicted"]), 6),
        "absolute_change": round(absolute_change, 6),
        "percent_change": round(float(row["percent_change"]), 6),
        "direction": str(row["direction"]),
        "explanation": str(row.get("explanation") or f"在该情景下预测值{('增加' if absolute_change >= 0 else '降低')}约 {abs(absolute_change):,.2f}，该结果来自模型模拟估计，需结合房屋其他特征判断。"),
    }


def create_charts(impacted, baseline, predicted, target, change_info):
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()
    chart_paths = []
    changes = predicted - baseline
    baseline_mean = float(baseline.mean()) if len(baseline) else 0.0
    predicted_mean = float(predicted.mean()) if len(predicted) else 0.0
    average_change = predicted_mean - baseline_mean

    if changes_are_effectively_equal(changes):
        plt.figure(figsize=(8, 5))
        labels = ["基准平均值", "情景平均值"]
        values = [baseline_mean, predicted_mean]
        bars = plt.bar(labels, values)
        plt.title("基准平均值与情景平均值对比")
        plt.xlabel("预测口径")
        plt.ylabel("预测价格（美元）")
        lower_bound = min(values)
        upper_bound = max(values)
        span = max(abs(upper_bound - lower_bound), abs(upper_bound) * 0.08, 1.0)
        plt.ylim(max(0, lower_bound - span), upper_bound + span)
        for bar, value in zip(bars, values):
            plt.text(bar.get_x() + bar.get_width() / 2, value, f"{value:,.0f}", ha="center", va="bottom", fontsize=10)
        plt.tight_layout()
        path = CHARTS_DIR / "scenario_average_bar.png"
        plt.savefig(path, dpi=160)
        plt.close()
        chart_paths.append(str(path))
    else:
        summary_values = [float(changes.mean()), float(changes.median()), float(changes.min()), float(changes.max())]
        summary_labels = ["平均变化", "中位数变化", "最小变化", "最大变化"]
        plt.figure(figsize=(9, 5))
        bars = plt.bar(summary_labels, summary_values)
        plt.axhline(0, color="#64748b", linewidth=1)
        plt.title("情景下预测价格变化分布")
        plt.xlabel("统计口径")
        plt.ylabel("预测价格变化（美元）")
        for bar, value in zip(bars, summary_values):
            plt.text(bar.get_x() + bar.get_width() / 2, value, f"{value:,.0f}", ha="center", va="bottom" if value >= 0 else "top", fontsize=9)
        plt.tight_layout()
        path = CHARTS_DIR / "change_distribution_summary.png"
        plt.savefig(path, dpi=160)
        plt.close()
        chart_paths.append(str(path))

    plt.figure(figsize=(8, 6))
    plt.scatter(baseline, predicted, alpha=0.55, s=18)
    low = float(min(baseline.min(), predicted.min()))
    high = float(max(baseline.max(), predicted.max()))
    plt.plot([low, high], [low, high], linestyle="--", linewidth=1.2, label="基准线")
    plt.title("基准值与预测值对比")
    plt.xlabel("基准值（美元）")
    plt.ylabel("预测值（美元）")
    plt.legend()
    plt.tight_layout()
    path = CHARTS_DIR / "baseline_vs_predicted_scatter.png"
    plt.savefig(path, dpi=160)
    plt.close()
    chart_paths.append(str(path))

    if len(impacted) > 1:
        plot_data = impacted.copy().head(20)
        plot_data["entity"] = plot_data["entity"].astype(str)
        plt.figure(figsize=(10, max(5, 0.35 * len(plot_data))))
        plt.barh(plot_data["entity"], plot_data["absolute_change"])
        plt.gca().invert_yaxis()
        plt.title("预测变化最大的对象")
        plt.xlabel("预测绝对变化（美元）")
        plt.ylabel("对象")
        for index, value in enumerate(plot_data["absolute_change"]):
            plt.text(value, index, f"{value:,.0f}", va="center", fontsize=8)
        plt.tight_layout()
        path = CHARTS_DIR / "top_20_changes.png"
        plt.savefig(path, dpi=160)
        plt.close()
        chart_paths.append(str(path))

    return chart_paths


def build_result(df, target, intervention_col, entity_col, baseline, predicted, model_info, change_info, impacted, chart_paths):
    changes = predicted - baseline
    coefficient = model_info.get("coefficient_per_data_unit")
    estimated_effect = None
    if coefficient is not None and change_info["change_type"] == "absolute":
        estimated_effect = float(coefficient) * safe_number(change_info["data_unit_change"], 0.0)
    limitations = list(PREDICTION_PLAN.get("limitations") or [])
    limitations.extend(HYPOTHESIS_PLAN.get("limitations") or [])
    intervention_name = str(get_nested(PREDICTION_PLAN, "intervention", "variable") or intervention_col or "情景变量")
    target_name = str(target or "目标指标")
    limitations.append(f"预测结果基于历史表格数据和模型关系估计，不能单独证明{intervention_name}变化与{target_name}变化之间的因果关系。")
    if change_info.get("unit_conversion") and "平方米" in str(change_info.get("unit_conversion")):
        limitations.append("原始房价数据常用平方英尺字段，本次已将用户输入的平方米换算为平方英尺后模拟。")
    if change_info.get("unit_conversion") and "房龄" in str(change_info.get("unit_conversion")):
        limitations.append("当前数据未直接提供房龄字段时，系统使用建造年份的反向变化近似模拟房龄变化。")
    if model_info.get("metrics", {}).get("r2") is not None:
        limitations.append(f"留出集 R² 约为 {model_info['metrics']['r2']}，仍存在未被模型解释的价格波动。")

    return {
        "task_type": "what_if_prediction",
        "scenario_summary": HYPOTHESIS_PLAN.get("scenario_summary") or PREDICTION_PLAN.get("prediction_goal", ""),
        "target_metric": target,
        "intervention": {
            **(PREDICTION_PLAN.get("intervention") if isinstance(PREDICTION_PLAN.get("intervention"), dict) else {}),
            "column": intervention_col,
            "change_type": change_info["change_type"],
            "change_value": change_info["change_value"],
            "unit": change_info.get("requested_unit") or "",
            "data_unit_change": round(float(change_info["data_unit_change"]), 6),
            "unit_conversion": change_info["unit_conversion"],
        },
        "entity_dimension": entity_col,
        "top_impacted_entities": [result_item_from_row(row) for _, row in impacted.iterrows()],
        "baseline_summary": {
            "mean": round(float(baseline.mean()), 6),
            "median": round(float(baseline.median()), 6),
            "count": int(len(baseline)),
        },
        "predicted_summary": {
            "mean": round(float(predicted.mean()), 6),
            "median": round(float(predicted.median()), 6),
            "count": int(len(predicted)),
            "mean_absolute_change": round(float(changes.mean()), 6),
            "median_absolute_change": round(float(changes.median()), 6),
            "min_absolute_change": round(float(changes.min()), 6),
            "max_absolute_change": round(float(changes.max()), 6),
        },
        "model_info": {
            "method": model_info["method"],
            "training_rows": int(clean_numeric(df[target]).notna().sum()) if target in df.columns else int(len(df)),
            "feature_columns": model_info.get("feature_columns") or [],
            "numeric_feature_columns": model_info.get("numeric_columns") or [],
            "categorical_feature_columns": model_info.get("categorical_columns") or [],
            "target_column": target,
            "intervention_column": intervention_col,
            "scenario_requested_change": change_info["change_value"],
            "scenario_requested_unit": change_info.get("requested_unit") or "",
            "scenario_change_in_data_units": round(float(change_info["data_unit_change"]), 6),
            "unit_conversion": change_info["unit_conversion"],
            "coefficient_per_data_unit": round(float(coefficient), 6) if coefficient is not None else None,
            "estimated_linear_effect": round(float(estimated_effect), 6) if estimated_effect is not None else None,
            "performance": model_info.get("metrics") or {},
        },
        "limitations": list(dict.fromkeys([str(item) for item in limitations if item])),
        "charts": chart_paths,
    }


def build_report_data(result):
    average_change = result["predicted_summary"].get("mean_absolute_change", 0.0)
    unit_conversion = result["model_info"].get("unit_conversion") or ""
    key_findings = [
        {
            "finding": f"在当前模型下，情景后的平均预测总价变化约为 {float(average_change):,.2f} 美元。",
            "evidence": "prediction_result.predicted_summary.mean_absolute_change",
        },
        {
            "finding": unit_conversion,
            "evidence": "prediction_result.model_info.unit_conversion",
        },
    ]
    return {
        "summary": result["scenario_summary"],
        "key_findings": key_findings,
        "top_impacted_entities": result["top_impacted_entities"],
        "model_info": result["model_info"],
        "recommendations": [
            "将该数值作为模型口径下的边际估计，不要直接作为实际成交价承诺。",
            "如需评估某一套具体房屋，应结合其质量、位置、装修、车库等字段重新审视模型输入。",
        ],
        "limitations": result["limitations"],
        "charts": result["charts"],
    }


def main():
    warnings.filterwarnings("ignore", category=UserWarning)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data(INPUT_FILE)
    df.columns = [str(column) for column in df.columns]
    target = choose_target(df)
    intervention_col = choose_intervention(df, target)
    entity_col = choose_entity(df)
    if not target:
        raise ValueError("无法识别可用于预测的目标字段。")
    if not intervention_col:
        raise ValueError("无法识别可用于情景调整的干预字段。")

    change_info = scenario_change_info(intervention_col)
    model_info = train_predictive_model(df, target, intervention_col)
    baseline, predicted = predict_scenario(df, model_info, target, intervention_col, change_info)
    impacted = build_impacted_entities(df, entity_col, baseline, predicted)
    chart_paths = create_charts(impacted, baseline, predicted, target, change_info)
    result = build_result(df, target, intervention_col, entity_col, baseline, predicted, model_info, change_info, impacted, chart_paths)
    (OUTPUT_DIR / "prediction_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report_data = build_report_data(result)
    (OUTPUT_DIR / "report_data.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
'''


def _is_unsupported_prediction_plan(prediction_plan: dict[str, Any]) -> bool:
    intervention = prediction_plan.get("intervention") if isinstance(prediction_plan.get("intervention"), dict) else {}
    if prediction_plan.get("is_supported") is False:
        return True
    return not str(intervention.get("column") or "").strip()


def _requires_deterministic_unit_aware_script(
    dataset_profile: dict[str, Any],
    hypothesis_plan: dict[str, Any],
    prediction_plan: dict[str, Any],
) -> bool:
    columns = {str(column) for column in dataset_profile.get("columns", [])}
    text = " ".join(
        [
            json.dumps(hypothesis_plan, ensure_ascii=False),
            json.dumps(prediction_plan, ensure_ascii=False),
        ]
    ).lower()
    has_price_target = any(str(column).lower() == "saleprice" or str(column) in {"房价", "总价", "售价", "价格"} for column in columns)
    has_area_column = any(str(column).lower() in {"grlivarea", "livingarea", "totalbsmtsf", "lotarea", "garagearea"} for column in columns)
    has_age_column = any(str(column).lower().replace("_", "") in {"houseage", "buildingage", "yearbuilt", "builtyear"} or str(column) in {"房龄", "房屋年龄", "建成年份", "建造年份", "建筑年份"} for column in columns)
    has_quality_column = any(str(column).lower() in {"overallqual", "overallcond", "kitchenqual", "exterqual"} or str(column) in {"装修", "装修等级", "质量等级"} for column in columns)
    has_bedroom_column = any(str(column).lower() in {"bedroomabvgr", "bedrooms", "bedroom"} or str(column) in {"卧室数", "居室数", "户型"} for column in columns)
    mentions_square_meters = any(token in text for token in ("平方米", "平米", "㎡", "m2", "m^2", "square meter"))
    mentions_area = any(token in text for token in ("面积", "grlivarea", "area", "平方"))
    mentions_distance = any(token in text for token in ("地铁", "距离", "米", "公里", "metro", "subway", "distance"))
    mentions_age = any(token in text for token in ("房龄", "房屋年龄", "建筑年龄", "楼龄", "house age", "building age"))
    mentions_quality = any(token in text for token in ("装修", "精装修", "普通装修", "装修等级", "质量", "quality", "finish"))
    mentions_bedroom = any(token in text for token in ("两居", "二居", "三居", "卧室", "居室", "户型", "bedroom"))
    mentions_price = any(token in text for token in ("总价", "房价", "价格", "saleprice", "price"))
    return has_price_target and mentions_price and (
        (has_area_column and ((mentions_square_meters and mentions_area) or mentions_distance))
        or (has_age_column and mentions_age)
        or (has_quality_column and mentions_quality)
        or (has_bedroom_column and mentions_bedroom)
    )


def _unsupported_plan_is_transformable(
    dataset_profile: dict[str, Any],
    hypothesis_plan: dict[str, Any],
    prediction_plan: dict[str, Any],
) -> bool:
    columns = {str(column) for column in dataset_profile.get("columns", [])}
    text = " ".join([
        json.dumps(hypothesis_plan, ensure_ascii=False),
        json.dumps(prediction_plan, ensure_ascii=False),
    ]).lower()
    has_price_target = any(str(column).lower() == "saleprice" or str(column) in {"房价", "总价", "售价", "价格"} for column in columns)
    has_age_column = any(str(column).lower().replace("_", "") in {"houseage", "buildingage", "yearbuilt", "builtyear"} or str(column) in {"房龄", "房屋年龄", "建成年份", "建造年份", "建筑年份"} for column in columns)
    has_quality_column = any(str(column).lower() in {"overallqual", "overallcond", "kitchenqual", "exterqual"} or str(column) in {"装修", "装修等级", "质量等级"} for column in columns)
    has_bedroom_column = any(str(column).lower() in {"bedroomabvgr", "bedrooms", "bedroom"} or str(column) in {"卧室数", "居室数", "户型"} for column in columns)
    mentions_age = any(token in text for token in ("房龄", "房屋年龄", "建筑年龄", "楼龄", "house age", "building age"))
    mentions_quality = any(token in text for token in ("装修", "精装修", "普通装修", "装修等级", "质量", "quality", "finish"))
    mentions_bedroom = any(token in text for token in ("两居", "二居", "三居", "卧室", "居室", "户型", "bedroom"))
    mentions_price = any(token in text for token in ("总价", "房价", "价格", "saleprice", "price"))
    return has_price_target and mentions_price and ((has_age_column and mentions_age) or (has_quality_column and mentions_quality) or (has_bedroom_column and mentions_bedroom))


def _extract_python_code(content: str) -> str:
    stripped = content.strip()
    match = re.search(r"```(?:python|py)?\s*(.*?)```", stripped, flags=re.DOTALL)
    return match.group(1).strip() if match else stripped


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
        raise ValueError("Generated prediction script is empty.")

    tree = ast.parse(script)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _validate_import_root(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module:
            _validate_import_root(node.module)
    missing_fragments = [
        fragment
        for fragment in ("font.sans-serif", "axes.unicode_minus")
        if fragment not in script
    ]
    if missing_fragments:
        raise ValueError(
            "Prediction script must configure Chinese matplotlib fonts: "
            + ", ".join(missing_fragments)
        )
    required_fragments = [
        "INPUT_FILE",
        "OUTPUT_DIR",
        "prediction_result.json",
        "report_data.json",
        "charts",
    ]
    missing_required = [fragment for fragment in required_fragments if fragment not in script]
    if missing_required:
        raise ValueError(
            "Prediction script is missing required fragments: "
            + ", ".join(missing_required)
        )
    missing_paths = []
    if input_file not in script:
        missing_paths.append(f'INPUT_FILE = Path(r"{input_file}")')
    if output_dir not in script:
        missing_paths.append(f'OUTPUT_DIR = Path(r"{output_dir}")')
    if missing_paths:
        raise ValueError(
            "Prediction script is missing the required runtime path constants: "
            + "; ".join(missing_paths)
        )
    english_chart_text = _find_english_visible_chart_text(tree)
    if english_chart_text:
        raise ValueError(
            "Prediction chart visible text must be Chinese: "
            + ", ".join(sorted(english_chart_text))
        )


def _validate_import_root(module_name: str) -> None:
    root = module_name.split(".", maxsplit=1)[0]
    if root not in ALLOWED_IMPORT_ROOTS:
        raise ValueError(f"Prediction script imports disallowed module: {module_name}")


def _find_english_visible_chart_text(tree: ast.AST) -> set[str]:
    visible_chart_calls = {
        "title",
        "xlabel",
        "ylabel",
        "suptitle",
        "figtext",
        "text",
        "set_title",
        "set_xlabel",
        "set_ylabel",
    }
    label_argument_calls = {
        "bar",
        "barh",
        "plot",
        "scatter",
        "lineplot",
        "barplot",
        "histplot",
        "boxplot",
    }
    offending: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call_name = _call_name(node.func)
        short_name = call_name.rsplit(".", 1)[-1]
        if short_name in visible_chart_calls:
            for arg in node.args[:1]:
                _collect_english_literal(arg, offending)
        if short_name in label_argument_calls:
            for keyword in node.keywords:
                if keyword.arg == "label":
                    _collect_english_literal(keyword.value, offending)
    return offending


def _collect_english_literal(node: ast.AST, offending: set[str]) -> None:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return
    text = node.value.strip()
    if not text:
        return
    if re.search(r"[\u4e00-\u9fff]", text):
        return
    if re.search(r"[A-Za-z]{3,}", text):
        offending.add(text)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""
