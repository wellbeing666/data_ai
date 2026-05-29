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


def test_validation_rejects_task_type_mismatch():
    job_id = f"test_validation_task_mismatch_{uuid.uuid4().hex}"
    job_dir = ROOT_DIR / "storage" / "jobs" / job_id
    charts_dir = job_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "controller_plan.json").write_text(
        json.dumps({"task_type": "general_data_analysis"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (job_dir / "execution_result.json").write_text(
        json.dumps({"success": True, "exit_code": 0, "timed_out": False}, ensure_ascii=False),
        encoding="utf-8",
    )
    (charts_dir / "class_average_score.png").write_bytes(b"png")
    analysis_result = {
        "success": True,
        "task_type": "grade_analysis",
        "summary": [{"class_name": "NAmes", "student_count": 225, "average_score": 145847.08}],
        "charts": [str(charts_dir / "class_average_score.png")],
    }
    (job_dir / "analysis_result.json").write_text(
        json.dumps(analysis_result, ensure_ascii=False),
        encoding="utf-8",
    )
    (job_dir / "report_data.json").write_text(
        json.dumps({"summary": "wrong template", "tables": [{"rows": analysis_result["summary"]}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_job_outputs(job_id)

    assert result["passed"] is False
    assert result["should_retry"] is True
    assert any(issue["issue_type"] == "task_type_mismatch" for issue in result["issues"])


def test_validation_allows_missing_optional_p_values():
    job_id = f"test_validation_optional_p_value_{uuid.uuid4().hex}"
    job_dir = ROOT_DIR / "storage" / "jobs" / job_id
    charts_dir = job_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "controller_plan.json").write_text(
        json.dumps({"task_type": "general_data_analysis"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (job_dir / "execution_result.json").write_text(
        json.dumps({"success": True, "exit_code": 0, "timed_out": False}, ensure_ascii=False),
        encoding="utf-8",
    )
    (charts_dir / "anova.png").write_bytes(b"png")
    analysis_result = {
        "success": True,
        "task_type": "general_data_analysis",
        "analysis_summary": {
            "categorical_anova": {
                "Neighborhood": {
                    "group_count": 25,
                    "mean": 180000.0,
                    "p_value_approx": None,
                },
                "MSZoning": {
                    "group_count": 5,
                    "mean": 165000.0,
                    "p_value_approx": "not_calculated",
                },
            }
        },
        "charts": [str(charts_dir / "anova.png")],
    }
    report_data = {
        "summary": "ok",
        "tables": [{"rows": [{"field": "Neighborhood", "mean": 180000.0, "p_value_approx": None}]}],
        "key_findings": [{"evidence": "analysis_result.analysis_summary", "text": "ok"}],
        "anova_results": {
            "Neighborhood": {"mean": 180000.0, "p_value_approx": None},
            "MSZoning": {"mean": 165000.0, "p_value_approx": "not_calculated"},
        },
    }
    (job_dir / "analysis_result.json").write_text(
        json.dumps(analysis_result, ensure_ascii=False),
        encoding="utf-8",
    )
    (job_dir / "report_data.json").write_text(
        json.dumps(report_data, ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_job_outputs(job_id)

    assert result["passed"] is True
    assert not any(issue["issue_type"] in {"empty_metric", "invalid_metric"} for issue in result["issues"])


def test_validation_reports_environment_interruption():
    job_id = f"test_validation_environment_interrupted_{uuid.uuid4().hex}"
    job_dir = ROOT_DIR / "storage" / "jobs" / job_id
    charts_dir = job_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    (job_dir / "execution_result.json").write_text(
        json.dumps(
            {
                "success": False,
                "exit_code": 3221225786,
                "timed_out": False,
                "error": {"type": "EnvironmentInterrupted"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (charts_dir / "placeholder.png").write_bytes(b"png")
    (job_dir / "analysis_result.json").write_text(
        json.dumps({"success": True, "task_type": "general_data_analysis", "summary": {"count": 1}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (job_dir / "report_data.json").write_text(
        json.dumps({"summary": "ok", "tables": [{"rows": [{"count": 1}]}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_job_outputs(job_id)

    assert result["passed"] is False
    assert any(issue["issue_type"] == "environment_interrupted" for issue in result["issues"])
    assert not any(issue["issue_type"] == "execution_failed" for issue in result["issues"])


if __name__ == "__main__":
    test_validation_ignores_repair_context_runtime_metrics()
    test_validation_rejects_task_type_mismatch()
    test_validation_allows_missing_optional_p_values()
    test_validation_reports_environment_interruption()
    print("Validation service tests passed.")
