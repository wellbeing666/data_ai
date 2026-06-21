import type { AnalysisIR, WorkflowJobResponse } from "../../types";
import { EmptyState } from "../WorkbenchComponents";

export function AnalysisIrPage({ analysisIr, job }: { analysisIr: AnalysisIR | null; job: WorkflowJobResponse | null }) {
  if (!job?.job_id) {
    return (
      <section className="page-section analysis-ir-page">
        <div className="section-heading dashboard-heading">
          <div>
            <h2>分析专用中间表示（Analysis IR）</h2>
            <span>自然语言目标会先编译为强类型语义，再交给后续 Agent 消费。</span>
          </div>
        </div>
        <EmptyState title="暂无 Analysis IR" text="启动或打开一次分析任务后，这里会展示 analysis_ir.json。" />
      </section>
    );
  }

  if (!analysisIr) {
    return (
      <section className="page-section analysis-ir-page">
        <div className="section-heading dashboard-heading">
          <div>
            <h2>分析专用中间表示（Analysis IR）</h2>
            <span>当前任务尚未生成 analysis_ir.json，完成预检与知识检索后会自动写入。</span>
          </div>
        </div>
        <EmptyState title="等待编译产物" text="Analysis IR 会明确实体、粒度、指标、限制、候选方法和输出依赖关系。" />
      </section>
    );
  }

  return (
    <section className="page-section analysis-ir-page">
      <div className="section-heading dashboard-heading">
        <div>
          <h2>分析专用中间表示（Analysis IR）</h2>
          <span>后续 Controller、Analysis、Code、Dashboard、Follow-up、PPT 统一消费这份 IR + delta。</span>
        </div>
        <small className="ir-version">版本 {analysisIr.schema_version || "1.0"}</small>
      </div>

      <div className="ir-hero-card">
        <strong>{analysisIr.task_type || job.task_type || "general_data_analysis"}</strong>
        <h3>{analysisIr.normalized_goal || job.user_goal || "当前分析任务"}</h3>
        <p>{analysisIr.semantic_digest || "IR 已生成，将作为后续 Agent 的语义事实源。"}</p>
      </div>

      <div className="ir-summary-grid" aria-label="Analysis IR 概览指标">
        <IrMetricCard label="实体" value={analysisIr.entities?.length ?? 0} />
        <IrMetricCard label="粒度" value={analysisIr.grain?.length ?? 0} />
        <IrMetricCard label="指标" value={analysisIr.metrics?.length ?? 0} />
        <IrMetricCard label="图表意图" value={analysisIr.chart_intents?.length ?? 0} />
      </div>

      <div className="ir-section-grid" aria-label="Analysis IR 语义信息">
        <IrSection title="实体 / Entities" items={(analysisIr.entities ?? []).map((item) => item.name || item.source_column)} emptyText="尚未识别业务实体。" />
        <IrSection title="分析粒度 / Grain" items={analysisIr.grain ?? []} emptyText="尚未锁定分析粒度。" />
        <IrSection title="指标 / Metrics" items={(analysisIr.metrics ?? []).map((item) => `${item.name || item.source_column}${item.aggregation ? ` · ${item.aggregation}` : ""}`)} emptyText="尚未定义分析指标。" />
        <IrSection title="维度 / Dimensions" items={(analysisIr.dimensions ?? []).map((item) => item.name || item.source_column)} emptyText="尚未定义拆解维度。" />
        <IrSection title="过滤条件 / Filters" items={(analysisIr.filters ?? []).map((item) => `${item.field} ${item.operator} ${formatUnknown(item.value)}`)} emptyText="未锁定过滤条件，默认使用全量数据。" />
        <IrSection title="时间窗 / Time Window" items={[formatTimeWindow(analysisIr.time_window)].filter(Boolean)} emptyText="未识别明确时间字段。" />
        <IrSection title="候选方法 / Candidate Methods" items={analysisIr.candidate_methods ?? []} emptyText="尚未选择候选分析方法。" />
        <IrSection title="假设 / Hypotheses" items={analysisIr.hypotheses ?? []} emptyText="当前任务没有预设假设。" />
        <IrSection title="证据需求 / Evidence" items={analysisIr.evidence_requirements ?? []} emptyText="尚未声明额外证据需求。" />
        <IrSection title="安全边界 / Guardrails" items={analysisIr.guardrails ?? []} emptyText="尚未声明额外安全边界。" />
      </div>

      <section className="ir-card wide">
        <h3>图表意图</h3>
        {(analysisIr.chart_intents ?? []).length ? (
          <div className="ir-chart-intents">
            {(analysisIr.chart_intents ?? []).map((item, index) => (
              <article key={`${item.title || item.purpose}-${index}`}>
                <strong>{item.title || item.purpose || `图表 ${index + 1}`}</strong>
                <span>{item.chart_type || "chart"}</span>
                <p>{item.purpose || "展示关键指标。"}</p>
                <small>{[item.x, item.y, item.group_by].filter(Boolean).join(" / ")}</small>
              </article>
            ))}
          </div>
        ) : (
          <p className="ir-muted">暂无图表意图。</p>
        )}
      </section>

      <section className="ir-card wide">
        <h3>输出产物依赖关系</h3>
        {(analysisIr.output_dependencies ?? []).length ? (
          <ol className="ir-dependency-list">
            {(analysisIr.output_dependencies ?? []).map((item, index) => (
              <li key={`${item.artifact}-${index}`}>
                <strong>{item.artifact}</strong>
                <span>依赖：{(item.depends_on ?? []).join("、") || "无"}</span>
                <p>{item.purpose}</p>
              </li>
            ))}
          </ol>
        ) : (
          <p className="ir-muted">暂无依赖声明。</p>
        )}
      </section>
    </section>
  );
}

function IrMetricCard({ label, value }: { label: string; value: number }) {
  return (
    <article>
      <strong>{value}</strong>
      <span>{label}</span>
    </article>
  );
}

function IrSection({ title, items, emptyText = "暂无" }: { title: string; items: Array<string | null | undefined>; emptyText?: string }) {
  const cleanItems = items.map((item) => String(item || "").trim()).filter(Boolean);
  return (
    <section className="ir-card">
      <h3>{title}</h3>
      {cleanItems.length ? (
        <div className="ir-chip-grid">
          {cleanItems.map((item, index) => <span key={`${title}-${index}-${item}`}>{item}</span>)}
        </div>
      ) : (
        <p className="ir-muted">{emptyText}</p>
      )}
    </section>
  );
}

function formatUnknown(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  if (typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

function formatTimeWindow(value: AnalysisIR["time_window"]): string {
  if (!value?.field && !value?.start && !value?.end && !value?.granularity) {
    return "";
  }
  return [value.field ? `字段：${value.field}` : "", value.start ? `开始：${value.start}` : "", value.end ? `结束：${value.end}` : "", value.granularity ? `粒度：${value.granularity}` : "", value.description || ""].filter(Boolean).join("；");
}
