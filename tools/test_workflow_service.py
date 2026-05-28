import json
import sys
import uuid
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services import workflow_service  # noqa: E402


class FakeRagService:
    def search(self, *args, **kwargs):
        return {"available": False, "results": []}


class FakeVisionParsingAgent:
    def parse_image(self, *, image_path, user_goal):
        return {
            "success": True,
            "image_type": "table",
            "columns": ["product", "sales"],
            "rows": [{"product": "A", "sales": 10}],
            "selected_table": {
                "columns": ["product", "sales"],
                "rows": [{"product": "A", "sales": 10}],
                "confidence": 0.9,
            },
            "tables": [],
            "chart_data": [],
            "confidence": 0.9,
            "warnings": [],
            "limitations": [],
        }


def _patch_common(task_type):
    originals = {
        "load_uploaded_dataset": workflow_service.load_uploaded_dataset,
        "generate_dataset_profile": workflow_service.generate_dataset_profile,
        "get_rag_service": workflow_service.get_rag_service,
        "format_rag_context": workflow_service.format_rag_context,
        "create_controller_plan": workflow_service.create_controller_plan,
        "get_uploaded_asset_type": workflow_service.get_uploaded_asset_type,
    }
    workflow_service.load_uploaded_dataset = lambda dataset_id: (Path("input.csv"), None)
    workflow_service.generate_dataset_profile = lambda dataset_id: {
        "dataset_id": dataset_id,
        "columns": ["product", "sales", "marketing_budget"],
        "numeric_summary": {"sales": {}, "marketing_budget": {}},
    }
    workflow_service.get_rag_service = lambda: FakeRagService()
    workflow_service.format_rag_context = lambda result: []
    workflow_service.get_uploaded_asset_type = lambda dataset_id: "tabular"
    workflow_service.create_controller_plan = lambda user_goal, dataset_profile, rag_context=None: {
        "task_type": task_type,
        "task_name": task_type,
        "reasoning_summary": "test",
        "steps": [],
        "required_columns": [],
        "analysis_methods": [],
        "charts": [],
        "expected_artifacts": [],
        "risks": [],
    }
    return originals


def _restore(originals):
    for name, value in originals.items():
        setattr(workflow_service, name, value)


def test_unified_workflow_routes_analysis_branch():
    originals = _patch_common("general_data_analysis")
    original_run_analysis = workflow_service.run_auto_repair_analysis_job
    job_id = f"test_workflow_analysis_{uuid.uuid4().hex}"

    def fake_run_analysis(dataset_id, user_goal, max_retries, timeout_seconds, job_id=None):
        job_dir = workflow_service.JOB_ROOT / str(job_id)
        (job_dir / "analysis_plan.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        return {
            "job_id": str(job_id),
            "dataset_id": dataset_id,
            "status": "success",
            "current_stage": "success",
            "attempts": [],
            "job_dir": str(job_dir),
            "analysis_plan_path": str(job_dir / "analysis_plan.json"),
        }

    workflow_service.run_auto_repair_analysis_job = fake_run_analysis
    try:
        result = workflow_service.run_workflow_job(
            job_id=job_id,
            dataset_id="dataset_a",
            user_goal="summarize the data",
        )
    finally:
        workflow_service.run_auto_repair_analysis_job = original_run_analysis
        _restore(originals)

    assert result["workflow_type"] == "auto_repair"
    assert result["task_type"] == "general_data_analysis"
    assert result["controller_plan_path"]
    assert result["analysis_plan_path"]


def test_unified_workflow_routes_prediction_branch():
    originals = _patch_common("what_if_prediction")
    original_run_prediction = workflow_service.run_prediction_job
    job_id = f"test_workflow_prediction_{uuid.uuid4().hex}"

    def fake_run_prediction(dataset_id, user_goal, max_retries, timeout_seconds, job_id=None):
        job_dir = workflow_service.JOB_ROOT / str(job_id)
        (job_dir / "hypothesis_plan.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        (job_dir / "prediction_plan.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
        return {
            "job_id": str(job_id),
            "dataset_id": dataset_id,
            "status": "success",
            "current_stage": "success",
            "attempts": [],
            "job_dir": str(job_dir),
            "hypothesis_plan_path": str(job_dir / "hypothesis_plan.json"),
            "prediction_plan_path": str(job_dir / "prediction_plan.json"),
        }

    workflow_service.run_prediction_job = fake_run_prediction
    try:
        result = workflow_service.run_workflow_job(
            job_id=job_id,
            dataset_id="dataset_p",
            user_goal="if marketing budget increases, predict sales",
        )
    finally:
        workflow_service.run_prediction_job = original_run_prediction
        _restore(originals)

    assert result["workflow_type"] == "what_if_prediction"
    assert result["task_type"] == "what_if_prediction"
    assert result["controller_plan_path"]
    assert result["hypothesis_plan_path"]
    assert result["prediction_plan_path"]


def test_unified_workflow_parses_image_before_controller():
    originals = _patch_common("general_data_analysis")
    extra_originals = {
        "VisionParsingAgent": workflow_service.VisionParsingAgent,
        "find_uploaded_image_file": workflow_service.find_uploaded_image_file,
        "get_dataset_dir": workflow_service.get_dataset_dir,
        "run_auto_repair_analysis_job": workflow_service.run_auto_repair_analysis_job,
    }
    job_id = f"test_workflow_image_{uuid.uuid4().hex}"
    dataset_dir = workflow_service.JOB_ROOT / f"test_upload_{uuid.uuid4().hex}"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    image_path = dataset_dir / "original.png"
    image_path.write_bytes(b"png")

    workflow_service.get_uploaded_asset_type = lambda dataset_id: "image"
    workflow_service.VisionParsingAgent = lambda: FakeVisionParsingAgent()
    workflow_service.find_uploaded_image_file = lambda dataset_id: image_path
    workflow_service.get_dataset_dir = lambda dataset_id: dataset_dir

    def fake_run_analysis(dataset_id, user_goal, max_retries, timeout_seconds, job_id=None):
        job_dir = workflow_service.JOB_ROOT / str(job_id)
        return {
            "job_id": str(job_id),
            "dataset_id": dataset_id,
            "status": "success",
            "current_stage": "success",
            "attempts": [],
            "job_dir": str(job_dir),
        }

    workflow_service.run_auto_repair_analysis_job = fake_run_analysis
    try:
        result = workflow_service.run_workflow_job(
            job_id=job_id,
            dataset_id="image_dataset",
            user_goal="analyze image table",
        )
    finally:
        for name, value in extra_originals.items():
            setattr(workflow_service, name, value)
        _restore(originals)

    assert result["asset_type"] == "image"
    assert result["visual_parse_result_path"]
    assert result["visual_extracted_dataset_path"]
    assert Path(result["visual_extracted_dataset_path"]).exists()
    assert result["visual_extraction_confidence"] == 0.9


if __name__ == "__main__":
    test_unified_workflow_routes_analysis_branch()
    test_unified_workflow_routes_prediction_branch()
    test_unified_workflow_parses_image_before_controller()
    print("Workflow service tests passed.")
