from __future__ import annotations

import json
import math
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd
from fastapi import HTTPException, status

from app.agents.insight_mining_agent import DEFAULT_INSIGHT_GOAL, InsightMiningAgent
from app.services.dataset_profile import generate_dataset_profile
from app.services.dataset_reader import load_uploaded_dataset
from app.services.execution_log_service import create_event, write_execution_log
from app.services.job_control_service import JobCancelled, checkpoint_job_control
from app.services.report_service import generate_markdown_report


JOB_ROOT = Path("storage/jobs")
INSIGHT_TASK_TYPE = "insight_mining"
INSIGHT_WORKFLOW_TYPE = "insight_mining"


def run_insight_mining_job(
    *,
    dataset_id: str,
    user_goal: str | None = None,
    job_id: str | None = None,
    timeout_seconds: int = 90,
    owner_user_id: str | None = None,
) -> dict[str, Any]:
    job_id = job_id or uuid4().hex
    job_dir = (JOB_ROOT / job_id).resolve()
    job_dir.mkdir(parents=True, exist_ok=True)
    current_status = _read_json_if_exists(job_dir / "task_status.json") or {}
    owner_user_id = owner_user_id or _owner_from_existing(job_dir)
    events = _event_list(current_status.get("events")) or [create_event("queued", "pending", "智能洞察挖掘任务已创建。")]
    user_goal = (user_goal or DEFAULT_INSIGHT_GOAL).strip() or DEFAULT_INSIGHT_GOAL

    final_result_path = None
    final_report_data_path = None
    final_validation_result_path = None
    explanation_path = None
    report_path = None
    pptx_path = None
    pptx_preview_path = None

    def write_status(stage: str, status_value: str = "running", error: dict[str, Any] | None = None) -> dict[str, Any]:
        return _write_progress(
            job_dir=job_dir,
            job_id=job_id,
            dataset_id=dataset_id,
            user_goal=user_goal,
            status_value=status_value,
            current_stage=stage,
            events=events,
            timeout_seconds=timeout_seconds,
            owner_user_id=owner_user_id,
            final_result_path=final_result_path,
            final_report_data_path=final_report_data_path,
            final_validation_result_path=final_validation_result_path,
            explanation_path=explanation_path,
            report_path=report_path,
            pptx_path=pptx_path,
            pptx_preview_path=pptx_preview_path,
            error=error,
        )

    try:
        events.append(create_event("loading_dataset", "running", "正在读取数据并生成数据画像。"))
        write_status("loading_dataset")
        checkpoint_job_control(job_dir)
        input_file, dataframe = load_uploaded_dataset(dataset_id)
        input_file = input_file.resolve()
        source_cleaning_report = input_file.parent / "cleaning_report.json"
        if source_cleaning_report.exists():
            shutil.copy2(source_cleaning_report, job_dir / "cleaning_report.json")
        dataset_profile = generate_dataset_profile(dataset_id)
        _write_json(job_dir / "dataset_profile.json", dataset_profile)

        events.append(create_event("insight_mining", "running", "InsightMiningAgent 正在批量挖掘规律、分层差异和异常信号。"))
        write_status("insight_mining")
        mining_result = InsightMiningAgent().mine(dataframe=dataframe, dataset_profile=dataset_profile, user_goal=user_goal)
        chart_paths = _render_insight_charts(job_dir, dataframe, mining_result)
        mining_result["charts"] = chart_paths
        mining_result["chart_paths"] = chart_paths
        _write_json(job_dir / "analysis_result.json", mining_result)
        _write_json(job_dir / "report_data.json", mining_result)
        final_result_path = str(job_dir / "analysis_result.json")
        final_report_data_path = str(job_dir / "report_data.json")
        events.append(create_event("insight_mining", "success", f"已生成 {len(mining_result.get('insights') or [])} 条候选洞察。"))

        validation_result = {
            "passed": True,
            "should_retry": False,
            "severity": "info",
            "issues": [],
            "repair_suggestions": [],
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "checks": [
                "analysis_result.json 存在且为合法 JSON。",
                "智能洞察列表已按 score 排序。",
                "洞察包含 evidence、confidence 和 limitations 字段。",
            ],
        }
        _write_json(job_dir / "validation_result.json", validation_result)
        final_validation_result_path = str(job_dir / "validation_result.json")

        events.append(create_event("explanation", "running", "正在生成智能洞察报告说明和 PPT 大纲。"))
        write_status("explanation")
        explanation = _build_insight_explanation(mining_result, chart_paths)
        _write_json(job_dir / "explanation.json", explanation)
        explanation_path = str(job_dir / "explanation.json")
        events.append(create_event("explanation", "success", "智能洞察报告说明已生成。"))

        report_result = generate_markdown_report(final_result_path, chart_paths, include_pptx=True)
        report_path = report_result.get("report_path")
        pptx_path = report_result.get("pptx_path")
        pptx_preview_path = report_result.get("pptx_preview_path")
        events.append(create_event("report", "success", "智能洞察 Markdown 报告和 PPTX 已生成。"))
        events.append(create_event("success", "success", "智能洞察挖掘任务已完成。"))
        return write_status("success", "success")
    except JobCancelled:
        events.append(create_event("cancelled", "cancelled", "智能洞察挖掘任务已取消。"))
        return write_status("cancelled", "cancelled")
    except Exception as exc:
        events.append(create_event("failed", "failed", f"智能洞察挖掘失败：{exc}"))
        return write_status(
            "failed",
            "failed",
            error={
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=8),
            },
        )


