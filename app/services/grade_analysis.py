import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import matplotlib
import pandas as pd
from fastapi import HTTPException, status

from app.services.dataset_reader import load_uploaded_dataset
from app.services.execution_log_service import write_fixed_template_execution_log


matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


JOB_ROOT = Path("storage/jobs")
ANALYSIS_TYPE = "grade_analysis"
RESULT_FILENAME = "analysis_result.json"
PASS_SCORE = 60
EXCELLENT_SCORE = 90


def create_grade_analysis_job(dataset_id: str, user_goal: str) -> dict[str, str]:
    if not _is_grade_analysis_goal(user_goal):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Unsupported analysis goal. Try a goal containing "成绩", "班级", and "统计".',
        )

    source_file, df = load_uploaded_dataset(dataset_id)
    df = df.rename(columns=lambda column: str(column).strip())
    fields = _identify_grade_fields(df)
    analysis_df = _build_analysis_dataframe(df, fields)
    summary = _build_class_summary(analysis_df)

    job_id = uuid4().hex
    job_dir = JOB_ROOT / job_id
    charts_dir = job_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=False)

    chart_paths = _generate_charts(summary, charts_dir)
    result_path = job_dir / RESULT_FILENAME

    analysis_plan = _build_grade_analysis_plan(user_goal, fields)
    result = {
        "job_id": job_id,
        "task_type": ANALYSIS_TYPE,
        "analysis_type": ANALYSIS_TYPE,
        "dataset_id": dataset_id,
        "user_goal": user_goal,
        "source_file": str(source_file),
        "analysis_plan": analysis_plan,
        "fields": fields,
        "thresholds": {
            "pass_score": PASS_SCORE,
            "excellent_score": EXCELLENT_SCORE,
        },
        "summary": summary,
        "charts": chart_paths,
        "result_path": str(result_path),
    }

    with result_path.open("w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, indent=2)

    write_fixed_template_execution_log(
        job_dir=job_dir,
        job_id=job_id,
        dataset_id=dataset_id,
        user_goal=user_goal,
        analysis_plan=analysis_plan,
        result_path=result_path,
        chart_paths=chart_paths,
        executor_code_path=str(Path(__file__).resolve()),
    )

    return {
        "job_id": job_id,
        "analysis_type": ANALYSIS_TYPE,
        "result_path": str(result_path),
        "charts_dir": str(charts_dir),
    }


def _build_grade_analysis_plan(
    user_goal: str,
    fields: dict[str, str | None],
) -> dict[str, Any]:
    return {
        "task_type": ANALYSIS_TYPE,
        "task_name": "成绩按班级统计分析",
        "user_goal": user_goal,
        "steps": [
            {
                "step_id": "step_001",
                "name": "字段识别",
                "description": "识别班级、姓名和成绩字段，确认分析所需字段是否存在。",
            },
            {
                "step_id": "step_002",
                "name": "数据清洗",
                "description": "将成绩字段转换为数值，并排除成绩为空或无法转换的记录。",
            },
            {
                "step_id": "step_003",
                "name": "班级统计",
                "description": "按班级计算人数、平均分、最高分、最低分、及格率和优秀率。",
            },
            {
                "step_id": "step_004",
                "name": "图表生成",
                "description": "生成班级平均分柱状图和班级及格率柱状图。",
            },
            {
                "step_id": "step_005",
                "name": "报告生成",
                "description": "整理关键发现并生成 Markdown 报告。",
            },
        ],
        "required_columns": [
            {
                "semantic_name": "class",
                "column_name": fields.get("class_field"),
                "required": True,
            },
            {
                "semantic_name": "score",
                "column_name": fields.get("score_field"),
                "required": True,
            },
            {
                "semantic_name": "name",
                "column_name": fields.get("name_field"),
                "required": False,
            },
        ],
        "analysis_methods": ["groupby_aggregation", "threshold_rate_calculation"],
        "charts": ["class_average_score", "class_pass_rate"],
        "expected_artifacts": ["analysis_result.json", "report.md", "charts/*.png"],
    }


def _is_grade_analysis_goal(user_goal: str) -> bool:
    goal = user_goal.lower()
    return all(keyword in goal for keyword in ("成绩", "班级", "统计"))


def _identify_grade_fields(df: pd.DataFrame) -> dict[str, str | None]:
    class_field = _find_text_field(df.columns, ("班级", "class"))
    name_field = _find_text_field(df.columns, ("姓名", "name"))

    if class_field is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Class field not found. Expected a column containing "班级" or "class".',
        )

    score_field = _find_score_field(df, excluded_fields={class_field, name_field})
    if score_field is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Score field not found. Expected a numeric column or a column containing "成绩", "分数", or "score".',
        )

    return {
        "class_field": class_field,
        "name_field": name_field,
        "score_field": score_field,
    }


def _find_text_field(columns: pd.Index, keywords: tuple[str, ...]) -> str | None:
    normalized_keywords = tuple(keyword.lower() for keyword in keywords)

    for column in columns:
        column_name = str(column).strip()
        normalized_name = column_name.lower()
        if any(keyword in normalized_name for keyword in normalized_keywords):
            return column_name

    return None


