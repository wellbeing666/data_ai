from typing import Any


def create_rule_based_analysis_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    task_type = _detect_task_type(user_goal)
    if task_type == "grade_analysis":
        return _create_grade_analysis_plan(user_goal, dataset_profile)
    if task_type == "insight_mining":
        return _create_insight_mining_plan(user_goal, dataset_profile)

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
    if _looks_like_insight_goal(goal):
        return "insight_mining"
    if _looks_like_prediction_goal(goal):
        return "what_if_prediction"
    if all(keyword in goal for keyword in ("成绩", "班级", "统计")):
        return "grade_analysis"
    if any(keyword in goal for keyword in ("销量下降", "销售下滑", "收入下降", "gmv 下降")):
        return "sales_decline_analysis"
    return "general_data_analysis"


def _looks_like_insight_goal(goal: str) -> bool:
    insight_keywords = (
        "智能洞察",
        "洞察挖掘",
        "自动洞察",
        "自动扫描",
        "无需目标",
        "不提交分析目标",
        "potential insight",
        "insight mining",
        "auto insight",
    )
    return any(keyword in goal for keyword in insight_keywords)


def _create_insight_mining_plan(user_goal: str, dataset_profile: dict[str, Any]) -> dict[str, Any]:
    columns = [str(column) for column in dataset_profile.get("columns", [])]
    return {
        "task_type": "insight_mining",
        "task_name": "智能洞察挖掘",
        "reasoning_summary": "用户选择无目标智能洞察模式，系统将自动扫描数据中的趋势、分组差异、相关性、异常和序列模式。",
        "steps": [
            {"step_id": "step_001", "name": "字段自动识别", "description": "识别日期、数值、类别、客户和商品字段。"},
            {"step_id": "step_002", "name": "批量模式扫描", "description": "扫描趋势、周末效应、分组差异、相关性、数据质量和简单购买序列。"},
            {"step_id": "step_003", "name": "洞察评分排序", "description": "按效应大小、样本覆盖和置信度排序，优先展示高价值洞察。"},
            {"step_id": "step_004", "name": "生成洞察报告", "description": "生成洞察说明、图表、建议动作和限制条件。"},
        ],
        "required_columns": columns[:12],
        "analysis_methods": ["模式识别", "分组对比", "趋势扫描", "相关性分析", "数据质量检查"],
        "charts": ["高分洞察图表", "趋势图", "分组差异图", "相关性散点图"],
        "expected_artifacts": [
            {"artifact_type": "json", "name": "analysis_result.json"},
            {"artifact_type": "json", "name": "explanation.json"},
            {"artifact_type": "image", "name": "charts/insight_*.png"},
        ],
        "risks": [
            {"risk_type": "correlation_not_causation", "severity": "medium", "description": "自动洞察只能提供相关信号，需要业务复核和实验验证。"}
        ],
    }


def _looks_like_prediction_goal(goal: str) -> bool:
    prediction_keywords = (
        "what if",
        "what-if",
        "if ",
        "forecast",
        "predict",
        "prediction",
        "simulate",
        "simulation",
        "scenario",
        "假设",
        "如果",
        "预测",
        "情景",
        "场景",
        "模拟",
        "可能变化",
        "可能提升",
        "可能下降",
        "提升",
        "提高",
        "增加",
        "降低",
        "减少",
        "权重",
        "预算",
        "干预",
    )
    return any(keyword in goal for keyword in prediction_keywords)


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

