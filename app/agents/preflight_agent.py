import json
from typing import Any

from app.agents.data_understanding_agent import create_data_understanding
from app.services.llm_client import LLMClient, get_llm_client


RESULT_KEYS = [
    "intent_type",
    "is_task_clear",
    "clarity_score",
    "detected_fields",
    "data_quality_report",
    "clarifying_questions",
    "intent_questions",
    "suggested_goals",
    "optimized_goal",
    "next_action",
    "data_understanding",
]

SYSTEM_PROMPT = """You are the intent recognition and prompt optimization Agent of an AI-native data analysis workbench.

Before the workflow starts, inspect the dataset profile and the user's natural-language goal. Return one valid JSON object only.

Rules:
- Never invent columns. Use only names in dataset_profile.columns.
- Keep all user-facing text in Simplified Chinese.
- Optimize the user's prompt so downstream Agents receive clearer metrics, dimensions, time scope, chart needs, and cautious wording requirements.
- Ask 3 to 4 concise multiple-choice intent questions that help refine the analysis prompt. Each option should include a label and append_text.
- Do not claim causal conclusions; use cautious language for sales decline and prediction tasks.

Required JSON schema:
{
  "intent_type": "general_data_analysis|sales_decline_analysis|grade_analysis|what_if_prediction|ambiguous",
  "is_task_clear": true,
  "clarity_score": 0.0,
  "detected_fields": [
    {"name": "字段名", "semantic_type": "date|metric|dimension|identifier|text|unknown", "business_meaning": "含义", "quality_note": "质量提示"}
  ],
  "data_quality_report": {
    "row_count": 0,
    "column_count": 0,
    "missing_fields": [],
    "warnings": []
  },
  "clarifying_questions": [],
  "intent_questions": [
    {"question_id": "scope", "question": "问题", "options": [{"value": "all", "label": "选项", "append_text": "拼接到最终提示词的中文要求"}]}
  ],
  "suggested_goals": [],
  "optimized_goal": "优化后的中文分析目标",
  "next_action": "ready_to_run|needs_user_choice"
}
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    data_understanding: dict[str, Any],
) -> str:
    return """请完成意图识别与提示词优化。

用户原始目标：
{user_goal}

数据画像 JSON：
{dataset_profile}

数据理解 Agent 输出 JSON：
{data_understanding}

请只返回符合 schema 的 JSON 对象。不要提及不存在的字段。intent_questions 需要是适合前端按钮选择的 3 到 4 个选择题。
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        data_understanding=json.dumps(data_understanding, ensure_ascii=False, indent=2),
    )


class PreflightAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def assess(self, user_goal: str, dataset_profile: dict[str, Any]) -> dict[str, Any]:
        data_understanding = create_data_understanding(user_goal, dataset_profile)
        fallback = create_rule_based_preflight(user_goal, dataset_profile, data_understanding)
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(user_goal, dataset_profile, data_understanding)},
                ],
                temperature=0.1,
            )
            return _normalize_result(result, fallback, dataset_profile, data_understanding, user_goal)
        except Exception:
            return fallback


