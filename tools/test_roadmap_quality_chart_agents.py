from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.chart_config_agent import create_chart_config  # noqa: E402
from app.agents.quality_review_agent import create_quality_review  # noqa: E402
from app.agents.roadmap_agent import create_analysis_roadmap  # noqa: E402


class FailingLLM:
    def chat_json(self, *args, **kwargs):
        raise RuntimeError("LLM unavailable")


def _profile():
    return {
        "columns": ["班级", "成绩", "及格率"],
        "row_count": 24,
        "column_count": 3,
        "numeric_summary": {"成绩": {}, "及格率": {}},
        "text_summary": {"班级": {}},
        "sample_rows": [
            {"班级": "三班", "成绩": 88, "及格率": 0.95},
            {"班级": "四班", "成绩": 76, "及格率": 0.82},
        ],
    }


def test_roadmap_excludes_quality_review_step():
    roadmap = create_analysis_roadmap(
        "把成绩按班级统计并生成图表",
        _profile(),
        {"task_type": "grade_analysis", "task_name": "成绩分析"},
        "auto_repair",
        llm_client=FailingLLM(),
    )

    assert roadmap["workflow_type"] == "auto_repair"
    assert len(roadmap["steps"]) >= 6
    assert not any(step["stage"] == "quality_review" for step in roadmap["steps"])
    assert all("title" in step and "agent" in step for step in roadmap["steps"])
    assert all("质检" not in f"{step.get('title', '')} {step.get('agent', '')}" for step in roadmap["steps"])


def test_quality_review_rewrites_causal_overclaim():
    review = create_quality_review(
        user_goal="找出影响销量下降的原因",
        dataset_profile={"columns": ["日期", "销量", "促销活动"], "row_count": 8},
        result_payload={"success": True, "charts": []},
        explanation={"summary": "促销活动导致销量下降。", "key_findings": ["促销导致下降"]},
        validation_result={"passed": True, "issues": []},
        chart_paths=[],
        workflow_type="auto_repair",
        llm_client=FailingLLM(),
    )

    assert review["risk_level"] in {"medium", "high"}
    assert any(issue["issue_type"] == "correlation_as_causation" for issue in review["issues"])
    assert "可能" in review["revised_summary"] or "相关" in review["revised_summary"]


def test_chart_config_filters_and_generates_echarts_option():
    result = create_chart_config(
        instruction="只看三班和四班，换成折线图，加一个及格率指标",
        result_payload={
            "summary": [
                {"班级": "一班", "平均成绩": 83, "及格率": 0.88},
                {"班级": "三班", "平均成绩": 91, "及格率": 0.96},
                {"班级": "四班", "平均成绩": 77, "及格率": 0.79},
            ]
        },
        dataset_profile=_profile(),
        llm_client=FailingLLM(),
    )

    assert result["echarts_option"]["xAxis"]["type"] == "category"
    assert result["echarts_option"]["series"][0]["type"] == "line"
    assert {row["班级"] for row in result["data_preview"]} == {"三班", "四班"}
    assert result["applied_filters"]


if __name__ == "__main__":
    test_roadmap_excludes_quality_review_step()
    test_quality_review_rewrites_causal_overclaim()
    test_chart_config_filters_and_generates_echarts_option()
    print("Roadmap, quality review and chart config agent tests passed.")
