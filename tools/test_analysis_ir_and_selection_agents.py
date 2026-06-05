from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.analysis_ir_agent import create_analysis_ir, render_analysis_ir_for_agent  # noqa: E402
from app.agents.selection_to_query_agent import create_selection_followup_patch  # noqa: E402


class FailingLLM:
    def chat_json(self, *args, **kwargs):
        raise RuntimeError("llm unavailable")


def test_analysis_ir_fallback_uses_existing_columns_only():
    profile = {
        "columns": ["日期", "地区", "渠道", "销量", "销售额"],
        "row_count": 12,
        "column_count": 5,
        "numeric_summary": {"销量": {}, "销售额": {}},
        "text_summary": {"地区": {}, "渠道": {}},
    }
    result = create_analysis_ir(
        "分析销量下降原因，按地区和渠道拆解",
        profile,
        llm_client=FailingLLM(),
    )
    columns = set(profile["columns"])
    assert result["task_type"] == "sales_decline_analysis"
    assert result["metrics"]
    assert all(item["source_column"] in columns for item in result["metrics"])
    assert all(item["source_column"] in columns for item in result["dimensions"])
    rendered = render_analysis_ir_for_agent(result, {"stage": "controller"})
    assert "Analysis IR + Delta JSON" in rendered
    assert "analysis_ir" in rendered


def test_selection_to_query_patch_creates_question():
    analysis_ir = {
        "metrics": [{"name": "销量", "source_column": "销量"}],
        "dimensions": [{"name": "地区", "source_column": "地区"}],
        "time_window": {"field": "日期"},
    }
    patch = create_selection_followup_patch(
        {"chart_path": "charts/region.png", "chart_title": "地区销量对比", "ratio_x0": 0.1, "ratio_y0": 0.2, "ratio_x1": 0.4, "ratio_y1": 0.8},
        analysis_ir=analysis_ir,
        llm_client=FailingLLM(),
    )
    assert patch["question"]
    assert patch["patch_type"] == "chart_selection"
    assert patch["selection_spec"]["chart_path"] == "charts/region.png"


if __name__ == "__main__":
    test_analysis_ir_fallback_uses_existing_columns_only()
    test_selection_to_query_patch_creates_question()
    print("Analysis IR and selection follow-up tests passed.")
