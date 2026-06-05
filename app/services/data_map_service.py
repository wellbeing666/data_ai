import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_reader import get_dataset_dir


DATA_MAP_FILENAME = "data_map.json"

ENTITY_HINTS = {
    "学生": ("学生", "姓名", "学号", "student"),
    "班级": ("班级", "class", "班"),
    "科目": ("科目", "语文", "数学", "英语", "物理", "化学", "成绩"),
    "商品": ("商品", "产品", "品类", "category", "product", "sku"),
    "客户": ("客户", "用户", "会员", "customer", "user"),
    "地区": ("地区", "区域", "城市", "省份", "region", "city"),
    "渠道": ("渠道", "channel"),
    "部门": ("部门", "团队", "department"),
    "员工": ("员工", "工号", "姓名", "employee"),
    "生产线": ("生产线", "产线", "line"),
    "工序": ("工序", "process"),
    "物料": ("物料", "材料", "库存", "仓库", "material"),
    "房源": ("房源", "小区", "户型", "房价", "house", "saleprice"),
    "时间": ("日期", "月份", "时间", "date", "month", "time", "year"),
}

METRIC_HINTS = (
    "销量",
    "销售额",
    "金额",
    "收入",
    "成绩",
    "分数",
    "率",
    "人数",
    "数量",
    "价格",
    "时长",
    "时间",
    "不良",
    "成本",
    "利润",
    "库存",
    "score",
    "sales",
    "amount",
    "price",
    "rate",
    "count",
    "duration",
)

ID_HINTS = ("id", "编号", "编码", "代码", "学号", "工号", "订单号")
DATE_HINT_PATTERN = re.compile(r"日期|月份|年月|时间|date|month|year|time", re.IGNORECASE)


def get_or_create_dataset_data_map(dataset_id: str, *, force: bool = False) -> dict[str, Any]:
    """Return a visual data map generated from the latest dataset profile."""
    dataset_dir = get_dataset_dir(dataset_id)
    path = dataset_dir / DATA_MAP_FILENAME
    profile = generate_dataset_profile(dataset_id)

    if path.exists() and not force:
        cached = _read_json(path)
        if _cache_matches_profile(cached, profile):
            return {
                "dataset_id": dataset_id,
                "data_map": cached,
                "data_map_path": str(path),
                "message": "数据地图已读取。",
            }

    data_map = build_data_map(profile)
    _write_json(path, data_map)
    return {
        "dataset_id": dataset_id,
        "data_map": data_map,
        "data_map_path": str(path),
        "message": "数据地图已生成。",
    }


def build_data_map(dataset_profile: dict[str, Any]) -> dict[str, Any]:
    columns = [str(item) for item in dataset_profile.get("columns") or []]
    numeric_columns = [str(key) for key in (dataset_profile.get("numeric_summary") or {}).keys()]
    text_columns = [str(key) for key in (dataset_profile.get("text_summary") or {}).keys()]
    time_columns = [column for column in columns if DATE_HINT_PATTERN.search(column)]

    metrics = _dedupe([column for column in numeric_columns if _is_metric_column(column)] or numeric_columns)
    dimensions = _dedupe([column for column in [*text_columns, *time_columns] if column not in metrics])
    identifiers = [column for column in columns if _is_identifier_column(column)]
    entities = _infer_entities(columns, metrics, dimensions, identifiers)
    possible_questions = _build_possible_questions(entities, metrics, dimensions, time_columns)
    nodes = _build_graph_nodes(entities, metrics, dimensions, time_columns, identifiers)
    edges = _build_graph_edges(entities, metrics, dimensions, time_columns)
    column_semantics = _build_column_semantics(columns, metrics, dimensions, time_columns, identifiers, entities)
    insights = _build_profile_insights(dataset_profile, metrics, dimensions)

    return {
        "schema_version": 1,
        "agent": "Data Map Agent",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": str(dataset_profile.get("dataset_id") or ""),
        "source_file": str(dataset_profile.get("filename") or ""),
        "row_count": int(dataset_profile.get("row_count") or 0),
        "column_count": int(dataset_profile.get("column_count") or len(columns)),
        "data_map": {
            "entities": entities,
            "metrics": metrics,
            "dimensions": dimensions,
            "time_dimensions": time_columns,
            "identifiers": identifiers,
            "possible_questions": possible_questions,
        },
        "graph": {
            "nodes": nodes,
            "edges": edges,
        },
        "columns": column_semantics,
        "insights": insights,
        "usage_note": "前端会将本 JSON 展示为可点击知识图谱，用户可以从节点问题直接回填分析目标。",
    }


