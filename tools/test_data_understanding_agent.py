from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.data_understanding_agent import DataUnderstandingAgent  # noqa: E402


PROFILE = {
    "columns": ["date", "region", "sales", "fake_safe"],
    "dtypes": {
        "date": "object",
        "region": "object",
        "sales": "float64",
        "fake_safe": "object",
    },
    "numeric_summary": {"sales": {"min": 1, "max": 10, "mean": 5}},
    "text_summary": {
        "region": {"unique_values": ["North", "South"]},
        "fake_safe": {"unique_values": ["note"]},
    },
    "missing_values": {
        "date": {"count": 0, "ratio": 0.0},
        "region": {"count": 0, "ratio": 0.0},
        "sales": {"count": 1, "ratio": 0.1},
        "fake_safe": {"count": 0, "ratio": 0.0},
    },
}


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


def test_filters_nonexistent_model_columns():
    llm = FakeLLMClient(
        payload={
            "columns": [
                {
                    "name": "sales",
                    "semantic_type": "metric",
                    "business_meaning": "Sales amount.",
                    "confidence": 0.9,
                },
                {
                    "name": "invented_column",
                    "semantic_type": "metric",
                    "business_meaning": "Should be removed.",
                    "confidence": 0.9,
                },
            ],
            "date_columns": ["date", "invented_column"],
            "target_columns": ["sales", "invented_column"],
            "dimension_columns": ["region"],
            "numeric_columns": ["sales"],
            "quality_issues": [],
            "suitability_score": 0.8,
            "warnings": [],
        }
    )
    result = DataUnderstandingAgent(llm_client=llm).understand(
        user_goal="Analyze sales decline by region",
        dataset_profile=PROFILE,
    )
    column_names = [item["name"] for item in result["columns"]]
    assert "invented_column" not in column_names
    assert set(column_names) == set(PROFILE["columns"])
    assert result["target_columns"] == ["sales"]
    assert result["date_columns"] == ["date"]
    assert llm.last_messages[0]["role"] == "system"


def test_fallback_rule_based_understanding():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    result = DataUnderstandingAgent(llm_client=llm).understand(
        user_goal="Analyze sales decline trend",
        dataset_profile=PROFILE,
    )
    assert result["numeric_columns"] == ["sales"]
    assert "sales" in result["target_columns"]
    assert "region" in result["dimension_columns"]
    assert result["quality_issues"][0]["column"] == "sales"


if __name__ == "__main__":
    test_filters_nonexistent_model_columns()
    test_fallback_rule_based_understanding()
    print("DataUnderstandingAgent tests passed.")