def create_preflight_assessment(
    user_goal: str,
    dataset_profile: dict[str, Any],
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return PreflightAgent(llm_client=llm_client).assess(user_goal=user_goal, dataset_profile=dataset_profile)


def create_rule_based_preflight(
    user_goal: str,
    dataset_profile: dict[str, Any],
    data_understanding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data_understanding = data_understanding or create_data_understanding(user_goal, dataset_profile)
    columns = _profile_columns(dataset_profile)
    lower_goal = str(user_goal or "").lower()
    missing_fields = _missing_fields(dataset_profile)
    warnings = _quality_warnings(dataset_profile, data_understanding)
    target_columns = _string_list(data_understanding.get("target_columns"))
    date_columns = _string_list(data_understanding.get("date_columns"))
    dimension_columns = _string_list(data_understanding.get("dimension_columns"))
    numeric_columns = _string_list(data_understanding.get("numeric_columns"))
    intent_type = _detect_intent_type(user_goal, columns)

    questions: list[str] = []
    if _looks_like_decline_goal(lower_goal):
        if date_columns:
            questions.append("请确认下降口径：最近一个月环比、本季度同比，还是按全量时间趋势判断？")
        if len(dimension_columns) >= 2:
            questions.append("请确认优先拆解维度：地区、渠道、商品类别，还是全部维度都参与对比？")
    if intent_type == "what_if_prediction":
        if not target_columns:
            questions.append("请确认预测目标指标，例如销量、销售额、平均响应时长或成绩。")
        if not _has_intervention_phrase(lower_goal):
            questions.append("请补充要模拟的干预变量和变化幅度，例如预算增加 20% 或窗口数增加 2 个。")
    if len(target_columns) > 1 and intent_type != "grade_analysis":
        questions.append(f"系统识别到多个可能目标字段：{'、'.join(target_columns[:4])}。请确认本次优先分析哪一个指标？")
    if len(str(user_goal or "").strip()) < 8:
        questions.append("当前目标较短，请补充希望比较的指标、时间范围或分组维度。")

    questions = _deduplicate(questions)[:3]
    clarity_score = _clarity_score(user_goal, target_columns, numeric_columns, questions, warnings)
    is_task_clear = clarity_score >= 0.72 and len(questions) == 0

    suggested_goals = _suggested_goals(intent_type, target_columns, dimension_columns, date_columns, columns)
    intent_questions = _intent_questions(intent_type, target_columns, dimension_columns, date_columns, numeric_columns, columns)
    return {
        "intent_type": intent_type,
        "is_task_clear": is_task_clear,
        "clarity_score": clarity_score,
        "detected_fields": _detected_fields(data_understanding, dataset_profile),
        "data_quality_report": {
            "row_count": int(dataset_profile.get("row_count") or 0),
            "column_count": int(dataset_profile.get("column_count") or len(columns)),
            "missing_fields": missing_fields,
            "warnings": warnings,
        },
        "clarifying_questions": questions,
        "intent_questions": intent_questions,
        "suggested_goals": suggested_goals,
        "optimized_goal": _build_optimized_goal(user_goal, suggested_goals, intent_type, target_columns, dimension_columns, date_columns),
        "next_action": "ready_to_run" if is_task_clear else "needs_user_choice",
        "data_understanding": data_understanding,
    }


def _normalize_result(
    result: Any,
    fallback: dict[str, Any],
    dataset_profile: dict[str, Any],
    data_understanding: dict[str, Any],
    user_goal: str,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return fallback

    profile_columns = _profile_columns(dataset_profile)
    allowed_columns = set(profile_columns)
    raw_intent = _safe_intent(result.get("intent_type"), fallback["intent_type"])
    use_fallback_prompt_content = False
    if not _is_intent_compatible(raw_intent, user_goal, profile_columns):
        raw_intent = fallback["intent_type"]
        use_fallback_prompt_content = True

    intent_questions = _normalize_intent_questions(result.get("intent_questions"))
    if use_fallback_prompt_content or _has_context_conflicting_grade_text(intent_questions, user_goal, profile_columns):
        intent_questions = fallback.get("intent_questions", [])

    suggested_goals = _deduplicate(_string_list(result.get("suggested_goals")))[:4]
    if use_fallback_prompt_content or _has_context_conflicting_grade_text(suggested_goals, user_goal, profile_columns):
        suggested_goals = fallback["suggested_goals"]
    elif not suggested_goals:
        suggested_goals = fallback["suggested_goals"]

    optimized_goal = str(result.get("optimized_goal") or fallback.get("optimized_goal") or "")
    if use_fallback_prompt_content or _has_context_conflicting_grade_text(optimized_goal, user_goal, profile_columns):
        optimized_goal = str(fallback.get("optimized_goal") or "")

    normalized = {
        "intent_type": raw_intent,
        "is_task_clear": bool(result.get("is_task_clear")) if result.get("is_task_clear") is not None else fallback["is_task_clear"],
        "clarity_score": _clamp_float(result.get("clarity_score"), 0.0, 1.0, fallback["clarity_score"]),
        "detected_fields": _normalize_detected_fields(result.get("detected_fields"), allowed_columns) or fallback["detected_fields"],
        "data_quality_report": _normalize_quality_report(result.get("data_quality_report"), fallback["data_quality_report"]),
        "clarifying_questions": _deduplicate(_string_list(result.get("clarifying_questions")))[:3],
        "intent_questions": intent_questions,
        "suggested_goals": suggested_goals,
        "optimized_goal": optimized_goal,
        "next_action": str(result.get("next_action") or fallback["next_action"]),
        "data_understanding": data_understanding,
    }
    if normalized["next_action"] not in {"ready_to_run", "needs_user_choice"}:
        normalized["next_action"] = "ready_to_run" if normalized["is_task_clear"] else "needs_user_choice"
    if normalized["clarifying_questions"] and normalized["next_action"] == "ready_to_run":
        normalized["next_action"] = "needs_user_choice"
        normalized["is_task_clear"] = False
    return {key: normalized[key] for key in RESULT_KEYS}


def _detect_intent_type(user_goal: str, columns: list[str]) -> str:
    goal_text = str(user_goal or "").lower()
    column_text = " ".join(columns).lower()
    combined_text = f"{goal_text} {column_text}"
    if _has_intervention_phrase(goal_text) or any(token in goal_text for token in ("预测", "what-if", "what if", "如果", "假设", "模拟")):
        return "what_if_prediction"
    if _looks_like_decline_goal(combined_text):
        return "sales_decline_analysis"
    if _has_grade_context(user_goal, columns):
        return "grade_analysis"
    if not str(user_goal or "").strip():
        return "ambiguous"
    return "general_data_analysis"


def _is_intent_compatible(intent_type: str, user_goal: str, columns: list[str]) -> bool:
    if intent_type == "grade_analysis":
        return _has_grade_context(user_goal, columns)
    return True


def _has_grade_context(user_goal: str, columns: list[str]) -> bool:
    goal = str(user_goal or "")
    lower_goal = goal.lower()
    if any(token in goal for token in ("成绩", "分数", "班级", "及格", "优秀", "考试", "测验", "学生")):
        return True
    if any(_has_english_word(lower_goal, token) for token in ("score", "grade", "student", "exam")):
        return True

    column_names = [str(column or "") for column in columns]
    if any(any(token in column for token in ("成绩", "分数", "及格", "优秀")) for column in column_names):
        return True

    token_sets = [_english_column_tokens(column) for column in column_names]
    has_score_column = any(tokens.intersection({"score", "scores", "grade", "grades", "exam"}) for tokens in token_sets)
    has_student_or_class_column = any(tokens.intersection({"student", "students", "class", "classes"}) for tokens in token_sets)
    return bool(has_score_column and has_student_or_class_column)


def _has_context_conflicting_grade_text(value: Any, user_goal: str, columns: list[str]) -> bool:
    if _has_grade_context(user_goal, columns):
        return False
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except TypeError:
            text = str(value)
    return any(token in text for token in ("成绩", "班级", "及格", "优秀", "单科", "教学"))


def _has_english_word(text: str, word: str) -> bool:
    tokens = _english_column_tokens(text)
    return word.lower() in tokens


def _english_column_tokens(value: str) -> set[str]:
    spaced = []
    previous = ""
    for char in str(value or ""):
        if previous and previous.islower() and char.isupper():
            spaced.append(" ")
        spaced.append(char)
        previous = char
    normalized = "".join(spaced).lower()
    token = []
    tokens: set[str] = set()
    for char in normalized:
        if char.isalnum():
            token.append(char)
        else:
            if token:
                tokens.add("".join(token))
                token = []
    if token:
        tokens.add("".join(token))
    return tokens


def _looks_like_decline_goal(text: str) -> bool:
    return any(token in text for token in ("下降", "下滑", "降低", "减少", "decline", "drop")) and any(
        token in text for token in ("销量", "销售", "sales", "订单", "收入", "销售额")
    )


def _has_intervention_phrase(text: str) -> bool:
    return any(token in text for token in ("增加", "减少", "提升", "降低", "上调", "下调", "+", "%", "如果", "假设", "increase", "decrease"))


def _profile_columns(dataset_profile: dict[str, Any]) -> list[str]:
    value = dataset_profile.get("columns")
    return [str(item) for item in value] if isinstance(value, list) else []


def _missing_fields(dataset_profile: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    row_count = int(dataset_profile.get("row_count") or 0)
    missing_values = dataset_profile.get("missing_values") if isinstance(dataset_profile.get("missing_values"), dict) else {}
    for column, summary in missing_values.items():
        if not isinstance(summary, dict):
            continue
        count = int(summary.get("count") or 0)
        if count <= 0:
            continue
        ratio = summary.get("ratio")
        if ratio is None:
            ratio = round(count / row_count, 4) if row_count else 0.0
        result.append({"column": str(column), "count": count, "ratio": float(ratio)})
    return result


def _quality_warnings(dataset_profile: dict[str, Any], data_understanding: dict[str, Any]) -> list[str]:
    warnings = []
    row_count = int(dataset_profile.get("row_count") or 0)
    if row_count and row_count < 10:
        warnings.append("样本量较小，结论应作为探索性发现。")
    if not data_understanding.get("numeric_columns"):
        warnings.append("未识别到数值字段，统计分析和图表生成能力会受限。")
    for item in _missing_fields(dataset_profile):
        ratio = float(item.get("ratio") or 0.0)
        if ratio >= 0.2:
            warnings.append(f"字段“{item['column']}”缺失率较高，约 {ratio:.0%}。")
        elif ratio > 0:
            warnings.append(f"字段“{item['column']}”存在 {item['count']} 个缺失值。")
    for issue in data_understanding.get("quality_issues") or []:
        text = _format_issue(issue)
        if text:
            warnings.append(text)
    return _deduplicate(warnings)[:8]


def _detected_fields(data_understanding: dict[str, Any], dataset_profile: dict[str, Any]) -> list[dict[str, str]]:
    missing_by_column = {item["column"]: item for item in _missing_fields(dataset_profile)}
    rows = []
    for item in data_understanding.get("columns") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if not name:
            continue
        quality_note = ""
        if name in missing_by_column:
            quality_note = f"存在 {missing_by_column[name]['count']} 个缺失值"
        rows.append(
            {
                "name": name,
                "semantic_type": str(item.get("semantic_type") or "unknown"),
                "business_meaning": str(item.get("business_meaning") or ""),
                "quality_note": quality_note,
            }
        )
    return rows


def _suggested_goals(
    intent_type: str,
    target_columns: list[str],
    dimension_columns: list[str],
    date_columns: list[str],
    columns: list[str],
) -> list[str]:
    target = target_columns[0] if target_columns else _first_numeric_like(columns) or "核心指标"
    dimension = dimension_columns[0] if dimension_columns else "主要维度"
    date = date_columns[0] if date_columns else "时间字段"
    if intent_type == "sales_decline_analysis":
        return [
            f"按{date}分析{target}趋势，并按{dimension}拆解下降来源。",
            f"找出{target}下降最明显的{dimension}组合，并生成图表和业务建议。",
        ]
    if intent_type == "grade_analysis":
        return [
            "把这批 Excel 成绩按班级统计平均分、及格率和优秀率并生成图表。",
            "识别成绩分布差异和需要重点关注的班级，并输出建议。",
        ]
    if intent_type == "what_if_prediction":
        return [
            f"如果关键投入变量发生变化，预测{target}可能如何变化，并按{dimension}排序。",
            f"模拟情景变化对{target}的影响，并输出谨慎解释和限制说明。",
        ]
    return [
        f"围绕{target}做总体统计、按{dimension}对比并生成图表。",
        "先进行数据质量检查，再输出关键发现、图表和业务建议。",
    ]


def _intent_questions(
    intent_type: str,
    target_columns: list[str],
    dimension_columns: list[str],
    date_columns: list[str],
    numeric_columns: list[str],
    columns: list[str],
) -> list[dict[str, Any]]:
    target = target_columns[0] if target_columns else _first_numeric_like(columns) or "核心指标"
    date = date_columns[0] if date_columns else "时间字段"
    dimensions = dimension_columns[:3] or ["主要维度"]
    numeric = numeric_columns[0] if numeric_columns else target

    if intent_type == "sales_decline_analysis":
        return [
            _question(
                "decline_scope",
                "本次销量下降应优先按哪种口径判断？",
                [
                    ("trend", "按全量月份趋势", f"下降判断口径采用{date}的全量趋势，并重点识别连续下降或低谷阶段。"),
                    ("latest_vs_first", "最近月份对比首月", f"重点比较最近可用月份与首月的{target}差异。"),
                    ("latest_vs_previous", "最近月份环比", f"重点比较最近两期{target}的环比变化。"),
                    ("all", "三种口径都看", f"同时查看全量趋势、首末对比和最近环比，避免单一口径误判。"),
                ],
            ),
            _question(
                "breakdown_dimension",
                "优先从哪个维度拆解可能原因？",
                [
                    ("all", "地区、渠道、商品类别都参与", f"按{ '、'.join(dimensions) }等可用维度拆解，并比较各分组的下降幅度。"),
                    ("first", dimensions[0], f"优先按{dimensions[0]}拆解{target}变化。"),
                    ("second", dimensions[1] if len(dimensions) > 1 else dimensions[0], f"优先按{dimensions[1] if len(dimensions) > 1 else dimensions[0]}拆解{target}变化。"),
                    ("third", dimensions[2] if len(dimensions) > 2 else dimensions[-1], f"优先按{dimensions[2] if len(dimensions) > 2 else dimensions[-1]}拆解{target}变化。"),
                ],
            ),
            _question(
                "risk_factors",
                "是否需要结合库存、折扣等辅助字段解释？",
                [
                    ("inventory_discount", "结合库存和折扣", "如存在库存、折扣率等辅助字段，请分析它们与销量变化的相关信号。"),
                    ("trend_only", "只看销量趋势", f"优先围绕{target}本身的趋势和分组差异输出结论。"),
                    ("all_numeric", "所有数值字段都筛查", f"对{numeric}等数值字段做相关性和分组对比筛查。"),
                    ("recommendation", "重点输出行动建议", "结论后请给出可执行的库存、渠道、价格或活动排查建议。"),
                ],
            ),
            _question(
                "language_safety",
                "结论表述应采用哪种稳健程度？",
                [
                    ("cautious", "谨慎相关性表述", "所有原因表述使用“可能、相关、显示出信号”，不得写成已证明因果。"),
                    ("balanced", "结论和限制并重", "同时输出关键发现、证据来源和限制说明。"),
                    ("action", "更强调业务动作", "建议部分请突出短期排查和后续验证动作。"),
                    ("ppt", "便于汇报", "请按适合汇报的结构输出结论和 PPT 大纲。"),
                ],
            ),
        ]

    if intent_type == "what_if_prediction":
        return [
            _question(
                "prediction_target",
                "预测结果优先关注哪个指标？",
                [
                    ("target", target, f"预测目标指标优先使用{target}。"),
                    ("numeric", numeric, f"如果{target}不可用，则使用{numeric}作为目标指标。"),
                    ("auto", "让 AI 自动匹配", "请根据字段语义自动选择最匹配的数值型目标指标。"),
                    ("aggregate", "只看总体变化", "如果对象维度不足，请输出总体预测变化。"),
                ],
            ),
            _question(
                "prediction_dimension",
                "预测结果按哪个对象排序？",
                [
                    ("first", dimensions[0], f"按{dimensions[0]}汇总并排序预测影响。"),
                    ("all", "自动选择最合适维度", "请优先选择有业务含义且分组数量适中的对象维度。"),
                    ("overall", "只看总体", "如果分组结果不稳定，请只输出总体变化和限制说明。"),
                    ("top", "只展示影响最大的对象", "结果中突出预测变化最大的 Top 对象。"),
                ],
            ),
            _question(
                "prediction_language",
                "预测解释需要强调什么？",
                [
                    ("cautious", "强调不代表确定因果", "预测解释必须使用“预计、可能、估计”，并说明不是确定因果。"),
                    ("model", "说明模型依据", "请解释模型或规则模拟的依据、特征字段和限制。"),
                    ("action", "输出行动建议", "请给出适合业务复盘和验证的后续动作。"),
                    ("charts", "优先生成对比图", "请优先生成基准值与预测值对比图、变化排序图。"),
                ],
            ),
        ]

    if intent_type == "grade_analysis":
        return [
            _question(
                "grade_metrics",
                "成绩分析优先展示哪些指标？",
                [
                    ("standard", "平均分、及格率、优秀率", "按班级统计平均分、及格率、优秀率，并生成对比图。"),
                    ("distribution", "分布和异常", "同时查看成绩分布、低分样本和缺失成绩记录。"),
                    ("subjects", "单科差异", "如存在单科成绩，请比较各班单科差异。"),
                    ("attendance", "结合出勤率", "如存在出勤率，请分析其与成绩表现的关系。"),
                ],
            ),
            _question(
                "grade_focus",
                "报告更关注哪类对象？",
                [
                    ("class", "班级整体差异", "结论优先围绕班级整体差异展开。"),
                    ("risk", "风险班级", "重点识别平均分或及格率较低的班级。"),
                    ("excellent", "优秀表现", "同时识别优秀率较高的班级和可复用经验。"),
                    ("quality", "数据质量", "请提示缺失、异常或非数值成绩对结论的影响。"),
                ],
            ),
            _question(
                "grade_output",
                "输出形式希望更偏向什么？",
                [
                    ("charts", "图表对比", "请生成班级平均分、及格率等图表。"),
                    ("recommendations", "教学建议", "请给出面向教学支持的建议动作。"),
                    ("ppt", "汇报大纲", "请生成适合汇报的 PPT 大纲。"),
                    ("table", "统计表优先", "请在结论中说明关键统计表字段和排名。"),
                ],
            ),
        ]

    return [
        _question(
            "target_metric",
            "本次分析优先关注哪个指标？",
            [
                ("target", target, f"优先围绕{target}进行统计、对比和图表生成。"),
                ("numeric", numeric, f"同时关注{numeric}等主要数值字段。"),
                ("quality", "先检查数据质量", "请先检查缺失值、异常值和字段可用性，再输出结论。"),
                ("auto", "让 AI 自动选择", "请根据数据画像自动选择最适合本目标的指标。"),
            ],
        ),
        _question(
            "dimension_scope",
            "希望按哪些维度拆解？",
            [
                ("first", dimensions[0], f"优先按{dimensions[0]}进行分组对比。"),
                ("all", "全部可用维度", f"按{ '、'.join(dimensions) }等可用维度进行对比。"),
                ("none", "不分组，只看总体", "先输出总体统计，再判断是否需要分组。"),
                ("auto", "让 AI 自动选择", "请选择分组数量适中、业务含义清晰的维度。"),
            ],
        ),
        _question(
            "output_style",
            "输出结果更偏向哪种形式？",
            [
                ("charts", "图表优先", "请优先生成趋势图、对比图或分布图。"),
                ("findings", "关键发现优先", "请突出最重要的 3 到 5 条发现。"),
                ("actions", "建议动作优先", "请输出可执行的业务建议和后续验证动作。"),
                ("ppt", "汇报材料优先", "请生成适合汇报的 PPT 大纲。"),
            ],
        ),
    ]


def _question(question_id: str, question: str, options: list[tuple[str, str, str]]) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "question": question,
        "options": [
            {"value": value, "label": label, "append_text": append_text}
            for value, label, append_text in options
        ],
    }


def _build_optimized_goal(
    user_goal: str,
    suggested_goals: list[str],
    intent_type: str,
    target_columns: list[str],
    dimension_columns: list[str],
    date_columns: list[str],
) -> str:
    base = str(user_goal or "").strip() or (suggested_goals[0] if suggested_goals else "请分析这份数据并生成图表。")
    pieces = [base]
    target = target_columns[0] if target_columns else "核心指标"
    if target_columns:
        pieces.append(f"重点指标：{target}。")
    if dimension_columns:
        pieces.append(f"分组维度优先使用：{'、'.join(dimension_columns[:4])}。")
    if date_columns:
        pieces.append(f"时间趋势优先使用：{'、'.join(date_columns[:2])}。")
    if intent_type == "sales_decline_analysis":
        pieces.append("请使用谨慎表述，只输出可能原因、相关信号和待验证假设，不要写成确定因果。")
    elif intent_type == "what_if_prediction":
        pieces.append("预测结果请使用预计、可能、估计等表述，并说明不是确定因果。")
    pieces.append("请生成图表、关键发现、建议动作和限制说明。")
    return " ".join(piece for piece in pieces if piece)


def _normalize_intent_questions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    questions: list[dict[str, Any]] = []
    for index, item in enumerate(value[:4], start=1):
        if not isinstance(item, dict):
            continue
        options = []
        for option_index, option in enumerate(item.get("options") if isinstance(item.get("options"), list) else [], start=1):
            if not isinstance(option, dict):
                continue
            label = str(option.get("label") or option.get("text") or option.get("value") or "").strip()
            append_text = str(option.get("append_text") or option.get("prompt_append") or label).strip()
            if not label:
                continue
            options.append(
                {
                    "value": str(option.get("value") or f"option_{option_index}"),
                    "label": label,
                    "append_text": append_text,
                }
            )
        if not options:
            continue
        questions.append(
            {
                "question_id": str(item.get("question_id") or item.get("id") or f"question_{index}"),
                "question": str(item.get("question") or item.get("title") or f"请选择第 {index} 个优化项"),
                "options": options[:4],
            }
        )
    return questions


def _first_numeric_like(columns: list[str]) -> str | None:
    for column in columns:
        if any(token in column.lower() for token in ("score", "sales", "amount", "rate", "price", "count")):
            return column
        if any(token in column for token in ("成绩", "销量", "销售额", "金额", "价格", "数量", "率", "时长", "时间")):
            return column
    return columns[0] if columns else None


def _normalize_detected_fields(value: Any, allowed_columns: set[str]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result = []
    seen = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name not in allowed_columns or name in seen:
            continue
        seen.add(name)
        result.append(
            {
                "name": name,
                "semantic_type": str(item.get("semantic_type") or "unknown"),
                "business_meaning": str(item.get("business_meaning") or ""),
                "quality_note": str(item.get("quality_note") or ""),
            }
        )
    return result


def _normalize_quality_report(value: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return fallback
    return {
        "row_count": int(value.get("row_count") or fallback.get("row_count") or 0),
        "column_count": int(value.get("column_count") or fallback.get("column_count") or 0),
        "missing_fields": value.get("missing_fields") if isinstance(value.get("missing_fields"), list) else fallback.get("missing_fields", []),
        "warnings": _string_list(value.get("warnings")) or fallback.get("warnings", []),
    }


def _safe_intent(value: Any, fallback: str) -> str:
    text = str(value or fallback)
    allowed = {"general_data_analysis", "sales_decline_analysis", "grade_analysis", "what_if_prediction", "ambiguous"}
    return text if text in allowed else fallback


def _clarity_score(user_goal: str, targets: list[str], numeric_columns: list[str], questions: list[str], warnings: list[str]) -> float:
    score = 0.55
    if len(str(user_goal or "").strip()) >= 8:
        score += 0.15
    if targets:
        score += 0.15
    if numeric_columns:
        score += 0.1
    score -= min(0.25, len(questions) * 0.1)
    score -= min(0.15, len(warnings) * 0.02)
    return round(max(0.0, min(1.0, score)), 2)


def _format_issue(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        column = value.get("column") or value.get("field") or value.get("name")
        issue = value.get("issue") or value.get("description") or value.get("message")
        if column and issue:
            return f"字段“{column}”：{issue}"
        if issue:
            return str(issue)
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _deduplicate(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _clamp_float(value: Any, low: float, high: float, fallback: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = fallback
    return round(max(low, min(high, parsed)), 2)