def _infer_entities(columns: list[str], metrics: list[str], dimensions: list[str], identifiers: list[str]) -> list[str]:
    text = " ".join(columns).lower()
    entities: list[str] = []
    for entity, hints in ENTITY_HINTS.items():
        if any(str(hint).lower() in text for hint in hints):
            entities.append(entity)

    for column in dimensions:
        normalized = _normalize_entity_label(column)
        if normalized and normalized not in entities and normalized not in metrics:
            entities.append(normalized)
        if len(entities) >= 8:
            break

    if not entities and identifiers:
        entities.append(_normalize_entity_label(identifiers[0]) or "业务对象")
    if not entities and dimensions:
        entities.append(_normalize_entity_label(dimensions[0]) or "业务对象")
    if not entities:
        entities.append("数据记录")
    return _dedupe(entities)[:8]


def _normalize_entity_label(column: str) -> str:
    value = str(column).strip()
    replacements = {
        "姓名": "人员",
        "名称": "对象",
        "编号": "对象",
        "编码": "对象",
        "日期": "时间",
        "月份": "时间",
        "商品类别": "商品",
        "品类": "商品",
        "地区": "地区",
        "区域": "地区",
    }
    for source, target in replacements.items():
        if source in value:
            return target
    value = re.sub(r"(_id|id)$", "", value, flags=re.IGNORECASE).strip("_ -")
    return value[:12] if value else ""


def _build_possible_questions(
    entities: list[str],
    metrics: list[str],
    dimensions: list[str],
    time_columns: list[str],
) -> dict[str, list[str]]:
    primary_metric = metrics[0] if metrics else "核心指标"
    primary_dimension = dimensions[0] if dimensions else (entities[0] if entities else "业务对象")
    questions: dict[str, list[str]] = {}
    for entity in entities:
        entity_questions = [
            f"哪些{entity}的{primary_metric}最高或最低？",
            f"哪些{entity}需要重点关注？",
        ]
        if primary_dimension and primary_dimension not in entity:
            entity_questions.append(f"按{primary_dimension}拆解，{entity}的{primary_metric}差异在哪里？")
        if time_columns:
            entity_questions.append(f"{entity}的{primary_metric}随{time_columns[0]}有什么变化趋势？")
        questions[entity] = _dedupe(entity_questions)[:4]

    if metrics:
        questions["指标"] = [
            f"{primary_metric}的整体趋势和异常点是什么？",
            f"哪些维度对{primary_metric}的差异最明显？",
        ]
    return questions


