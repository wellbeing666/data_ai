import json
import math
from pathlib import Path
from typing import Any

from app.services.llm_client import LLMClient, get_llm_client


SYSTEM_PROMPT = """You are the analysis roadmap Agent of an AI-native data analysis workbench.

Convert the user's goal and controller plan into a concise visual execution roadmap. Return only valid JSON.
All user-facing text must be Simplified Chinese. Do not invent data columns.
Use short node labels, not long paragraphs.

Required schema:
{
  "title": "路线图标题",
  "goal": "用户目标",
  "workflow_type": "auto_repair|what_if_prediction|insight_mining",
  "graph_type": "flowchart|hierarchy|network",
  "mermaid_code": "flowchart TD\n  S1[步骤] --> S2[步骤]",
  "steps": [
    {
      "step_id": "S1",
      "agent": "Agent 名称",
      "title": "步骤标题",
      "description": "步骤说明",
      "status_stage": "controller",
      "depends_on": [],
      "expected_artifacts": []
    }
  ]
}
"""


def build_user_prompt(
    user_goal: str,
    dataset_profile: dict[str, Any],
    controller_plan: dict[str, Any],
    workflow_type: str,
) -> str:
    return """Build a concise visual roadmap for this analysis workflow.

User goal:
{user_goal}

Workflow type:
{workflow_type}

Dataset columns:
{columns}

Controller plan JSON:
{controller_plan}

Return only the required JSON object.
""".format(
        user_goal=user_goal,
        workflow_type=workflow_type,
        columns=json.dumps(dataset_profile.get("columns") or [], ensure_ascii=False),
        controller_plan=json.dumps(controller_plan, ensure_ascii=False, indent=2),
    )


class RoadmapAgent:
    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client or get_llm_client()

    def create(
        self,
        user_goal: str,
        dataset_profile: dict[str, Any],
        controller_plan: dict[str, Any],
        workflow_type: str,
    ) -> dict[str, Any]:
        fallback = create_rule_based_roadmap(user_goal, dataset_profile, controller_plan, workflow_type)
        try:
            result = self.llm_client.chat_json(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(user_goal, dataset_profile, controller_plan, workflow_type)},
                ],
                temperature=0.1,
            )
            return _normalize_result(result, fallback)
        except Exception:
            return fallback


def create_analysis_roadmap(
    user_goal: str,
    dataset_profile: dict[str, Any],
    controller_plan: dict[str, Any],
    workflow_type: str,
    llm_client: LLMClient | None = None,
) -> dict[str, Any]:
    return RoadmapAgent(llm_client=llm_client).create(
        user_goal=user_goal,
        dataset_profile=dataset_profile,
        controller_plan=controller_plan,
        workflow_type=workflow_type,
    )


