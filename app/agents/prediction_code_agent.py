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
- The code must create at least one PNG chart under OUTPUT_DIR / "charts".
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

Chinese chart requirements:
- Configure matplotlib Chinese font before any figure is created.
- Use Chinese visible text in every chart title, axis label, legend, and annotation.
- Do not use English chart titles such as "Top predicted changes" or "Baseline vs predicted".

Reliability requirements:
- If model training fails or fields are insufficient, fall back inside the script to a simple rule-based simulation.
- Treat validation feedback as mandatory. If validation reported missing artifacts, the repaired script must write prediction_result.json, report_data.json, and at least one PNG chart before exiting.
- Prefer robust pandas operations, numeric coercion, Top 20 chart categories, and cautious limitations instead of crashing.
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
        return f'''import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.tree import DecisionTreeRegressor
except Exception:
    LinearRegression = None
    DecisionTreeRegressor = None

INPUT_FILE = Path(r{input_file!r})
OUTPUT_DIR = Path(r{output_dir!r})
CHARTS_DIR = OUTPUT_DIR / "charts"
DATASET_PROFILE = json.loads({json.dumps(json.dumps(dataset_profile, ensure_ascii=False))})
HYPOTHESIS_PLAN = json.loads({json.dumps(json.dumps(hypothesis_plan, ensure_ascii=False))})
PREDICTION_PLAN = json.loads({json.dumps(json.dumps(prediction_plan, ensure_ascii=False))})


def load_data(path):
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {{".xlsx", ".xls"}}:
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


def clean_numeric(df, column):
    if column and column in df.columns:
        return pd.to_numeric(df[column], errors="coerce")
    return pd.Series([np.nan] * len(df))


def choose_target(df):
    target = PREDICTION_PLAN.get("target_metric") or ""
    if target in df.columns:
        return target
    numeric = [c for c in df.columns if pd.to_numeric(df[c], errors="coerce").notna().sum() > 0]
    return numeric[0] if numeric else ""


def choose_entity(df):
    entity = PREDICTION_PLAN.get("entity_dimension") or ""
    if entity in df.columns:
        return entity
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("category"):
            if df[c].nunique(dropna=True) <= max(50, len(df) // 2):
                return c
    return ""


def change_multiplier():
    intervention = PREDICTION_PLAN.get("intervention", {{}})
    change_type = intervention.get("change_type") or "unknown"
    change_value = safe_number(intervention.get("change_value"), 0.0)
    if change_type in {{"relative", "weight_shift"}}:
        return change_value
    if abs(change_value) > 1:
        return change_value / 100.0
    return change_value


def feature_frame(df, target):
    features = [c for c in PREDICTION_PLAN.get("feature_columns", []) if c in df.columns and c != target]
    if not features:
        features = [c for c in df.columns if c != target and pd.to_numeric(df[c], errors="coerce").notna().sum() > 0]
    if not features:
        return pd.DataFrame(index=df.index), []
    X = pd.DataFrame({{c: pd.to_numeric(df[c], errors="coerce") for c in features}})
    X = X.replace([np.inf, -np.inf], np.nan).fillna(X.median(numeric_only=True)).fillna(0)
    return X, features


def predict_rows(df, target):
    y = clean_numeric(df, target).replace([np.inf, -np.inf], np.nan)
    valid = y.notna()
    X, features = feature_frame(df, target)
    baseline = y.fillna(y.median() if y.notna().any() else 0)
    delta = change_multiplier()
    intervention_col = PREDICTION_PLAN.get("intervention", {{}}).get("column") or ""
    method = "rule_based_simulation"
    predicted = baseline * (1 + delta * 0.3)

    if target and len(df) >= 8 and valid.sum() >= 6 and LinearRegression is not None and not X.empty:
        try:
            model = LinearRegression()
            model.fit(X.loc[valid], y.loc[valid])
            X_scenario = X.copy()
            if intervention_col in X_scenario.columns:
                X_scenario[intervention_col] = X_scenario[intervention_col] * (1 + delta)
            elif X_scenario.shape[1] > 0:
                X_scenario[X_scenario.columns[0]] = X_scenario[X_scenario.columns[0]] * (1 + delta)
            predicted = pd.Series(model.predict(X_scenario), index=df.index)
            method = "linear_regression"
        except Exception:
            predicted = baseline * (1 + delta * 0.3)
            method = "rule_based_simulation"

    return baseline.astype(float), pd.Series(predicted, index=df.index).astype(float), method, features


def aggregate_impacts(df, target, entity, baseline, predicted):
    work = df.copy()
    work["_baseline"] = baseline
    work["_predicted"] = predicted
    if entity and entity in work.columns:
        grouped = work.groupby(entity, dropna=False)[["_baseline", "_predicted"]].mean().reset_index()
        grouped = grouped.rename(columns={{entity: "entity"}})
    else:
        grouped = pd.DataFrame([{{"entity": "整体", "_baseline": baseline.mean(), "_predicted": predicted.mean()}}])
    grouped["absolute_change"] = grouped["_predicted"] - grouped["_baseline"]
    grouped["percent_change"] = np.where(grouped["_baseline"].abs() > 1e-9, grouped["absolute_change"] / grouped["_baseline"], 0)
    grouped["direction"] = np.where(grouped["absolute_change"] >= 0, "增加", "降低")
    grouped = grouped.replace([np.inf, -np.inf], np.nan).fillna(0)
    grouped["_rank"] = grouped["absolute_change"].abs()
    grouped = grouped.sort_values("_rank", ascending=False).head(10)
    return grouped


def build_result(df, target, entity, baseline, predicted, method, features, impacted, chart_paths):
    top_entities = []
    for _, row in impacted.iterrows():
        top_entities.append({{
            "entity": str(row["entity"]),
            "baseline_value": round(float(row["_baseline"]), 6),
            "predicted_value": round(float(row["_predicted"]), 6),
            "absolute_change": round(float(row["absolute_change"]), 6),
            "percent_change": round(float(row["percent_change"]), 6),
            "direction": str(row["direction"]),
            "explanation": "该对象在当前情景下显示出较明显的预测变化，需结合业务背景进一步验证。"
        }})
    limitations = list(PREDICTION_PLAN.get("limitations") or [])
    if method == "rule_based_simulation":
        limitations.append("当前结果使用规则模拟或简化模型，不代表确定因果。")
    if len(df) < 30:
        limitations.append("样本量较小，预测稳定性有限。")
    return {{
        "task_type": "what_if_prediction",
        "scenario_summary": HYPOTHESIS_PLAN.get("scenario_summary") or PREDICTION_PLAN.get("prediction_goal", ""),
        "target_metric": target,
        "intervention": PREDICTION_PLAN.get("intervention", {{}}),
        "entity_dimension": entity,
        "top_impacted_entities": top_entities,
        "baseline_summary": {{
            "mean": round(float(baseline.mean()), 6),
            "median": round(float(baseline.median()), 6),
            "count": int(len(baseline))
        }},
        "predicted_summary": {{
            "mean": round(float(predicted.mean()), 6),
            "median": round(float(predicted.median()), 6),
            "count": int(len(predicted))
        }},
        "model_info": {{
            "method": method,
            "training_rows": int(len(df)),
            "feature_columns": features,
            "available_features": len(features)
        }},
        "limitations": list(dict.fromkeys(limitations)),
        "charts": chart_paths
    }}


def create_charts(impacted, target):
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    configure_matplotlib()
    chart_paths = []
    if impacted.empty:
        return chart_paths
    plot_data = impacted.copy()
    plot_data["entity"] = plot_data["entity"].astype(str)

    plt.figure(figsize=(10, 5))
    plt.barh(plot_data["entity"], plot_data["absolute_change"], color="#0f766e")
    plt.gca().invert_yaxis()
    plt.title("预测变化最大的对象")
    plt.xlabel("预测绝对变化")
    plt.ylabel("对象")
    plt.tight_layout()
    path = CHARTS_DIR / "top_predicted_changes.png"
    plt.savefig(path, dpi=160)
    plt.close()
    chart_paths.append(str(path))

    plt.figure(figsize=(10, 5))
    x = np.arange(len(plot_data))
    width = 0.38
    plt.bar(x - width / 2, plot_data["_baseline"], width, label="基准值")
    plt.bar(x + width / 2, plot_data["_predicted"], width, label="预测值")
    plt.xticks(x, plot_data["entity"], rotation=30, ha="right")
    plt.title("基准值与预测值对比")
    plt.ylabel(target or "指标值")
    plt.legend()
    plt.tight_layout()
    path = CHARTS_DIR / "baseline_vs_predicted.png"
    plt.savefig(path, dpi=160)
    plt.close()
    chart_paths.append(str(path))
    return chart_paths


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_data(INPUT_FILE)
    df.columns = [str(c) for c in df.columns]
    target = choose_target(df)
    entity = choose_entity(df)
    if not target:
        numeric = df.select_dtypes(include=[np.number])
        if numeric.empty:
            df["_synthetic_metric"] = np.arange(len(df), dtype=float)
            target = "_synthetic_metric"
        else:
            target = str(numeric.columns[0])
    baseline, predicted, method, features = predict_rows(df, target)
    impacted = aggregate_impacts(df, target, entity, baseline, predicted)
    chart_paths = create_charts(impacted, target)
    result = build_result(df, target, entity, baseline, predicted, method, features, impacted, chart_paths)
    (OUTPUT_DIR / "prediction_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    report_data = {{
        "summary": result["scenario_summary"],
        "key_findings": [
            {{
                "finding": f"预测平均值从 {{result['baseline_summary']['mean']}} 变化到 {{result['predicted_summary']['mean']}}。",
                "evidence": "prediction_result.baseline_summary and prediction_result.predicted_summary"
            }}
        ],
        "top_impacted_entities": result["top_impacted_entities"],
        "model_info": result["model_info"],
        "recommendations": ["将预测变化较大的对象作为优先复盘对象，并结合外部业务因素验证。"],
        "limitations": result["limitations"],
        "charts": chart_paths
    }}
    (OUTPUT_DIR / "report_data.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
'''


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
