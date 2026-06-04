from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.agents.explanation_agent import ExplanationAgent  # noqa: E402


GRADE_RESULT = {
    "task_type": "grade_analysis",
    "summary": [
        {
            "class_name": "Class A",
            "average_score": 88,
            "pass_rate": 0.95,
            "excellent_rate": 0.35,
        },
        {
            "class_name": "Class B",
            "average_score": 76,
            "pass_rate": 0.82,
            "excellent_rate": 0.12,
        },
    ],
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


def test_llm_explanation_normalizes_chart_paths():
    llm = FakeLLMClient(
        payload={
            "summary": "Sales declined because of channel issues.",
            "key_findings": ["Channel changed."],
            "chart_explanations": [
                {"chart": "/tmp/allowed.png", "explanation": "Allowed"},
                {"chart": "/tmp/not_allowed.png", "explanation": "Filtered"},
            ],
            "recommendations": ["Investigate channel."],
            "limitations": [],
            "ppt_outline": [
                {
                    "title": "Sales decline",
                    "bullets": ["Channel may be related."],
                    "chart": "/tmp/not_allowed.png",
                }
            ],
        }
    )
    result = ExplanationAgent(llm_client=llm).explain(
        user_goal="Analyze sales decline reasons",
        dataset_profile={"columns": ["date", "sales"]},
        analysis_result={"success": True},
        chart_paths=["/tmp/allowed.png"],
        limitations=["No experiment data."],
    )
    assert result["chart_explanations"][0]["chart"] == "/tmp/allowed.png"
    assert result["chart_explanations"][1]["chart"] == ""
    assert result["ppt_outline"][0]["chart"] == ""
    assert any(("可能" in item or "因果" in item or "相关" in item) for item in result["limitations"])
    assert any(word in result["summary"] for word in ("可能", "相关", "信号", "待验证"))


def test_grade_fallback_mentions_class_pass_and_excellent_rates():
    llm = FakeLLMClient(error=RuntimeError("llm unavailable"))
    result = ExplanationAgent(llm_client=llm).explain(
        user_goal="Summarize grade analysis by class",
        dataset_profile={"columns": ["class", "score"]},
        analysis_result=GRADE_RESULT,
        chart_paths=["/tmp/score.png"],
        limitations=[],
    )
    joined = " ".join([result["summary"], *result["key_findings"]]).lower()
    assert "班级" in joined
    assert "及格率" in joined
    assert "优秀率" in joined
    assert result["ppt_outline"][1]["chart"] == "/tmp/score.png"


if __name__ == "__main__":
    test_llm_explanation_normalizes_chart_paths()
    test_grade_fallback_mentions_class_pass_and_excellent_rates()
    print("ExplanationAgent tests passed.")
