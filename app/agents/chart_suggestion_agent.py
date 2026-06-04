import json
import re
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the chart refinement suggestion Agent of an AI-native analytics workbench.

Return only one valid JSON object.
All suggestions must be in Simplified Chinese and must be directly actionable for one specific chart.
Do not return generic repeated options. Each suggestion should mention concrete fields, chart type, filtering/sorting, annotation, or reporting goal.

Required schema:
{
  "suggestions": ["string"]
}
"""

GENERIC_SUGGESTIONS = {
    "改为折线图表示。",
    "改为柱状图对比，并按数值从高到低排序。",
    "只保留变化最明显的前 5 个对象。",
    "优化标题、图例和坐标轴，让图表更适合汇报。",
    "改为基准值与预测值对比柱状图。",
    "只展示预测变化最大的前 5 个对象。",
    "改为折线图展示预测变化趋势。",
}

FIELD_LABELS = {
    "saleprice": "房价（SalePrice）",
    "overallqual": "整体质量（OverallQual）",
    "grlivarea": "地上居住面积（GrLivArea）",
    "totalbsmtsf": "地下室总面积（TotalBsmtSF）",
    "1stflrsf": "一层面积（1stFlrSF）",
    "garagecars": "车库容量（GarageCars）",
    "garagearea": "车库面积（GarageArea）",
    "neighborhood": "社区/区域（Neighborhood）",
    "mszoning": "住宅分区（MSZoning）",
    "yearbuilt": "建造年份（YearBuilt）",
    "yearremodadd": "翻修年份（YearRemodAdd）",
    "totrmsabvgrd": "地上房间数（TotRmsAbvGrd）",
    "fullbath": "全卫数量（FullBath）",
    "lotarea": "地块面积（LotArea）",
    "sales": "销量",
    "revenue": "销售额",
    "score": "成绩",
}

DISCRETE_FIELDS = {"overallqual", "overallcond", "garagecars", "fullbath", "bedroomabvgr", "totrmsabvgrd"}


def build_user_prompt(
    *,
    user_goal: str,
    chart_path: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    workflow_type: str,
    visual_parse_result: dict[str, Any] | None,
) -> str:
    context = {
        "user_goal": user_goal,
        "workflow_type": workflow_type,
        "chart_path": chart_path,
        "chart_filename": str(chart_path).replace("\\", "/").rsplit("/", 1)[-1],
        "inferred_chart_type": _infer_chart_type(chart_path),
        "inferred_chart_field": _friendly_field_name(_extract_chart_field(chart_path)),
        "dataset_columns": dataset_profile.get("columns", [])[:80],
        "numeric_columns": list((dataset_profile.get("numeric_summary") or {}).keys())[:40],
        "text_columns": list((dataset_profile.get("text_summary") or {}).keys())[:40],
        "row_count": dataset_profile.get("row_count"),
        "target_metric": _choose_target_metric(dataset_profile, result_payload),
        "result_preview": _compact_payload(result_payload),
        "visual_parse_summary": _compact_payload(visual_parse_result or {}),
    }
    return """Generate 3 to 4 quick refinement suggestions for the target chart.

The suggestions are shown as clickable buttons under this chart. They should help the user improve this exact chart for the current analysis task.

Context JSON:
{context}

