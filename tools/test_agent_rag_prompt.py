import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.analysis_agent import build_user_prompt as build_analysis_prompt
from app.agents.controller_agent import build_user_prompt as build_controller_prompt
from app.agents.data_understanding_agent import build_user_prompt as build_understanding_prompt
from app.agents.explanation_agent import build_user_prompt as build_explanation_prompt


def main() -> None:
    dataset_profile = {"columns": ["班级", "成绩"], "numeric_summary": {"成绩": {}}}
    rag_context = [{"source": "metrics.md", "chunk": "及格率=及格人数/总人数"}]

    controller = build_controller_prompt("按班级统计成绩", dataset_profile, rag_context)
    understanding = build_understanding_prompt("按班级统计成绩", dataset_profile, rag_context)
    analysis = build_analysis_prompt(
        "按班级统计成绩",
        dataset_profile,
        {"target_columns": ["成绩"]},
        {"task_type": "grade_analysis"},
        rag_context,
    )
    explanation = build_explanation_prompt(
        "按班级统计成绩",
        dataset_profile,
        {"task_type": "grade_analysis"},
        [],
        [],
        rag_context,
    )

    for prompt in (controller, understanding, analysis, explanation):
        assert "Retrieved business knowledge JSON" in prompt
        assert "及格率" in prompt
        assert "dataset_profile" in prompt or "analysis_result" in prompt

    print("Agent RAG prompt tests passed.")


if __name__ == "__main__":
    main()
