from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.controller_agent import ControllerAgent  # noqa: E402


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


def test_controller_uses_llm_json_plan():
    llm = FakeLLMClient(
        payload={
            "task_type": "sales_decline_analysis",
            "task_name": "Sales decline diagnosis",
            "reasoning_summary": "The goal asks why sales declined.",
            "steps": [{"name": "Profile sales trend"}],
            "required_columns": [],
            "analysis_methods": [],
            "charts": [],
            "expected_artifacts": [],
            "risks": [],
            "extra": "removed",
        }
    )
    plan = ControllerAgent(llm_client=llm).create_plan(
        user_goal="Analyze why sales declined",
        dataset_profile={"columns": ["date", "sales"]},
    )
    assert plan["task_type"] == "sales_decline_analysis"
    assert "extra" not in plan
    assert llm.last_messages[0]["role"] == "system"


def test_controller_falls_back_to_rule_plan():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    plan = ControllerAgent(llm_client=llm).create_plan(
        user_goal="general summary",
        dataset_profile={"columns": ["a", "b"]},
    )
    assert plan["task_type"] == "general_data_analysis"
    assert set(plan) == {
        "task_type",
        "task_name",
        "reasoning_summary",
        "steps",
        "required_columns",
        "analysis_methods",
        "charts",
        "expected_artifacts",
        "risks",
    }


def test_controller_accepts_prediction_task_type_from_llm():
    llm = FakeLLMClient(
        payload={
            "task_type": "what_if_prediction",
            "task_name": "What-if prediction",
            "reasoning_summary": "The goal asks about a hypothetical budget increase.",
            "steps": [],
            "required_columns": [],
            "analysis_methods": [],
            "charts": [],
            "expected_artifacts": [],
            "risks": [],
        }
    )
    plan = ControllerAgent(llm_client=llm).create_plan(
        user_goal="If marketing budget increases by 20%, predict sales changes",
        dataset_profile={"columns": ["product", "sales", "marketing_budget"]},
    )
    assert plan["task_type"] == "what_if_prediction"


def test_controller_rule_fallback_detects_prediction_goal():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    plan = ControllerAgent(llm_client=llm).create_plan(
        user_goal="如果营销预算增加 20%，预测销量可能如何变化",
        dataset_profile={"columns": ["商品", "销量", "营销预算"]},
    )
    assert plan["task_type"] == "what_if_prediction"


if __name__ == "__main__":
    test_controller_uses_llm_json_plan()
    test_controller_falls_back_to_rule_plan()
    test_controller_accepts_prediction_task_type_from_llm()
    test_controller_rule_fallback_detects_prediction_goal()
    print("ControllerAgent tests passed.")
