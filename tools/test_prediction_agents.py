import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.hypothesis_agent import create_hypothesis_plan  # noqa: E402
from app.agents.prediction_agent import create_prediction_plan  # noqa: E402


class FailingLLM:
    def chat_json(self, *args, **kwargs):
        raise RuntimeError("LLM unavailable")


class HallucinatingLLM:
    def chat_json(self, *args, **kwargs):
        return {
            "task_type": "what_if_prediction",
            "prediction_goal": "test",
            "target_metric": "不存在目标",
            "intervention": {
                "variable": "广告投放",
                "column": "不存在字段",
                "change_type": "relative",
                "change_value": 0.2,
            },
            "entity_dimension": "不存在维度",
            "feature_columns": ["营销预算", "不存在特征"],
            "model_candidates": ["linear_regression"],
            "fallback_strategy": "rule fallback",
            "charts": ["bar"],
            "limitations": [],
        }


def _dataset_profile():
    return {
        "columns": ["商品", "销量", "营销预算", "价格"],
        "numeric_summary": {"销量": {}, "营销预算": {}, "价格": {}},
        "text_summary": {"商品": {}},
    }


def test_rule_hypothesis_parses_chinese_what_if_goal():
    plan = create_hypothesis_plan(
        "如果下个月营销预算增加 20%，哪些商品的销量最可能提升？",
        _dataset_profile(),
        llm_client=FailingLLM(),
    )

    assert plan["scenario_type"] == "what_if_prediction"
    assert plan["intervention"]["change_type"] == "relative"
    assert abs(plan["intervention"]["change_value"] - 0.2) < 0.0001
    assert plan["intervention"]["matched_column"] == "营销预算"
    assert plan["target_metric"]["matched_column"] == "销量"
    assert plan["entity_dimension"]["matched_column"] == "商品"


def test_prediction_plan_falls_back_to_existing_columns_only():
    dataset_profile = _dataset_profile()
    hypothesis = create_hypothesis_plan(
        "如果下个月营销预算增加 20%，哪些商品的销量最可能提升？",
        dataset_profile,
        llm_client=FailingLLM(),
    )
    plan = create_prediction_plan(
        "如果下个月营销预算增加 20%，哪些商品的销量最可能提升？",
        dataset_profile,
        hypothesis,
        llm_client=FailingLLM(),
    )

    assert plan["task_type"] == "what_if_prediction"
    assert plan["target_metric"] == "销量"
    assert plan["intervention"]["column"] == "营销预算"
    assert plan["entity_dimension"] == "商品"
    assert set(plan["feature_columns"]).issubset(set(dataset_profile["columns"]))
    assert "rule_based_simulation" in plan["model_candidates"]


def test_prediction_plan_filters_hallucinated_columns():
    dataset_profile = _dataset_profile()
    hypothesis = {
        "intervention": {"matched_column": "营销预算", "change_type": "relative", "change_value": 0.2},
        "target_metric": {"matched_column": "销量"},
        "entity_dimension": {"matched_column": "商品"},
    }
    plan = create_prediction_plan(
        "如果营销预算增加 20%，销量会怎样？",
        dataset_profile,
        hypothesis,
        llm_client=HallucinatingLLM(),
    )

    assert plan["target_metric"] == "销量"
    assert plan["intervention"]["column"] == "营销预算"
    assert plan["entity_dimension"] == "商品"
    assert plan["feature_columns"] == ["营销预算"]


if __name__ == "__main__":
    test_rule_hypothesis_parses_chinese_what_if_goal()
    test_prediction_plan_falls_back_to_existing_columns_only()
    test_prediction_plan_filters_hallucinated_columns()
    print("Prediction agent tests passed.")
