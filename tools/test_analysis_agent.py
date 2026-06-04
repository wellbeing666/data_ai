from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.analysis_agent import AnalysisAgent  # noqa: E402


PROFILE = {
    "columns": ["date", "region", "sales", "orders"],
    "numeric_summary": {
        "sales": {"min": 1, "max": 10, "mean": 5},
        "orders": {"min": 1, "max": 4, "mean": 2},
    },
}

DATA_UNDERSTANDING = {
    "date_columns": ["date"],
    "target_columns": ["sales"],
    "dimension_columns": ["region"],
    "numeric_columns": ["sales", "orders"],
}

SALES_CONTROLLER_PLAN = {"task_type": "sales_decline_analysis"}


class FakeLLMClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.last_messages = None

    def chat_json(self, messages, temperature=0.1):
        self.last_messages = messages
        if self.error is not None:
            raise self.error
        return self.payload


def test_filters_nonexistent_fields_and_adds_causal_limitation():
    llm = FakeLLMClient(
        payload={
            "analysis_goal": "Find possible reasons for sales decline",
            "methods": ["Segment comparison"],
            "grouping_dimensions": ["region", "invented_region"],
            "metrics": ["sales", "fake_metric"],
            "chart_plan": [
                {
                    "chart_type": "line",
                    "title": "Sales trend",
                    "x": "date",
                    "y": "fake_metric",
                    "group_by": "region",
                }
            ],
            "statistical_checks": ["Check missing values"],
            "limitations": [],
        }
    )
    result = AnalysisAgent(llm_client=llm).create_plan(
        user_goal="Find possible reasons for sales decline",
        dataset_profile=PROFILE,
        data_understanding_result=DATA_UNDERSTANDING,
        controller_plan=SALES_CONTROLLER_PLAN,
    )
    assert result["grouping_dimensions"] == ["region"]
    assert result["metrics"] == ["sales"]
    assert result["chart_plan"][0]["y"] == ""
    assert any(("可能原因" in item or "相关信号" in item or "确定因果" in item) for item in result["limitations"])
    assert llm.last_messages[0]["role"] == "system"


def test_fallback_rule_based_analysis_plan():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    result = AnalysisAgent(llm_client=llm).create_plan(
        user_goal="Find possible reasons for sales decline",
        dataset_profile=PROFILE,
        data_understanding_result=DATA_UNDERSTANDING,
        controller_plan=SALES_CONTROLLER_PLAN,
    )
    assert result["metrics"] == ["sales"]
    assert result["grouping_dimensions"] == ["region"]
    assert result["chart_plan"][0]["chart_type"] == "line"
    assert any(("确定因果" in item or "相关信号" in item or "可能原因" in item) for item in result["limitations"])


if __name__ == "__main__":
    test_filters_nonexistent_fields_and_adds_causal_limitation()
    test_fallback_rule_based_analysis_plan()
    print("AnalysisAgent tests passed.")