def _find_score_field(
    df: pd.DataFrame,
    excluded_fields: set[str | None],
) -> str | None:
    score_keywords = ("成绩", "分数", "score")

    keyword_matches = [
        str(column).strip()
        for column in df.columns
        if any(keyword in str(column).lower() for keyword in score_keywords)
    ]

    for column in keyword_matches:
        if _to_numeric_series(df[column]).notna().any():
            return column

    numeric_columns = [
        str(column).strip()
        for column in df.select_dtypes(include=["number"]).columns
        if str(column).strip() not in excluded_fields
    ]

    if numeric_columns:
        return numeric_columns[0]

    return None


def _build_analysis_dataframe(
    df: pd.DataFrame,
    fields: dict[str, str | None],
) -> pd.DataFrame:
    class_field = fields["class_field"]
    score_field = fields["score_field"]

    if class_field is None or score_field is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Grade analysis fields are incomplete.",
        )

    analysis_df = pd.DataFrame(
        {
            "class_name": df[class_field].astype(str).str.strip(),
            "score": _to_numeric_series(df[score_field]),
        }
    )
    analysis_df = analysis_df.dropna(subset=["score"])
    analysis_df = analysis_df[analysis_df["class_name"].ne("")]
    analysis_df = analysis_df[analysis_df["class_name"].str.lower().ne("nan")]

    if analysis_df.empty:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid class and score rows found for grade analysis.",
        )

    return analysis_df


def _build_class_summary(analysis_df: pd.DataFrame) -> list[dict[str, Any]]:
    grouped = analysis_df.groupby("class_name", sort=True)["score"]
    summary_df = grouped.agg(
        student_count="count",
        average_score="mean",
        max_score="max",
        min_score="min",
    ).reset_index()

    pass_rate = grouped.apply(lambda scores: (scores >= PASS_SCORE).mean()).reset_index(
        name="pass_rate"
    )
    excellent_rate = grouped.apply(
        lambda scores: (scores >= EXCELLENT_SCORE).mean()
    ).reset_index(name="excellent_rate")

    summary_df = summary_df.merge(pass_rate, on="class_name").merge(
        excellent_rate,
        on="class_name",
    )

    summary_df["average_score"] = summary_df["average_score"].round(2)
    summary_df["max_score"] = summary_df["max_score"].round(2)
    summary_df["min_score"] = summary_df["min_score"].round(2)
    summary_df["pass_rate"] = summary_df["pass_rate"].round(4)
    summary_df["excellent_rate"] = summary_df["excellent_rate"].round(4)

    return [
        {
            "class_name": str(row["class_name"]),
            "student_count": int(row["student_count"]),
            "average_score": _to_json_number(row["average_score"]),
            "max_score": _to_json_number(row["max_score"]),
            "min_score": _to_json_number(row["min_score"]),
            "pass_rate": _to_json_number(row["pass_rate"]),
            "excellent_rate": _to_json_number(row["excellent_rate"]),
        }
        for _, row in summary_df.iterrows()
    ]


def _generate_charts(summary: list[dict[str, Any]], charts_dir: Path) -> list[str]:
    _configure_matplotlib()

    average_score_path = charts_dir / "class_average_score.png"
    pass_rate_path = charts_dir / "class_pass_rate.png"

    class_names = [item["class_name"] for item in summary]
    average_scores = [item["average_score"] for item in summary]
    pass_rates = [item["pass_rate"] * 100 for item in summary]

    _save_bar_chart(
        labels=class_names,
        values=average_scores,
        title="班级平均分",
        ylabel="平均分",
        output_path=average_score_path,
        value_suffix="",
    )
    _save_bar_chart(
        labels=class_names,
        values=pass_rates,
        title="班级及格率",
        ylabel="及格率（%）",
        output_path=pass_rate_path,
        value_suffix="%",
        y_limit=(0, 105),
    )

    return [str(average_score_path), str(pass_rate_path)]


def _configure_matplotlib() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def _save_bar_chart(
    labels: list[str],
    values: list[float],
    title: str,
    ylabel: str,
    output_path: Path,
    value_suffix: str,
    y_limit: tuple[int, int] | None = None,
) -> None:
    figure_width = max(8, min(16, len(labels) * 1.2))
    fig, ax = plt.subplots(figsize=(figure_width, 5))
    bars = ax.bar(labels, values, color="#0f766e")
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("班级")

    if y_limit is not None:
        ax.set_ylim(*y_limit)

    ax.bar_label(
        bars,
        labels=[f"{value:.2f}{value_suffix}" for value in values],
        padding=3,
        fontsize=9,
    )
    ax.tick_params(axis="x", rotation=25)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def _to_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _to_json_number(value: Any) -> float | int | None:
    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        value = value.item()

    if isinstance(value, float) and value.is_integer():
        return int(value)

    return value
