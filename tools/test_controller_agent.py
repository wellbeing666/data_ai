import json
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


def test_controller_fallback_uses_raw_goal_from_analysis_ir_payload():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    raw_goal = "分析销量从 2026 年 1 月到 6 月的变化趋势，识别下降阶段，并按地区、渠道和商品类别拆解可能原因。"
    compiled_goal = "Analysis IR + Delta JSON:\n" + json.dumps(
        {
            "analysis_ir": {
                "task_type": "sales_decline_analysis",
                "normalized_goal": raw_goal,
                "guardrails": ["相关性不等于因果，预测不等于承诺。"],
            },
            "delta": {"stage": "controller", "raw_user_goal": raw_goal},
        },
        ensure_ascii=False,
    )
    plan = ControllerAgent(llm_client=llm).create_plan(
        user_goal=compiled_goal,
        dataset_profile={"columns": ["日期", "地区", "渠道", "商品类别", "销量", "销售额"]},
    )
    assert plan["task_type"] == "sales_decline_analysis"


def test_controller_corrects_sales_decline_misclassified_as_prediction():
    llm = FakeLLMClient(
        payload={
            "task_type": "what_if_prediction",
            "task_name": "What-if prediction",
            "reasoning_summary": "Incorrectly treated as prediction.",
            "steps": [],
            "required_columns": [],
            "analysis_methods": [],
            "charts": [],
            "expected_artifacts": [],
            "risks": [],
        }
    )
    plan = ControllerAgent(llm_client=llm).create_plan(
        user_goal="分析销量从 2026 年 1 月到 6 月的变化趋势，识别下降阶段，并按地区、渠道和商品类别拆解可能原因。",
        dataset_profile={"columns": ["日期", "地区", "渠道", "商品类别", "销量", "销售额"]},
    )
    assert plan["task_type"] == "sales_decline_analysis"


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
    test_controller_fallback_uses_raw_goal_from_analysis_ir_payload()
    test_controller_corrects_sales_decline_misclassified_as_prediction()
    test_controller_rule_fallback_detects_prediction_goal()
    print("ControllerAgent tests passed.")

