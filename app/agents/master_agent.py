from typing import Any


def create_rule_based_analysis_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    task_type = _detect_task_type(user_goal)
    if task_type == "grade_analysis":
        return _create_grade_analysis_plan(user_goal, dataset_profile)

    return {
        "task_type": task_type,
        "task_name": "通用数据分析",
        "reasoning_summary": "当前规则版主控 Agent 未匹配到固定模板，生成通用分析计划。",
        "steps": [],
        "required_columns": [],
        "analysis_methods": [],
        "charts": [],
        "expected_artifacts": [],
        "risks": [
            {
                "risk_type": "unsupported_template",
                "severity": "high",
                "description": "当前自动修复流程仅内置 grade_analysis 代码生成模板。",
            }
        ],
    }


def _detect_task_type(user_goal: str) -> str:
    goal = user_goal.lower()
    if all(keyword in goal for keyword in ("成绩", "班级", "统计")):
        return "grade_analysis"
    if any(keyword in goal for keyword in ("销量下降", "销售下滑", "收入下降", "gmv 下降")):
        return "sales_decline_analysis"
    return "general_data_analysis"


def _create_grade_analysis_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    columns = [str(column) for column in dataset_profile.get("columns", [])]
    class_column = _find_column(columns, ("班级", "class"))
    name_column = _find_column(columns, ("姓名", "name"))
    score_column = _find_column(columns, ("成绩", "分数", "score"))

    if score_column is None:
        numeric_summary = dataset_profile.get("numeric_summary", {})
        numeric_columns = [column for column in columns if column in numeric_summary]
        score_column = numeric_columns[0] if numeric_columns else None

    risks = []
    if class_column is None:
        risks.append(
            {
                "risk_type": "missing_class_column",
                "severity": "high",
                "description": "未识别到班级字段。",
            }
        )
    if score_column is None:
        risks.append(
            {
                "risk_type": "missing_score_column",
                "severity": "high",
                "description": "未识别到成绩或分数字段。",
            }
        )

    return {
        "task_type": "grade_analysis",
        "task_name": "成绩按班级统计分析",
        "reasoning_summary": "用户目标要求按班级统计成绩，规则版主控 Agent 选择 grade_analysis。",
        "steps": [
            {
                "step_id": "step_001",
                "name": "识别字段",
                "description": "识别班级、姓名和成绩字段。",
            },
            {
                "step_id": "step_002",
                "name": "清洗成绩",
                "description": "将成绩转换为数值并排除缺失成绩。",
            },
            {
                "step_id": "step_003",
                "name": "班级统计",
                "description": "按班级计算人数、平均分、最高分、最低分、及格率和优秀率。",
            },
            {
                "step_id": "step_004",
                "name": "生成图表",
                "description": "生成平均分和及格率柱状图。",
            },
        ],
        "required_columns": [
            {
                "semantic_name": "class",
                "column_name": class_column,
                "required": True,
                "reason": "用于按班级分组统计。",
            },
            {
                "semantic_name": "score",
                "column_name": score_column,
                "required": True,
                "reason": "用于计算成绩统计指标。",
            },
            {
                "semantic_name": "name",
                "column_name": name_column,
                "required": False,
                "reason": "可用于核对学生人数。",
            },
        ],
        "analysis_methods": [
            {
                "method": "groupby_aggregation",
                "description": "按班级聚合成绩。",
            },
            {
                "method": "threshold_rate_calculation",
                "description": "计算及格率和优秀率。",
            },
        ],
        "charts": [
            {
                "chart_id": "chart_001",
                "chart_type": "bar",
                "title": "班级平均分",
                "x": class_column,
                "y": "average_score",
            },
            {
                "chart_id": "chart_002",
                "chart_type": "bar",
                "title": "班级及格率",
                "x": class_column,
                "y": "pass_rate",
            },
        ],
        "expected_artifacts": [
            {"artifact_type": "json", "name": "analysis_result.json"},
            {"artifact_type": "json", "name": "report_data.json"},
            {"artifact_type": "image", "name": "charts/class_average_score.png"},
            {"artifact_type": "image", "name": "charts/class_pass_rate.png"},
        ],
        "risks": risks,
    }


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