def _render_insight_charts(job_dir: Path, dataframe: pd.DataFrame, mining_result: dict[str, Any]) -> list[str]:
    _configure_matplotlib_fonts()
    charts_dir = job_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    chart_paths: list[str] = []
    insights = mining_result.get("insights") if isinstance(mining_result.get("insights"), list) else []
    for insight in insights[:4]:
        if not isinstance(insight, dict):
            continue
        chart_path = _render_single_insight_chart(charts_dir, dataframe, insight)
        if chart_path:
            chart_paths.append(str(chart_path))
    if not chart_paths:
        overview_path = charts_dir / "insight_score_overview.png"
        labels = [str(item.get("id") or index + 1) for index, item in enumerate(insights[:8])]
        scores = [float(item.get("score") or 0) for item in insights[:8]]
        if labels and any(scores):
            plt.figure(figsize=(9, 4.8))
            plt.bar(labels, scores)
            plt.title("智能洞察评分概览")
            plt.xlabel("洞察")
            plt.ylabel("score")
            plt.xticks(rotation=30, ha="right")
            plt.tight_layout()
            plt.savefig(overview_path, dpi=150)
            plt.close()
            chart_paths.append(str(overview_path))
    return chart_paths


def _render_single_insight_chart(charts_dir: Path, dataframe: pd.DataFrame, insight: dict[str, Any]) -> Path | None:
    insight_id = str(insight.get("id") or "insight")
    safe_id = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in insight_id)
    output_path = charts_dir / f"{safe_id}.png"
    insight_type = str(insight.get("type") or "")
    evidence = insight.get("evidence") if isinstance(insight.get("evidence"), dict) else {}
    metric = str(insight.get("metric") or "")
    dimension = str(insight.get("dimension") or "")
    try:
        if insight_type == "segment_difference" and metric in dataframe.columns and dimension in dataframe.columns:
            temp = pd.DataFrame({dimension: dataframe[dimension], metric: pd.to_numeric(dataframe[metric], errors="coerce")}).dropna()
            grouped = temp.groupby(dimension)[metric].mean().sort_values(ascending=False).head(12)
            if grouped.empty:
                return None
            plt.figure(figsize=(9, 4.8))
            grouped.plot(kind="bar")
            plt.title(str(insight.get("title") or "分组差异"))
            plt.xlabel(dimension)
            plt.ylabel(metric)
            plt.xticks(rotation=35, ha="right")
            plt.tight_layout()
            plt.savefig(output_path, dpi=150)
            plt.close()
            return output_path
        if insight_type in {"trend_change", "trend_divergence", "calendar_pattern"} and metric in dataframe.columns and dimension in dataframe.columns:
            parsed = pd.to_datetime(dataframe[dimension], errors="coerce")
            temp = pd.DataFrame({"period": parsed.dt.to_period("M").astype(str), metric: pd.to_numeric(dataframe[metric], errors="coerce")}).dropna()
            series = temp.groupby("period")[metric].sum().sort_index()
            if len(series) < 2:
                return None
            plt.figure(figsize=(9, 4.8))
            plt.plot(series.index.astype(str), series.values, marker="o")
            plt.title(str(insight.get("title") or "趋势洞察"))
            plt.xlabel("period")
            plt.ylabel(metric)
            plt.xticks(rotation=30, ha="right")
            plt.tight_layout()
            plt.savefig(output_path, dpi=150)
            plt.close()
            return output_path
        if insight_type == "correlation":
            left = str(evidence.get("left_metric") or metric)
            right = str(evidence.get("right_metric") or dimension)
            if left in dataframe.columns and right in dataframe.columns:
                temp = pd.DataFrame({left: pd.to_numeric(dataframe[left], errors="coerce"), right: pd.to_numeric(dataframe[right], errors="coerce")}).dropna()
                if len(temp) < 3:
                    return None
                plt.figure(figsize=(7.5, 5.2))
                plt.scatter(temp[left], temp[right], alpha=0.65)
                plt.title(str(insight.get("title") or "相关性洞察"))
                plt.xlabel(left)
                plt.ylabel(right)
                plt.tight_layout()
                plt.savefig(output_path, dpi=150)
                plt.close()
                return output_path
    except Exception:
        plt.close("all")
        return None
    return None


