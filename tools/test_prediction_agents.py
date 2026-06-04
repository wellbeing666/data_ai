import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.hypothesis_agent import create_hypothesis_plan  # noqa: E402
from app.agents.prediction_agent import create_prediction_plan  # noqa: E402
from app.agents.prediction_code_agent import PredictionCodeAgent, RuleBasedPredictionCodeAgent  # noqa: E402


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


class FakePredictionCodeLLM:
    def __init__(self, content):
        self.content = content

    def chat(self, *args, **kwargs):
        return self.content


PREDICTION_INPUT_FILE = r"C:\workspace\data.csv"
PREDICTION_OUTPUT_DIR = r"C:\workspace\storage\jobs\prediction1"

VALID_PREDICTION_SCRIPT_WITHOUT_CONSTANTS = r'''import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
    plt.rcParams["axes.unicode_minus"] = False
    chart_path = CHARTS_DIR / "chart.png"
    plt.figure()
    plt.title("\u9884\u6d4b\u7ed3\u679c")
    plt.xlabel("\u5bf9\u8c61")
    plt.ylabel("\u6307\u6807\u503c")
    plt.plot([1, 2], [1, 2])
    plt.savefig(chart_path)
    plt.close()
    payload = {"task_type": "what_if_prediction", "charts": [str(chart_path)]}
    (OUTPUT_DIR / "prediction_result.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (OUTPUT_DIR / "report_data.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
'''


def _dataset_profile():
    return {
        "columns": ["商品", "销量", "营销预算", "价格"],
        "numeric_summary": {"销量": {}, "营销预算": {}, "价格": {}},
        "text_summary": {"商品": {}},
    }


