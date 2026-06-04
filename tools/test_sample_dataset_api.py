import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

(ROOT_DIR / "storage").mkdir(exist_ok=True)

from fastapi.testclient import TestClient  # noqa: E402

import app.services.sample_dataset_service as sample_module  # noqa: E402
from app.main import app  # noqa: E402


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        sample_module.UPLOAD_ROOT = Path(temp_dir)
        client = TestClient(app)

        listing = client.get("/api/datasets/samples")
        assert listing.status_code == 200, listing.text
        sample_types = {item["sample_type"] for item in listing.json()["samples"]}
        assert {"sales_decline", "grade_scores", "survey_feedback", "health_activity", "ecommerce_orders"}.issubset(sample_types)

        created = client.post("/api/datasets/samples", json={"sample_type": "sales_decline"})
        assert created.status_code == 200, created.text
        payload = created.json()
        assert payload["asset_type"] == "tabular"
        assert payload["file_type"] == "csv"
        assert payload["recommended_goal"]
        assert Path(payload["file_path"]).exists()
        assert Path(payload["file_path"]).read_text(encoding="utf-8-sig").startswith("日期,月份,地区")

        rejected = client.post("/api/datasets/samples", json={"sample_type": "unknown"})
        assert rejected.status_code == 400

    print("Sample dataset API tests passed.")


if __name__ == "__main__":
    main()
