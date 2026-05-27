import json
import sys
import uuid
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.prediction_validation_service import validate_prediction_outputs  # noqa: E402


def test_prediction_validation_accepts_required_artifacts():
    job_id = f"test_prediction_validation_{uuid.uuid4().hex}"
    job_dir = ROOT_DIR / "storage" / "jobs" / job_id
    charts_dir = job_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "execution_result.json").write_text(
        json.dumps({"success": True}, ensure_ascii=False),
        encoding="utf-8",
    )
    (job_dir / "prediction_result.json").write_text(
        json.dumps(
            {
                "task_type": "what_if_prediction",
                "scenario_summary": "如果营销预算增加 20%，销量变化估计",
                "target_metric": "销量",
                "intervention": {"column": "营销预算", "change_type": "relative", "change_value": 0.2},
                "entity_dimension": "商品",
                "top_impacted_entities": [
                    {
                        "entity": "A",
                        "baseline_value": 100,
                        "predicted_value": 110,
                        "absolute_change": 10,
                        "percent_change": 0.1,
                        "direction": "increase",
                        "explanation": "模拟显示可能提升。",
                    }
                ],
                "baseline_summary": {"mean": 100},
                "predicted_summary": {"mean": 110},
                "model_info": {"method": "rule_based_simulation", "training_rows": 1},
                "limitations": ["测试样本"],
                "charts": [str(charts_dir / "top.png")],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (job_dir / "report_data.json").write_text(json.dumps({"summary": "ok"}), encoding="utf-8")
    (charts_dir / "top.png").write_bytes(b"png")

    result = validate_prediction_outputs(job_id)

    assert result["passed"] is True
    assert result["issues"] == []
    assert (job_dir / "prediction_validation_result.json").exists()
    assert (job_dir / "validation_result.json").exists()


if __name__ == "__main__":
    test_prediction_validation_accepts_required_artifacts()
    print("Prediction validation tests passed.")
