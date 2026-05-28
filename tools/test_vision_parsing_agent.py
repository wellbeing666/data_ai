import csv
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.vision_parsing_agent import (  # noqa: E402
    normalize_visual_parse_result,
    write_visual_extracted_csv,
)


def test_normalizes_selected_table_and_writes_csv():
    result = normalize_visual_parse_result(
        {
            "success": True,
            "image_type": "table",
            "selected_table": {
                "columns": ["product", "sales"],
                "rows": [["A", 10], ["B", 20]],
                "confidence": 0.86,
            },
        }
    )
    assert result["success"] is True
    assert result["columns"] == ["product", "sales"]
    assert result["rows"][0] == {"product": "A", "sales": 10}
    assert result["confidence"] == 0.86

    with tempfile.TemporaryDirectory() as temp_dir:
        csv_path = write_visual_extracted_csv(result, Path(temp_dir) / "visual_extracted.csv")
        rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8-sig")))
    assert rows == [{"product": "A", "sales": "10"}, {"product": "B", "sales": "20"}]


def test_accepts_json_string_response():
    result = normalize_visual_parse_result(
        '{"success": true, "columns": ["month", "revenue"], "rows": [{"month": "Jan", "revenue": 100}]}'
    )
    assert result["success"] is True
    assert result["columns"] == ["month", "revenue"]
    assert result["rows"] == [{"month": "Jan", "revenue": 100}]


def test_accepts_top_level_row_array_response():
    result = normalize_visual_parse_result(
        [
            {"region": "East", "orders": 12},
            {"region": "West", "orders": 9},
        ]
    )
    assert result["success"] is True
    assert result["columns"] == ["region", "orders"]
    assert result["rows"][1] == {"region": "West", "orders": 9}


def test_accepts_wrapped_data_response():
    result = normalize_visual_parse_result(
        {
            "result": {
                "data": [
                    {"category": "A", "profit": 30},
                    {"category": "B", "profit": 20},
                ]
            }
        }
    )
    assert result["success"] is True
    assert result["columns"] == ["category", "profit"]


def test_accepts_chart_data_as_table_fallback():
    result = normalize_visual_parse_result(
        {
            "success": True,
            "image_type": "chart",
            "chart_data": [
                {"quarter": "Q1", "value": 15},
                {"quarter": "Q2", "value": 18},
            ],
        }
    )
    assert result["success"] is True
    assert result["selected_table"]["columns"] == ["quarter", "value"]


def test_rejects_too_little_structured_data():
    result = normalize_visual_parse_result(
        {
            "success": True,
            "selected_table": {
                "columns": ["product"],
                "rows": [["A"]],
            },
        }
    )
    assert result["success"] is False
    assert result["warnings"]


if __name__ == "__main__":
    test_normalizes_selected_table_and_writes_csv()
    test_accepts_json_string_response()
    test_accepts_top_level_row_array_response()
    test_accepts_wrapped_data_response()
    test_accepts_chart_data_as_table_fallback()
    test_rejects_too_little_structured_data()
    print("Vision parsing agent tests passed.")
