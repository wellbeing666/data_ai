import csv
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status


UPLOAD_ROOT = Path("storage/uploads")

SAMPLE_META: dict[str, dict[str, Any]] = {
    "sales_decline": {
        "filename": "sample_sales_decline.csv",
        "description": "销售下降诊断样例数据，包含日期、地区、渠道、商品类别、销量、销售额、库存和折扣率。",
        "recommended_goal": "分析销量从 2026 年 1 月到 6 月的变化趋势，识别下降阶段，并按地区、渠道和商品类别拆解可能原因。",
        "suggested_goals": [
            "分析销量从 2026 年 1 月到 6 月的变化趋势，识别下降阶段，并按地区、渠道和商品类别拆解可能原因。",
            "比较各地区、渠道、商品类别的销量变化，找出下降最明显的组合并生成图表。",
            "分析折扣率、库存与销量变化之间的关系，输出可能风险信号和业务建议。",
            "生成月度销量趋势、地区对比、渠道对比和商品类别对比图，并给出谨慎结论。",
        ],
    },
    "grade_scores": {
        "filename": "sample_grade_scores.csv",
        "description": "成绩分析样例数据，包含班级、学生、各科成绩、总成绩和出勤率。",
        "recommended_goal": "把这批成绩按班级统计平均分、及格率、优秀率并生成图表。",
        "suggested_goals": [
            "把这批成绩按班级统计平均分、及格率、优秀率并生成图表。",
            "比较各班总成绩和单科成绩差异，找出需要重点关注的班级。",
            "分析成绩、出勤率之间的关系，并输出学习支持建议。",
            "识别缺失或异常成绩记录，生成数据质量提示和班级对比图。",
        ],
    },
    "survey_feedback": {
        "filename": "sample_survey_feedback.csv",
        "description": "问卷调查样例数据，包含用户群体、满意度、推荐意愿、等待时长和反馈主题。",
        "recommended_goal": "分析问卷满意度差异，找出影响推荐意愿的主要因素并生成图表。",
        "suggested_goals": [
            "分析问卷满意度差异，找出影响推荐意愿的主要因素并生成图表。",
            "按用户群体和反馈主题比较满意度、推荐意愿和投诉次数。",
            "分析等待时长与满意度、推荐意愿之间的关系，并提出改进建议。",
            "识别满意度较低的主题和用户群体，生成优先优化清单。",
        ],
    },
    "health_activity": {
        "filename": "sample_health_activity.csv",
        "description": "运动健康样例数据，包含日期、用户、步数、运动分钟、睡眠小时和心率。",
        "recommended_goal": "分析运动行为、睡眠和心率之间的关系，识别健康风险样本并生成图表。",
        "suggested_goals": [
            "分析运动行为、睡眠和心率之间的关系，识别健康风险样本并生成图表。",
            "按用户比较步数、运动分钟、睡眠小时和体感疲劳分的差异。",
            "分析睡眠不足时静息心率和疲劳分的变化，并输出健康提醒。",
            "生成每日趋势和用户对比图，找出需要重点关注的异常样本。",
        ],
    },
    "ecommerce_orders": {
        "filename": "sample_ecommerce_orders.csv",
        "description": "电商订单样例数据，包含店铺、类目、订单数、客单价、转化率、广告花费和销售额。",
        "recommended_goal": "分析电商订单表现，比较不同店铺和类目的销售额、转化率和广告效率。",
        "suggested_goals": [
            "分析电商订单表现，比较不同店铺和类目的销售额、转化率和广告效率。",
            "按店铺和类目拆解销售额贡献，找出增长较好的组合。",
            "分析广告花费、订单数、转化率和销售额之间的关系。",
            "生成销售额趋势、类目对比和广告效率图，并输出运营建议。",
        ],
    },
}


def create_sample_dataset(sample_type: str) -> dict[str, Any]:
    normalized_type = str(sample_type or "sales_decline").strip() or "sales_decline"
    if normalized_type not in SAMPLE_META:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的样例数据类型：{normalized_type}",
        )

    dataset_id = uuid4().hex
    dataset_dir = UPLOAD_ROOT / dataset_id
    dataset_dir.mkdir(parents=True, exist_ok=False)
    meta = SAMPLE_META[normalized_type]
    rows = _rows_for_sample(normalized_type)
    file_path = dataset_dir / meta["filename"]
    _write_csv(file_path, rows)
    metadata = {
        "dataset_id": dataset_id,
        "filename": meta["filename"],
        "file_type": "csv",
        "file_path": str(file_path),
        "asset_type": "tabular",
        "preview_url": None,
        "sample_type": normalized_type,
        "recommended_goal": meta["recommended_goal"],
        "description": meta["description"],
        "suggested_goals": list(meta.get("suggested_goals") or [meta["recommended_goal"]]),
    }
    (dataset_dir / "metadata.json").write_text(_json_dumps(metadata), encoding="utf-8")
    return metadata


def list_sample_dataset_types() -> list[dict[str, Any]]:
    return [
        {"sample_type": key, **value}
        for key, value in SAMPLE_META.items()
    ]