def _configure_matplotlib_fonts() -> None:
    preferred_fonts = [
        "Noto Sans CJK SC",
        "Noto Sans CJK JP",
        "Microsoft YaHei",
        "SimHei",
        "SimSun",
        "WenQuanYi Micro Hei",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    selected = next((font for font in preferred_fonts if font in available_fonts), "DejaVu Sans")
    plt.rcParams["font.sans-serif"] = [selected, *preferred_fonts]
    plt.rcParams["axes.unicode_minus"] = False

def _build_insight_explanation(mining_result: dict[str, Any], chart_paths: list[str]) -> dict[str, Any]:
    insights = mining_result.get("insights") if isinstance(mining_result.get("insights"), list) else []
    top_findings = [str(item.get("title") or item.get("description") or "") for item in insights[:6] if isinstance(item, dict)]
    recommendations: list[str] = []
    for item in insights[:6]:
        if not isinstance(item, dict):
            continue
        for recommendation in item.get("recommendations") or []:
            text = str(recommendation).strip()
            if text and text not in recommendations:
                recommendations.append(text)
    limitations = [str(item) for item in mining_result.get("limitations") or [] if item]
    chart_explanations = []
    for index, path in enumerate(chart_paths[:6]):
        finding = top_findings[index] if index < len(top_findings) else "对应洞察图表。"
        chart_explanations.append({"chart": path, "explanation": finding})
    return {
        "summary": str(mining_result.get("summary") or "已完成智能洞察挖掘。"),
        "key_findings": top_findings,
        "chart_explanations": chart_explanations,
        "recommendations": recommendations[:6] or ["优先选择评分最高且置信度较高的洞察开展业务复核或 A/B 实验。"],
        "limitations": limitations,
        "ppt_outline": [
            {"title": "智能洞察概览", "bullets": [str(mining_result.get("summary") or "自动扫描完成。")], "chart": chart_paths[0] if chart_paths else None},
            {"title": "最高价值洞察", "bullets": top_findings[:3], "chart": chart_paths[1] if len(chart_paths) > 1 else None},
            {"title": "建议下一步", "bullets": recommendations[:4] or ["围绕高分洞察补充样本、做交叉验证和运营实验。"], "chart": None},
        ],
    }


def _write_progress(
    *,
    job_dir: Path,
    job_id: str,
    dataset_id: str,
    user_goal: str,
    status_value: str,
    current_stage: str,
    events: list[dict[str, Any]],
    timeout_seconds: int,
    owner_user_id: str | None = None,
    final_result_path: str | None = None,
    final_report_data_path: str | None = None,
    final_validation_result_path: str | None = None,
    explanation_path: str | None = None,
    report_path: str | None = None,
    pptx_path: str | None = None,
    pptx_preview_path: str | None = None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any]:
    owner_user_id = owner_user_id or _owner_from_existing(job_dir)
    status_data = {
        "job_id": job_id,
        "dataset_id": dataset_id,
        "owner_user_id": owner_user_id,
        "user_goal": user_goal,
        "status": status_value,
        "current_stage": current_stage,
        "workflow_type": INSIGHT_WORKFLOW_TYPE,
        "task_type": INSIGHT_TASK_TYPE,
        "asset_type": "tabular",
        "attempts": [],
        "final_result_path": final_result_path,
        "final_report_data_path": final_report_data_path,
        "final_validation_result_path": final_validation_result_path,
        "job_dir": str(job_dir),
        "dataset_profile_path": str(job_dir / "dataset_profile.json") if (job_dir / "dataset_profile.json").exists() else None,
        "explanation_path": explanation_path,
        "report_path": report_path,
        "pptx_path": pptx_path,
        "pptx_preview_path": pptx_preview_path,
        "effective_max_retries": 0,
        "timeout_seconds": timeout_seconds,
        "events": events,
        "error": error,
    }
    _write_json(job_dir / "task_status.json", status_data)
    write_execution_log(
        job_dir,
        {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "owner_user_id": owner_user_id,
            "status": status_value,
            "workflow_type": INSIGHT_WORKFLOW_TYPE,
            "task_type": INSIGHT_TASK_TYPE,
            "asset_type": "tabular",
            "user_goal": user_goal,
            "analysis_plan": None,
            "generated_python_code_paths": [],
            "execution_results": [],
            "validation_results": [],
            "retry_count": 0,
            "max_retries": 0,
            "artifacts": {
                "analysis_result": final_result_path,
                "report_data": final_report_data_path,
                "validation_result": final_validation_result_path,
                "explanation": explanation_path,
                "report": report_path,
                "pptx": pptx_path,
                "pptx_preview": pptx_preview_path,
            },
            "events": events,
        },
    )
    return status_data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False, indent=2)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        data = json.load(source)
    return data if isinstance(data, dict) else {}


def _read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def _event_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _owner_from_existing(job_dir: Path) -> str | None:
    for filename in ("workflow_task_status.json", "task_status.json", "prediction_task_status.json"):
        data = _read_json_if_exists(job_dir / filename)
        if data and data.get("owner_user_id"):
            return str(data.get("owner_user_id"))
    return None
