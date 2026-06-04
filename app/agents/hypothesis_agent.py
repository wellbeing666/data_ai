import json
import re
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the Hypothesis Agent for a what-if prediction workflow.

Parse the user's natural-language hypothetical question into structured JSON.
Return only one valid JSON object. Do not output markdown or explanation.
Never invent dataset columns. If a referenced field is not present, keep it as a business phrase and set matched_column to an empty string.

Required schema:
{
  "scenario_type": "what_if_prediction",
  "scenario_summary": "...",
  "intervention": {
    "raw_text": "...",
    "variable": "...",
    "matched_column": "",
    "change_type": "relative|absolute|weight_shift|unknown",
    "change_value": 0.0,
    "unit": ""
  },
  "target_metric": {
    "raw_text": "...",
    "matched_column": ""
  },
  "entity_dimension": {
    "raw_text": "...",
    "matched_column": ""
  },
  "time_horizon": "",
  "assumptions": [],
  "limitations": []
}
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
) -> str:
    return """Parse this hypothetical prediction request.

User goal:
{user_goal}

Dataset profile JSON:
{dataset_profile}

Retrieved business knowledge JSON:
{rag_context}

Use only dataset_profile.columns for matched_column values.
""".format(
        user_goal=user_goal,
        dataset_profile=json.dumps(dataset_profile, ensure_ascii=False, indent=2),
        rag_context=json.dumps(rag_context or [], ensure_ascii=False, indent=2),
    )


class HypothesisAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def parse(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        rag_context: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_user_prompt(user_goal, dataset_profile, rag_context),
                    },
                ],
                temperature=0.1,
            )
            return _normalize(result, user_goal, dataset_profile)
        except Exception:
            return create_rule_based_hypothesis(user_goal, dataset_profile)


