from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.preflight_agent import create_preflight_assessment  # noqa: E402


class FailingLLM:
    def chat_json(self, *args, **kwargs):
        raise RuntimeError("LLM unavailable")


def _sales_profile():
    return {
        "columns": ["日期", "地区", "渠道", "商品类别", "销量", "销售额"],
        "row_count": 48,
        "column_count": 6,
        "dtypes": {"日期": "object", "销量": "int64", "销售额": "float64"},
        "missing_values": {"销量": {"count": 1, "ratio": 0.02}},
        "numeric_summary": {"销量": {"min": 80, "max": 420, "mean": 250}, "销售额": {}},
        "text_summary": {"地区": {}, "渠道": {}, "商品类别": {}},
        "sample_rows": [],
    }


def test_sales_decline_preflight_asks_clarification():
    result = create_preflight_assessment(
        "找出销量下降的原因",
        _sales_profile(),
        llm_client=FailingLLM(),
    )

    assert result["intent_type"] == "sales_decline_analysis"
    assert result["is_task_clear"] is False
    assert result["next_action"] == "needs_user_choice"
    assert 1 <= len(result["clarifying_questions"]) <= 3
    assert any("下降口径" in item for item in result["clarifying_questions"])
    assert result["data_quality_report"]["missing_fields"][0]["column"] == "销量"
    assert all(item["name"] in _sales_profile()["columns"] for item in result["detected_fields"])


def test_grade_preflight_can_be_ready_to_run():
    profile = {
        "columns": ["班级", "姓名", "成绩"],
        "row_count": 36,
        "column_count": 3,
        "dtypes": {"成绩": "float64"},
        "missing_values": {},
        "numeric_summary": {"成绩": {"min": 55, "max": 98, "mean": 82}},
        "text_summary": {"班级": {}, "姓名": {}},
    }
    result = create_preflight_assessment(
        "把这批成绩按班级统计平均分、及格率、优秀率并生成图表",
        profile,
        llm_client=FailingLLM(),
    )

    assert result["intent_type"] == "grade_analysis"
    assert result["clarifying_questions"] == []
    assert result["next_action"] == "ready_to_run"
    assert result["clarity_score"] >= 0.72


if __name__ == "__main__":
    test_sales_decline_preflight_asks_clarification()
    test_grade_preflight_can_be_ready_to_run()
    print("Preflight agent tests passed.")