def render_analysis_roadmap(roadmap: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    steps = _step_list(roadmap.get("steps"))
    graph_type = _select_graph_type(roadmap, steps)
    dot_code = _build_dot_code(steps, graph_type)
    mermaid_code = _valid_mermaid_code(roadmap.get("mermaid_code")) or _build_mermaid_code(steps)
    render_script = _render_script_text()

    dot_path = output_path / "analysis_roadmap.dot"
    mermaid_path = output_path / "analysis_roadmap.mmd"
    script_path = output_path / "analysis_roadmap_render.py.txt"
    image_path = output_path / "analysis_roadmap.png"
    dot_path.write_text(dot_code, encoding="utf-8")
    mermaid_path.write_text(mermaid_code, encoding="utf-8")
    script_path.write_text(render_script, encoding="utf-8")
    _render_with_matplotlib(steps, image_path, graph_type, str(roadmap.get("title") or "AI 分析路线图"))
    return {
        "graph_type": graph_type,
        "dot_code": dot_code,
        "mermaid_code": mermaid_code,
        "dot_path": str(dot_path),
        "mermaid_path": str(mermaid_path),
        "render_script_path": str(script_path),
        "rendered_image_path": str(image_path),
        "rendered_image_url": f"/storage/jobs/{output_path.name}/analysis_roadmap.png" if output_path.name else str(image_path),
    }


def create_rule_based_roadmap(
    user_goal: str,
    dataset_profile: dict[str, Any],
    controller_plan: dict[str, Any],
    workflow_type: str,
) -> dict[str, Any]:
    task_type = str(controller_plan.get("task_type") or "general_data_analysis")
    if workflow_type == "insight_mining" or task_type == "insight_mining":
        steps = [
            _step("S1", "数据服务", "数据画像", "读取上传数据，生成字段、样本量、缺失值和数值分布画像。", "loading_dataset", [], ["dataset_profile.json"]),
            _step("S2", "InsightMiningAgent", "自动扫描", "无需用户目标，批量扫描时间趋势、周末效应、分组差异、相关性、异常和序列模式。", "insight_mining", ["S1"], ["analysis_result.json"]),
            _step("S3", "评分排序器", "价值排序", "按效应大小、样本覆盖、置信度和可解释性对洞察进行评分排序。", "insight_mining", ["S2"], ["report_data.json"]),
            _step("S4", "解释 Agent", "洞察报告", "生成中文洞察报告、可行动建议、限制说明和 PPT 大纲。", "explanation", ["S3"], ["explanation.json", "report.md"]),
        ]
        graph_type = "network"
    elif workflow_type == "what_if_prediction" or task_type == "what_if_prediction":
        steps = [
            _step("S1", "数据服务", "数据画像", "读取表格或图片抽取结果，生成字段、样本量、缺失值和数值分布画像。", "loading_dataset", [], ["dataset_profile.json"]),
            _step("S2", "RAG 检索", "业务口径", "检索相关业务口径，辅助后续 Agent 选择更稳健的解释方式。", "rag_retrieval", ["S1"], ["rag_retrieval.json"]),
            _step("S3", "主控 Agent", "任务分流", "识别目标属于情景预测，并确认进入 what-if 预测工作流。", "controller", ["S1", "S2"], ["controller_plan.json"]),
            _step("S4", "假设解析 Agent", "抽取假设", "识别干预变量、变化幅度、目标指标和对象维度。", "hypothesis", ["S3"], ["hypothesis_plan.json"]),
            _step("S5", "预测计划 Agent", "预测方案", "选择模型或规则模拟方法，确定特征字段、口径和输出结构。", "prediction_plan", ["S4"], ["prediction_plan.json"]),
            _step("S6", "代码 Agent", "生成脚本", "把预测方案转成 Python 脚本，并进行静态安全校验。", "code_generation", ["S5"], ["generated_prediction_script_attempt_*.py.txt"]),
            _step("S7", "沙箱与验证 Agent", "执行校验", "执行脚本，生成预测结果和图表，再验证产物结构与谨慎表述。", "validation", ["S6"], ["prediction_result.json", "charts/"]),
            _step("S8", "解释 Agent", "预测报告", "输出预测发现、限制说明、建议动作和 PPT 大纲。", "explanation", ["S7"], ["prediction_explanation.json", "report_data.json"]),
        ]
        graph_type = "hierarchy"
    else:
        controller_steps = controller_plan.get("steps") if isinstance(controller_plan.get("steps"), list) else []
        description = "；".join(_step_text(item) for item in controller_steps[:3] if _step_text(item))
        steps = [
            _step("S1", "数据服务", "数据画像", "读取上传表格或视觉抽取后的结构化数据，生成字段、样本量、缺失值和数值分布画像。", "loading_dataset", [], ["dataset_profile.json"]),
            _step("S2", "RAG 检索", "业务口径", "检索相关业务口径，帮助后续 Agent 使用正确术语和谨慎结论。", "rag_retrieval", ["S1"], ["rag_retrieval.json"]),
            _step("S3", "主控 Agent", "任务拆解", description or "把自然语言目标转成可执行的数据分析任务。", "controller", ["S1", "S2"], ["controller_plan.json"]),
            _step("S4", "数据理解 Agent", "字段语义", "判断日期字段、目标指标、维度字段、数值字段和数据质量问题。", "data_understanding", ["S3"], ["data_understanding.json"]),
            _step("S5", "分析计划 Agent", "分析方案", "确定分析指标、分组维度、统计检查、图表计划和必要限制说明。", "analysis", ["S4"], ["analysis_plan.json"]),
            _step("S6", "代码 Agent", "生成脚本", "把分析计划转成 Python 脚本，并进行静态安全校验。", "code_generation", ["S5"], ["generated_script_attempt_*.py.txt"]),
            _step("S7", "沙箱与验证 Agent", "执行修复", "执行脚本并验证结果；如发现问题，带着修复建议重新生成。", "validation", ["S6"], ["analysis_result.json", "charts/"]),
            _step("S8", "解释 Agent", "结论报告", "将通过验证的结果转成中文关键发现、建议、限制说明和 PPT 大纲。", "explanation", ["S7"], ["explanation.json", "report_data.json"]),
        ]
        graph_type = "flowchart"
    if workflow_type == "insight_mining" or task_type == "insight_mining":
        normalized_workflow_type = "insight_mining"
    else:
        normalized_workflow_type = "what_if_prediction" if workflow_type == "what_if_prediction" else "auto_repair"
    return {
        "title": "AI 分析路线图",
        "user_goal": str(user_goal or ""),
        "goal": str(user_goal or ""),
        "workflow_type": normalized_workflow_type,
        "task_type": task_type,
        "graph_type": graph_type,
        "summary": "AI 已将自然语言目标拆解为一条可执行、可验证、可回溯的多 Agent 任务链。",
        "dataset_columns": [str(item) for item in dataset_profile.get("columns") or []],
        "steps": steps,
        "mermaid_code": _build_mermaid_code(steps),
        "dot_code": _build_dot_code(steps, graph_type),
    }


def _normalize_result(result: Any, fallback: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return fallback
    steps = result.get("steps") if isinstance(result.get("steps"), list) else []
    normalized_steps = []
    for index, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage") or item.get("status_stage") or "")
        inputs = _string_list(item.get("inputs")) or _string_list(item.get("depends_on"))
        outputs = _string_list(item.get("outputs")) or _string_list(item.get("expected_artifacts"))
        if stage == "quality_review" or "质检" in str(item.get("title") or item.get("agent") or ""):
            continue
        normalized_steps.append(
            {
                "step_id": str(item.get("step_id") or f"S{index}"),
                "agent": str(item.get("agent") or "Agent"),
                "title": _short_label(str(item.get("title") or f"步骤 {index}"), 16),
                "description": str(item.get("description") or ""),
                "stage": stage,
                "status_stage": stage,
                "inputs": inputs,
                "depends_on": inputs,
                "outputs": outputs,
                "expected_artifacts": outputs,
                "status_hint": str(item.get("status_hint") or stage),
            }
        )
    if not normalized_steps:
        normalized_steps = fallback["steps"]
    workflow_type = str(result.get("workflow_type") or fallback.get("workflow_type") or "auto_repair")
    if workflow_type not in {"auto_repair", "what_if_prediction", "insight_mining"}:
        workflow_type = fallback.get("workflow_type", "auto_repair")
    user_goal = str(result.get("user_goal") or result.get("goal") or fallback.get("user_goal") or fallback.get("goal") or "")
    graph_type = str(result.get("graph_type") or fallback.get("graph_type") or _select_graph_type(result, normalized_steps))
    if graph_type not in {"flowchart", "hierarchy", "network"}:
        graph_type = "flowchart"
    return {
        "title": str(result.get("title") or fallback.get("title") or "AI 分析路线图"),
        "user_goal": user_goal,
        "goal": user_goal,
        "workflow_type": workflow_type,
        "task_type": str(result.get("task_type") or fallback.get("task_type") or ""),
        "graph_type": graph_type,
        "summary": str(result.get("summary") or fallback.get("summary") or "AI 已生成分析路线图。"),
        "dataset_columns": _string_list(result.get("dataset_columns")) or fallback.get("dataset_columns", []),
        "steps": normalized_steps,
        "mermaid_code": _valid_mermaid_code(result.get("mermaid_code")) or _build_mermaid_code(normalized_steps),
        "dot_code": _build_dot_code(normalized_steps, graph_type),
    }


def _render_with_matplotlib(steps: list[dict[str, Any]], image_path: Path, graph_type: str, title: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    preferred_fonts = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Microsoft YaHei",
        "SimHei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    font_name = next((font for font in preferred_fonts if font in available_fonts), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [font_name]
    plt.rcParams["axes.unicode_minus"] = False

    count = max(len(steps), 1)
    if graph_type == "network":
        width, height = 12, max(6, min(11, math.ceil(count / 2) * 2.1))
    else:
        width, height = 10, max(6, count * 1.25 + 1.5)
    fig, ax = plt.subplots(figsize=(width, height), dpi=180)
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.text(0.5, 0.965, _short_label(title, 28), ha="center", va="top", fontsize=18, fontweight="bold")

    positions = _layout_positions(count, graph_type)
    for index, (step, (x, y)) in enumerate(zip(steps, positions), start=1):
        label = f"{index}. {_short_label(str(step.get('title') or f'步骤 {index}'), 12)}\n{_short_label(str(step.get('agent') or 'Agent'), 14)}"
        if graph_type == "network":
            radius = 0.082 if index == 1 else 0.072
            node = Circle((x, y), radius=radius, linewidth=1.4, edgecolor="#0f766e", facecolor="#ecfeff")
            ax.add_patch(node)
        else:
            node = FancyBboxPatch(
                (x - 0.19, y - 0.045),
                0.38,
                0.09,
                boxstyle="round,pad=0.018,rounding_size=0.025",
                linewidth=1.4,
                edgecolor="#0f766e",
                facecolor="#ecfeff",
            )
            ax.add_patch(node)
        ax.text(x, y, label, ha="center", va="center", fontsize=10.5, color="#111827")

    for (x1, y1), (x2, y2) in zip(positions, positions[1:]):
        shrink = 0.08 if graph_type == "network" else 0.055
        arrow = FancyArrowPatch(
            (x1, y1 - shrink),
            (x2, y2 + shrink),
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=1.2,
            color="#0f766e",
            connectionstyle="arc3,rad=0.0" if graph_type != "network" else "arc3,rad=0.08",
        )
        ax.add_patch(arrow)

    fig.tight_layout(pad=0.4)
    fig.savefig(image_path, bbox_inches="tight")
    plt.close(fig)


def _layout_positions(count: int, graph_type: str) -> list[tuple[float, float]]:
    if count <= 0:
        return []
    if graph_type == "network":
        positions = []
        for index in range(count):
            column = index % 4
            row = index // 4
            x = 0.12 + column * 0.25
            y = 0.82 - row * 0.24
            positions.append((min(x, 0.88), max(y, 0.16)))
        return positions
    if graph_type == "hierarchy":
        levels = [1, 2, 2, 3]
        positions = []
        step_index = 0
        top = 0.84
        gap_y = 0.18
        for level_index, level_count in enumerate(levels):
            remaining = count - step_index
            if remaining <= 0:
                break
            n = min(level_count, remaining)
            xs = [0.5] if n == 1 else [0.22 + i * (0.56 / max(n - 1, 1)) for i in range(n)]
            for x in xs:
                positions.append((x, top - level_index * gap_y))
                step_index += 1
        while len(positions) < count:
            i = len(positions)
            positions.append((0.22 + (i % 3) * 0.28, max(0.12, top - (3 + i // 3) * gap_y)))
        return positions
    if count == 1:
        return [(0.5, 0.5)]
    return [(0.5, 0.86 - i * (0.72 / max(count - 1, 1))) for i in range(count)]


def _build_dot_code(steps: list[dict[str, Any]], graph_type: str = "flowchart") -> str:
    graph_name = "network" if graph_type == "network" else "hierarchy" if graph_type == "hierarchy" else "flowchart"
    rankdir = "LR" if graph_type == "network" else "TB"
    shape = "circle" if graph_type == "network" else "box"
    lines = [f"digraph {graph_name} {{", f"    rankdir={rankdir};", f"    node [shape={shape}, style=rounded];", ""]
    for index, step in enumerate(steps, start=1):
        node_id = _safe_dot_id(str(step.get("step_id") or f"S{index}"))
        label = _escape_dot_label(f"{index}. {_short_label(str(step.get('title') or f'步骤 {index}'), 16)}")
        extra = "shape=doublecircle, " if graph_type == "network" and index == 1 else ""
        lines.append(f'    {node_id} [{extra}label="{label}"];')
    lines.append("")
    step_ids = [_safe_dot_id(str(step.get("step_id") or f"S{index}")) for index, step in enumerate(steps, start=1)]
    for previous, current in zip(step_ids, step_ids[1:]):
        lines.append(f"    {previous} -> {current};")
    lines.append("}")
    return "\n".join(lines)


def _render_script_text() -> str:
    return '''from pathlib import Path

# This renderer is intentionally dependency-light. The service uses the same
# matplotlib layout logic to generate analysis_roadmap.png for the frontend.
# Run from a job directory that contains analysis_roadmap.json.

import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    roadmap = json.loads(Path("analysis_roadmap.json").read_text(encoding="utf-8"))
    steps = roadmap.get("steps") or []
    fig, ax = plt.subplots(figsize=(8, max(4, len(steps) * 1.1)))
    ax.set_axis_off()
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    for index, step in enumerate(steps, start=1):
        y = 0.9 - (index - 1) * (0.8 / max(len(steps) - 1, 1))
        ax.text(0.5, y, f"{index}. {step.get('title', '')}", ha="center", va="center",
                bbox={"boxstyle": "round,pad=0.3", "fc": "#ecfeff", "ec": "#0f766e"})
    fig.savefig("analysis_roadmap.png", bbox_inches="tight")


if __name__ == "__main__":
    main()
'''


def _select_graph_type(roadmap: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    graph_type = str(roadmap.get("graph_type") or "").strip()
    if graph_type in {"flowchart", "hierarchy", "network"}:
        return graph_type
    workflow_type = str(roadmap.get("workflow_type") or "")
    if workflow_type == "what_if_prediction":
        return "hierarchy"
    if workflow_type == "insight_mining":
        return "network"
    if len(steps) >= 9:
        return "network"
    return "flowchart"


def _step_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _valid_mermaid_code(value: Any) -> str:
    code = str(value or "").strip()
    if not code:
        return ""
    if code.startswith("flowchart") or code.startswith("graph"):
        return code
    return ""


def _build_mermaid_code(steps: list[dict[str, Any]]) -> str:
    lines = ["flowchart TD"]
    for index, step in enumerate(steps, start=1):
        step_id = _safe_mermaid_id(str(step.get("step_id") or f"S{index}"))
        title = _escape_mermaid_label(str(step.get("title") or f"步骤 {index}"))
        agent = _escape_mermaid_label(str(step.get("agent") or "Agent"))
        lines.append(f'  {step_id}["{index}. {title}<br/>{agent}"]')
    step_ids = [_safe_mermaid_id(str(step.get("step_id") or f"S{index}")) for index, step in enumerate(steps, start=1)]
    for previous, current in zip(step_ids, step_ids[1:]):
        lines.append(f"  {previous} --> {current}")
    return "\n".join(lines)


def _safe_mermaid_id(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum() or char == "_")
    return cleaned or "S"


def _safe_dot_id(value: str) -> str:
    cleaned = "".join(char for char in value if char.isalnum() or char == "_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _escape_dot_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "'")


def _escape_mermaid_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', "'").replace("[", "(").replace("]", ")")


def _step(
    step_id: str,
    agent: str,
    title: str,
    description: str,
    status_stage: str,
    depends_on: list[str],
    expected_artifacts: list[str],
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "agent": agent,
        "title": title,
        "description": description,
        "stage": status_stage,
        "status_stage": status_stage,
        "inputs": depends_on,
        "depends_on": depends_on,
        "outputs": expected_artifacts,
        "expected_artifacts": expected_artifacts,
        "status_hint": status_stage,
    }


def _step_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return str(item.get("description") or item.get("name") or item.get("title") or "")
    return ""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item)]


def _short_label(value: str, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)] + "…"


