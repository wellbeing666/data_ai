from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


IR_VERSION = "1.0"


class IRFieldRef(BaseModel):
    name: str = ""
    role: str = ""
    source_column: str = ""
    confidence: float = 0.0
    description: str = ""


class IRTimeWindow(BaseModel):
    field: str = ""
    start: str | None = None
    end: str | None = None
    granularity: str = ""
    description: str = ""


class IRFilter(BaseModel):
    field: str = ""
    operator: str = ""
    value: Any = None
    description: str = ""


class IRMetric(BaseModel):
    name: str = ""
    source_column: str = ""
    aggregation: str = ""
    direction: str = ""
    business_definition: str = ""
    evidence_required: list[str] = Field(default_factory=list)


class IRChartIntent(BaseModel):
    chart_type: str = ""
    purpose: str = ""
    x: str = ""
    y: str = ""
    group_by: str = ""
    title: str = ""


class IRDependency(BaseModel):
    artifact: str = ""
    depends_on: list[str] = Field(default_factory=list)
    purpose: str = ""


class AnalysisIR(BaseModel):
    schema_version: str = IR_VERSION
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent: str = "analysis_ir_agent"
    task_type: str = "general_data_analysis"
    normalized_goal: str = ""
    semantic_digest: str = ""
    entities: list[IRFieldRef] = Field(default_factory=list)
    grain: list[str] = Field(default_factory=list)
    metrics: list[IRMetric] = Field(default_factory=list)
    dimensions: list[IRFieldRef] = Field(default_factory=list)
    time_window: IRTimeWindow = Field(default_factory=IRTimeWindow)
    filters: list[IRFilter] = Field(default_factory=list)
    candidate_methods: list[str] = Field(default_factory=list)
    chart_intents: list[IRChartIntent] = Field(default_factory=list)
    hypotheses: list[str] = Field(default_factory=list)
    evidence_requirements: list[str] = Field(default_factory=list)
    output_dependencies: list[IRDependency] = Field(default_factory=list)
    guardrails: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source: dict[str, Any] = Field(default_factory=dict)


class FollowUpIRPatch(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent: str = "selection_to_query_agent"
    patch_type: Literal["chart_selection"] = "chart_selection"
    question: str = ""
    selection_spec: dict[str, Any] = Field(default_factory=dict)
    filters: list[IRFilter] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    evidence_requirements: list[str] = Field(default_factory=list)
    reuse_follow_up_endpoint: bool = True


def normalize_ir_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a raw IR dict while preserving forward-compatible extras."""
    return AnalysisIR.model_validate(payload).model_dump(mode="json")