def _build_graph_nodes(
    entities: list[str],
    metrics: list[str],
    dimensions: list[str],
    time_columns: list[str],
    identifiers: list[str],
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for label in entities:
        nodes.append({"id": f"entity:{label}", "label": label, "type": "entity", "description": f"可作为分析对象的实体：{label}", "size": 1.18})
    for label in metrics[:12]:
        nodes.append({"id": f"metric:{label}", "label": label, "type": "metric", "field": label, "description": f"可度量指标：{label}", "size": 1.05})
    for label in dimensions[:12]:
        node_type = "time" if label in time_columns else "dimension"
        nodes.append({"id": f"{node_type}:{label}", "label": label, "type": node_type, "field": label, "description": f"可筛选/分组维度：{label}", "size": 0.96})
    for label in identifiers[:6]:
        nodes.append({"id": f"identifier:{label}", "label": label, "type": "identifier", "field": label, "description": f"标识字段：{label}", "size": 0.86})
    return _dedupe_nodes(nodes)


def _build_graph_edges(
    entities: list[str],
    metrics: list[str],
    dimensions: list[str],
    time_columns: list[str],
) -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for entity in entities[:6]:
        for metric in metrics[:5]:
            edges.append({"source": f"entity:{entity}", "target": f"metric:{metric}", "relation": "观测指标"})
        for dimension in dimensions[:5]:
            target_type = "time" if dimension in time_columns else "dimension"
            edges.append({"source": f"entity:{entity}", "target": f"{target_type}:{dimension}", "relation": "可按维度拆解"})
    for dimension in dimensions[:4]:
        for metric in metrics[:3]:
            source_type = "time" if dimension in time_columns else "dimension"
            edges.append({"source": f"{source_type}:{dimension}", "target": f"metric:{metric}", "relation": "分组统计"})
    return _dedupe_edges(edges)[:80]


def _build_column_semantics(
    columns: list[str],
    metrics: list[str],
    dimensions: list[str],
    time_columns: list[str],
    identifiers: list[str],
    entities: list[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for column in columns:
        if column in metrics:
            semantic_type = "metric"
            linked_node = f"metric:{column}"
        elif column in time_columns:
            semantic_type = "time_dimension"
            linked_node = f"time:{column}"
        elif column in dimensions:
            semantic_type = "dimension"
            linked_node = f"dimension:{column}"
        elif column in identifiers:
            semantic_type = "identifier"
            linked_node = f"identifier:{column}"
        else:
            semantic_type = "attribute"
            linked_node = f"entity:{entities[0]}" if entities else ""
        result.append({
            "name": column,
            "semantic_type": semantic_type,
            "linked_node": linked_node,
            "suggested_usage": _column_usage_text(column, semantic_type),
        })
    return result


def _build_profile_insights(dataset_profile: dict[str, Any], metrics: list[str], dimensions: list[str]) -> list[dict[str, Any]]:
    insights = [
        {
            "title": "数据规模",
            "description": f"当前数据包含 {int(dataset_profile.get('row_count') or 0)} 行、{int(dataset_profile.get('column_count') or 0)} 列。",
            "level": "info",
        },
        {
            "title": "核心分析入口",
            "description": f"可优先从 {', '.join(dimensions[:3]) or '维度字段'} × {', '.join(metrics[:3]) or '指标字段'} 开始探索。",
            "level": "success",
        },
    ]
    missing_values = dataset_profile.get("missing_values") if isinstance(dataset_profile.get("missing_values"), dict) else {}
    missing_columns = [str(column) for column, summary in missing_values.items() if isinstance(summary, dict) and int(summary.get("count") or 0) > 0]
    if missing_columns:
        insights.append({
            "title": "质量提醒",
            "description": f"字段 {', '.join(missing_columns[:5])} 存在缺失值，分析时建议同步查看数据修复策略。",
            "level": "warning",
        })
    return insights


def _column_usage_text(column: str, semantic_type: str) -> str:
    if semantic_type == "metric":
        return f"作为统计指标，可计算均值、总和、排名或趋势：{column}。"
    if semantic_type == "time_dimension":
        return f"作为时间轴，可生成趋势图或周期对比：{column}。"
    if semantic_type == "dimension":
        return f"作为筛选或分组维度，可做对比分析：{column}。"
    if semantic_type == "identifier":
        return f"作为唯一标识或明细定位字段：{column}。"
    return f"作为辅助解释属性：{column}。"


def _is_metric_column(column: str) -> bool:
    text = column.lower()
    return any(hint.lower() in text for hint in METRIC_HINTS) or not DATE_HINT_PATTERN.search(column)


def _is_identifier_column(column: str) -> bool:
    text = column.lower()
    return any(hint.lower() in text for hint in ID_HINTS)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _dedupe_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("id") or "")
        if node_id and node_id not in seen:
            seen.add(node_id)
            result.append(node)
    return result


def _dedupe_edges(edges: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, str]] = []
    for edge in edges:
        key = (edge.get("source", ""), edge.get("target", ""), edge.get("relation", ""))
        if key[0] and key[1] and key not in seen:
            seen.add(key)
            result.append(edge)
    return result


def _cache_matches_profile(cached: dict[str, Any], profile: dict[str, Any]) -> bool:
    if not cached:
        return False
    return (
        str(cached.get("dataset_id") or "") == str(profile.get("dataset_id") or "")
        and int(cached.get("row_count") or -1) == int(profile.get("row_count") or 0)
        and int(cached.get("column_count") or -1) == int(profile.get("column_count") or 0)
    )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
