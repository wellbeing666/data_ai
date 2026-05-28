import json
import sys
import uuid
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.validation_service import validate_job_outputs  # noqa: E402


def test_validation_ignores_repair_context_runtime_metrics():
    job_id = f"test_validation_repair_context_{uuid.uuid4().hex}"
    job_dir = ROOT_DIR / "storage" / "jobs" / job_id
    charts_dir = job_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "execution_result.json").write_text(
        json.dumps({"success": True, "exit_code": 0, "timed_out": False}, ensure_ascii=False),
        encoding="utf-8",
    )
    (charts_dir / "class_pass_rate.png").write_bytes(b"png")
    analysis_result = {
        "success": True,
        "task_type": "grade_analysis",
        "summary": [
            {
                "class_name": "A",
                "student_count": 10,
                "average_score": 82.5,
                "pass_rate": 0.9,
                "excellent_rate": 0.2,
            }
        ],
        "charts": [str(charts_dir / "class_pass_rate.png")],
        "repair_context": {
            "previous_execution_result": {
                "duration_ms": 1234,
                "artifacts": [{"size_bytes": 99999}],
            },
            "previous_validation_result": {
                "should_retry": True,
            },
        },
    }
    (job_dir / "analysis_result.json").write_text(
        json.dumps(analysis_result, ensure_ascii=False),
        encoding="utf-8",
    )
    (job_dir / "report_data.json").write_text(
        json.dumps(
            {
                "summary": "ok",
                "tables": [{"rows": analysis_result["summary"]}],
                "key_findings": [{"evidence": "analysis_result.summary", "text": "A pass rate is 0.9."}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = validate_job_outputs(job_id)

    assert result["passed"] is True
    assert result["issues"] == []


if __name__ == "__main__":
    test_validation_ignores_repair_context_runtime_metrics()
    print("Validation service tests passed.")
