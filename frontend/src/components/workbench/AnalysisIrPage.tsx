import type { CSSProperties } from "react";

import type { AnalysisIR, WorkflowJobResponse } from "../../types";
import { EmptyState } from "../WorkbenchComponents";

type IrStyle = CSSProperties;

type IrSectionConfig = {
  title: string;
  subtitle: string;
  description: string;
  items: Array<string | null | undefined>;
  emptyText: string;
};

const FLOW_STEPS = ["目标", "实体", "指标", "方法", "产物"];

export function AnalysisIrPage({
  analysisIr,
  job,
}: {
  analysisIr: AnalysisIR | null;
  job: WorkflowJobResponse | null;
}) {
  if (!job?.job_id) {
    return (
      <section className="page-section analysis-ir-page analysis-ir-empty-page">
        <div className="section-heading dashboard-heading">
          <div>
            <h2>分析专用中间表示（Analysis IR）</h2>
            <span>
              将分析目标转译为统一语义口径，用于约束任务执行、图表生成与后续追问。
            </span>
          </div>
        </div>
        <EmptyState
          title="暂无 Analysis IR"
          text="启动或打开一次分析任务后，这里会展示已结构化的分析口径。"
        />
      </section>
    );
  }

  if (!analysisIr) {
    return (
      <section className="page-section analysis-ir-page analysis-ir-empty-page">
        <div className="section-heading dashboard-heading">
          <div>
            <h2>分析专用中间表示（Analysis IR）</h2>
            <span>
              系统正在准备实体、指标、时间窗、证据需求与输出依赖等语义信息。
            </span>
          </div>
        </div>
        <EmptyState
          title="等待编译产物"
          text="Analysis IR 会在任务进入分析链路后自动展示。"
        />
      </section>
    );
  }

  const entities = analysisIr.entities ?? [];
  const grain = analysisIr.grain ?? [];
  const metrics = analysisIr.metrics ?? [];
  const dimensions = analysisIr.dimensions ?? [];
  const filters = analysisIr.filters ?? [];
  const candidateMethods = analysisIr.candidate_methods ?? [];
  const hypotheses = analysisIr.hypotheses ?? [];
  const evidenceRequirements = analysisIr.evidence_requirements ?? [];
  const guardrails = analysisIr.guardrails ?? [];
  const chartIntents = analysisIr.chart_intents ?? [];
  const outputDependencies = analysisIr.output_dependencies ?? [];
  const timeWindowText = formatTimeWindow(analysisIr.time_window);
  const taskType =
    analysisIr.task_type || job.task_type || "general_data_analysis";
  const goal = analysisIr.normalized_goal || job.user_goal || "当前分析任务";
  const digest =
    analysisIr.semantic_digest ||
    "已将分析任务拆解为可执行、可校验、可复用的统一语义结构。";
  const confidence = averageConfidence(analysisIr);
  const lockedScopeCount = [
    entities.length,
    metrics.length,
    dimensions.length,
    timeWindowText ? 1 : 0,
    guardrails.length,
  ].filter(Boolean).length;

  const summaryCards = [
    {
      label: "实体",
      value: entities.length,
      description: "业务对象与字段锚点",
      total: Math.max(entities.length, 4),
    },
    {
      label: "粒度",
      value: grain.length,
      description: "分析聚合层级",
      total: Math.max(grain.length, 4),
    },
    {
      label: "指标",
      value: metrics.length,
      description: "计算口径与聚合方式",
      total: Math.max(metrics.length, 4),
    },
    {
      label: "图表意图",
      value: chartIntents.length,
      description: "可视化表达方向",
      total: Math.max(chartIntents.length, 4),
    },
  ];

  const semanticSections: IrSectionConfig[] = [
    {
      title: "实体",
      subtitle: "Entities",
      description: "从数据字段中锁定业务对象，降低后续解释漂移。",
      items: entities.map(formatFieldRef),
      emptyText: "尚未识别业务实体。",
    },
    {
      title: "分析粒度",
      subtitle: "Grain",
      description: "明确分析结果应落在哪些时间、区域或业务层级上。",
      items: grain,
      emptyText: "尚未锁定分析粒度。",
    },
    {
      title: "指标",
      subtitle: "Metrics",
      description: "统一核心指标、来源字段与统计方式。",
      items: metrics.map(formatMetric),
      emptyText: "尚未定义分析指标。",
    },
    {
      title: "维度",
      subtitle: "Dimensions",
      description: "定义可用于拆解、对比和筛选的观察角度。",
      items: dimensions.map(formatFieldRef),
      emptyText: "尚未定义拆解维度。",
    },
    {
      title: "过滤条件",
      subtitle: "Filters",
      description: "记录已锁定的数据范围与筛选口径。",
      items: filters.map(
        (item) =>
          `${item.field}${item.operator ? ` ${item.operator}` : ""}${item.value === undefined ? "" : ` ${formatUnknown(item.value)}`}`,
      ),
      emptyText: "未锁定过滤条件，默认使用可用数据范围。",
    },
    {
      title: "时间窗",
      subtitle: "Time Window",
      description: "固定时间字段、起止范围与统计粒度。",
      items: [timeWindowText],
      emptyText: "未识别明确时间字段。",
    },
    {
      title: "候选方法",
      subtitle: "Candidate Methods",
      description: "保留可执行的分析策略，便于后续链路选择。",
      items: candidateMethods,
      emptyText: "尚未选择候选分析方法。",
    },
    {
      title: "假设",
      subtitle: "Hypotheses",
      description: "记录需要被数据验证或谨慎解释的业务假设。",
      items: hypotheses,
      emptyText: "当前任务没有预设假设。",
    },
    {
      title: "证据需求",
      subtitle: "Evidence",
      description: "说明结论需要哪些图表、表格或校验信号支撑。",
      items: evidenceRequirements,
      emptyText: "尚未声明额外证据需求。",
    },
    {
      title: "安全边界",
      subtitle: "Guardrails",
      description: "约束结论措辞、数据来源和可执行范围。",
      items: guardrails,
      emptyText: "尚未声明额外安全边界。",
    },
  ];

  return (
    <section className="page-section analysis-ir-page">
      <div className="ir-dashboard-hero">
        <div className="ir-hero-copy">
          <div className="ir-title-row">
            <span className="ir-version">
              版本 {analysisIr.schema_version || "1.0"}
            </span>
            <span className="ir-task-chip">{taskType}</span>
          </div>
          <h2>分析专用中间表示（Analysis IR）</h2>
          <p className="ir-goal-text">{goal}</p>
          <p className="ir-digest-text">{digest}</p>
          <div className="ir-hero-actions" aria-label="Analysis IR 状态摘要">
            <span>{lockedScopeCount} 类语义口径已锁定</span>
            <span>
              {confidence
                ? `平均置信度 ${confidence}%`
                : "置信度随字段识别结果生成"}
            </span>
            <span>{formatGeneratedAt(analysisIr.generated_at)}</span>
          </div>
        </div>
        <div className="ir-orbit-panel" aria-hidden="true">
          <div className="ir-orbit-core">
            <span>IR</span>
          </div>
          <span className="ir-orbit-dot dot-a" />
          <span className="ir-orbit-dot dot-b" />
          <span className="ir-orbit-dot dot-c" />
          <div className="ir-signal-bars">
            <span />
            <span />
            <span />
          </div>
        </div>
      </div>

      <div className="ir-flow-strip" aria-label="Analysis IR 流程">
        {FLOW_STEPS.map((step, index) => (
          <div
            className="ir-flow-step"
            key={step}
            style={{ animationDelay: `${index * 80}ms` } as IrStyle}
          >
            <span>{index + 1}</span>
            <strong>{step}</strong>
          </div>
        ))}
      </div>

      <div
        className="ir-summary-grid ir-summary-grid-enhanced"
        aria-label="Analysis IR 概览指标"
      >
        {summaryCards.map((card, index) => (
          <IrMetricCard
            key={card.label}
            label={card.label}
            value={card.value}
            description={card.description}
            total={card.total}
            index={index}
          />
        ))}
      </div>

      <div className="ir-semantic-layout" aria-label="Analysis IR 语义信息">
        <section className="ir-semantic-map ir-card wide">
          <div className="ir-card-heading">
            <div>
              <h3>语义结构地图</h3>
              <p>
                把目标、字段、指标和约束拆成可读模块，便于快速判断分析口径是否完整。
              </p>
            </div>
            <span>
              {semanticSections.reduce(
                (sum, section) => sum + cleanItems(section.items).length,
                0,
              )}{" "}
              项
            </span>
          </div>
          <div className="ir-section-grid ir-section-grid-enhanced">
            {semanticSections.map((section) => (
              <IrSection
                key={`${section.title}-${section.subtitle}`}
                title={section.title}
                subtitle={section.subtitle}
                description={section.description}
                items={section.items}
                emptyText={section.emptyText}
              />
            ))}
          </div>
        </section>

        <aside className="ir-insight-rail">
          <section className="ir-card ir-rail-card">
            <h3>口径完整度</h3>
            <div className="ir-completeness-list">
              <CompletenessItem
                label="业务实体"
                active={entities.length > 0}
                detail={`${entities.length} 项`}
              />
              <CompletenessItem
                label="核心指标"
                active={metrics.length > 0}
                detail={`${metrics.length} 项`}
              />
              <CompletenessItem
                label="拆解维度"
                active={dimensions.length > 0}
                detail={`${dimensions.length} 项`}
              />
              <CompletenessItem
                label="时间范围"
                active={Boolean(timeWindowText)}
                detail={timeWindowText ? "已识别" : "未识别"}
              />
              <CompletenessItem
                label="安全边界"
                active={guardrails.length > 0}
                detail={`${guardrails.length} 项`}
              />
            </div>
          </section>

          <section className="ir-card ir-rail-card">
            <h3>方法预览</h3>
            {candidateMethods.length ? (
              <div className="ir-method-stack">
                {candidateMethods.slice(0, 5).map((method, index) => (
                  <span key={`${method}-${index}`}>{method}</span>
                ))}
              </div>
            ) : (
              <p className="ir-muted">暂无候选方法。</p>
            )}
          </section>

          <section className="ir-card ir-rail-card">
            <h3>约束摘要</h3>
            {guardrails.length ? (
              <ul className="ir-guardrail-list">
                {guardrails.slice(0, 4).map((item, index) => (
                  <li key={`${item}-${index}`}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="ir-muted">暂无额外约束。</p>
            )}
          </section>
        </aside>
      </div>

      <section className="ir-card wide ir-chart-gallery-card">
        <div className="ir-card-heading">
          <div>
            <h3>图表意图</h3>
            <p>用更直观的方式呈现每张图承担的分析任务。</p>
          </div>
          <span>{chartIntents.length || 0} 个</span>
        </div>
        {chartIntents.length ? (
          <div className="ir-chart-intents ir-chart-intents-enhanced">
            {chartIntents.map((item, index) => (
              <article key={`${item.title || item.purpose}-${index}`}>
                <div className="ir-chart-type-icon">
                  {chartTypeIcon(item.chart_type)}
                </div>
                <div>
                  <strong>
                    {item.title || item.purpose || `图表 ${index + 1}`}
                  </strong>
                  <span>{item.chart_type || "chart"}</span>
                  <p>{item.purpose || "展示关键指标。"}</p>
                  <small>
                    {[item.x, item.y, item.group_by]
                      .filter(Boolean)
                      .join(" / ") || "字段待定"}
                  </small>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="ir-muted">暂无图表意图。</p>
        )}
      </section>

      <section className="ir-card wide ir-dependency-card">
        <div className="ir-card-heading">
          <div>
            <h3>输出产物依赖关系</h3>
            <p>标明关键产物的输入来源，帮助判断后续报告和图表的可追溯性。</p>
          </div>
          <span>{outputDependencies.length || 0} 个</span>
        </div>
        {outputDependencies.length ? (
          <ol className="ir-dependency-list ir-dependency-timeline">
            {outputDependencies.map((item, index) => (
              <li key={`${item.artifact}-${index}`}>
                <span className="ir-dependency-index">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <strong>{item.artifact}</strong>
                  <span>
                    依赖：{(item.depends_on ?? []).join("、") || "无"}
                  </span>
                  <p>{item.purpose || "记录分析链路中的关键产物。"}</p>
                </div>
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

function IrMetricCard({
  label,
  value,
  description,
  total,
  index,
}: {
  label: string;
  value: number;
  description: string;
  total: number;
  index: number;
}) {
  const percent =
    total <= 0 ? 0 : Math.min(100, Math.round((value / total) * 100));
  return (
    <article
      className="ir-metric-card"
      style={{ animationDelay: `${index * 90}ms` } as IrStyle}
    >
      <div
        className="ir-metric-ring"
        aria-hidden="true"
        style={{
          background: `radial-gradient(circle at center, #ffffff 55%, transparent 56%), conic-gradient(#0ea5e9 ${percent}%, rgba(226, 232, 240, 0.9) 0)`,
        }}
      >
        <span>{value}</span>
      </div>
      <div>
        <strong>{value}</strong>
        <span>{label}</span>
        <p>{description}</p>
      </div>
    </article>
  );
}

function IrSection({
  title,
  subtitle,
  description,
  items,
  emptyText = "暂无",
}: IrSectionConfig) {
  const clean = cleanItems(items);
  return (
    <section className="ir-card ir-semantic-card">
      <div className="ir-semantic-card-title">
        <div>
          <h3>{title}</h3>
          <span>{subtitle}</span>
        </div>
        <small>{clean.length}</small>
      </div>
      <p className="ir-section-description">{description}</p>
      {clean.length ? (
        <div className="ir-chip-grid ir-chip-grid-enhanced">
          {clean.map((item, index) => (
            <span key={`${title}-${index}-${item}`}>{item}</span>
          ))}
        </div>
      ) : (
        <p className="ir-muted">{emptyText}</p>
      )}
    </section>
  );
}

function CompletenessItem({
  label,
  active,
  detail,
}: {
  label: string;
  active: boolean;
  detail: string;
}) {
  return (
    <div className={active ? "active" : ""}>
      <span />
      <strong>{label}</strong>
      <small>{detail}</small>
    </div>
  );
}

function cleanItems(items: Array<string | null | undefined>): string[] {
  return items.map((item) => String(item || "").trim()).filter(Boolean);
}

function formatFieldRef(
  item:
    | NonNullable<AnalysisIR["entities"]>[number]
    | NonNullable<AnalysisIR["dimensions"]>[number],
): string {
  const name = item.name || item.source_column || "";
  const role = item.role ? ` · ${item.role}` : "";
  const confidence =
    typeof item.confidence === "number"
      ? ` · ${Math.round(item.confidence * 100)}%`
      : "";
  return `${name}${role}${confidence}`;
}

function formatMetric(
  item: NonNullable<AnalysisIR["metrics"]>[number],
): string {
  const name = item.name || item.source_column || "";
  const aggregation = item.aggregation ? ` · ${item.aggregation}` : "";
  const direction = item.direction ? ` · ${item.direction}` : "";
  return `${name}${aggregation}${direction}`;
}

function averageConfidence(value: AnalysisIR): number | null {
  const confidenceValues = [
    ...(value.entities ?? []),
    ...(value.dimensions ?? []),
  ]
    .map((item) => item.confidence)
    .filter(
      (item): item is number =>
        typeof item === "number" && Number.isFinite(item),
    );
  if (!confidenceValues.length) {
    return null;
  }
  const average =
    confidenceValues.reduce((sum, item) => sum + item, 0) /
    confidenceValues.length;
  return Math.round(average * 100);
}

function chartTypeIcon(chartType?: string): string {
  const normalized = String(chartType || "").toLowerCase();
  if (normalized.includes("line")) return "↗";
  if (normalized.includes("bar")) return "▥";
  if (normalized.includes("pie")) return "◔";
  if (normalized.includes("scatter")) return "✣";
  if (normalized.includes("heat")) return "▦";
  return "◇";
}

function formatGeneratedAt(value?: string): string {
  if (!value) {
    return "生成时间待记录";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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
  return [
    value.field ? `字段：${value.field}` : "",
    value.start ? `开始：${value.start}` : "",
    value.end ? `结束：${value.end}` : "",
    value.granularity ? `粒度：${value.granularity}` : "",
    value.description || "",
  ]
    .filter(Boolean)
    .join("；");
}