def create_hypothesis_plan(
    user_goal: str,
    dataset_profile: dict[str, Any],
    rag_context: list[dict[str, Any]] | None = None,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return HypothesisAgent(llm_client=llm_client).parse(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        rag_context=rag_context,
    )


def create_rule_based_hypothesis(
    user_goal: str,
    dataset_profile: dict[str, Any],
) -> dict[str, Any]:
    columns = _columns(dataset_profile)
    lowered = user_goal.lower()
    change_value = _extract_change_value(user_goal)
    unit = _extract_unit(user_goal)
    change_type = "relative" if unit == "%" else "absolute"
    if "权重" in user_goal or "weight" in lowered:
        change_type = "weight_shift"

    intervention_phrase = _extract_after_if(user_goal)
    target_phrase = _target_phrase(user_goal)
    entity_phrase = _entity_phrase(user_goal)
    intervention_text = intervention_phrase or user_goal

    return {
        "scenario_type": "what_if_prediction",
        "scenario_summary": user_goal,
        "intervention": {
            "raw_text": intervention_text,
            "variable": _intervention_variable(intervention_text),
            "matched_column": _best_column(
                intervention_text,
                columns,
                prefer_numeric=True,
                dataset_profile=dataset_profile,
                allow_numeric_fallback=False,
            ),
            "change_type": change_type,
            "change_value": change_value,
            "unit": unit,
        },
        "target_metric": {
            "raw_text": target_phrase,
            "matched_column": _best_column(
                target_phrase or user_goal,
                columns,
                prefer_numeric=True,
                dataset_profile=dataset_profile,
                allow_numeric_fallback=True,
            ),
        },
        "entity_dimension": {
            "raw_text": entity_phrase,
            "matched_column": _best_column(entity_phrase, columns, allow_numeric_fallback=False),
        },
        "time_horizon": "下个月" if "下个月" in user_goal else "",
        "assumptions": ["预测结果基于当前上传数据进行模拟估计，不代表确定因果。"],
        "limitations": [],
    }


def _normalize(result: Any, user_goal: str, dataset_profile: dict[str, Any]) -> dict[str, Any]:
    fallback = create_rule_based_hypothesis(user_goal, dataset_profile)
    if not isinstance(result, dict):
        return fallback
    columns = set(_columns(dataset_profile))
    normalized = {
        **fallback,
        "scenario_summary": str(result.get("scenario_summary") or fallback["scenario_summary"]),
        "time_horizon": str(result.get("time_horizon") or fallback["time_horizon"]),
        "assumptions": _list(result.get("assumptions")) or fallback["assumptions"],
        "limitations": _list(result.get("limitations")),
    }
    for key in ("intervention", "target_metric", "entity_dimension"):
        value = result.get(key) if isinstance(result.get(key), dict) else {}
        normalized[key] = {**fallback[key], **value}
        matched = str(value.get("matched_column") or "")
        if key == "intervention":
            reference_text = " ".join(
                str(part or "")
                for part in (value.get("raw_text"), value.get("variable"), fallback[key].get("raw_text"), user_goal)
            )
            model_match = matched if matched in columns and _column_matches_phrase(matched, reference_text) else ""
            normalized[key]["matched_column"] = model_match or fallback[key].get("matched_column", "")
        else:
            normalized[key]["matched_column"] = matched if matched in columns else fallback[key].get("matched_column", "")
        for field_name, field_value in fallback[key].items():
            if normalized[key].get(field_name) in (None, ""):
                normalized[key][field_name] = field_value
    normalized["scenario_type"] = "what_if_prediction"
    return normalized


def _extract_change_value(text: str) -> float:
    bedroom_change = _extract_bedroom_change(text)
    if bedroom_change is not None:
        return bedroom_change
    quality_change = _extract_quality_level_change(text)
    if quality_change is not None:
        return quality_change
    distance_change = _extract_from_to_distance_change(text)
    if distance_change is not None:
        return distance_change
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", text)
    if match:
        return float(match.group(1)) / 100.0
    match = re.search(r"(增加|提升|提高|减少|降低|下降|缩短|拉近|延长|扩大|新增)\s*([+-]?\d+(?:\.\d+)?)", text)
    if match:
        value = float(match.group(2))
        if match.group(1) in {"减少", "降低", "下降", "缩短", "拉近"}:
            value = -value
        return value
    match = re.search(
        r"([+-]?\d+(?:\.\d+)?)\s*(平方米|平米|㎡|m2|m\^2|平方英尺|sq\.?\s*ft|sqft|公里|千米|km|米|m|年|层|档|级|间)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return float(match.group(1))
    return 0.0


def _extract_bedroom_change(text: str) -> float | None:
    pattern = re.compile(
        r"(?:从)?\s*([一二两三四五六七八九十\d]+)\s*(?:居|室|房|卧|间)\s*"
        r"(?:变为|变成|调整为|改为|增加到|增加至|到|至)\s*"
        r"([一二两三四五六七八九十\d]+)\s*(?:居|室|房|卧|间)",
    )
    match = pattern.search(text)
    if not match:
        return None
    start = _chinese_number_to_float(match.group(1))
    end = _chinese_number_to_float(match.group(2))
    if start is None or end is None:
        return None
    return float(end - start)


def _extract_quality_level_change(text: str) -> float | None:
    if not any(token in text for token in ("装修", "精装", "简装", "普通", "质量", "等级")):
        return None
    if any(token in text for token in ("普通变为精装修", "普通变成精装修", "普通到精装修", "普通提升为精装修", "普通改为精装修")):
        return 1.0
    if any(token in text for token in ("普通变为豪华", "普通变成豪华", "普通到豪华")):
        return 2.0
    if any(token in text for token in ("精装修变为普通", "精装修变成普通", "精装修到普通")):
        return -1.0
    if any(token in text for token in ("简装变为普通", "简装变成普通", "简装到普通")):
        return 1.0
    if any(token in text for token in ("普通变为简装", "普通变成简装", "普通到简装")):
        return -1.0
    return None


def _chinese_number_to_float(value: str) -> float | None:
    value = str(value or "").strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    mapping = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value in mapping:
        return float(mapping[value])
    if value == "十":
        return 10.0
    if "十" in value:
        left, _, right = value.partition("十")
        tens = mapping.get(left, 1 if left == "" else 0)
        ones = mapping.get(right, 0) if right else 0
        return float(tens * 10 + ones)
    return None


def _extract_from_to_distance_change(text: str) -> float | None:
    pattern = re.compile(
        r"从\s*([+-]?\d+(?:\.\d+)?)\s*(公里|千米|km|米|m)?\s*"
        r"(?:缩短到|缩短至|降低到|降低至|下降到|下降至|减少到|减少至|变为|变成|到|至)\s*"
        r"([+-]?\d+(?:\.\d+)?)\s*(公里|千米|km|米|m)?",
        flags=re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    old_value = _distance_to_meters(float(match.group(1)), match.group(2) or match.group(4) or "")
    new_value = _distance_to_meters(float(match.group(3)), match.group(4) or match.group(2) or "")
    return new_value - old_value


def _distance_to_meters(value: float, unit: str) -> float:
    normalized = str(unit or "").lower()
    if normalized in {"公里", "千米", "km"}:
        return value * 1000.0
    return value


def _extract_unit(text: str) -> str:
    lowered = text.lower()
    if "%" in text:
        return "%"
    if any(token in text for token in ("平方米", "平米", "㎡")) or any(token in lowered for token in ("m2", "m^2", "square meter")):
        return "平方米"
    if any(token in text for token in ("平方英尺",)) or any(token in lowered for token in ("sqft", "sq ft", "square foot", "square feet")):
        return "平方英尺"
    if any(token in text for token in ("装修", "精装", "等级", "档")):
        return "等级"
    if any(token in text for token in ("两居", "二居", "三居", "卧室", "居室", "户型")) or any(token in lowered for token in ("bedroom", "bedrooms")):
        return "间"
    if "年" in text or any(token in lowered for token in ("year", "years")):
        return "年"
    if any(token in text for token in ("公里", "千米", "米")) or re.search(r"\b(km|m)\b", lowered):
        return "米"
    return ""


def _extract_after_if(text: str) -> str:
    for marker in ("如果", "假设", "当"):
        if marker in text:
            tail = text.split(marker, 1)[1]
            return re.split(r"[，,？?]", tail, maxsplit=1)[0].strip()
    return ""


def _target_phrase(text: str) -> str:
    candidates = ["总价", "房价", "售价", "价格", "SalePrice", "销量", "销售额", "不及格率", "及格率", "优秀率", "成绩", "订单数", "转化率"]
    return next((item for item in candidates if item in text), "")


def _entity_phrase(text: str) -> str:
    candidates = ["同一套房", "某套房", "房屋", "房子", "住宅", "房源", "小区", "区域", "周边", "商品", "产品", "班级", "学生", "渠道", "品类", "客户"]
    return next((item for item in candidates if item in text), "")


def _intervention_variable(text: str) -> str:
    candidates = [
        "房屋年龄",
        "建筑年龄",
        "房龄",
        "楼龄",
        "建成年份",
        "建筑年份",
        "建造年份",
        "YearBuilt",
        "距离地铁",
        "地铁距离",
        "距地铁距离",
        "距地铁",
        "地铁站",
        "地铁",
        "距离",
        "贷款利率",
        "按揭利率",
        "房贷利率",
        "利率",
        "楼层",
        "低层",
        "中高层",
        "装修等级",
        "装修",
        "精装修",
        "普通装修",
        "卧室数",
        "居室数",
        "两居",
        "二居",
        "三居",
        "户型",
        "营销预算",
        "预算",
        "面积",
        "平时成绩权重",
        "权重",
    ]
    lowered = text.lower()
    for candidate in candidates:
        if candidate in text:
            return candidate
    if "house age" in lowered or "building age" in lowered:
        return "房龄"
    if "yearbuilt" in lowered or "year built" in lowered:
        return "建造年份"
    if "subway" in lowered or "metro" in lowered:
        return "距离地铁"
    if "bedroom" in lowered:
        return "卧室数"
    return text


def _best_column(
    phrase: str,
    columns: list[str],
    prefer_numeric: bool = False,
    dataset_profile: dict[str, Any] | None = None,
    allow_numeric_fallback: bool = True,
) -> str:
    if not columns:
        return ""
    phrase = phrase or ""
    if not phrase.strip():
        return ""
    phrase_lower = phrase.lower()
    for column in columns:
        column_lower = column.lower()
        if column and (column in phrase or phrase in column or column_lower in phrase_lower or phrase_lower in column_lower):
            return column
    aliases = _column_aliases()
    for keyword, names in aliases.items():
        if keyword.lower() in phrase_lower:
            for preferred_name in names:
                for column in columns:
                    column_lower = column.lower()
                    if preferred_name.lower() == column_lower or preferred_name.lower() in column_lower:
                        return column
    if prefer_numeric and allow_numeric_fallback and dataset_profile:
        numeric = [str(column) for column in dataset_profile.get("numeric_summary", {}).keys()]
        non_identifier_numeric = [column for column in numeric if not _is_identifier_column(column)]
        if non_identifier_numeric:
            return non_identifier_numeric[0]
        if numeric:
            return numeric[0]
    return ""


def _column_matches_phrase(column: str, phrase: str) -> bool:
    if not column or not phrase:
        return False
    column_lower = str(column).lower()
    phrase_lower = str(phrase).lower()
    if column in phrase or column_lower in phrase_lower:
        return True
    aliases = _column_aliases()
    for keyword, names in aliases.items():
        if keyword.lower() not in phrase_lower:
            continue
        for preferred_name in names:
            preferred_lower = preferred_name.lower()
            if preferred_lower == column_lower or preferred_lower in column_lower or column_lower in preferred_lower:
                return True
    return False


def _house_age_aliases() -> list[str]:
    return [
        "HouseAge",
        "house_age",
        "BuildingAge",
        "building_age",
        "房龄",
        "房屋年龄",
        "建筑年龄",
        "楼龄",
        "YearBuilt",
        "year_built",
        "BuiltYear",
        "Built_Year",
        "建成年份",
        "建造年份",
        "建筑年份",
    ]


def _column_aliases() -> dict[str, list[str]]:
    distance_aliases = [
        "DistanceToMetro",
        "MetroDistance",
        "SubwayDistance",
        "DistanceToSubway",
        "NearestMetroDistance",
        "NearestSubwayDistance",
        "distance_to_metro",
        "distance_to_subway",
        "metro_distance",
        "subway_distance",
        "距离地铁",
        "地铁距离",
        "距地铁",
        "距地铁距离",
        "地铁",
        "subway",
        "metro",
    ]
    return {
        "距离地铁": distance_aliases,
        "地铁距离": distance_aliases,
        "距地铁": distance_aliases,
        "地铁": distance_aliases,
        "subway": distance_aliases,
        "metro": distance_aliases,
        "房龄": _house_age_aliases(),
        "房屋年龄": _house_age_aliases(),
        "建筑年龄": _house_age_aliases(),
        "楼龄": _house_age_aliases(),
        "建成年份": ["YearBuilt", "year_built", "BuiltYear", "Built_Year", "建成年份", "建造年份", "建筑年份"],
        "建造年份": ["YearBuilt", "year_built", "BuiltYear", "Built_Year", "建成年份", "建造年份", "建筑年份"],
        "建筑年份": ["YearBuilt", "year_built", "BuiltYear", "Built_Year", "建成年份", "建造年份", "建筑年份"],
        "yearbuilt": ["YearBuilt", "year_built", "BuiltYear", "Built_Year"],
        "面积": ["GrLivArea", "LivingArea", "TotalBsmtSF", "1stFlrSF", "2ndFlrSF", "LotArea", "GarageArea", "面积", "Area", "SF"],
        "平方米": ["GrLivArea", "LivingArea", "TotalBsmtSF", "1stFlrSF", "2ndFlrSF", "LotArea", "GarageArea", "面积", "Area", "SF"],
        "平米": ["GrLivArea", "LivingArea", "TotalBsmtSF", "1stFlrSF", "2ndFlrSF", "LotArea", "GarageArea", "面积", "Area", "SF"],
        "装修等级": ["OverallQual", "KitchenQual", "ExterQual", "OverallCond", "装修等级", "装修", "quality"],
        "装修": ["OverallQual", "KitchenQual", "ExterQual", "OverallCond", "装修等级", "装修", "quality"],
        "精装修": ["OverallQual", "KitchenQual", "ExterQual", "OverallCond", "装修等级", "装修", "quality"],
        "普通装修": ["OverallQual", "KitchenQual", "ExterQual", "OverallCond", "装修等级", "装修", "quality"],
        "卧室数": ["BedroomAbvGr", "Bedrooms", "Bedroom", "卧室数", "居室数", "居室", "户型", "TotRmsAbvGrd"],
        "居室数": ["BedroomAbvGr", "Bedrooms", "Bedroom", "卧室数", "居室数", "居室", "户型", "TotRmsAbvGrd"],
        "两居": ["BedroomAbvGr", "Bedrooms", "Bedroom", "卧室数", "居室数", "居室", "户型", "TotRmsAbvGrd"],
        "二居": ["BedroomAbvGr", "Bedrooms", "Bedroom", "卧室数", "居室数", "居室", "户型", "TotRmsAbvGrd"],
        "三居": ["BedroomAbvGr", "Bedrooms", "Bedroom", "卧室数", "居室数", "居室", "户型", "TotRmsAbvGrd"],
        "户型": ["BedroomAbvGr", "Bedrooms", "Bedroom", "卧室数", "居室数", "居室", "户型", "TotRmsAbvGrd"],
        "贷款利率": ["InterestRate", "MortgageRate", "LoanRate", "贷款利率", "房贷利率", "按揭利率", "利率"],
        "按揭利率": ["InterestRate", "MortgageRate", "LoanRate", "贷款利率", "房贷利率", "按揭利率", "利率"],
        "房贷利率": ["InterestRate", "MortgageRate", "LoanRate", "贷款利率", "房贷利率", "按揭利率", "利率"],
        "利率": ["InterestRate", "MortgageRate", "LoanRate", "贷款利率", "房贷利率", "按揭利率", "利率"],
        "楼层": ["Floor", "FloorLevel", "楼层", "所在楼层", "floor"],
        "低层": ["Floor", "FloorLevel", "楼层", "所在楼层", "floor"],
        "中高层": ["Floor", "FloorLevel", "楼层", "所在楼层", "floor"],
        "同一套房": ["Id", "房屋编号", "编号", "house_id", "ID", "id"],
        "某套房": ["Id", "房屋编号", "编号", "house_id", "ID", "id"],
        "房屋": ["Id", "房屋编号", "编号", "house_id", "ID", "id"],
        "房子": ["Id", "房屋编号", "编号", "house_id", "ID", "id"],
        "住宅": ["Id", "房屋编号", "编号", "house_id", "ID", "id"],
        "房源": ["Id", "房屋编号", "编号", "house_id", "ID", "id"],
        "总价": ["SalePrice", "房价", "总价", "售价", "价格", "Price"],
        "房价": ["SalePrice", "房价", "总价", "售价", "价格", "Price"],
        "售价": ["SalePrice", "房价", "总价", "售价", "价格", "Price"],
        "价格": ["SalePrice", "房价", "总价", "售价", "价格", "Price"],
        "saleprice": ["SalePrice", "房价", "总价", "售价", "价格", "Price"],
        "商品": ["商品", "产品", "sku", "SKU"],
        "销量": ["销量", "销售量", "数量"],
        "销售额": ["销售额", "收入", "GMV", "金额"],
        "预算": ["预算", "营销", "投放", "费用"],
        "平时": ["平时", "过程", "日常"],
        "成绩": ["成绩", "分数", "得分", "总评"],
        "班级": ["班级", "班"],
        "不及格率": ["成绩", "分数", "总评"],
    }


def _is_identifier_column(column: str) -> bool:
    text = str(column).strip().lower()
    return text in {"id", "编号", "序号", "房屋编号", "house_id", "row_id"} or text.endswith("_id")


def _columns(dataset_profile: dict[str, Any]) -> list[str]:
    return [str(column) for column in dataset_profile.get("columns", [])]


def _list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


