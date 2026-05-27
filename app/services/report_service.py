import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status


REPORT_FILENAME = "report.md"


def generate_markdown_report(
    analysis_result_path: str,
    chart_paths: list[str] | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    result_path = Path(analysis_result_path).resolve()
    if not result_path.exists() or not result_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="analysis_result_path does not exist or is not a file.",
        )

    analysis_result = _load_json(result_path)
    result_dir = result_path.parent
    resolved_output_path = Path(output_path).resolve() if output_path else result_dir / REPORT_FILENAME

    if not _is_relative_to(resolved_output_path, result_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="output_path must be inside the analysis result directory.",
        )

    resolved_chart_paths = _resolve_chart_paths(
        chart_paths=chart_paths or [],
        analysis_result=analysis_result,
        base_dir=result_dir,
    )

    task_type = str(
        analysis_result.get("task_type")
        or analysis_result.get("analysis_type")
        or _deep_get(analysis_result, ["analysis_plan", "task_type"])
        or ""
    )
    if task_type == "grade_analysis":
        markdown = _build_grade_analysis_report(analysis_result, resolved_chart_paths, result_dir)
    elif task_type == "sales_decline_analysis":
        markdown = _build_sales_decline_report(analysis_result, resolved_chart_paths, result_dir)
    else:
        markdown = _build_general_report(analysis_result, resolved_chart_paths, result_dir)

    resolved_output_path.write_text(markdown, encoding="utf-8")
    return {
        "report_path": str(resolved_output_path),
        "analysis_result_path": str(result_path),
        "chart_paths": [str(path) for path in resolved_chart_paths],
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"analysis_result.json is not valid JSON: {exc}",
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="analysis_result.json must be a JSON object.",
        )

    return data


def _resolve_chart_paths(
    chart_paths: list[str],
    analysis_result: dict[str, Any],
    base_dir: Path,
) -> list[Path]:
    raw_paths = chart_paths or [str(path) for path in analysis_result.get("charts", [])]
    resolved_paths = []

    for raw_path in raw_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = base_dir / path
        path = path.resolve()
        if path.exists() and path.is_file():
            resolved_paths.append(path)

    charts_dir = base_dir / "charts"
    if not resolved_paths and charts_dir.exists():
        resolved_paths = sorted(path.resolve() for path in charts_dir.glob("*.png") if path.is_file())

    return resolved_paths


