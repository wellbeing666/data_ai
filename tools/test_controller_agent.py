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


if __name__ == "__main__":
    test_controller_uses_llm_json_plan()
    test_controller_falls_back_to_rule_plan()
    print("ControllerAgent tests passed.")
