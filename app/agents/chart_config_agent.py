import json
import re
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the natural-language chart iteration Agent of an AI-native analytics workbench.

Given the current analysis result and a user's chart instruction, return an ECharts option JSON.
Return only one valid JSON object. Do not include JavaScript functions in the option.
All visible chart text must be Simplified Chinese when possible.

Required schema:
{
  "chart_id": "string",
  "title": "string",
  "description": "string",
  "echarts_option": {},
  "data_preview": [],
  "applied_filters": [],
  "warnings": []
}
"""


def build_user_prompt(
    instruction: str,
    result_payload: dict[str, Any],
    dataset_profile: dict[str, Any],
    current_config: dict[str, Any] | None,
) -> str:
    return """Create or modify an ECharts config from this analysis result.

User chart instruction:
{instruction}

Dataset profile JSON:
{dataset_profile}

Analysis or prediction result JSON:
{result_payload}

Current chart config JSON:
{current_config}

Return only the required JSON object.
""".format(
        instruction=instruction,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        result_payload=json.dumps(result_payload, ensure_ascii=False, indent=2),
        current_config=json.dumps(current_config or {}, ensure_ascii=False, indent=2),
    )


class ChartConfigAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def create_config(
        self,
        instruction: str,
        result_payload: dict[str, Any],
        dataset_profile: dict[str, Any],
        current_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = create_rule_based_chart_config(instruction, result_payload, dataset_profile, current_config)
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(instruction, result_payload, dataset_profile, current_config)},
                ],
                temperature=0.1,
            )
            return _normalize_result(result, fallback)
        except Exception:
            return fallback


def create_chart_config(
    instruction: str,
    result_payload: dict[str, Any],
    dataset_profile: dict[str, Any],
    current_config: dict[str, Any] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return ChartConfigAgent(llm_client=llm_client).create_config(
        instruction=instruction,
        result_payload=result_payload,
        dataset_profile=dataset_profile,
        current_config=current_config,
    )


def create_rule_based_chart_config(
    instruction: str,
    result_payload: dict[str, Any],
    dataset_profile: dict[str, Any],
    current_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    rows = _extract_rows(result_payload)
    warnings: list[str] = []
    if not rows:
        rows = _rows_from_profile(dataset_profile)
        warnings.append("未在分析结果中找到表格型明细，已使用数据画像样例行生成预览配置。")
    rows, applied_filters = _apply_instruction_filters(rows, instruction)
    dimension = _choose_dimension(rows, instruction)
    metrics = _choose_metrics(rows, instruction)
    if not dimension or not metrics:
        option = _empty_option("暂无可绘制数据", "当前结果缺少可识别的维度或数值指标。")
        warnings.append("缺少可识别的维度或数值指标。")
        return _result("chart_empty", "暂无可绘制数据", "未生成可视化配置。", option, rows, applied_filters, warnings)

    chart_type = _chart_type(instruction, current_config)
    title = _chart_title(instruction, chart_type, metrics, dimension)
    option = _build_option(chart_type, title, rows, dimension, metrics)
    return _result(
        chart_id=f"iterative_{chart_type}",
        title=title,
        description=f"根据自然语言指令生成的 {chart_type} 图，维度为“{dimension}”，指标为“{'、'.join(metrics)}”。",
        option=option,
        rows=rows,
        applied_filters=applied_filters,
        warnings=warnings,
    )


def _normalize_result(result: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return fallback
    option = result.get("echarts_option") if isinstance(result.get("echarts_option"), dict) else fallback["echarts_option"]
    return {
        "chart_id": str(result.get("chart_id") or fallback["chart_id"]),
        "title": str(result.get("title") or fallback["title"]),
        "description": str(result.get("description") or fallback["description"]),
        "echarts_option": option,
        "data_preview": result.get("data_preview") if isinstance(result.get("data_preview"), list) else fallback["data_preview"],
        "applied_filters": _string_list(result.get("applied_filters")) or fallback["applied_filters"],
        "warnings": _string_list(result.get("warnings")) or fallback["warnings"],
    }


def _result(
    chart_id: str,
    title: str,
    description: str,
    option: dict[str, Any],
    rows: list[dict[str, Any]],
    applied_filters: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    return {
        "chart_id": chart_id,
        "title": title,
        "description": description,
        "echarts_option": option,
        "data_preview": rows[:20],
        "applied_filters": applied_filters,
        "warnings": warnings,
    }


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return _normalize_rows(payload)
    if not isinstance(payload, dict):
        return []
    for key in (
        "summary",
        "group_summary",
        "top_impacted_entities",
        "rows",
        "data",
        "records",
        "table",
        "tables",
    ):
        value = payload.get(key)
        rows = _normalize_rows(value)
        if rows:
            return rows
    for value in payload.values():
        rows = _extract_rows(value)
        if rows:
            return rows
    return []


def _normalize_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        for key in ("rows", "data", "records", "summary"):
            rows = _normalize_rows(value.get(key))
            if rows:
                return rows
        return []
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if isinstance(item, dict):
            rows.append({str(key): _json_value(val) for key, val in item.items()})
    return rows


def _rows_from_profile(dataset_profile: dict[str, Any]) -> list[dict[str, Any]]:
    rows = dataset_profile.get("sample_rows")
    if isinstance(rows, list):
        return [item for item in rows if isinstance(item, dict)]
    return []


def _apply_instruction_filters(rows: list[dict[str, Any]], instruction: str) -> tuple[list[dict[str, Any]], list[str]]:
    text = str(instruction or "")
    filters = _extract_filter_terms(text)
    if not filters:
        return rows, []
    filtered = []
    for row in rows:
        joined = " ".join(str(value) for value in row.values())
        if any(term and term in joined for term in filters):
            filtered.append(row)
    return (filtered or rows), ([f"仅展示：{'、'.join(filters)}"] if filtered else [])


def _extract_filter_terms(text: str) -> list[str]:
    match = re.search(r"只看(.+)", text)
    if not match:
        match = re.search(r"筛选(.+)", text)
    if not match:
        return []
    raw = match.group(1)
    raw = re.split(r"[。；;,.，]", raw)[0]
    pieces = re.split(r"和|与|、|/|，|,|\s+", raw)
    return [piece.strip() for piece in pieces if len(piece.strip()) >= 1][:6]


def _choose_dimension(rows: list[dict[str, Any]], instruction: str) -> str:
    if not rows:
        return ""
    columns = list(rows[0].keys())
    preferred_tokens = ["班级", "class", "类别", "品类", "地区", "区域", "渠道", "商品", "对象", "entity", "name", "名称", "月份", "日期"]
    text = str(instruction or "").lower()
    for column in columns:
        if str(column) in instruction or str(column).lower() in text:
            if not _is_numeric(rows[0].get(column)):
                return column
    for token in preferred_tokens:
        for column in columns:
            if token in str(column).lower() or token in str(column):
                return column
    for column in columns:
        if not _is_numeric(rows[0].get(column)):
            return column
    return columns[0]


def _choose_metrics(rows: list[dict[str, Any]], instruction: str) -> list[str]:
    if not rows:
        return []
    columns = list(rows[0].keys())
    numeric_columns = [column for column in columns if any(_is_numeric(row.get(column)) for row in rows)]
    text = str(instruction or "").lower()
    requested = []
    metric_aliases = {
        "及格率": ["及格率", "pass_rate"],
        "优秀率": ["优秀率", "excellent_rate"],
        "平均": ["平均", "average", "mean"],
        "销量": ["销量", "sales"],
        "成绩": ["成绩", "score"],
        "变化": ["变化", "change"],
    }
    for _label, aliases in metric_aliases.items():
        if any(alias.lower() in text or alias in instruction for alias in aliases):
            for column in numeric_columns:
                lowered = str(column).lower()
                if any(alias.lower() in lowered or alias in str(column) for alias in aliases):
                    requested.append(column)
    for column in numeric_columns:
        if str(column) in instruction or str(column).lower() in text:
            requested.append(column)
    if requested:
        return _deduplicate(requested)[:4]
    return numeric_columns[:3]


def _chart_type(instruction: str, current_config: dict[str, Any] | None) -> str:
    text = str(instruction or "").lower()
    if any(token in text for token in ("折线", "line")):
        return "line"
    if any(token in text for token in ("饼图", "pie")):
        return "pie"
    if any(token in text for token in ("散点", "scatter")):
        return "scatter"
    if any(token in text for token in ("仪表盘", "dashboard")):
        return "dashboard"
    if current_config and isinstance(current_config.get("echarts_option"), dict):
        return _current_chart_type(current_config.get("echarts_option")) or "bar"
    return "bar"


def _current_chart_type(option: Any) -> str:
    if not isinstance(option, dict):
        return ""
    series = option.get("series")
    if isinstance(series, list) and series and isinstance(series[0], dict):
        return str(series[0].get("type") or "")
    return ""


def _chart_title(instruction: str, chart_type: str, metrics: list[str], dimension: str) -> str:
    if "仪表盘" in instruction or chart_type == "dashboard":
        return "AI 生成分析仪表盘"
    if "折线" in instruction or chart_type == "line":
        return f"{dimension}维度下的{'、'.join(metrics)}趋势"
    return f"按{dimension}对比{'、'.join(metrics)}"


def _build_option(chart_type: str, title: str, rows: list[dict[str, Any]], dimension: str, metrics: list[str]) -> dict[str, Any]:
    categories = [str(row.get(dimension, "")) for row in rows]
    if chart_type == "pie":
        metric = metrics[0]
        return {
            "title": {"text": title, "left": "center"},
            "tooltip": {"trigger": "item"},
            "legend": {"bottom": 0},
            "series": [
                {
                    "name": metric,
                    "type": "pie",
                    "radius": "58%",
                    "data": [{"name": str(row.get(dimension, "")), "value": _number(row.get(metric))} for row in rows],
                }
            ],
        }
    if chart_type == "scatter" and len(metrics) >= 2:
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "item"},
            "xAxis": {"name": metrics[0], "type": "value"},
            "yAxis": {"name": metrics[1], "type": "value"},
            "series": [
                {
                    "name": f"{metrics[0]} / {metrics[1]}",
                    "type": "scatter",
                    "data": [[_number(row.get(metrics[0])), _number(row.get(metrics[1])), str(row.get(dimension, ""))] for row in rows],
                }
            ],
        }
    series_type = "line" if chart_type == "line" else "bar"
    if chart_type == "dashboard":
        series = []
        for index, metric in enumerate(metrics[:3]):
            series.append({"name": metric, "type": "bar" if index == 0 else "line", "data": [_number(row.get(metric)) for row in rows], "smooth": index > 0})
        return {
            "title": {"text": title},
            "tooltip": {"trigger": "axis"},
            "legend": {"top": 28},
            "grid": {"top": 80, "left": 48, "right": 32, "bottom": 64},
            "xAxis": {"type": "category", "data": categories, "axisLabel": {"rotate": 25}},
            "yAxis": {"type": "value"},
            "series": series,
        }
    return {
        "title": {"text": title},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 28},
        "grid": {"top": 80, "left": 48, "right": 32, "bottom": 64},
        "xAxis": {"type": "category", "data": categories, "axisLabel": {"rotate": 25}},
        "yAxis": {"type": "value"},
        "series": [
            {"name": metric, "type": series_type, "data": [_number(row.get(metric)) for row in rows], "smooth": series_type == "line"}
            for metric in metrics
        ],
    }


def _empty_option(title: str, subtitle: str) -> dict[str, Any]:
    return {"title": {"text": title, "subtext": subtitle, "left": "center", "top": "center"}, "series": []}


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        float(value)
        return value is not None and value != ""
    except (TypeError, ValueError):
        return False


def _number(value: Any) -> float:
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return 0.0


def _json_value(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item)]


def _deduplicate(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