def _build_grade_analysis_report(
    analysis_result: dict[str, Any],
    chart_paths: list[Path],
    report_dir: Path,
) -> str:
    summary = _as_list(analysis_result.get("summary"))
    task_name = "成绩按班级统计分析报告"
    thresholds = analysis_result.get("thresholds", {})
    pass_score = thresholds.get("pass_score", 60)
    excellent_score = thresholds.get("excellent_score", 90)

    total_students = sum(_safe_number(row.get("student_count")) for row in summary)
    class_count = len(summary)
    best_average = _max_row(summary, "average_score")
    lowest_average = _min_row(summary, "average_score")
    best_pass_rate = _max_row(summary, "pass_rate")
    best_excellent_rate = _max_row(summary, "excellent_rate")

    lines = [
        f"# {task_name}",
        "",
        "## 分析目标",
        "按班级统计学生成绩，展示班级之间的平均分、及格率和优秀率差异，为课程设计演示提供结构化分析结果。",
        "",
        "## 数据概况",
        f"- 班级数量：{class_count}",
        f"- 有效成绩记录数：{int(total_students)}",
        f"- 及格线：{pass_score} 分",
        f"- 优秀线：{excellent_score} 分",
        "",
        "## 关键发现",
    ]

    if best_average:
        lines.append(
            f"- 平均分最高的班级是 **{best_average.get('class_name')}**，平均分为 **{_fmt_number(best_average.get('average_score'))}**。"
        )
    if lowest_average:
        lines.append(
            f"- 平均分最低的班级是 **{lowest_average.get('class_name')}**，平均分为 **{_fmt_number(lowest_average.get('average_score'))}**。"
        )
    if best_pass_rate:
        lines.append(
            f"- 及格率最高的班级是 **{best_pass_rate.get('class_name')}**，及格率为 **{_fmt_percent(best_pass_rate.get('pass_rate'))}**。"
        )
    if best_excellent_rate:
        lines.append(
            f"- 优秀率最高的班级是 **{best_excellent_rate.get('class_name')}**，优秀率为 **{_fmt_percent(best_excellent_rate.get('excellent_rate'))}**。"
        )
    if not summary:
        lines.append("- 暂未发现可展示的班级统计结果。")

    lines.extend(
        [
            "",
            "## 班级对比明细",
            "",
            "| 班级 | 人数 | 平均分 | 最高分 | 最低分 | 及格率 | 优秀率 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in summary:
        lines.append(
            "| {class_name} | {student_count} | {average_score} | {max_score} | {min_score} | {pass_rate} | {excellent_rate} |".format(
                class_name=row.get("class_name", ""),
                student_count=int(_safe_number(row.get("student_count"))),
                average_score=_fmt_number(row.get("average_score")),
                max_score=_fmt_number(row.get("max_score")),
                min_score=_fmt_number(row.get("min_score")),
                pass_rate=_fmt_percent(row.get("pass_rate")),
                excellent_rate=_fmt_percent(row.get("excellent_rate")),
            )
        )

    lines.extend(
        [
            "",
            "## 图表说明",
            *_build_chart_lines(chart_paths, report_dir),
            "",
            "## 可能原因 / 统计结论",
            "- 班级平均分可以反映各班整体成绩水平，适合用于横向对比。",
            "- 及格率体现基础达标情况，优秀率体现高分段学生占比；两者结合能更完整地观察班级成绩结构。",
            "- 如果某个班级平均分不低但优秀率偏低，可能说明学生集中在中等分段；如果及格率偏低，则需要重点关注临界和低分学生。",
            "",
            "## 数据限制",
            "- 当前报告基于上传文件中的一次成绩数据，不能代表长期趋势。",
            "- 及格率和优秀率默认按固定阈值计算，如学校规则不同需要调整。",
            "- 缺失或无法转换为数值的成绩记录会影响统计结果，建议在正式分析前确认数据完整性。",
        ]
    )

    return "\n".join(lines) + "\n"


def _build_sales_decline_report(
    analysis_result: dict[str, Any],
    chart_paths: list[Path],
    report_dir: Path,
) -> str:
    task_name = _deep_get(analysis_result, ["analysis_plan", "task_name"]) or "销量下降分析报告"
    summary = analysis_result.get("summary") or analysis_result.get("result") or []

    lines = [
        f"# {task_name}",
        "",
        "## 分析目标",
        "围绕销量或销售指标的下降现象进行描述性拆解，识别与下降同步变化的时间、渠道、产品或地区因素。",
        "",
        "## 数据概况",
        f"- 分析结果记录数：{len(summary) if isinstance(summary, list) else 1}",
        "- 本报告仅基于已生成的结构化分析结果和图表进行总结。",
        "",
        "## 关键发现",
        *_build_generic_findings(analysis_result),
        "",
        "## 图表说明",
        *_build_chart_lines(chart_paths, report_dir),
        "",
        "## 可能原因 / 统计结论",
        "- 以下内容仅表示统计相关或同步变化，不构成绝对因果判断。",
        "- 如果某些渠道、地区或产品在销量下降期间变化更明显，它们可能是需要优先排查的方向。",
        "- 若时间趋势中存在集中下滑区间，建议结合促销、库存、价格、流量和外部活动进一步验证。",
        "- 当前分析不能单独证明“某因素导致销量下降”，只能为后续业务排查提供线索。",
        "",
        "## 数据限制",
        "- 如果缺少历史同期数据，无法充分判断同比变化。",
        "- 如果缺少渠道、地区、产品或流量字段，下降拆解会受到限制。",
        "- 统计相关不等于因果关系，重要结论需要结合业务背景和实验验证。",
    ]
    return "\n".join(lines) + "\n"


def _build_general_report(
    analysis_result: dict[str, Any],
    chart_paths: list[Path],
    report_dir: Path,
) -> str:
    task_name = _deep_get(analysis_result, ["analysis_plan", "task_name"]) or "数据分析报告"
    lines = [
        f"# {task_name}",
        "",
        "## 分析目标",
        "根据已生成的分析结果，对数据进行结构化总结和展示。",
        "",
        "## 数据概况",
        f"- 任务类型：{analysis_result.get('task_type', 'unknown')}",
        f"- 分析是否成功：{analysis_result.get('success', 'unknown')}",
        "",
        "## 关键发现",
        *_build_generic_findings(analysis_result),
        "",
        "## 图表说明",
        *_build_chart_lines(chart_paths, report_dir),
        "",
        "## 可能原因 / 统计结论",
        "- 当前报告基于已有统计结果进行归纳，适合用于展示主要数据模式。",
        "- 若需要进一步解释变化原因，建议补充时间、维度和业务背景字段。",
        "",
        "## 数据限制",
        "- 当前报告依赖 analysis_result.json 中已有的结果字段。",
        "- 如果原始数据存在缺失、重复或字段含义不清，结论可靠性会受到影响。",
    ]
    return "\n".join(lines) + "\n"


def _build_chart_lines(chart_paths: list[Path], report_dir: Path) -> list[str]:
    if not chart_paths:
        return ["- 暂无可用图表。"]

    lines = []
    for index, chart_path in enumerate(chart_paths, start=1):
        title = _guess_chart_title(chart_path)
        display_path = _markdown_path(chart_path, report_dir)
        lines.extend(
            [
                f"### 图表 {index}：{title}",
                f"![{title}]({display_path})",
                f"- 说明：该图用于展示{title}。",
                "",
            ]
        )
    return lines


def _build_generic_findings(analysis_result: dict[str, Any]) -> list[str]:
    findings = analysis_result.get("key_findings") or analysis_result.get("findings")
    if isinstance(findings, list) and findings:
        lines = []
        for finding in findings[:5]:
            if isinstance(finding, dict):
                title = finding.get("title") or finding.get("name") or "发现"
                description = finding.get("description") or finding.get("insight") or ""
                lines.append(f"- **{title}**：{description}")
            else:
                lines.append(f"- {finding}")
        return lines

    summary = analysis_result.get("summary")
    if isinstance(summary, list) and summary:
        return [f"- 已生成 {len(summary)} 条结构化统计结果，可查看 analysis_result.json 获取明细。"]
    if isinstance(summary, str) and summary:
        return [f"- {summary}"]
    return ["- 暂未发现可自动提取的关键发现。"]


def _guess_chart_title(chart_path: Path) -> str:
    name = chart_path.stem.lower()
    if "average" in name or "avg" in name:
        return "班级平均分"
    if "pass_rate" in name or "pass" in name:
        return "班级及格率"
    if "excellent" in name:
        return "班级优秀率"
    if "trend" in name:
        return "趋势变化"
    return chart_path.stem.replace("_", " ")


def _markdown_path(chart_path: Path, report_dir: Path) -> str:
    try:
        return chart_path.relative_to(report_dir).as_posix()
    except ValueError:
        return chart_path.as_posix()


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _max_row(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    valid_rows = [row for row in rows if _is_number(row.get(key))]
    return max(valid_rows, key=lambda row: float(row[key]), default=None)


def _min_row(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    valid_rows = [row for row in rows if _is_number(row.get(key))]
    return min(valid_rows, key=lambda row: float(row[key]), default=None)


def _safe_number(value: Any) -> float:
    if _is_number(value):
        return float(value)
    return 0.0


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fmt_number(value: Any) -> str:
    if not _is_number(value):
        return "-"
    number = float(value)
    return str(int(number)) if number.is_integer() else f"{number:.2f}"


def _fmt_percent(value: Any) -> str:
    if not _is_number(value):
        return "-"
    return f"{float(value) * 100:.2f}%"


def _deep_get(data: dict[str, Any], keys: list[str]) -> Any:
    value: Any = data
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False