def _rows_for_sample(sample_type: str) -> list[dict[str, Any]]:
    builders = {
        "sales_decline": _build_sales_decline_rows,
        "grade_scores": _build_grade_rows,
        "survey_feedback": _build_survey_rows,
        "health_activity": _build_health_rows,
        "ecommerce_orders": _build_ecommerce_rows,
    }
    return builders[sample_type]()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("sample rows must not be empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _json_dumps(data: dict[str, Any]) -> str:
    import json

    return json.dumps(data, ensure_ascii=False, indent=2)


def _add_months(start: date, months: int) -> date:
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    return date(year, month, 1)


def _build_sales_decline_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    start = date(2026, 1, 1)
    regions = ["华东", "华南", "华北"]
    channels = ["线上商城", "门店", "直播"]
    categories = ["家电", "个护", "食品"]
    products = ["A款", "B款", "C款"]
    for month_index in range(6):
        month_date = _add_months(start, month_index)
        decline_factor = 1.0 - month_index * 0.055
        for region_index, region in enumerate(regions):
            for channel_index, channel in enumerate(channels):
                for category_index, category in enumerate(categories):
                    base = 420 - region_index * 18 - channel_index * 24 - category_index * 12
                    inventory = 220 - month_index * 18 - category_index * 10
                    discount = round(0.05 + channel_index * 0.025 + month_index * 0.01, 3)
                    stock_penalty = 0.9 if inventory < 150 and category == "家电" else 1.0
                    sales = max(40, round(base * decline_factor * stock_penalty))
                    rows.append(
                        {
                            "日期": month_date.isoformat(),
                            "月份": month_date.strftime("%Y-%m"),
                            "地区": region,
                            "渠道": channel,
                            "商品类别": category,
                            "商品": products[category_index],
                            "销量": sales,
                            "销售额": round(sales * (78 + category_index * 22) * (1 - discount), 2),
                            "库存": inventory,
                            "折扣率": discount,
                        }
                    )
    return rows


def _build_grade_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    classes = ["一班", "二班", "三班", "四班"]
    for class_index, class_name in enumerate(classes):
        for student_index in range(1, 13):
            base = 84 - class_index * 4 + (student_index % 5) * 3 - (student_index // 6) * 6
            chinese = max(42, min(100, base + 2))
            math = max(40, min(100, base + (student_index % 3) * 4 - 1))
            english = max(45, min(100, base + (student_index % 4) * 2))
            score = round((chinese + math + english) / 3, 1)
            rows.append(
                {
                    "班级": class_name,
                    "姓名": f"学生{class_index + 1:02d}{student_index:02d}",
                    "学号": f"S2026{class_index + 1}{student_index:02d}",
                    "语文成绩": chinese,
                    "数学成绩": math,
                    "英语成绩": english,
                    "成绩": score if not (class_name == "四班" and student_index == 12) else "",
                    "性别": "男" if student_index % 2 else "女",
                    "出勤率": round(0.88 + (student_index % 6) * 0.018, 3),
                }
            )
    return rows


def _build_survey_rows() -> list[dict[str, Any]]:
    groups = ["学生", "运营人员", "老师", "管理者"]
    topics = ["功能易用性", "响应速度", "报告质量", "图表体验"]
    rows: list[dict[str, Any]] = []
    for index in range(80):
        group = groups[index % len(groups)]
        topic = topics[(index // 2) % len(topics)]
        wait = 2 + (index % 7) * 1.5 + (3 if topic == "响应速度" else 0)
        satisfaction = max(1, min(5, round(4.6 - wait * 0.18 + (index % 5) * 0.08, 1)))
        rows.append(
            {
                "用户群体": group,
                "反馈主题": topic,
                "满意度": satisfaction,
                "推荐意愿": max(1, min(10, round(satisfaction * 2 - (wait > 8) * 1.2, 1))),
                "等待时长分钟": round(wait, 1),
                "投诉次数": 1 if satisfaction < 3.2 else 0,
            }
        )
    return rows


def _build_health_rows() -> list[dict[str, Any]]:
    users = ["U001", "U002", "U003", "U004", "U005", "U006"]
    rows: list[dict[str, Any]] = []
    start = date(2026, 3, 1)
    for day in range(28):
        current = start + timedelta(days=day)
        for user_index, user in enumerate(users):
            steps = 5200 + user_index * 500 + (day % 6) * 430
            exercise = round(steps / 420 + (day % 3) * 3, 1)
            sleep = round(6.2 + (user_index % 3) * 0.45 - (day % 7 == 0) * 0.6, 1)
            rows.append(
                {
                    "日期": current.isoformat(),
                    "用户": user,
                    "步数": steps,
                    "运动分钟": exercise,
                    "睡眠小时": sleep,
                    "静息心率": 78 - user_index * 2 + (sleep < 6.5) * 5,
                    "体感疲劳分": round(max(1, 8 - sleep + (steps < 6000) * 1.3), 1),
                }
            )
    return rows


def _build_ecommerce_rows() -> list[dict[str, Any]]:
    stores = ["旗舰店", "专营店", "直播店"]
    categories = ["数码", "家居", "美妆", "食品"]
    rows: list[dict[str, Any]] = []
    start = date(2026, 2, 1)
    for day in range(45):
        current = start + timedelta(days=day)
        for store_index, store in enumerate(stores):
            for category_index, category in enumerate(categories):
                ad = 800 + store_index * 180 + category_index * 90 + (day % 8) * 35
                orders = round(60 + ad / 55 + category_index * 6 - store_index * 3)
                conversion = round(0.024 + category_index * 0.003 + store_index * 0.002 - (day % 9) * 0.0004, 4)
                unit_price = 80 + category_index * 35 + store_index * 8
                rows.append(
                    {
                        "日期": current.isoformat(),
                        "店铺": store,
                        "类目": category,
                        "订单数": orders,
                        "客单价": unit_price,
                        "转化率": conversion,
                        "广告花费": ad,
                        "销售额": round(orders * unit_price, 2),
                    }
                )
    return rows