Return only the required JSON object.
""".format(context=json.dumps(context, ensure_ascii=False, indent=2))


class ChartSuggestionAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def create_suggestions(
        self,
        *,
        user_goal: str,
        chart_path: str,
        dataset_profile: dict[str, Any],
        result_payload: dict[str, Any],
        workflow_type: str,
        visual_parse_result: dict[str, Any] | None = None,
    ) -> list[str]:
        fallback = create_rule_based_chart_refine_suggestions(
            user_goal=user_goal,
            chart_path=chart_path,
            dataset_profile=dataset_profile,
            result_payload=result_payload,
            workflow_type=workflow_type,
            visual_parse_result=visual_parse_result,
        )
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            user_goal=user_goal,
                            chart_path=chart_path,
                            dataset_profile=dataset_profile,
                            result_payload=result_payload,
                            workflow_type=workflow_type,
                            visual_parse_result=visual_parse_result,
                        ),
                    },
                ],
                temperature=0.2,
            )
            return _normalize_suggestions(result, fallback)
        except Exception:
            return fallback


def create_chart_refine_suggestions(
    *,
    user_goal: str,
    chart_path: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    workflow_type: str,
    visual_parse_result: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
) -> list[str]:
    return ChartSuggestionAgent(llm_client=llm_client).create_suggestions(
        user_goal=user_goal,
        chart_path=chart_path,
        dataset_profile=dataset_profile,
        result_payload=result_payload,
        workflow_type=workflow_type,
        visual_parse_result=visual_parse_result,
    )


def create_rule_based_chart_refine_suggestions(
    *,
    user_goal: str,
    chart_path: str,
    dataset_profile: dict[str, Any],
    result_payload: dict[str, Any],
    workflow_type: str,
    visual_parse_result: dict[str, Any] | None = None,
) -> list[str]:
    chart_type = _infer_chart_type(chart_path)
    field = _extract_chart_field(chart_path)
    field_label = _friendly_field_name(field)
    target_metric = _choose_target_metric(dataset_profile, result_payload)
    target_label = _friendly_field_name(target_metric)
    group_field = _choose_group_field(dataset_profile, exclude={_normalize_key(field), _normalize_key(target_metric)})
    group_label = _friendly_field_name(group_field)

    if workflow_type == "what_if_prediction":
        return _clean_suggestions(
            [
                f"改为{target_label}的基准值与预测值并列柱状图，并按预测变化绝对值从高到低排序。",
                f"只展示{target_label}变化最大的前 5 个对象，并在柱尾标注变化量和变化率。",
                f"把预测提升和预测下降分成两种颜色表达，并在标题中写清当前情景假设。",
                f"增加模型限制说明到图表副标题，突出预测结果是估计值而不是确定因果。",
            ]
        )

    if chart_type == "heatmap":
        return _clean_suggestions(
            [
                f"只展示与{target_label}相关性最高的前 10 个字段，并按相关系数绝对值排序。",
                f"将热力图色阶固定为 -1 到 1，并放大字段标签，便于比较强弱关系。",
                "隐藏 Id 等标识类字段，只保留可解释的面积、质量、年份和配套相关变量。",
                f"改为{target_label}相关系数横向柱状图，突出正相关和负相关最明显的变量。",
            ]
        )

    if chart_type == "scatter":
        suggestions = [
            f"保留{field_label}与{target_label}散点关系，增加线性趋势线、相关系数和样本量标注。",
            f"剔除{field_label}或{target_label}的极端离群点后重绘，并在标题中说明过滤口径。",
        ]
        if _normalize_key(field) in DISCRETE_FIELDS:
            suggestions.append(f"改为箱线图，比较不同{field_label}等级下{target_label}的中位数、分位数和异常点。")
        else:
            suggestions.append(f"改为分箱柱状图，将{field_label}按区间分组后展示{target_label}均值和中位数。")
        if group_field:
            suggestions.append(f"按{group_label}分组着色，只保留样本量最高的前 5 组，减少视觉干扰。")
        else:
            suggestions.append(f"突出{field_label}高值区间中的高{target_label}样本，并优化坐标轴金额格式。")
        return _clean_suggestions(suggestions)

    if chart_type in {"bar", "barh"}:
        dimension = field_label if field else group_label or "当前分组"
        return _clean_suggestions(
            [
                f"按{target_label}均值从高到低重排{dimension}，并只保留前 10 组。",
                f"增加{target_label}中位数或样本量标签，避免只看均值造成误判。",
                f"改为横向柱状图展示{dimension}差异，长标签保持完整可读。",
                f"突出最高和最低的{dimension}，并在标题中说明对比口径。",
            ]
        )

    if chart_type == "line":
        return _clean_suggestions(
            [
                f"保留时间顺序并增加{target_label}趋势线，同时标注最高点和最低点。",
                f"改为按{group_label or '关键分组'}拆分的多折线图，只保留样本量最高的前 5 组。",
                f"增加环比变化柱或变化率标签，突出{target_label}波动最大的区间。",
                "优化标题和横轴刻度密度，使趋势图更适合汇报展示。",
            ]
        )

    if visual_parse_result:
        return _clean_suggestions(
            [
                "结合图片抽取字段重新命名标题，标注视觉解析可能存在误差。",
                f"只保留与{target_label}最相关的字段和分组，减少截图识别噪声。",
                "按图片中的业务对象排序，并在图表中标注最高值、最低值和异常值。",
                "将坐标轴单位和字段中文名补充完整，便于与原图核对。",
            ]
        )

    return _clean_suggestions(
        [
            f"围绕{target_label}重绘图表，明确维度、指标和排序口径。",
            f"只保留与本轮目标“{_short_goal(user_goal)}”最相关的前 8 个分组。",
            "增加样本量、均值或中位数标签，让图表结论更可核对。",
            "优化标题、副标题和坐标轴单位，使图表可以直接放入报告。",
        ]
    )


def _normalize_suggestions(result: Any, fallback: list[str]) -> list[str]:
    raw_items: Any = []
    if isinstance(result, dict):
        raw_items = result.get("suggestions")
    elif isinstance(result, list):
        raw_items = result
    suggestions = []
    if isinstance(raw_items, list):
        for item in raw_items:
            text = _finish_sentence(str(item or "").strip())
            if not text or text in GENERIC_SUGGESTIONS or len(text) < 12:
                continue
            suggestions.append(text)
    return _clean_suggestions([*suggestions, *fallback])


def _clean_suggestions(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _finish_sentence(str(value or "").strip())
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= 4:
            break
    return result[:4]


def _finish_sentence(value: str) -> str:
    if not value:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    if value[-1] not in "。！？.!?":
        value += "。"
    return value


def _infer_chart_type(chart_path: str) -> str:
    lower = str(chart_path or "").lower()
    if "heatmap" in lower or "corr" in lower:
        return "heatmap"
    if "scatter" in lower:
        return "scatter"
    if "line" in lower or "trend" in lower or "monthly" in lower:
        return "line"
    if "barh" in lower:
        return "barh"
    if "bar" in lower or "top" in lower or "rank" in lower:
        return "bar"
    return "chart"


def _extract_chart_field(chart_path: str) -> str:
    name = str(chart_path or "").replace("\\", "/").rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    match = re.search(r"scatter[_-]([^._-]+)", stem, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    for prefix in ("bar_", "bar-", "line_", "line-", "box_", "box-"):
        if stem.lower().startswith(prefix):
            return stem[len(prefix) :]
    tokens = re.split(r"[_\-]", stem)
    for token in reversed(tokens):
        if token and token.lower() not in {"chart", "plot", "heatmap", "correlation", "refined"}:
            return token
    return ""


def _choose_target_metric(dataset_profile: dict[str, Any], result_payload: dict[str, Any]) -> str:
    for key in ("target_metric", "target_column", "metric"):
        value = result_payload.get(key) if isinstance(result_payload, dict) else None
        if isinstance(value, str) and value:
            return value
    columns = [str(item) for item in dataset_profile.get("columns", []) if item]
    for preferred in ("SalePrice", "房价", "价格", "销售额", "销量", "成绩", "平均响应时长_秒", "平均排队时间_分钟"):
        for column in columns:
            if column == preferred or preferred.lower() in column.lower():
                return column
    numeric_columns = list((dataset_profile.get("numeric_summary") or {}).keys())
    return str(numeric_columns[-1]) if numeric_columns else "目标指标"


def _choose_group_field(dataset_profile: dict[str, Any], exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    columns = [str(item) for item in dataset_profile.get("columns", []) if item]
    for preferred in ("Neighborhood", "MSZoning", "区域", "地区", "渠道", "商品", "品类", "班级", "对象"):
        for column in columns:
            if _normalize_key(column) in exclude:
                continue
            if column == preferred or preferred.lower() in column.lower():
                return column
    text_columns = list((dataset_profile.get("text_summary") or {}).keys())
    for column in text_columns:
        if _normalize_key(column) not in exclude:
            return str(column)
    return ""


def _friendly_field_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "目标指标"
    key = _normalize_key(text)
    return FIELD_LABELS.get(key, text)


def _normalize_key(value: Any) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(value or "")).lower()


def _compact_payload(payload: Any, max_items: int = 8) -> Any:
    if isinstance(payload, dict):
        compact: dict[str, Any] = {}
        for index, (key, value) in enumerate(payload.items()):
            if index >= max_items:
                break
            compact[str(key)] = _compact_payload(value, max_items=max_items)
        return compact
    if isinstance(payload, list):
        return [_compact_payload(item, max_items=max_items) for item in payload[:max_items]]
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        text = payload
        if isinstance(payload, str) and len(payload) > 240:
            text = payload[:240] + "..."
        return text
    return str(payload)


def _short_goal(user_goal: str) -> str:
    text = str(user_goal or "").strip()
    return text[:24] + ("..." if len(text) > 24 else "")