def _house_price_profile():
    return {
        "columns": ["Id", "YearBuilt", "YrSold", "GrLivArea", "OverallQual", "Neighborhood", "SalePrice"],
        "numeric_summary": {
            "Id": {},
            "YearBuilt": {},
            "YrSold": {},
            "GrLivArea": {},
            "OverallQual": {},
            "SalePrice": {},
        },
        "text_summary": {"Neighborhood": {}},
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


def test_rule_prediction_code_uses_chinese_chart_text_and_fonts():
    script = RuleBasedPredictionCodeAgent().generate_script(
        input_file="storage/uploads/demo/input.csv",
        output_dir="storage/jobs/demo",
        dataset_profile=_dataset_profile(),
        hypothesis_plan={
            "scenario_summary": "如果营销预算增加 20%，销量会怎样？",
            "intervention": {"matched_column": "营销预算", "change_type": "relative", "change_value": 0.2},
            "target_metric": {"matched_column": "销量"},
            "entity_dimension": {"matched_column": "商品"},
        },
        prediction_plan={
            "task_type": "what_if_prediction",
            "prediction_goal": "如果营销预算增加 20%，销量会怎样？",
            "target_metric": "销量",
            "intervention": {"column": "营销预算", "change_type": "relative", "change_value": 0.2},
            "entity_dimension": "商品",
            "feature_columns": ["营销预算"],
            "limitations": [],
        },
    )

    assert "font.sans-serif" in script
    assert "axes.unicode_minus" in script
    assert "预测变化最大的对象" in script
    assert "预测绝对变化" in script
    assert "基准值与预测值对比" in script
    assert "基准值" in script
    assert "预测值" in script
    assert "Top predicted changes" not in script
    assert "Baseline vs predicted" not in script


def test_prediction_code_injects_runtime_constants():
    script = PredictionCodeAgent(
        llm_client=FakePredictionCodeLLM(VALID_PREDICTION_SCRIPT_WITHOUT_CONSTANTS)
    ).generate_script(
        input_file=PREDICTION_INPUT_FILE,
        output_dir=PREDICTION_OUTPUT_DIR,
        dataset_profile=_dataset_profile(),
        hypothesis_plan={"scenario_summary": "test"},
        prediction_plan={"task_type": "what_if_prediction"},
        attempt=1,
    )

    assert f'INPUT_FILE = Path(r"{PREDICTION_INPUT_FILE}")' in script
    assert f'OUTPUT_DIR = Path(r"{PREDICTION_OUTPUT_DIR}")' in script
    assert 'CHARTS_DIR = OUTPUT_DIR / "charts"' in script


def test_house_age_hypothesis_maps_to_yearbuilt():
    plan = create_hypothesis_plan(
        "如果房龄增加 5 年，预测价格会降低多少？",
        _house_price_profile(),
        llm_client=FailingLLM(),
    )

    assert plan["scenario_type"] == "what_if_prediction"
    assert plan["intervention"]["variable"] == "房龄"
    assert plan["intervention"]["matched_column"] == "YearBuilt"
    assert plan["intervention"]["change_type"] == "absolute"
    assert abs(plan["intervention"]["change_value"] - 5.0) < 0.0001
    assert plan["intervention"]["unit"] == "年"
    assert plan["target_metric"]["matched_column"] == "SalePrice"


def test_house_age_prediction_plan_is_supported_with_yearbuilt():
    dataset_profile = _house_price_profile()
    hypothesis = create_hypothesis_plan(
        "如果房龄增加 5 年，预测价格会降低多少？",
        dataset_profile,
        llm_client=FailingLLM(),
    )
    plan = create_prediction_plan(
        "如果房龄增加 5 年，预测价格会降低多少？",
        dataset_profile,
        hypothesis,
        llm_client=FailingLLM(),
    )

    assert plan["task_type"] == "what_if_prediction"
    assert plan["is_supported"] is True
    assert plan["target_metric"] == "SalePrice"
    assert plan["intervention"]["column"] == "YearBuilt"
    assert plan["intervention"]["change_type"] == "absolute"
    assert abs(plan["intervention"]["change_value"] - 5.0) < 0.0001
    assert "unsupported_missing_required_column" not in plan["model_candidates"]


def test_rule_prediction_code_handles_house_age_yearbuilt_direction():
    script = RuleBasedPredictionCodeAgent().generate_script(
        input_file="storage/uploads/demo/house.csv",
        output_dir="storage/jobs/demo_house_age",
        dataset_profile=_house_price_profile(),
        hypothesis_plan={
            "scenario_summary": "如果房龄增加 5 年，预测价格会降低多少？",
            "intervention": {
                "variable": "房龄",
                "matched_column": "YearBuilt",
                "change_type": "absolute",
                "change_value": 5,
                "unit": "年",
            },
            "target_metric": {"matched_column": "SalePrice"},
            "entity_dimension": {"matched_column": "Id"},
        },
        prediction_plan={
            "task_type": "what_if_prediction",
            "prediction_goal": "如果房龄增加 5 年，预测价格会降低多少？",
            "target_metric": "SalePrice",
            "intervention": {"column": "YearBuilt", "change_type": "absolute", "change_value": 5, "unit": "年"},
            "entity_dimension": "Id",
            "feature_columns": ["YearBuilt", "GrLivArea", "OverallQual", "Neighborhood"],
            "limitations": [],
        },
    )

    assert "房龄变化按建造年份反向调整" in script
    assert "data_unit_change = -change_value" in script
    assert "YearBuilt" in script
    assert "平方米换算" in script


if __name__ == "__main__":
    test_rule_hypothesis_parses_chinese_what_if_goal()
    test_prediction_plan_falls_back_to_existing_columns_only()
    test_prediction_plan_filters_hallucinated_columns()
    test_rule_prediction_code_uses_chinese_chart_text_and_fonts()
    test_prediction_code_injects_runtime_constants()
    test_house_age_hypothesis_maps_to_yearbuilt()
    test_house_age_prediction_plan_is_supported_with_yearbuilt()
    test_rule_prediction_code_handles_house_age_yearbuilt_direction()
    print("Prediction agent tests passed.")

