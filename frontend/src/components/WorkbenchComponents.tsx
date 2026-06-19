import { useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent as ReactDragEvent, PointerEvent as ReactPointerEvent } from "react";

import { toStorageUrl } from "../api";
import { toVersionedStorageUrl } from "./workbench/charts/chartHelpers";
import type {
  AnalysisRoadmap,
  AnalysisResult,
  DashboardConfig,
  DashboardWidget,
  DatasetDataMap,
  DatasetDataMapNode,
  DebateReflection,
  CleaningPlanResponse,
  CleaningReportResponse,
  DatasetProfile,
  ExecutionAttemptLog,
  ExecutionLogEvent,
  ExplanationResult,
  EvidenceChain,
  EvidenceFinding,
  HealthStatus,
  KnowledgeDocument,
  KnowledgeSearchResponse,
  PredictionExplanationResult,
  PredictionResult,
  PptPreview,
  PreflightAssessment,
  QualityReview,
  CrossArtifactConsistencyReport,
  ReportGenerateResponse,
  SampleDatasetResponse,
  ValidationAttemptLog,
  VisualParseResult,
  WorkflowFollowUpResponse,
  WorkflowAgentConsoleResponse,
  WorkflowAgentProfile,
  WorkflowAgentUpdateRequest,
  FollowUpRecommendation,
  WorkflowJobListItem,
  WorkflowJobResponse,
  WorkflowLogResponse
} from "../types";
import {
  agentInitial,
  arrayValue,
  attemptStageClass,
  attemptStageText,
  attemptStatusClass,
  attemptStatusText,
  buildAgentCards,
  buildAttemptProgressViews,
  buildNoChartReason,
  buildPredictionSteps,
  chartTitle,
  eventStatusLabel,
  formatCell,
  formatDateTime,
  formatListItem,
  formatNumber,
  formatPercent,
  formatTime,
  getChartPaths,
  imageTypeLabel,
  interventionDisplay,
  normalizePptOutline,
  predictionPlanSummary,
  ragSummary,
  severityLabel,
  shortPath,
  stageLabel,
  statusFromJob,
  statusLabel,
  stepStatusLabel,
  stringValue,
  structuredFieldValue,
  workflowLabel
} from "../utils/workbenchUtils";
import type { AgentCardView, AnyRecord, AttemptProgressView, StepView } from "../utils/workbenchUtils";

export function SetupPage({
  profile,
  health,
  isFallbackMode
}: {
  profile: DatasetProfile | null;
  health: HealthStatus | null;
  isFallbackMode: boolean;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>开始一次分析</h2>
        <span>{isFallbackMode ? "规则分析模式" : "智能分析模式"}</span>
      </div>
      <div className="setup-grid">
        <article className="info-card">
          <strong>1. 上传数据</strong>
          <p>支持 CSV、XLSX、XLS 和图片截图。图片会先抽取为结构化数据，再进入 Agent 工作流。</p>
        </article>
        <article className="info-card">
          <strong>2. 输入目标</strong>
          <p>例如“按班级统计成绩并生成图表”或“找出影响销量下降的可能原因”。</p>
        </article>
        <article className="info-card">
          <strong>3. 查看过程</strong>
          <p>启动后会立即进入 Agent 过程页，状态、图表和报告会实时刷新。</p>
        </article>
      </div>
      <dl className="info-list wide">
        <div>
          <dt>DeepSeek 状态</dt>
          <dd>{health?.message ?? "正在读取配置"}</dd>
        </div>
        {profile ? (
          <div>
            <dt>字段</dt>
            <dd>{profile.columns.join("、")}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}


export function SampleDataPanel({
  onGenerate,
  disabled
}: {
  onGenerate: (sampleType: string) => void;
  disabled: boolean;
}) {
  const samples = [
    { key: "sales_decline", title: "销售下降案例", desc: "含日期、地区、渠道、商品类别、销量和销售额。" },
    { key: "grade_scores", title: "成绩统计案例", desc: "含班级、姓名、学号、单科成绩和综合成绩。" },
    { key: "survey_feedback", title: "问卷调查案例", desc: "含满意度、NPS、渠道和反馈文本。" },
    { key: "health_activity", title: "运动健康案例", desc: "含步数、睡眠、心率、运动时长和消耗热量。" },
    { key: "ecommerce_orders", title: "电商订单案例", desc: "含订单、品类、地区、客单价、复购和退款。" }
  ];

  return (
    <div className="sample-data-panel">
      <strong>您可以先通过示例数据尝试系统功能</strong>
      <p>无需准备文件，选择一个示例即可预览数据、修改分析目标并快速体验完整流程。</p>
      <div className="sample-grid">
        {samples.map((sample) => (
          <button key={sample.key} type="button" disabled={disabled} onClick={() => onGenerate(sample.key)}>
            <span>{sample.title}</span>
            <small>{sample.desc}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

export function SamplePreviewModal({
  sample,
  rowCount,
  columns,
  rows,
  goal,
  onGoalChange,
  onConfirm,
  onSelect,
  onCancel
}: {
  sample: SampleDatasetResponse;
  rowCount: number;
  columns: string[];
  rows: AnyRecord[];
  goal: string;
  onGoalChange: (goal: string) => void;
  onConfirm: () => void;
  onSelect: () => void;
  onCancel: () => void;
}) {
  const visibleColumns = columns.slice(0, 10);
  const previewRows = rows.slice(0, 30);
  const suggestions = (sample.suggested_goals?.length ? sample.suggested_goals : [sample.recommended_goal]).slice(0, 4);

  return (
    <div className="sample-preview-backdrop" role="dialog" aria-modal="true" aria-label="示例数据预览">
      <div className="sample-preview-modal">
        <div className="sample-preview-head">
          <div>
            <strong>{sample.filename}</strong>
            <p>{sample.description}</p>
          </div>
          <button type="button" onClick={onCancel}>
            暂不分析
          </button>
        </div>
        <div className="sample-preview-meta">
          <span>{rowCount} 行</span>
          <span>{columns.length} 列</span>
          <span>推荐目标：{sample.recommended_goal}</span>
        </div>
        <div className="sample-preview-table-wrap">
          <table>
            <thead>
              <tr>
                {visibleColumns.map((column) => (
                  <th key={column}>{column}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {previewRows.map((row, rowIndex) => (
                <tr key={`sample-${rowIndex}`}>
                  {visibleColumns.map((column) => (
                    <td key={`${rowIndex}-${column}`}>{formatCell(row[column])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <section className="sample-goal-section">
          <label className="form-label" htmlFor="sample-analysis-goal">
            试用分析目标
          </label>
          <textarea
            id="sample-analysis-goal"
            rows={4}
            value={goal}
            onChange={(event) => onGoalChange(event.target.value)}
          />
          <div className="sample-goal-options" aria-label="可直接使用的示例分析目标">
            {suggestions.map((suggestion) => (
              <button key={suggestion} type="button" onClick={() => onGoalChange(suggestion)}>
                {suggestion}
              </button>
            ))}
          </div>
        </section>
        <p className="sample-preview-note">当前显示前 {previewRows.length} 行。确认后系统将使用该 CSV 和上方分析目标进入多 Agent 分析流程。</p>
        <div className="sample-preview-actions">
          <a className="secondary-button sample-download-link" href={toStorageUrl(sample.file_path)} download>
            下载 CSV
          </a>
          <button className="secondary-button" type="button" onClick={onSelect}>
            选中该文件
          </button>
          <button className="secondary-button" type="button" onClick={onCancel}>
            暂不分析
          </button>
          <button className="primary-button" type="button" onClick={onConfirm}>
            确认并开始分析
          </button>
        </div>
      </div>
    </div>
  );
}

export function PreflightPanel({
  assessment,
  onApplyGoal,
  onApplyAndRun
}: {
  assessment: PreflightAssessment;
  onApplyGoal: (goal: string) => void;
  onApplyAndRun: (goal: string) => void;
}) {
  const [selectedOptions, setSelectedOptions] = useState<Record<string, string>>({});
  const qualityItems = Object.entries(assessment.data_quality_report ?? {}).filter(([, value]) => Boolean(value));

  useEffect(() => {
    setSelectedOptions({});
  }, [assessment.preflight_path, assessment.user_goal]);

  const optimizedGoal = useMemo(
    () => composeOptimizedGoal(assessment, selectedOptions),
    [assessment, selectedOptions]
  );

  return (
    <section className="preflight-card">
      <div className="preflight-head">
        <strong>意图识别</strong>
        <span className={assessment.is_task_clear ? "success-badge" : "warning-badge"}>
          {assessment.is_task_clear ? "可直接分析" : "建议补充"}
        </span>
      </div>
      <p className="preflight-intro">AI 会先优化您的提示词，并补充关键口径，让后续分析结果更贴近目标。</p>
      <dl className="compact-list artifact-kv">
        <div>
          <dt>意图类型</dt>
          <dd>{workflowLabel(assessment.intent_type)}</dd>
        </div>
        <div>
          <dt>清晰度</dt>
          <dd>{Math.round((assessment.clarity_score ?? 0) * 100)}%</dd>
        </div>
        <div>
          <dt>下一步</dt>
          <dd>{assessment.next_action === "needs_user_choice" ? "请选择优化项" : "可以继续执行"}</dd>
        </div>
      </dl>

      {assessment.intent_questions?.length ? (
        <div className="intent-question-list">
          {assessment.intent_questions.slice(0, 4).map((question, questionIndex) => (
            <article className="intent-question" key={question.question_id || `question-${questionIndex}`}>
              <strong>{question.question}</strong>
              <div className="intent-choice-grid">
                {question.options.slice(0, 4).map((option) => {
                  const active = selectedOptions[question.question_id] === option.value;
                  return (
                    <button
                      className={active ? "active" : ""}
                      key={`${question.question_id}-${option.value}`}
                      type="button"
                      onClick={() => setSelectedOptions((current) => ({ ...current, [question.question_id]: option.value }))}
                    >
                      {option.label}
                    </button>
                  );
                })}
              </div>
            </article>
          ))}
        </div>
      ) : null}

      <div className="optimized-goal-box">
        <span>优化后的分析目标</span>
        <p>{optimizedGoal}</p>
      </div>
      <div className="intent-actions">
        <button className="secondary-button" type="button" onClick={() => onApplyGoal(optimizedGoal)}>
          应用到分析目标
        </button>
        <button className="primary-button" type="button" onClick={() => onApplyAndRun(optimizedGoal)}>
          应用并启动分析
        </button>
      </div>

      <ChipList title="仍需确认的问题" items={assessment.clarifying_questions ?? []} tone="warning" />
      <ChipList title="推荐目标写法" items={assessment.suggested_goals ?? []} />
      {qualityItems.length ? (
        <details className="raw-json-details compact">
          <summary>查看数据质量摘要</summary>
          <pre>{JSON.stringify(assessment.data_quality_report, null, 2)}</pre>
        </details>
      ) : null}
    </section>
  );
}

export function RoadmapPage({
  roadmap,
  job
}: {
  roadmap: AnalysisRoadmap | null;
  job: WorkflowJobResponse | null;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>分析路线图</h2>
        {job ? <span>{workflowLabel(job.workflow_type || job.task_type)} · {stageLabel(job.current_stage || job.status)}</span> : <span>等待主控规划</span>}
      </div>
      {roadmap ? (
        <>
          <article className="info-card roadmap-summary">
            <strong>{roadmap.title}</strong>
            <p>{roadmap.summary}</p>
          </article>
          <article className="info-card roadmap-rendered-card">
            <div className="roadmap-rendered-head">
              <strong>可视化执行路线</strong>
              <span>{roadmap.graph_type || "flowchart"}</span>
            </div>
            {roadmap.mermaid_code ? (
              <MermaidDiagram code={roadmap.mermaid_code} steps={roadmap.steps} />
            ) : (
              <RoadmapRenderedDiagram steps={roadmap.steps} />
            )}
          </article>
        </>
      ) : (
        <EmptyState title="暂无分析路线图" text="任务启动后，主控 Agent 会先生成可视化路线图，再进入执行链路。" />
      )}
    </section>
  );
}


export function RoadmapRenderedDiagram({ steps }: { steps: AnalysisRoadmap["steps"] }) {
  return (
    <div className="roadmap-rendered-diagram" aria-label="已渲染的多 Agent 分析流程图">
      {steps.map((step, index) => (
        <div className="roadmap-rendered-step-wrap" key={`${step.step_id}-${index}`}>
          <article className="roadmap-rendered-step">
            <span className="roadmap-rendered-index">{index + 1}</span>
            <div>
              <small>{step.agent}</small>
              <strong>{step.title}</strong>
              <p>{step.description}</p>
              <em>{stageLabel(step.stage)} · {step.outputs.join("、") || "结构化产物"}</em>
            </div>
          </article>
          {index < steps.length - 1 ? <span className="roadmap-rendered-arrow">↓</span> : null}
        </div>
      ))}
    </div>
  );
}

function composeOptimizedGoal(assessment: PreflightAssessment, selectedOptions: Record<string, string>): string {
  const pieces = [assessment.optimized_goal || assessment.user_goal || assessment.suggested_goals?.[0] || ""];
  (assessment.intent_questions ?? []).forEach((question) => {
    const selectedValue = selectedOptions[question.question_id];
    const option = question.options.find((item) => item.value === selectedValue);
    if (option?.append_text) {
      pieces.push(option.append_text);
    }
  });
  const seen = new Set<string>();
  return pieces
    .map((piece) => piece.trim())
    .filter((piece) => {
      if (!piece || seen.has(piece)) {
        return false;
      }
      seen.add(piece);
      return true;
    })
    .join(" ");
}

export function MermaidDiagram({ code, steps }: { code: string; steps?: AnalysisRoadmap["steps"] }) {
  const graph = useMemo(() => parseMermaidFlowchart(code, steps ?? []), [code, steps]);

  if (!graph.nodes.length) {
    return <pre className="mermaid-diagram mermaid-code-fallback">{code}</pre>;
  }

  const nodeWidth = 270;
  const nodeHeight = 82;
  const gap = 42;
  const padding = 28;
  const width = nodeWidth + padding * 2;
  const height = padding * 2 + graph.nodes.length * nodeHeight + Math.max(0, graph.nodes.length - 1) * gap;

  return (
    <div className="mermaid-diagram roadmap-svg-frame" aria-label="流程图渲染结果">
      <svg viewBox={`0 0 ${width} ${height}`} role="img">
        <defs>
          <marker id="roadmap-arrow" markerWidth="10" markerHeight="10" refX="5" refY="5" orient="auto" markerUnits="strokeWidth">
            <path d="M 0 0 L 10 5 L 0 10 z" />
          </marker>
        </defs>
        {graph.nodes.map((node, index) => {
          const x = padding;
          const y = padding + index * (nodeHeight + gap);
          const isFirst = index === 0;
          const isLast = index === graph.nodes.length - 1;
          return (
            <g key={node.id}>
              {index > 0 ? (
                <line
                  x1={width / 2}
                  y1={y - gap + 8}
                  x2={width / 2}
                  y2={y - 10}
                  className="roadmap-svg-edge"
                  markerEnd="url(#roadmap-arrow)"
                />
              ) : null}
              <rect
                x={x}
                y={y}
                width={nodeWidth}
                height={nodeHeight}
                rx={isFirst || isLast ? 38 : 18}
                className={isFirst || isLast ? "roadmap-svg-node endpoint" : "roadmap-svg-node"}
              />
              <circle cx={x + 34} cy={y + 41} r="18" className="roadmap-svg-index" />
              <text x={x + 34} y={y + 46} textAnchor="middle" className="roadmap-svg-index-text">{index + 1}</text>
              <text x={x + 64} y={y + 32} className="roadmap-svg-title">{node.title}</text>
              <text x={x + 64} y={y + 55} className="roadmap-svg-agent">{node.agent || node.stage || "Agent"}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function parseMermaidFlowchart(code: string, fallbackSteps: AnalysisRoadmap["steps"]): { nodes: Array<{ id: string; title: string; agent: string; stage?: string }> } {
  const nodes = new Map<string, { id: string; title: string; agent: string; stage?: string }>();
  const order: string[] = [];

  code.split(/\r?\n/).forEach((line) => {
    const nodeMatch = line.match(/^\s*([A-Za-z0-9_]+)\["(.+)"\]\s*$/);
    if (!nodeMatch) {
      return;
    }
    const id = nodeMatch[1];
    const labelParts = nodeMatch[2].split(/<br\s*\/?>(?![^<]*>)/i);
    const title = (labelParts[0] || id).replace(/^\d+\.\s*/, "");
    const agent = labelParts.slice(1).join(" ");
    if (!nodes.has(id)) {
      order.push(id);
    }
    nodes.set(id, { id, title, agent });
  });

  const edgeOrder: string[] = [];
  code.split(/\r?\n/).forEach((line) => {
    const edgeMatch = line.match(/^\s*([A-Za-z0-9_]+)\s*--?>\s*([A-Za-z0-9_]+)\s*$/);
    if (!edgeMatch) {
      return;
    }
    const [from, to] = [edgeMatch[1], edgeMatch[2]];
    if (nodes.has(from) && !edgeOrder.includes(from)) {
      edgeOrder.push(from);
    }
    if (nodes.has(to) && !edgeOrder.includes(to)) {
      edgeOrder.push(to);
    }
  });

  const finalOrder = edgeOrder.length ? edgeOrder : order;
  const parsedNodes = finalOrder.map((id) => nodes.get(id)).filter((node): node is { id: string; title: string; agent: string; stage?: string } => Boolean(node));
  if (parsedNodes.length) {
    return { nodes: parsedNodes };
  }
  return {
    nodes: (fallbackSteps || []).map((step, index) => ({
      id: step.step_id || `S${index + 1}`,
      title: step.title || `步骤 ${index + 1}`,
      agent: step.agent || "Agent",
      stage: step.stage
    }))
  };
}





export function QualityReviewPanel({ review }: { review: QualityReview | null }) {
  if (!review) {
    return null;
  }
  return (
    <section className="quality-review-card">
      <div className="section-heading compact-heading">
        <h2>质检 Agent 自检</h2>
        <span className={review.passed ? "success-badge" : "warning-badge"}>
          {review.passed ? "自检通过" : `存在${review.risk_level || "风险"}`}
        </span>
      </div>
      {review.revised_summary ? <p className="summary-text">{review.revised_summary}</p> : null}
      {review.issues.length ? (
        <div className="issue-list">
          <span>风险清单</span>
          {review.issues.map((issue, index) => (
            <article key={`${issue.issue_type}-${index}`}>
              <strong>{severityLabel(issue.severity)} · {issue.issue_type}</strong>
              <p>{issue.finding}</p>
              {issue.evidence ? <small>{issue.evidence}</small> : null}
              {issue.suggestion ? <p>{issue.suggestion}</p> : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="agent-muted">未发现需要阻断的结论风险。</p>
      )}
      <ChipList title="安全表述建议" items={review.safe_language_suggestions ?? []} />
      <ChipList title="缺失证据" items={review.missing_evidence ?? []} tone="warning" />
    </section>
  );
}

export function ConsistencyReportPanel({ report }: { report: CrossArtifactConsistencyReport | null }) {
  if (!report) {
    return null;
  }
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const visibleChecks = checks.filter((check) => String(check.status || "pass") !== "pass").slice(0, 5);
  return (
    <div className="consistency-panel">
      <header>
        <strong>跨产物口径一致性 Agent</strong>
        <span className={report.passed ? "" : "warning"}>{report.passed ? "一致性通过" : `存在${severityLabel(report.risk_level)}风险`}</span>
      </header>
      <p className="agent-muted">{report.summary || "已扫描解释、报告数据、PPT 大纲、Dashboard、图表标题和追问回答等产物。"}</p>
      {visibleChecks.length ? (
        <div className="consistency-check-list">
          {visibleChecks.map((check, index) => (
            <article key={`${check.check_id}-${index}`}>
              <strong>{severityLabel(String(check.severity || "low"))} · {check.topic}</strong>
              <p>{check.finding}</p>
              {check.suggested_action ? <small>{check.suggested_action}</small> : null}
            </article>
          ))}
        </div>
      ) : (
        <p className="agent-muted">未发现日期范围、指标口径、样本条件、单位或基准口径冲突。</p>
      )}
    </div>
  );
}

export function HistoryPanel({
  items,
  activeJobId,
  loading,
  message,
  searchQuery,
  deletingJobId,
  selectedJobIds,
  onRefresh,
  onSearchQueryChange,
  onSearch,
  onClearSearch,
  onToggleSelection,
  onToggleSelectAll,
  onDeleteSelected,
  onOpen,
  onDelete
}: {
  items: WorkflowJobListItem[];
  activeJobId: string | null;
  loading: boolean;
  message: string;
  searchQuery: string;
  deletingJobId: string | null;
  selectedJobIds: string[];
  onRefresh: () => void;
  onSearchQueryChange: (query: string) => void;
  onSearch: () => void;
  onClearSearch: () => void;
  onToggleSelection: (jobId: string, checked: boolean) => void;
  onToggleSelectAll: () => void;
  onDeleteSelected: () => void;
  onOpen: (jobId: string) => void;
  onDelete: (jobId: string) => void;
}) {
  const hasSearchQuery = searchQuery.trim().length > 0;
  const selectedCount = selectedJobIds.filter((jobId) => items.some((item) => item.job_id === jobId)).length;
  const allSelected = items.length > 0 && items.every((item) => selectedJobIds.includes(item.job_id));

  return (
    <section className="panel history-panel">
      <div className="panel-header">
        <h2>分析对话列表</h2>
        <button className="text-button" type="button" disabled={loading} onClick={onRefresh}>
          {loading ? "刷新中" : "刷新"}
        </button>
      </div>
      <form
        className="history-search"
        onSubmit={(event) => {
          event.preventDefault();
          onSearch();
        }}
      >
        <input
          aria-label="查找分析对话"
          type="search"
          value={searchQuery}
          placeholder="按目标、文件名、状态或任务编号查找"
          disabled={loading}
          onChange={(event) => onSearchQueryChange(event.target.value)}
        />
        <button className="history-search-button" type="submit" disabled={loading}>
          查找
        </button>
        {hasSearchQuery ? (
          <button className="text-button history-clear-button" type="button" disabled={loading} onClick={onClearSearch}>
            清空
          </button>
        ) : null}
      </form>
      <div className="history-bulk-actions">
        <label>
          <input type="checkbox" checked={allSelected} disabled={!items.length || loading} onChange={() => onToggleSelectAll()} />
          全选
        </label>
        <button className="history-delete-selected-button" type="button" disabled={!selectedCount || loading || Boolean(deletingJobId)} onClick={onDeleteSelected}>
          删除选中{selectedCount ? `（${selectedCount}）` : ""}
        </button>
      </div>
      {message ? <p className="history-message">{message}</p> : null}
      {items.length ? (
        <div className="history-list">
          {items.map((item) => {
            const active = item.job_id === activeJobId;
            const deleting = deletingJobId === item.job_id;
            const selected = selectedJobIds.includes(item.job_id);
            return (
              <article className={`history-item ${active ? "active" : ""}`} key={item.job_id}>
                <label className="history-select-checkbox" aria-label="选择分析对话">
                  <input
                    type="checkbox"
                    checked={selected}
                    disabled={loading || deleting}
                    onChange={(event) => onToggleSelection(item.job_id, event.target.checked)}
                  />
                </label>
                <button className="history-open-button" type="button" onClick={() => onOpen(item.job_id)}>
                  <span className="history-item-title">{workflowLabel(item.workflow_type || item.task_type)}</span>
                  <span className="history-item-goal">{item.user_goal || "未记录分析目标"}</span>
                  <span className="history-item-meta">
                    {item.dataset_filename || item.dataset_id || "未知数据集"} · {statusLabel(item.status)} · {formatDateTime(item.updated_at || item.created_at || "")}
                  </span>
                </button>
                <button
                  className="history-delete-button"
                  type="button"
                  disabled={loading || deleting}
                  onClick={() => onDelete(item.job_id)}
                >
                  {deleting ? "删除中" : "删除"}
                </button>
              </article>
            );
          })}
        </div>
      ) : (
        <p className="history-empty">{hasSearchQuery ? "没有匹配的分析对话。" : "暂无可复看的分析对话。"}</p>
      )}
    </section>
  );
}

export function KnowledgePage({
  documents,
  selectedFile,
  query,
  searchResult,
  message,
  onFileChange,
  onQueryChange,
  onUpload,
  onSearch,
  onDelete
}: {
  documents: KnowledgeDocument[];
  selectedFile: File | null;
  query: string;
  searchResult: KnowledgeSearchResponse | null;
  message: string;
  onFileChange: (file: File | null) => void;
  onQueryChange: (query: string) => void;
  onUpload: () => void;
  onSearch: () => void;
  onDelete: (docId: string) => void;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>全局业务知识库</h2>
        <span>{documents.length} 个文档</span>
      </div>

      <div className="knowledge-grid">
        <article className="info-card">
          <strong>上传知识文档</strong>
          <label className="upload-zone compact-upload">
            <input
              type="file"
              accept=".txt,.md"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
            <span>{selectedFile ? selectedFile.name : "选择 .txt / .md 文件"}</span>
          </label>
          <button className="primary-button" type="button" onClick={onUpload}>
            写入知识库
          </button>
          {message ? <p className="message success">{message}</p> : null}
        </article>

        <article className="info-card">
          <strong>测试检索</strong>
          <textarea
            rows={4}
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
          <button className="secondary-button" type="button" onClick={onSearch}>
            检索知识库
          </button>
        </article>
      </div>

      <div className="knowledge-grid">
        <section className="info-card">
          <strong>文档列表</strong>
          {documents.length ? (
            <div className="document-list">
              {documents.map((document) => (
                <article className="document-item" key={document.doc_id}>
                  <div>
                    <strong>{document.filename}</strong>
                    <p>
                      {document.chunk_count} chunks · {document.indexed ? "已索引" : "未索引"}
                    </p>
                    {document.index_error ? <p>{document.index_error}</p> : null}
                  </div>
                  <button type="button" onClick={() => onDelete(document.doc_id)}>
                    删除
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <p>暂无知识文档。</p>
          )}
        </section>

        <section className="info-card">
          <strong>检索结果</strong>
          {searchResult ? (
            <>
              <p>{searchResult.message}</p>
              <div className="document-list">
                {searchResult.results.map((item, index) => (
                  <article className="document-item result" key={`${item.doc_id}-${item.chunk_index}-${index}`}>
                    <div>
                      <strong>{item.filename || `片段 ${index + 1}`}</strong>
                      <p>{item.chunk}</p>
                      <span>score {item.score ?? "-"}</span>
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <p>输入问题后可以查看 top-k 知识片段。</p>
          )}
        </section>
      </div>
    </section>
  );
}

export function PredictionPage({
  file,
  goal,
  status,
  message,
  job,
  log,
  hypothesisPlan,
  predictionPlan,
  predictionResult,
  explanation,
  onFileChange,
  onGoalChange,
  onRun
}: {
  file: File | null;
  goal: string;
  status: string;
  message: string;
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  predictionResult: PredictionResult | null;
  explanation: PredictionExplanationResult;
  onFileChange: (file: File | null) => void;
  onGoalChange: (goal: string) => void;
  onRun: () => void;
}) {
  const events = log?.events?.length ? log.events : job?.events ?? [];
  const chartPaths = getChartPaths(predictionResult, job);
  const unsupportedReason = predictionResult?.status === "unsupported"
    ? stringValue(predictionResult.unsupported_reason, "当前数据缺少完成该情景预测所需的字段。")
    : "";
  const steps = buildPredictionSteps({
    job,
    log,
    controllerPlan: null,
    ragRetrieval: null,
    visualParseResult: null,
    hypothesisPlan,
    predictionPlan,
    predictionResult,
    explanation,
    qualityReview: null,
    events
  });

  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>情景预测</h2>
        <span>{job ? `Job ${job.job_id}` : "What-if Simulation"}</span>
      </div>

      <div className="knowledge-grid">
        <article className="info-card">
          <strong>上传预测数据</strong>
          <label className="upload-zone compact-upload">
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
            <span>{file ? file.name : "选择 CSV / Excel 文件"}</span>
          </label>
          <label className="form-label" htmlFor="prediction-goal">
            假设性问题
          </label>
          <textarea
            id="prediction-goal"
            rows={4}
            value={goal}
            onChange={(event) => onGoalChange(event.target.value)}
          />
          <button
            className="primary-button"
            type="button"
            disabled={status === "uploading" || status === "running"}
            onClick={onRun}
          >
            启动情景预测
          </button>
          {message ? <p className={`message ${status === "failed" ? "error" : "success"}`}>{message}</p> : null}
        </article>

        <article className="info-card">
          <strong>示例问题</strong>
          <p>如果下个月营销预算增加 20%，哪些商品的销量最可能提升？</p>
          <p>如果将平时成绩权重提升 10%，不及格率会发生什么变化？</p>
          <p>预测结果是基于当前数据的模拟估计，不代表确定因果。</p>
        </article>
      </div>

      <section className="result-section">
        <div className="section-heading">
          <h2>预测 Agent 过程</h2>
          <span>{job ? job.current_stage ?? job.status : "等待启动"}</span>
        </div>
        <div className="agent-timeline">
          {steps.map((step) => (
            <article className={`agent-step ${step.status}`} key={step.key}>
              <span className="agent-dot" />
              <div>
                <strong>{step.title}</strong>
                <p>{step.summary}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {predictionResult ? (
        unsupportedReason ? (
          <section className="result-section">
            <div className="section-heading">
              <h2>情景预测无法计算</h2>
              <span>{predictionResult.model_info?.method ? String(predictionResult.model_info.method) : "unsupported"}</span>
            </div>
            <p className="summary-text">{unsupportedReason}</p>
            <ResultList title="限制说明" items={arrayValue(predictionResult.limitations).map(String)} />
          </section>
        ) : (
          <section className="result-section">
            <div className="section-heading">
              <h2>预测影响 Top 对象</h2>
              <span>{predictionResult.model_info?.method ? String(predictionResult.model_info.method) : "model"}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>对象</th>
                    <th>基准值</th>
                    <th>预测值</th>
                    <th>变化</th>
                    <th>变化率</th>
                  </tr>
                </thead>
                <tbody>
                  {predictionResult.top_impacted_entities.map((item) => (
                    <tr key={`${item.entity}-${item.absolute_change}`}>
                      <td>{item.entity}</td>
                      <td>{formatNumber(item.baseline_value)}</td>
                      <td>{formatNumber(item.predicted_value)}</td>
                      <td>{formatNumber(item.absolute_change)}</td>
                      <td>{formatPercent(item.percent_change)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )
      ) : null}

      {chartPaths.length ? (
        <section className="result-section">
          <div className="section-heading">
            <h2>预测图表</h2>
            <span>{chartPaths.length} 个图表</span>
          </div>
          <div className="chart-grid">
            {chartPaths.map((chartPath, index) => (
              <figure className="chart-card" key={chartPath}>
                <img alt={`预测图表 ${index + 1}`} src={toStorageUrl(chartPath)} />
                <figcaption>{chartTitle(chartPath, index)}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ) : null}

      {explanation.summary ? (
        <section className="result-section">
          <div className="section-heading">
            <h2>预测解释</h2>
            <span>谨慎表述</span>
          </div>
          <p className="summary-text">{explanation.summary}</p>
          <ResultList title="关键发现" items={explanation.key_findings} />
          <ResultList title="建议动作" items={explanation.recommendations} />
          <ResultList title="限制说明" items={explanation.limitations} />
        </section>
      ) : null}

      <div className="agent-output-grid">
        <JsonSummary title="假设解析 Agent 输出" value={hypothesisPlan} />
        <JsonSummary title="预测计划 Agent 输出" value={predictionPlan} />
      </div>
    </section>
  );
}


const AGENT_PORTRAIT_KEYS = new Set([
  "visual",
  "rag",
  "controller",
  "understanding",
  "analysis",
  "hypothesis",
  "prediction_plan",
  "code",
  "safety",
  "sandbox",
  "validation",
  "debate_matrix",
  "explanation",
  "quality_review",
  "cross_artifact_consistency",
  "generic"
]);

function agentPortraitPath(agentKey: string): string {
  const normalizedKey = AGENT_PORTRAIT_KEYS.has(agentKey) ? agentKey : "generic";
  return `/agent-portraits/${normalizedKey}.svg`;
}

function AgentPortrait({ card, size = "medium" }: { card: AgentCardView; size?: "small" | "medium" | "large" }) {
  return (
    <span className={`agent-portrait agent-portrait-${size} agent-portrait-status-${card.status}`}>
      <img src={agentPortraitPath(card.key)} alt={`${card.agentName} 形象`} />
    </span>
  );
}

function processProgressPercent(cards: AgentCardView[]): number {
  if (!cards.length) {
    return 0;
  }
  return Math.round((cards.filter((card) => card.status === "done").length / cards.length) * 100);
}

function selectSpotlightAgent(cards: AgentCardView[]): AgentCardView | null {
  return (
    cards.find((card) => card.status === "active") ??
    cards.find((card) => card.status === "failed") ??
    [...cards].reverse().find((card) => card.status === "done") ??
    cards[0] ??
    null
  );
}

function agentOrderLabel(index: number, total: number): string {
  if (index < 0 || total <= 0) {
    return "等待接入";
  }
  return `第 ${index + 1} / ${total} 位 Agent`;
}


export function ProcessPage({
  job,
  log,
  steps,
  controllerPlan,
  ragRetrieval,
  visualParseResult,
  dataUnderstanding,
  analysisPlan,
  hypothesisPlan,
  predictionPlan,
  explanation,
  debateReflection,
  qualityReview,
  isPredictionWorkflow,
  events,
  onControlJob,
  controlLoadingAction
}: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  steps: StepView[];
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  visualParseResult: VisualParseResult | null;
  dataUnderstanding: AnyRecord | null;
  analysisPlan: AnyRecord | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  explanation: ExplanationResult;
  debateReflection: DebateReflection | null;
  qualityReview: QualityReview | null;
  isPredictionWorkflow: boolean;
  events: ExecutionLogEvent[];
  onControlJob?: (action: string) => void;
  controlLoadingAction?: string | null;
}) {
  const cards = buildAgentCards({
    job,
    log,
    steps,
    controllerPlan,
    ragRetrieval,
    visualParseResult,
    dataUnderstanding,
    analysisPlan,
    hypothesisPlan,
    predictionPlan,
    explanation,
    debateReflection,
    qualityReview,
    isPredictionWorkflow
  });
  const attemptViews = buildAttemptProgressViews({
    job,
    log,
    events
  });
  const spotlightAgent = selectSpotlightAgent(cards);
  const spotlightIndex = spotlightAgent ? cards.findIndex((card) => card.key === spotlightAgent.key) : -1;
  const latestEvent = events.length ? events[events.length - 1] : null;

  return (
    <section className="page-section process-page process-page-vn">
      <div className="section-heading process-heading process-heading-enhanced">
        <div>
          <h2>Agent 协作现场</h2>
          {job ? <span>{workflowLabel(job.workflow_type || job.task_type)} · Job {job.job_id}</span> : <span>等待任务启动</span>}
        </div>
        {cards.length ? <span>{processProgressPercent(cards)}% 完成</span> : null}
      </div>
      {job && onControlJob ? (
        <JobControlDock
          job={job}
          loadingAction={controlLoadingAction || null}
          onControlJob={onControlJob}
        />
      ) : null}
      <AgentStoryStage
        cards={cards}
        spotlightAgent={spotlightAgent}
        spotlightIndex={spotlightIndex}
        latestEvent={latestEvent}
      />
      <div className="agent-chat-list agent-dialog-list" aria-label="Agent 详细输出">
        {cards.length ? (
          cards.map((card) => <AgentMessageCard card={card} key={card.key} />)
        ) : (
          <EmptyState title="等待 Agent 接入" text="任务启动后，参与工作的 Agent 会按执行顺序逐个出现在这里。" compact />
        )}
      </div>
      <QualityReviewPanel review={qualityReview} />
      <AttemptProgressSection attempts={attemptViews} isPredictionWorkflow={isPredictionWorkflow} />
    </section>
  );
}

function AgentStoryStage({
  cards,
  spotlightAgent,
  spotlightIndex,
  latestEvent
}: {
  cards: AgentCardView[];
  spotlightAgent: AgentCardView | null;
  spotlightIndex: number;
  latestEvent: ExecutionLogEvent | null;
}) {
  if (!spotlightAgent) {
    return <EmptyState title="等待任务启动" text="上传数据并提交目标后，Agent 协作现场会展示当前出场的智能体、动作和产物进度。" compact />;
  }

  return (
    <div className="agent-story-stage" aria-label="Agent 协作现场概览">
      <div className={`agent-story-spotlight ${spotlightAgent.status}`} role="status" aria-live="polite">
        <div className="agent-story-character">
          <span className="agent-story-halo" />
          <AgentPortrait card={spotlightAgent} size="large" />
        </div>
        <div className="agent-story-dialogue">
          <span className="agent-scene-label">当前出场 · {agentOrderLabel(spotlightIndex, cards.length)}</span>
          <h3>{spotlightAgent.agentName}</h3>
          <p>{spotlightAgent.output || spotlightAgent.action}</p>
          <dl>
            <div>
              <dt>输入</dt>
              <dd>{spotlightAgent.inputSource}</dd>
            </div>
            <div>
              <dt>动作</dt>
              <dd>{spotlightAgent.action}</dd>
            </div>
          </dl>
          {latestEvent ? <small>{stageLabel(latestEvent.stage)} · {eventStatusLabel(latestEvent.status)} · {formatTime(latestEvent.timestamp)}</small> : null}
        </div>
      </div>
      <div className="agent-cast-strip" aria-label="Agent 出场顺序">
        {cards.map((card, index) => (
          <div
            className={`agent-cast-member ${card.status} ${spotlightAgent.key === card.key ? "current" : ""}`}
            key={`cast-${card.key}`}
            aria-current={spotlightAgent.key === card.key ? "step" : undefined}
          >
            <AgentPortrait card={card} size="small" />
            <strong>{card.agentName}</strong>
            <span>{agentOrderLabel(index, cards.length)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}


type JobControlAction = {
  action: string;
  label: string;
  kind?: "danger" | "primary";
  disabled?: boolean;
};

function JobControlDock({
  job,
  loadingAction,
  onControlJob
}: {
  job: WorkflowJobResponse;
  loadingAction: string | null;
  onControlJob: (action: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ top: 160, left: Math.max(24, window.innerWidth - 92) });
  const [dragging, setDragging] = useState(false);
  const dragMovedRef = useRef(false);
  const statusValue = job.status || "pending";
  const controlState = job.control_state ?? {};
  const paused = Boolean(controlState.pause_requested) || controlState.control_status === "paused";
  const active = statusValue === "pending" || statusValue === "running";
  const terminal = ["success", "failed", "cancelled"].includes(statusValue);
  const canRerunAgent = statusValue === "success";
  const actions: JobControlAction[] = [
    { action: "pause", label: "暂停", disabled: !active || paused },
    { action: "resume", label: "继续", kind: "primary", disabled: !paused },
    { action: "cancel", label: "取消", kind: "danger", disabled: !active && !paused },
    { action: "rerun_all", label: "完整重跑", disabled: !terminal },
    { action: "rerun_failed", label: "失败处重跑", disabled: !terminal },
    { action: "rerun_explanation", label: "只重跑解释", disabled: !canRerunAgent },
    { action: "rerun_charts", label: "只重跑图表", disabled: !canRerunAgent },
    { action: "rerun_quality", label: "只重跑质检", disabled: !canRerunAgent }
  ];

  const startDrag = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const originX = event.clientX;
    const originY = event.clientY;
    const startLeft = position.left;
    const startTop = position.top;
    setDragging(true);
    dragMovedRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
    const onMove = (moveEvent: PointerEvent) => {
      const deltaX = moveEvent.clientX - originX;
      const deltaY = moveEvent.clientY - originY;
      if (Math.abs(deltaX) + Math.abs(deltaY) > 4) {
        dragMovedRef.current = true;
      }
      setPosition({
        left: Math.min(Math.max(12, startLeft + deltaX), Math.max(12, window.innerWidth - 72)),
        top: Math.min(Math.max(80, startTop + deltaY), Math.max(90, window.innerHeight - 72))
      });
    };
    const onUp = () => {
      setDragging(false);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp, { once: true });
  };

  const toggleOpen = () => {
    if (dragMovedRef.current) {
      dragMovedRef.current = false;
      return;
    }
    setOpen((value) => !value);
  };

  return (
    <div
      className={`job-control-dock ${open ? "open" : ""} ${dragging ? "dragging" : ""}`}
      style={{ top: position.top, left: position.left }}
    >
      {open ? (
        <div className="job-control-float-panel" role="dialog" aria-label="任务控制面板">
          <div className="job-control-float-head">
            <strong>任务控制</strong>
            <span>{statusLabel(statusValue)} · {stageLabel(job.current_stage || statusValue)}</span>
          </div>
          {controlState.control_message ? <p>{String(controlState.control_message)}</p> : null}
          <div className="job-control-float-grid">
            {actions.map((item) => (
              <button
                key={item.action}
                type="button"
                className={item.kind === "danger" ? "danger-button" : item.kind === "primary" ? "primary-button" : "secondary-button"}
                disabled={item.disabled || loadingAction === item.action}
                onClick={() => onControlJob(item.action)}
              >
                {loadingAction === item.action ? "处理中" : item.label}
              </button>
            ))}
          </div>
          <small>重跑会复用本次数据与目标，执行期间可继续查看页面内容。</small>
        </div>
      ) : null}
      <button
        type="button"
        className="job-control-dock-button"
        onPointerDown={startDrag}
        onClick={toggleOpen}
        aria-expanded={open}
        aria-label={open ? "收起任务控制" : "展开任务控制"}
      >
        {open ? "收起" : "控制"}
      </button>
    </div>
  );
}



export function AgentMessageCard({ card }: { card: AgentCardView }) {
  const active = card.status === "active";
  return (
    <article className={`agent-message-card agent-dialog-card ${card.status}`} aria-current={active ? "step" : undefined} aria-live={active ? "polite" : undefined}>
      <div className="agent-avatar agent-avatar-portrait"><AgentPortrait card={card} size="small" /></div>
      <div className="agent-message-body">
        <div className="agent-message-head">
          <div>
            <strong>{card.agentName}</strong>
            <span>{card.title}</span>
          </div>
          <span className={`agent-status-badge ${card.status}`}>{stepStatusLabel(card.status)}</span>
        </div>

        <dl className="agent-detail-grid">
          <div>
            <dt>输入来源</dt>
            <dd>{card.inputSource}</dd>
          </div>
          <div>
            <dt>当前动作</dt>
            <dd>{card.action}</dd>
          </div>
          <div>
            <dt>输出摘要</dt>
            <dd>{card.output}</dd>
          </div>
        </dl>

        {card.evidence.length ? (
          <div className="agent-evidence">
            <span>可审计依据</span>
            <ul>
              {card.evidence.map((item, index) => (
                <li key={`${card.key}-evidence-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <ArtifactSummary card={card} />

        {card.artifactPath ? (
          <a className="artifact-link" href={toStorageUrl(card.artifactPath)} target="_blank" rel="noreferrer">
            查看产物：{card.artifactLabel ?? shortPath(card.artifactPath)}
          </a>
        ) : null}

        <RawJsonDetails value={card.raw} title="查看原始输出" />
      </div>
    </article>
  );
}


export function AttemptProgressSection({
  attempts,
  isPredictionWorkflow
}: {
  attempts: AttemptProgressView[];
  isPredictionWorkflow: boolean;
}) {
  if (!attempts.length) {
    return null;
  }
  return (
    <section className="attempt-section">
      <div className="section-heading">
        <h2>{isPredictionWorkflow ? "预测脚本生成与验证" : "代码生成与验证"}</h2>
        <span>{attempts.length} 次尝试</span>
      </div>
      <div className="attempt-list">
        {attempts.map((attempt) => (
          <AttemptProgressCard attempt={attempt} key={attempt.attempt} />
        ))}
      </div>
    </section>
  );
}

export function AttemptProgressCard({ attempt }: { attempt: AttemptProgressView }) {
  const validationIssues = attempt.validation?.issues ?? [];
  const repairSuggestions = attempt.validation?.repair_suggestions ?? [];
  return (
    <article className="attempt-card">
      <div className="attempt-card-head">
        <strong>第 {attempt.attempt} 次尝试</strong>
        <span className={`agent-status-badge ${attemptStatusClass(attempt)}`}>
          {attemptStatusText(attempt)}
        </span>
      </div>
      <div className="attempt-stage-row">
        <AttemptStage label="脚本生成" status={attempt.codeStatus} />
        <AttemptStage label="安全检查" status={attempt.safetyStatus} />
        <AttemptStage label="沙箱执行" status={attempt.sandboxStatus} />
        <AttemptStage label="结果验证" status={attempt.validationStatus} />
      </div>

      <dl className="compact-list attempt-meta">
        <div>
          <dt>脚本路径</dt>
          <dd>{attempt.attemptResult?.script_path ? shortPath(attempt.attemptResult.script_path) : "生成中或等待生成"}</dd>
        </div>
        <div>
          <dt>执行结果</dt>
          <dd>{attempt.execution ? (attempt.execution.success ? "执行成功" : "执行失败") : "等待执行"}</dd>
        </div>
        <div>
          <dt>验证结果</dt>
          <dd>{attempt.validation ? (attempt.validation.passed ? "验证通过" : `验证未通过，严重级别 ${severityLabel(attempt.validation.severity)}`) : "等待验证"}</dd>
        </div>
      </dl>

      {validationIssues.length ? (
        <IssueList title="验证发现的问题" items={validationIssues} />
      ) : null}
      {repairSuggestions.length ? (
        <IssueList title="修复建议" items={repairSuggestions} />
      ) : null}
      {attempt.attemptResult?.safety_issues?.length ? (
        <ChipList title="安全检查问题" items={attempt.attemptResult.safety_issues} tone="warning" />
      ) : null}
    </article>
  );
}

export function AttemptStage({ label, status }: { label: string; status?: string }) {
  return (
    <div className={`attempt-stage ${attemptStageClass(status)}`}>
      <span>{label}</span>
      <strong>{attemptStageText(status)}</strong>
    </div>
  );
}

export function IssueList({ title, items }: { title: string; items: Array<Record<string, unknown>> }) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="issue-list">
      <span>{title}</span>
      {items.map((item, index) => (
        <article key={`${title}-${index}`}>
          <strong>{stringValue(item.issue_type ?? item.target_agent, `问题 ${index + 1}`)}</strong>
          <p>{stringValue(item.message, formatListItem(item))}</p>
          {item.location ? <small>{String(item.location)}</small> : null}
        </article>
      ))}
    </div>
  );
}

export function ArtifactSummary({ card }: { card: AgentCardView }) {
  if (!card.raw) {
    return <p className="agent-muted">等待该 Agent 生成输出。</p>;
  }

  if (card.artifactKind === "visual") {
    return <VisualArtifactSummary value={card.raw as VisualParseResult} />;
  }
  if (card.artifactKind === "rag") {
    return <RagArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "controller") {
    return <ControllerArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "understanding") {
    return <UnderstandingArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "analysis") {
    return <AnalysisPlanArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "hypothesis") {
    return <HypothesisArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "prediction_plan") {
    return <PredictionPlanArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "execution") {
    return <ExecutionArtifactSummary value={card.raw as ExecutionAttemptLog} />;
  }
  if (card.artifactKind === "validation") {
    return <ValidationArtifactSummary value={card.raw as ValidationAttemptLog} />;
  }
  if (card.artifactKind === "debate_reflection") {
    return <DebateArtifactSummary value={card.raw as DebateReflection} />;
  }
  if (card.artifactKind === "explanation") {
    return <ExplanationArtifactSummary value={card.raw as ExplanationResult} />;
  }
  if (card.artifactKind === "quality_review") {
    return <QualityReviewArtifactSummary value={card.raw as QualityReview} />;
  }
  if (card.artifactKind === "consistency_report") {
    return <ConsistencyReportPanel report={card.raw as CrossArtifactConsistencyReport | null} />;
  }
  return <GenericArtifactSummary value={card.raw} />;
}

export function ControllerArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["任务类型", stringValue(value.task_type, "-")],
          ["任务名称", stringValue(value.task_name, "-")],
          ["分流结果", workflowLabel(value.task_type)]
        ]}
      />
      <SummaryParagraph label="判断依据" text={stringValue(value.reasoning_summary, "主控 Agent 已生成任务计划。")} />
      <ChipList title="执行步骤" items={arrayValue(value.steps).slice(0, 6)} />
    </div>
  );
}

export function VisualArtifactSummary({ value }: { value: VisualParseResult }) {
  const warnings = [...(value.warnings ?? []), ...(value.limitations ?? [])].filter(Boolean);
  return (
    <div className="artifact-summary">
      <div className="metric-row">
        <div>
          <strong>{value.columns?.length ?? 0}</strong>
          <span>抽取列数</span>
        </div>
        <div>
          <strong>{value.rows?.length ?? 0}</strong>
          <span>抽取行数</span>
        </div>
        <div>
          <strong>{Number.isFinite(value.confidence) ? `${Math.round(value.confidence * 100)}%` : "-"}</strong>
          <span>置信度</span>
        </div>
      </div>
      <ChipList title="字段" items={value.columns ?? []} />
      {warnings.length ? <ChipList title="警告与限制" items={warnings} tone="warning" /> : null}
      <DataPreviewTable rows={value.rows ?? []} columns={value.columns ?? []} />
    </div>
  );
}

export function RagArtifactSummary({ value }: { value: AnyRecord }) {
  const results = Array.isArray(value.results) ? value.results.slice(0, 3) : [];
  return (
    <div className="artifact-summary">
      <SummaryParagraph label="检索结果" text={ragSummary(value)} />
      {results.length ? (
        <div className="mini-list">
          {results.map((item, index) => {
            const record = item as AnyRecord;
            return (
              <article key={`rag-${index}`}>
                <strong>{stringValue(record.filename, `知识片段 ${index + 1}`)}</strong>
                <p>{stringValue(record.chunk, stringValue(record.source, "已命中相关知识。"))}</p>
              </article>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function UnderstandingArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["适用性评分", value.suitability_score === undefined ? "-" : String(value.suitability_score)],
          ["日期字段", arrayValue(value.date_columns).join("、") || "-"]
        ]}
      />
      <ChipList title="目标字段" items={arrayValue(value.target_columns)} />
      <ChipList title="维度字段" items={arrayValue(value.dimension_columns)} />
      <ChipList title="数值字段" items={arrayValue(value.numeric_columns)} />
      <ChipList title="质量问题" items={arrayValue(value.quality_issues)} tone="warning" />
    </div>
  );
}

export function AnalysisPlanArtifactSummary({ value }: { value: AnyRecord }) {
  const chartPlan = Array.isArray(value.chart_plan) ? value.chart_plan.slice(0, 4) : [];
  return (
    <div className="artifact-summary">
      <SummaryParagraph label="分析目标" text={stringValue(value.analysis_goal, "已生成分析计划。")} />
      <ChipList title="分析方法" items={arrayValue(value.methods)} />
      <ChipList title="分组维度" items={arrayValue(value.grouping_dimensions)} />
      <ChipList title="分析指标" items={arrayValue(value.metrics)} />
      {chartPlan.length ? <GenericArtifactSummary value={chartPlan} title="图表计划" /> : null}
      <ChipList title="限制说明" items={arrayValue(value.limitations)} tone="warning" />
    </div>
  );
}

export function HypothesisArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["目标指标", structuredFieldValue(value.target_metric)],
          ["对象维度", structuredFieldValue(value.entity_dimension)],
          ["干预变量", interventionDisplay(value.intervention)],
          ["干预方向", stringValue(value.intervention_direction, "-")]
        ]}
      />
      <SummaryParagraph label="假设摘要" text={stringValue(value.scenario_summary, stringValue(value.hypothesis, "已完成假设解析。"))} />
      <ChipList title="限制说明" items={arrayValue(value.limitations)} tone="warning" />
    </div>
  );
}

export function PredictionPlanArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["目标指标", stringValue(value.target_metric, "-")],
          ["对象维度", stringValue(value.entity_dimension, "-")],
          ["干预字段", interventionDisplay(value.intervention)],
          ["候选模型", arrayValue(value.model_candidates).join("、") || "-"]
        ]}
      />
      <ChipList title="预测步骤" items={arrayValue(value.steps)} />
      <ChipList title="限制说明" items={arrayValue(value.limitations)} tone="warning" />
    </div>
  );
}

export function ExecutionArtifactSummary({ value }: { value: ExecutionAttemptLog }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["是否成功", value.success ? "是" : "否"],
          ["退出码", value.exit_code === undefined || value.exit_code === null ? "-" : String(value.exit_code)],
          ["耗时", `${value.duration_ms ?? "-"} ms`]
        ]}
      />
      <details className="raw-json-details">
        <summary>查看沙箱输出</summary>
        <pre>{String(value.stderr || value.stdout || "暂无执行输出")}</pre>
      </details>
    </div>
  );
}

export function ValidationArtifactSummary({ value }: { value: ValidationAttemptLog }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["是否通过", value.passed ? "是" : "否"],
          ["严重级别", severityLabel(value.severity)],
          ["是否建议重试", value.should_retry ? "是" : "否"]
        ]}
      />
      <GenericArtifactSummary value={value.issues ?? []} title="问题列表" />
      <GenericArtifactSummary value={value.repair_suggestions ?? []} title="修复建议" />
    </div>
  );
}


export function DebateArtifactSummary({ value }: { value: DebateReflection }) {
  const rounds = Array.isArray(value?.debate_rounds) ? value.debate_rounds : [];
  const findings = value?.consensus_findings ?? [];
  const recommendations = value?.consensus_recommendations ?? [];
  const guardrails = value?.statistical_guardrails ?? [];
  const revisions = value?.phrasing_revisions ?? [];

  return (
    <div className="artifact-summary debate-mini">
      <KeyValueGrid
        items={[
          ["辩论轮次", String(rounds.length || 0)],
          ["共识发现", `${findings.length} 条`],
          ["统计护栏", `${guardrails.length} 条`]
        ]}
      />
      {value?.final_consensus ? <SummaryParagraph label="最终共识" text={String(value.final_consensus)} /> : null}
      {rounds.length ? (
        <div className="debate-round-list compact">
          {rounds.slice(0, 3).map((round, index) => (
            <article key={`debate-artifact-${index}`}>
              <strong>第 {round.round ?? index + 1} 轮交互</strong>
              <p><b>激进商业洞察 Agent：</b>{String(round.aggressive_business_agent ?? round.agent_a ?? "-")}</p>
              <p><b>严谨统计质检 Agent：</b>{String(round.statistical_qc_agent ?? round.agent_b ?? "-")}</p>
            </article>
          ))}
        </div>
      ) : null}
      <ChipList title="共识发现" items={findings.slice(0, 4)} />
      <ChipList title="建议动作" items={recommendations.slice(0, 4)} />
      <ChipList title="统计限制" items={guardrails.slice(0, 4)} />
      <ChipList title="表述修正" items={revisions.slice(0, 4)} />
    </div>
  );
}

export function ExplanationArtifactSummary({ value }: { value: ExplanationResult }) {
  return (
    <div className="artifact-summary">
      <SummaryParagraph label="结论摘要" text={value.summary || "等待解释 Agent 输出结论。"} />
      <ChipList title="关键发现" items={value.key_findings ?? []} />
      <ChipList title="建议动作" items={value.recommendations ?? []} />
      <ChipList title="限制说明" items={value.limitations ?? []} tone="warning" />
    </div>
  );
}


export function QualityReviewArtifactSummary({ value }: { value: QualityReview }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["质检结果", value.passed ? "通过" : "存在风险"],
          ["风险级别", severityLabel(value.risk_level)],
          ["问题数量", String(value.issues?.length ?? 0)]
        ]}
      />
      <SummaryParagraph label="修正版摘要" text={value.revised_summary || "质检 Agent 未生成修正版摘要。"} />
      <ChipList title="安全表述建议" items={value.safe_language_suggestions ?? []} />
      <ChipList title="缺失证据" items={value.missing_evidence ?? []} tone="warning" />
    </div>
  );
}

export function GenericArtifactSummary({ value, title = "结构化输出" }: { value: unknown; title?: string }) {
  if (value === null || value === undefined) {
    return null;
  }
  return (
    <details className="raw-json-details compact" open={false}>
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function RawJsonDetails({ value, title }: { value: unknown; title: string }) {
  if (value === null || value === undefined) {
    return null;
  }
  return (
    <details className="raw-json-details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

export function DataPreviewTable({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: string[] }) {
  const previewRows = rows.slice(0, 5);
  const visibleColumns = columns.slice(0, 6);
  if (!previewRows.length || !visibleColumns.length) {
    return null;
  }
  return (
    <div className="table-wrap compact-table">
      <table>
        <thead>
          <tr>
            {visibleColumns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {previewRows.map((row, rowIndex) => (
            <tr key={`preview-${rowIndex}`}>
              {visibleColumns.map((column) => (
                <td key={`${rowIndex}-${column}`}>{formatCell(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function KeyValueGrid({ items }: { items: Array<[string, string]> }) {
  return (
    <dl className="compact-list artifact-kv">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SummaryParagraph({ label, text }: { label: string; text: string }) {
  return (
    <div className="summary-block">
      <span>{label}</span>
      <p>{text}</p>
    </div>
  );
}

export function ChipList({ title, items, tone = "default" }: { title: string; items?: unknown[] | null; tone?: "default" | "warning" }) {
  const cleanItems = Array.isArray(items) ? items.map((item) => formatListItem(item)).filter(Boolean) : [];
  if (!cleanItems.length) {
    return null;
  }
  return (
    <div className="chip-section">
      <span>{title}</span>
      <div className="chip-row">
        {cleanItems.map((item, index) => (
          <span className={`summary-chip ${tone}`} key={`${title}-${index}-${item}`}>
            {item}
          </span>
        ))}
      </div>
    </div>
  );
}

export function DataSourceNotice({ job }: { job: WorkflowJobResponse | null }) {
  if (job?.asset_type !== "image") {
    return null;
  }
  return (
    <div className="source-notice">
      本次数据来源于视觉解析，图片抽取可能存在识别误差，建议结合原图核对关键字段和数值。
    </div>
  );
}

export function DashboardPage({
  dashboard,
  job,
  chartRefreshToken,
  message,
  saving,
  refreshing,
  onDashboardChange,
  onSave,
  onRefresh
}: {
  dashboard: DashboardConfig | null;
  job: WorkflowJobResponse | null;
  chartRefreshToken: number;
  message?: string;
  saving?: boolean;
  refreshing?: boolean;
  onDashboardChange?: (dashboard: DashboardConfig) => void;
  onSave?: () => void;
  onRefresh?: () => void;
}) {
  const [draggingWidgetId, setDraggingWidgetId] = useState<string | null>(null);

  if (!dashboard) {
    return (
      <section className="page-section">
        <div className="section-heading">
          <h2>自动 Dashboard</h2>
          <span>等待 Dashboard 生成 Agent</span>
        </div>
        <EmptyState
          title="暂无 Dashboard"
          text="分析完成后，Dashboard 生成 Agent 会基于本轮结果自动生成 KPI 卡片、趋势图、对比图、结构拆解和明细表。"
        />
      </section>
    );
  }

  const widgets = dashboard.widgets ?? [];
  const filters = dashboard.filters ?? [];
  const refreshInterval = dashboard.refresh?.interval_seconds ?? 300;
  const sourceRows = dashboardRows(dashboard, "dataset_rows");
  const filteredRows = applyDashboardFilters(sourceRows, filters);
  const activeFilterCount = filters.filter((filter) => isActiveDashboardFilter(filter.value)).length;

  const emitChange = (next: DashboardConfig) => onDashboardChange?.(next);
  const updateRefreshInterval = (value: number) => {
    emitChange({
      ...dashboard,
      refresh: {
        ...(dashboard.refresh ?? {}),
        enabled: value > 0,
        interval_seconds: value
      }
    });
  };
  const updateFilter = (id: string, value: string) => {
    emitChange({
      ...dashboard,
      filters: filters.map((filter) => (filter.id === id ? { ...filter, value } : filter))
    });
  };
  const reorderWidgets = (sourceId: string, targetId: string) => {
    if (sourceId === targetId) {
      return;
    }
    const sourceIndex = widgets.findIndex((widget) => widget.id === sourceId);
    const targetIndex = widgets.findIndex((widget) => widget.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0) {
      return;
    }
    const nextWidgets = [...widgets];
    const [moved] = nextWidgets.splice(sourceIndex, 1);
    nextWidgets.splice(targetIndex, 0, moved);
    emitChange({
      ...dashboard,
      widgets: nextWidgets,
      layout: nextWidgets.map((widget, index) => ({
        i: widget.id,
        x: (index % 12),
        y: Math.floor(index / 2),
        w: widget.type === "table" ? 12 : widget.type === "kpi" ? 3 : 6,
        h: widget.type === "table" ? 4 : widget.type === "kpi" ? 2 : 4
      }))
    });
  };
  const handleDrop = (event: ReactDragEvent<HTMLElement>, targetId: string) => {
    event.preventDefault();
    const sourceId = event.dataTransfer.getData("text/plain") || draggingWidgetId;
    if (sourceId) {
      reorderWidgets(sourceId, targetId);
    }
    setDraggingWidgetId(null);
  };

  return (
    <section className="page-section dashboard-page">
      <div className="section-heading dashboard-heading">
        <div>
          <h2>{dashboard.title || "自动 Dashboard"}</h2>
          <span>{dashboard.description || "从一次性分析升级为持续监控视图"}</span>
        </div>
        <div className="dashboard-actions">
          <button className="secondary-button" type="button" disabled={!job?.job_id || refreshing} onClick={onRefresh}>
            {refreshing ? "刷新中" : "刷新数据"}
          </button>
          <button className="secondary-button" type="button" disabled={!dashboard || saving} onClick={onSave}>
            {saving ? "保存中" : "保存布局"}
          </button>
        </div>
      </div>

      {message ? <p className="message success">{message}</p> : null}

      <section className="dashboard-toolbar">
        <label>
          自动刷新频率
          <select value={refreshInterval} onChange={(event) => updateRefreshInterval(Number(event.target.value))}>
            <option value={0}>关闭</option>
            <option value={60}>每 1 分钟</option>
            <option value={300}>每 5 分钟</option>
            <option value={900}>每 15 分钟</option>
            <option value={3600}>每 1 小时</option>
          </select>
        </label>
        <div className="dashboard-filter-row">
          {filters.length ? (
            filters.map((filter) => (
              <label key={filter.id}>
                {filter.label || filter.field}
                {filter.options?.length ? (
                  <select value={filter.value ?? ""} onChange={(event) => updateFilter(filter.id, event.target.value)}>
                    <option value="">全部</option>
                    {filter.options.map((option) => <option key={option} value={option}>{option}</option>)}
                  </select>
                ) : (
                  <input value={filter.value ?? ""} placeholder="输入筛选值" onChange={(event) => updateFilter(filter.id, event.target.value)} />
                )}
              </label>
            ))
          ) : (
            <span className="agent-muted">本轮数据未生成可用筛选器。</span>
          )}
        </div>
        <span className="dashboard-filter-summary">
          {activeFilterCount ? `已筛选 ${filteredRows.length} / ${sourceRows.length} 行` : `当前展示 ${sourceRows.length || dashboardRows(dashboard, "result_rows").length} 行可交互数据`}
        </span>
      </section>

      <div className="dashboard-grid" aria-label="可拖拽调整布局的 Dashboard 组件">
        {widgets.map((widget) => (
          <article
            className={`dashboard-widget dashboard-widget-${widget.type} ${draggingWidgetId === widget.id ? "dragging" : ""}`}
            key={widget.id}
            style={dashboardWidgetStyle(dashboard, widget)}
            draggable
            onDragStart={(event) => {
              setDraggingWidgetId(widget.id);
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("text/plain", widget.id);
            }}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => handleDrop(event, widget.id)}
            onDragEnd={() => setDraggingWidgetId(null)}
          >
            <DashboardWidgetView widget={widget} dashboard={dashboard} filteredRows={filteredRows} chartRefreshToken={chartRefreshToken} />
          </article>
        ))}
      </div>
    </section>
  );
}

function DashboardWidgetView({
  widget,
  dashboard,
  filteredRows,
  chartRefreshToken
}: {
  widget: DashboardWidget;
  dashboard: DashboardConfig;
  filteredRows: AnyRecord[];
  chartRefreshToken: number;
}) {
  const widgetRows = rowsForDashboardWidget(dashboard, widget, filteredRows);
  if (widget.type === "kpi") {
    const value = resolveDashboardKpiValue(widget, widgetRows);
    return (
      <div className="dashboard-kpi-card">
        <span>{widget.title}</span>
        <strong>{formatDashboardValue(value)}{widget.unit ? <em>{widget.unit}</em> : null}</strong>
        {widget.description ? <p>{widget.description}</p> : null}
      </div>
    );
  }

  if (widget.type === "chart") {
    const points = aggregateDashboardWidget(widget, widgetRows);
    if (!points.length && widget.chart_path) {
      return <DashboardImageChart widget={widget} chartRefreshToken={chartRefreshToken} />;
    }
    return <DashboardInteractiveChart widget={widget} points={points} />;
  }

  if (widget.type === "breakdown") {
    const points = aggregateDashboardWidget(widget, widgetRows);
    return <DashboardBreakdownCard widget={widget} points={points} />;
  }

  if (widget.type === "image_chart") {
    return <DashboardImageChart widget={widget} chartRefreshToken={chartRefreshToken} />;
  }

  if (widget.type === "table") {
    const columns = (widget.columns?.length ? widget.columns : tableColumnsFromRows(widgetRows)) ?? [];
    const rows = widgetRows.length ? widgetRows : (widget.rows ?? []);
    return (
      <div className="dashboard-table-card">
        <header>
          <strong>{widget.title}</strong>
          {widget.description ? <span>{widget.description}</span> : null}
        </header>
        <div className="dashboard-table-wrap">
          <table className="dashboard-table">
            <thead>
              <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
            </thead>
            <tbody>
              {rows.slice(0, Number(widget.page_size || 12)).map((row, rowIndex) => (
                <tr key={`dashboard-row-${rowIndex}`}>
                  {columns.map((column) => <td key={`${rowIndex}-${column}`}>{formatCell(row[column])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-generic-card">
      <strong>{widget.title}</strong>
      <pre>{JSON.stringify(widget, null, 2)}</pre>
    </div>
  );
}

function DashboardInteractiveChart({ widget, points }: { widget: DashboardWidget; points: DashboardPoint[] }) {
  const chartType = String(widget.chart_type || "bar");
  return (
    <div className="dashboard-chart-card interactive-chart-card">
      <header>
        <strong>{widget.title}</strong>
        {widget.chart_role ? <span>{widget.chart_role}</span> : null}
      </header>
      {points.length ? (
        chartType === "line" ? <DashboardLineChart points={points} /> : <DashboardBarChart points={points} />
      ) : (
        <p className="agent-muted">筛选后暂无可绘制数据。</p>
      )}
      {widget.description ? <p>{widget.description}</p> : null}
    </div>
  );
}

function DashboardLineChart({ points }: { points: DashboardPoint[] }) {
  const width = 520;
  const height = 220;
  const padding = 34;
  const values = points.map((point) => point.value);
  const min = Math.min(0, ...values);
  const max = Math.max(1, ...values);
  const span = Math.max(max - min, 1);
  const coordinates = points.map((point, index) => {
    const x = padding + (points.length <= 1 ? 0 : (index / (points.length - 1)) * (width - padding * 2));
    const y = height - padding - ((point.value - min) / span) * (height - padding * 2);
    return { x, y, point };
  });
  return (
    <svg className="dashboard-line-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="趋势折线图">
      <line x1={padding} y1={height - padding} x2={width - padding} y2={height - padding} />
      <line x1={padding} y1={padding} x2={padding} y2={height - padding} />
      <polyline points={coordinates.map((item) => `${item.x},${item.y}`).join(" ")} />
      {coordinates.map((item, index) => (
        <g key={`${item.point.label}-${index}`}>
          <circle cx={item.x} cy={item.y} r="4" />
          {(index === 0 || index === coordinates.length - 1 || coordinates.length <= 6) ? <text x={item.x} y={height - 8}>{item.point.label}</text> : null}
          {(index === coordinates.length - 1) ? <text x={item.x} y={item.y - 10}>{formatDashboardValue(item.point.value)}</text> : null}
        </g>
      ))}
    </svg>
  );
}

function DashboardBarChart({ points }: { points: DashboardPoint[] }) {
  const max = Math.max(1, ...points.map((point) => Math.abs(point.value)));
  return (
    <div className="dashboard-bar-list">
      {points.slice(0, 12).map((point) => (
        <div className="dashboard-bar-row" key={point.label}>
          <span title={point.label}>{point.label}</span>
          <div><i style={{ width: `${Math.max(4, Math.abs(point.value) / max * 100)}%` }} /></div>
          <strong>{formatDashboardValue(point.value)}</strong>
        </div>
      ))}
    </div>
  );
}

function DashboardBreakdownCard({ widget, points }: { widget: DashboardWidget; points: DashboardPoint[] }) {
  const total = points.reduce((sum, point) => sum + Math.abs(point.value), 0) || 1;
  return (
    <div className="dashboard-breakdown-card">
      <header>
        <strong>{widget.title}</strong>
        <span>{widget.chart_role || "breakdown"}</span>
      </header>
      {points.length ? (
        <div className="dashboard-breakdown-list">
          {points.slice(0, 10).map((point) => {
            const ratio = Math.abs(point.value) / total;
            return (
              <div key={point.label} className="dashboard-breakdown-row">
                <span>{point.label}</span>
                <div><i style={{ width: `${Math.max(3, ratio * 100)}%` }} /></div>
                <strong>{(ratio * 100).toFixed(1)}%</strong>
              </div>
            );
          })}
        </div>
      ) : <p className="agent-muted">筛选后暂无结构拆解数据。</p>}
      {widget.description ? <p>{widget.description}</p> : null}
    </div>
  );
}

function DashboardImageChart({ widget, chartRefreshToken }: { widget: DashboardWidget; chartRefreshToken: number }) {
  return (
    <div className="dashboard-chart-card">
      <header>
        <strong>{widget.title}</strong>
        {widget.chart_role ? <span>{widget.chart_role}</span> : null}
      </header>
      {widget.chart_path ? (
        <img alt={widget.title} src={toVersionedStorageUrl(widget.chart_path, chartRefreshToken)} />
      ) : (
        <p className="agent-muted">该图表组件尚未绑定图片或结构化数据。</p>
      )}
      {widget.description ? <p>{widget.description}</p> : null}
    </div>
  );
}

interface DashboardPoint {
  label: string;
  value: number;
  count: number;
}

function aggregateDashboardWidget(widget: DashboardWidget, rows: AnyRecord[]): DashboardPoint[] {
  const ownRows = Array.isArray(widget.rows) ? (widget.rows as AnyRecord[]) : [];
  const sourceRows = rows.length ? rows : ownRows;
  const xField = String(widget.x || widget.dimension || widget.field || "");
  const yField = String(widget.y || widget.metric || "");
  if (!sourceRows.length || !xField) {
    return [];
  }
  const aggregation = String(widget.aggregation || (yField ? "sum" : "count"));
  const groups = new Map<string, { sum: number; count: number }>();
  sourceRows.forEach((row) => {
    const rawLabel = row[xField];
    const label = rawLabel === null || rawLabel === undefined || rawLabel === "" ? "未填写" : String(rawLabel);
    const rawValue = yField ? numberFromCell(row[yField]) : 1;
    if (rawValue === null) {
      return;
    }
    const current = groups.get(label) ?? { sum: 0, count: 0 };
    current.sum += rawValue;
    current.count += 1;
    groups.set(label, current);
  });
  const points = Array.from(groups.entries()).map(([label, value]) => ({
    label,
    value: aggregation === "mean" ? value.sum / Math.max(1, value.count) : aggregation === "count" ? value.count : value.sum,
    count: value.count
  }));
  if (String(widget.chart_type || "") === "line") {
    return points.sort((left, right) => left.label.localeCompare(right.label, "zh-Hans-CN", { numeric: true })).slice(0, Number(widget.limit || 18));
  }
  return points.sort((left, right) => Math.abs(right.value) - Math.abs(left.value)).slice(0, Number(widget.limit || 12));
}

function resolveDashboardKpiValue(widget: DashboardWidget, rows: AnyRecord[]): string | number | null | undefined {
  const calculation = String(widget.calculation || "");
  const metric = String(widget.metric || "");
  if (calculation === "count_rows") {
    return rows.length || widget.value;
  }
  if (metric && rows.length && ["mean", "sum"].includes(calculation)) {
    const values = rows.map((row) => numberFromCell(row[metric])).filter((value): value is number => value !== null);
    if (!values.length) {
      return widget.value;
    }
    const sum = values.reduce((total, value) => total + value, 0);
    return calculation === "mean" ? sum / values.length : sum;
  }
  return widget.value;
}

function rowsForDashboardWidget(dashboard: DashboardConfig, widget: DashboardWidget, filteredRows: AnyRecord[]): AnyRecord[] {
  const source = String(widget.source || "dataset_rows");
  if (source === "dataset_rows") {
    return filteredRows;
  }
  const rows = dashboardRows(dashboard, source);
  if (rows.length) {
    return rows;
  }
  return Array.isArray(widget.rows) ? (widget.rows as AnyRecord[]) : [];
}

function dashboardRows(dashboard: DashboardConfig, source: string): AnyRecord[] {
  const dataSources = dashboard.data_sources as Record<string, { rows?: unknown[] } | undefined> | undefined;
  const rows = dataSources?.[source]?.rows;
  if (Array.isArray(rows)) {
    return rows.filter((row): row is AnyRecord => Boolean(row) && typeof row === "object" && !Array.isArray(row));
  }
  return [];
}

function applyDashboardFilters(rows: AnyRecord[], filters: DashboardConfig["filters"]): AnyRecord[] {
  const activeFilters = (filters ?? []).filter((filter) => isActiveDashboardFilter(filter.value));
  if (!rows.length || !activeFilters.length) {
    return rows;
  }
  return rows.filter((row) => activeFilters.every((filter) => dashboardFilterMatches(row, filter.field, filter.value ?? "")));
}

function dashboardFilterMatches(row: AnyRecord, field: string, value: string): boolean {
  const raw = row[field];
  if (!isActiveDashboardFilter(value)) {
    return true;
  }
  if (raw === null || raw === undefined) {
    return false;
  }
  return String(raw).toLowerCase().includes(String(value).toLowerCase());
}

function isActiveDashboardFilter(value: unknown): boolean {
  const text = String(value ?? "").trim();
  return Boolean(text && text !== "全部");
}

function dashboardWidgetStyle(dashboard: DashboardConfig, widget: DashboardWidget): Record<string, string> {
  const item = (dashboard.layout ?? []).find((layout) => layout.i === widget.id);
  const span = Math.max(3, Math.min(12, Number(item?.w || (widget.type === "kpi" ? 3 : widget.type === "table" ? 12 : 6))));
  return { gridColumn: `span ${span}` };
}

function tableColumnsFromRows(rows: AnyRecord[]): string[] {
  const seen: string[] = [];
  rows.slice(0, 10).forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (!seen.includes(key)) {
        seen.push(key);
      }
    });
  });
  return seen.slice(0, 10);
}

function numberFromCell(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const numeric = Number(value.replace(/,/g, "").replace(/%$/, ""));
    return Number.isFinite(numeric) ? numeric : null;
  }
  return null;
}

function formatDashboardValue(value: DashboardWidget["value"] | number): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return String(value);
}

function normalizeDataMapNodes(dataMap: DatasetDataMap | null): DatasetDataMapNode[] {
  const explicitNodes = dataMap?.graph?.nodes ?? [];
  if (explicitNodes.length) {
    return explicitNodes;
  }
  const map = dataMap?.data_map;
  const nodes: DatasetDataMapNode[] = [];
  (map?.entities ?? []).forEach((label) => nodes.push({ id: `entity:${label}`, label, type: "entity" }));
  (map?.metrics ?? []).forEach((label) => nodes.push({ id: `metric:${label}`, label, type: "metric", field: label }));
  (map?.dimensions ?? []).forEach((label) => nodes.push({ id: `dimension:${label}`, label, type: "dimension", field: label }));
  return nodes;
}

function layoutDataMapNodes(nodes: DatasetDataMapNode[]): Array<DatasetDataMapNode & { x: number; y: number }> {
  if (!nodes.length) {
    return [];
  }
  const centerX = 360;
  const centerY = 230;
  const entityNodes = nodes.filter((node) => node.type === "entity");
  const otherNodes = nodes.filter((node) => node.type !== "entity");
  const positioned: Array<DatasetDataMapNode & { x: number; y: number }> = [];
  entityNodes.forEach((node, index) => {
    const offset = (index - (entityNodes.length - 1) / 2) * 82;
    positioned.push({ ...node, x: centerX + offset, y: centerY });
  });
  otherNodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + (index / Math.max(1, otherNodes.length)) * Math.PI * 2;
    const radius = node.type === "metric" ? 170 : 210;
    positioned.push({ ...node, x: centerX + Math.cos(angle) * radius, y: centerY + Math.sin(angle) * radius });
  });
  return positioned;
}

function questionsForDataMapNode(dataMap: DatasetDataMap | null, node: DatasetDataMapNode): string[] {
  const questions = dataMap?.data_map?.possible_questions ?? {};
  return questions[node.label] ?? questions[node.type === "metric" ? "指标" : ""] ?? [];
}

function nodeRadius(node: DatasetDataMapNode): number {
  const base = node.type === "entity" ? 38 : node.type === "metric" ? 31 : 27;
  return base * Number(node.size || 1);
}

function dataMapNodeTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    entity: "业务实体",
    metric: "度量指标",
    dimension: "分析维度",
    time: "时间维度",
    identifier: "标识字段"
  };
  return labels[type] ?? type;
}


export function InsightsPage({
  explanation,
  report,
  job,
  evidenceChain,
  debateReflection,
  pptPreview,
  followUpRecommendations,
  followUps,
  followUpQuestion,
  followUpLoading,
  pptGenerating,
  pptMessage,
  onGeneratePptx,
  onFollowUpQuestionChange,
  onSubmitFollowUp
}: {
  explanation: ExplanationResult;
  report: ReportGenerateResponse | null;
  job: WorkflowJobResponse | null;
  evidenceChain?: EvidenceChain | null;
  debateReflection?: DebateReflection | null;
  pptPreview?: PptPreview | null;
  followUpRecommendations?: FollowUpRecommendation[];
  followUps?: WorkflowFollowUpResponse[];
  followUpQuestion?: string;
  followUpLoading?: boolean;
  pptGenerating?: boolean;
  pptMessage?: string;
  onGeneratePptx?: () => void;
  onFollowUpQuestionChange?: (value: string) => void;
  onSubmitFollowUp?: () => void;
}) {
  const pptxPath = report?.pptx_path || job?.pptx_path || pptPreview?.pptx_path || null;
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>结论与报告</h2>
        <div className="report-downloads">
          {report?.report_path || job?.report_path ? (
            <a className="download-button" href={toStorageUrl(report?.report_path || job?.report_path || "")} download>
              下载报告
            </a>
          ) : <span>等待报告生成</span>}
          {pptxPath ? (
            <a className="download-button" href={toStorageUrl(pptxPath)} download>
              下载 PPTX
            </a>
          ) : onGeneratePptx && job?.status === "success" ? (
            <button className="download-button" type="button" disabled={Boolean(pptGenerating)} onClick={onGeneratePptx}>
              {pptGenerating ? "生成中" : "生成 PPTX"}
            </button>
          ) : null}
        </div>
      </div>
      <DataSourceNotice job={job} />
      {pptMessage ? <p className="ppt-generate-message">{pptMessage}</p> : null}
      {explanation.summary ? (
        <>
          <p className="summary-text">{explanation.summary}</p>
          <EvidenceResultList title="关键发现" items={explanation.key_findings} evidenceChain={evidenceChain} />
          <DebateReflectionPanel debate={debateReflection ?? null} />
          <EvidenceResultList title="建议动作" items={explanation.recommendations} evidenceChain={evidenceChain} />
          <EvidenceResultList title="限制说明" items={explanation.limitations} evidenceChain={evidenceChain} />
          <PptOutline outline={explanation.ppt_outline} />
          <PptPreviewPanel preview={pptPreview || null} />
          <FollowUpPanel
            followUps={followUps ?? []}
            recommendations={followUpRecommendations ?? []}
            question={followUpQuestion ?? ""}
            loading={Boolean(followUpLoading)}
            onQuestionChange={onFollowUpQuestionChange}
            onSubmit={onSubmitFollowUp}
          />
        </>
      ) : (
        <EmptyState title="暂无结论" text="验证 Agent 通过后，解释 Agent 会生成结论、建议和 PPT 大纲。" />
      )}
    </section>
  );
}


function DebateReflectionPanel({ debate }: { debate?: DebateReflection | null }) {
  if (!debate) {
    return null;
  }
  const rounds = Array.isArray(debate.debate_rounds) ? debate.debate_rounds : [];
  const findings = debate.consensus_findings ?? [];
  const recommendations = debate.consensus_recommendations ?? [];
  const guardrails = debate.statistical_guardrails ?? [];
  const revisions = debate.phrasing_revisions ?? [];
  const finalConsensus = formatListItem(debate.final_consensus);

  return (
    <section className="debate-panel">
      <div className="section-heading compact-heading">
        <h2>Debate Matrix 双 Agent 交互过程</h2>
        <span>{rounds.length || 0} 轮动态辩论</span>
      </div>
      {rounds.length ? (
        <div className="debate-round-grid">
          {rounds.map((round, index) => (
            <article key={`debate-round-${index}`} className="debate-round-card">
              <strong>第 {round.round ?? index + 1} 轮</strong>
              <div className="debate-agent debate-agent-a">
                <span>角色 A：激进商业洞察 Agent</span>
                <p>{String(round.aggressive_business_agent ?? round.agent_a ?? "-")}</p>
              </div>
              <div className="debate-agent debate-agent-b">
                <span>角色 B：严谨统计质检 Agent</span>
                <p>{String(round.statistical_qc_agent ?? round.agent_b ?? "-")}</p>
              </div>
            </article>
          ))}
        </div>
      ) : null}
      <div className="debate-consensus-grid">
        <ResultList title="双方达成的业务共识" items={findings} />
        <ResultList title="可执行策略建议" items={recommendations} />
        <ResultList title="统计质检护栏" items={guardrails} />
        <ResultList title="报告表述修正" items={revisions} />
      </div>
      {finalConsensus ? <p className="debate-final-consensus">{finalConsensus}</p> : null}
    </section>
  );
}

function EvidenceResultList({
  title,
  items,
  evidenceChain
}: {
  title: string;
  items: string[];
  evidenceChain?: EvidenceChain | null;
}) {
  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>({});
  const cleanItems = items.filter(Boolean);
  if (!cleanItems.length) {
    return null;
  }
  return (
    <div className="result-list evidence-result-list">
      <strong>{title}</strong>
      <ul>
        {cleanItems.map((item, index) => {
          const key = `${title}-${index}`;
          const evidence = findEvidenceForText(item, evidenceChain);
          return (
            <li key={key}>
              <div className="finding-row">
                <span>{item}</span>
                <button
                  className="secondary-button compact-button"
                  type="button"
                  title="查看证据"
                  onClick={() => setOpenKeys((current) => ({ ...current, [key]: !current[key] }))}
                >
                  查看证据
                </button>
              </div>
              {openKeys[key] ? <EvidencePanel evidence={evidence} /> : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

interface EvidenceNumberCandidate {
  raw: string;
  value: number;
  isPercent: boolean;
  context: string;
}

const EVIDENCE_NUMBER_PATTERN = /[-+]?\d+(?:\.\d+)?%?/g;
const EVIDENCE_DATE_OR_ORDINAL_UNITS = "年月日号页行列个条项次季度";

function findEvidenceForText(text: string, evidenceChain?: EvidenceChain | null): EvidenceFinding | null {
  const cleanText = text.trim();
  if (!cleanText) {
    return null;
  }

  const findings = evidenceChain?.findings ?? [];
  const normalized = normalizeEvidenceText(cleanText);
  const exactMatch = findings.find((finding) => {
    const findingText = normalizeEvidenceText(finding.text || "");
    return findingText === normalized || findingText.includes(normalized) || normalized.includes(findingText);
  });
  if (exactMatch) {
    return exactMatch;
  }

  const queryNumbers = extractEvidenceNumbers(cleanText);
  const scoredMatches = findings
    .map((finding) => {
      const candidateNumbers = evidenceNumbersFromFinding(finding);
      const numberMatches = countSharedEvidenceNumbers(queryNumbers, candidateNumbers);
      const textScore = evidenceTextOverlap(cleanText, finding.text || "");
      const score = numberMatches * 10 + textScore + (finding.has_evidence ? 0.5 : 0);
      return { finding, numberMatches, textScore, score };
    })
    .sort((left, right) => right.score - left.score);

  const best = scoredMatches[0];
  if (best && (best.numberMatches > 0 || best.textScore >= 0.58)) {
    return best.finding;
  }

  return fallbackEvidenceForText(cleanText, evidenceChain);
}

function normalizeEvidenceText(value: string): string {
  return value.replace(/\s+/g, "").replace(/[，。,.；;：:]/g, "").toLowerCase();
}

function extractEvidenceNumbers(text: string): EvidenceNumberCandidate[] {
  const result: EvidenceNumberCandidate[] = [];
  EVIDENCE_NUMBER_PATTERN.lastIndex = 0;
  for (const match of text.matchAll(EVIDENCE_NUMBER_PATTERN)) {
    const raw = match[0];
    const start = match.index ?? 0;
    const end = start + raw.length;
    const isPercent = raw.endsWith("%");
    if (shouldSkipEvidenceNumber(text, start, end, raw, isPercent)) {
      continue;
    }
    const numeric = Number((isPercent ? raw.slice(0, -1) : raw).replace(/,/g, ""));
    if (!Number.isFinite(numeric)) {
      continue;
    }
    result.push({
      raw,
      value: numeric,
      isPercent,
      context: text.slice(Math.max(0, start - 18), Math.min(text.length, end + 18))
    });
  }
  return result;
}

function shouldSkipEvidenceNumber(text: string, start: number, end: number, raw: string, isPercent: boolean): boolean {
  if (isPercent) {
    return false;
  }

  const previousChar = start > 0 ? text[start - 1] : "";
  const nextChar = end < text.length ? text[end] : "";

  if (EVIDENCE_DATE_OR_ORDINAL_UNITS.includes(nextChar)) {
    return true;
  }
  if (previousChar === "第" && EVIDENCE_DATE_OR_ORDINAL_UNITS.includes(nextChar)) {
    return true;
  }
  if (["-", "/", "－", "—"].includes(previousChar) || ["-", "/", "－", "—"].includes(nextChar)) {
    return true;
  }
  if (raw.startsWith("-") && /\d/.test(previousChar)) {
    return true;
  }
  return false;
}

function evidenceNumbersFromFinding(finding: EvidenceFinding): EvidenceNumberCandidate[] {
  const candidates = extractEvidenceNumbers(finding.text || "");

  (finding.numbers ?? []).forEach((item) => {
    const raw = typeof item.raw === "string" ? item.raw : item.value !== undefined ? String(item.value) : "";
    const value = numberValue(item.value ?? raw);
    if (value !== null) {
      candidates.push({
        raw: raw || String(value),
        value,
        isPercent: Boolean(item.is_percent) || raw.endsWith("%"),
        context: finding.text || ""
      });
    }
  });

  (finding.evidence_items ?? []).forEach((item) => {
    if (item.number) {
      candidates.push(...extractEvidenceNumbers(String(item.number)));
    }
    const value = numberValue(item.value);
    if (value !== null) {
      const raw = String(item.value);
      candidates.push({
        raw,
        value,
        isPercent: raw.endsWith("%"),
        context: item.calculation || finding.text || ""
      });
    }
  });

  return candidates;
}

function countSharedEvidenceNumbers(queryNumbers: EvidenceNumberCandidate[], candidateNumbers: EvidenceNumberCandidate[]): number {
  if (!queryNumbers.length || !candidateNumbers.length) {
    return 0;
  }
  const used = new Set<number>();
  let count = 0;
  queryNumbers.forEach((queryNumber) => {
    const index = candidateNumbers.findIndex((candidate, candidateIndex) => !used.has(candidateIndex) && evidenceNumbersClose(queryNumber, candidate));
    if (index >= 0) {
      used.add(index);
      count += 1;
    }
  });
  return count;
}

function evidenceNumbersClose(left: EvidenceNumberCandidate, right: EvidenceNumberCandidate): boolean {
  const leftTargets = evidenceNumberTargets(left);
  const rightTargets = evidenceNumberTargets(right);
  return leftTargets.some((leftTarget) => rightTargets.some((rightTarget) => closeNumber(leftTarget, rightTarget)));
}

function evidenceNumberTargets(number: EvidenceNumberCandidate): number[] {
  const targets = [number.value];
  if (number.isPercent) {
    targets.push(number.value / 100);
    targets.push(-number.value);
    targets.push(-number.value / 100);
    targets.push(Math.abs(number.value));
    targets.push(Math.abs(number.value) / 100);
    targets.push(-Math.abs(number.value));
    targets.push(-Math.abs(number.value) / 100);
  }
  return Array.from(new Set(targets.filter((value) => Number.isFinite(value))));
}

function closeNumber(left: number, right: number): boolean {
  const tolerance = Math.max(0.000001, Math.abs(right) * 0.001);
  return Math.abs(left - right) <= tolerance;
}

function numberValue(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const cleaned = value.trim().replace(/,/g, "").replace(/%$/, "");
    if (!cleaned) {
      return null;
    }
    const numeric = Number(cleaned);
    return Number.isFinite(numeric) ? numeric : null;
  }
  return null;
}

function evidenceTextOverlap(left: string, right: string): number {
  const leftTokens = evidenceTextTokens(left);
  const rightTokens = evidenceTextTokens(right);
  if (!leftTokens.size || !rightTokens.size) {
    return 0;
  }
  let common = 0;
  leftTokens.forEach((token) => {
    if (rightTokens.has(token)) {
      common += 1;
    }
  });
  return common / Math.max(leftTokens.size, rightTokens.size);
}

function evidenceTextTokens(value: string): Set<string> {
  const normalized = normalizeEvidenceText(value).replace(/[0-9+\-.%]/g, "");
  const tokens = new Set<string>();
  for (let index = 0; index < normalized.length - 1; index += 1) {
    tokens.add(normalized.slice(index, index + 2));
  }
  if (!tokens.size && normalized) {
    tokens.add(normalized);
  }
  return tokens;
}

function fallbackEvidenceForText(text: string, evidenceChain?: EvidenceChain | null): EvidenceFinding {
  const numbers = extractEvidenceNumbers(text);
  const charts = Array.from(new Set((evidenceChain?.findings ?? []).flatMap((finding) => finding.charts ?? [])));
  const hasNumbers = numbers.length > 0;
  return {
    finding_id: `local_${normalizeEvidenceText(text).slice(0, 32)}`,
    text,
    numbers: numbers.map((number) => ({
      raw: number.raw,
      value: number.value,
      is_percent: number.isPercent
    })),
    has_evidence: !hasNumbers,
    risk_level: hasNumbers ? "high" : "low",
    evidence_items: [],
    charts,
    calculation_note: hasNumbers
      ? "该结论含数字，但暂未在可用证据链中找到对应结构化来源。"
      : "该结论不含可抽取数字，依据为解释文本与图表整体判断。"
  };
}

function EvidencePanel({ evidence }: { evidence: EvidenceFinding | null }) {
  if (!evidence) {
    return <div className="evidence-panel warning">暂未找到可展开的结构化证据，质检会将含数字但缺证据的结论标为高风险。</div>;
  }
  return (
    <div className={`evidence-panel risk-${evidence.risk_level || "low"}`}>
      <div className="evidence-head">
        <strong>{evidence.has_evidence ? "已匹配证据" : "证据不足"}</strong>
        <span>{evidence.risk_level === "high" ? "高风险" : "可核对"}</span>
      </div>
      <p>{evidence.calculation_note}</p>
      {evidence.evidence_items?.length ? (
        <div className="evidence-item-list">
          {evidence.evidence_items.map((item, index) => (
            <article key={`${evidence.finding_id}-${index}`}>
              <strong>{item.number ? `数字 ${item.number}` : `证据 ${index + 1}`}</strong>
              <dl className="compact-list artifact-kv">
                <div><dt>来源</dt><dd>{item.source_file || "分析产物"}</dd></div>
                <div><dt>路径</dt><dd>{item.json_path || "未记录"}</dd></div>
                <div><dt>匹配值</dt><dd>{formatCell(item.value)}</dd></div>
              </dl>
              {item.row_context ? <RawJsonDetails value={item.row_context} title="查看原始分组表" /> : null}
              {item.calculation ? <p>{item.calculation}</p> : null}
            </article>
          ))}
        </div>
      ) : <p className="agent-muted">该发现没有匹配到数字证据。</p>}
      {evidence.charts?.length ? (
        <div className="evidence-chart-list">
          {evidence.charts.map((chartPath, index) => (
            <a key={`${chartPath}-${index}`} href={toStorageUrl(chartPath)} target="_blank" rel="noreferrer">
              相关图表 {index + 1}
            </a>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function PptPreviewPanel({ preview }: { preview: PptPreview | null }) {
  const [page, setPage] = useState(0);
  const slides = preview?.slides ?? [];
  useEffect(() => {
    setPage(0);
  }, [preview?.pptx_path, slides.length]);
  if (!slides.length) {
    return null;
  }
  const current = slides[Math.min(page, slides.length - 1)];
  return (
    <section className="ppt-preview-panel">
      <div className="section-heading compact-heading">
        <h2>PPT 页面预览</h2>
        <span>{current.page} / {slides.length}</span>
      </div>
      <article className="ppt-slide-card">
        <strong>{current.title}</strong>
        {current.subtitle || current.section_label ? <span>{current.subtitle || current.section_label}</span> : null}
        <ul>
          {current.bullets.map((bullet, index) => <li key={`${current.page}-${index}`}>{bullet}</li>)}
        </ul>
        {current.chart ? <img alt="PPT 图表预览" src={toStorageUrl(current.chart)} /> : null}
      </article>
      <div className="button-row">
        <button className="secondary-button" type="button" disabled={page <= 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>上一页</button>
        <button className="secondary-button" type="button" disabled={page >= slides.length - 1} onClick={() => setPage((value) => Math.min(slides.length - 1, value + 1))}>下一页</button>
      </div>
    </section>
  );
}

function FollowUpPanel({
  followUps,
  recommendations,
  question,
  loading,
  onQuestionChange,
  onSubmit
}: {
  followUps: WorkflowFollowUpResponse[];
  recommendations: FollowUpRecommendation[];
  question: string;
  loading: boolean;
  onQuestionChange?: (value: string) => void;
  onSubmit?: () => void;
}) {
  if (!onQuestionChange || !onSubmit) {
    return null;
  }
  return (
    <section className="follow-up-panel">
      <div className="section-heading compact-heading">
        <h2>继续追问</h2>
        <span>基于当前分析产物</span>
      </div>
      {recommendations.length ? (
        <div className="follow-up-recommendations">
          <strong>推荐继续追问</strong>
          <div className="follow-up-recommendation-list">
            {recommendations.slice(0, 5).map((item, index) => (
              <button
                key={`${item.question}-${index}`}
                type="button"
                onClick={() => onQuestionChange(item.question)}
              >
                <span>{item.question}</span>
                {item.rationale ? <small>{item.rationale}</small> : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}
      <textarea
        rows={3}
        value={question}
        placeholder="例如：为什么三班更高？或：把结论改成给校长看的版本。"
        onChange={(event) => onQuestionChange(event.target.value)}
      />
      <button className="primary-button" type="button" disabled={loading || !question.trim()} onClick={onSubmit}>
        {loading ? "分析中" : "发送追问"}
      </button>
      {followUps.length ? (
        <div className="follow-up-list">
          {followUps.map((item, index) => (
            <article key={`${item.created_at}-${index}`}>
              <strong>{item.question}</strong>
              <p>{item.answer}</p>
              {item.used_artifacts?.length ? <small>参考产物：{item.used_artifacts.join("、")}</small> : null}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function CleaningPlanModal({
  plan,
  report,
  selectedStrategies,
  loading,
  onStrategyChange,
  onConfirm,
  onClose
}: {
  plan: CleaningPlanResponse;
  report: CleaningReportResponse | null;
  selectedStrategies: Record<string, string>;
  loading: boolean;
  onStrategyChange: (issueId: string, strategyId: string) => void;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const preview = report?.preview ?? plan.preview;
  const columns = preview.columns.slice(0, 12);
  const rows = preview.rows.slice(0, 30);
  return (
    <div className="sample-preview-backdrop" role="dialog" aria-modal="true" aria-label="数据质量修复建议">
      <div className="cleaning-modal">
        <div className="sample-preview-head">
          <div>
            <strong>数据质量修复建议</strong>
            <p>{report?.message || plan.message}</p>
          </div>
          <button type="button" onClick={onClose}>稍后处理</button>
        </div>

        <div className="cleaning-issue-list">
          {plan.issues.length ? plan.issues.map((issue) => (
            <article className="cleaning-issue-card" key={issue.issue_id}>
              <strong>{issue.message}</strong>
              <small>{issue.affected_count} 条记录受影响 · {severityLabel(issue.severity)}</small>
              <div className="cleaning-strategy-grid">
                {issue.strategies.map((strategy) => {
                  const checked = (selectedStrategies[issue.issue_id] || issue.default_strategy_id) === strategy.strategy_id;
                  return (
                    <label className={checked ? "selected" : ""} key={strategy.strategy_id}>
                      <input
                        type="radio"
                        name={issue.issue_id}
                        checked={checked}
                        onChange={() => onStrategyChange(issue.issue_id, strategy.strategy_id)}
                      />
                      <span>{strategy.label}</span>
                      <small>{strategy.description}</small>
                    </label>
                  );
                })}
              </div>
            </article>
          )) : (
            <article className="cleaning-issue-card">
              <strong>当前数据文件没有发现需要自动修复的问题</strong>
              <small>确认后将直接使用当前数据进入正式分析。</small>
            </article>
          )}
        </div>

        <div className="sample-preview-table-wrap cleaning-preview-table">
          <table>
            <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`cleaning-preview-${rowIndex}`}>
                  {columns.map((column) => <td key={`${rowIndex}-${column}`}>{formatCell(row[column])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {report?.applied_strategies?.length ? (
          <div className="cleaning-applied-list">
            <strong>已采用的清洗策略</strong>
            {report.applied_strategies.map((item) => (
              <span key={`${item.issue_id}-${item.strategy_id}`}>{item.strategy_label}</span>
            ))}
          </div>
        ) : null}

        <div className="sample-preview-actions">
          {report?.cleaned_dataset_path ? (
            <a className="secondary-button" href={toStorageUrl(report.cleaned_dataset_path)} download>下载清洗后 CSV</a>
          ) : null}
          <button className="secondary-button" type="button" onClick={onClose}>返回调整</button>
          <button className="primary-button" type="button" disabled={loading} onClick={onConfirm}>
            {loading ? "处理中" : report ? "继续分析" : "确认修复并继续分析"}
          </button>
        </div>
      </div>
    </div>
  );
}


export function LogsPage({
  job,
  log,
  events
}: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  events: ExecutionLogEvent[];
}) {
  const executionResults = log?.execution_results ?? [];
  const validationResults = log?.validation_results ?? [];

  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>执行日志</h2>
        <span>{job ? statusLabel(statusFromJob(job.status)) : "等待任务启动"}</span>
      </div>

      <div className="log-summary-grid">
        <div>
          <span>事件数量</span>
          <strong>{events.length}</strong>
        </div>
        <div>
          <span>沙箱执行次数</span>
          <strong>{executionResults.length}</strong>
        </div>
        <div>
          <span>验证次数</span>
          <strong>{validationResults.length}</strong>
        </div>
      </div>

      <section className="result-section">
        <div className="section-heading">
          <h2>完整事件流</h2>
          <span>{events.length} 条事件</span>
        </div>
        <EventLogList events={events} />
      </section>

      <section className="result-section">
        <div className="section-heading">
          <h2>沙箱执行日志</h2>
          <span>{executionResults.length} 次执行</span>
        </div>
        {executionResults.length ? (
          <div className="log-stack">
            {executionResults.map((execution, index) => (
              <ExecutionLogBlock execution={execution} key={`${execution.path}-${index}`} />
            ))}
          </div>
        ) : (
          <EmptyState title="暂无沙箱执行日志" text="代码 Agent 生成脚本并进入沙箱后，这里会显示完整 stdout / stderr。" compact />
        )}
      </section>

      <section className="result-section">
        <div className="section-heading">
          <h2>验证 Agent 日志</h2>
          <span>{validationResults.length} 次验证</span>
        </div>
        {validationResults.length ? (
          <div className="log-stack">
            {validationResults.map((validation, index) => (
              <ValidationLogBlock validation={validation} key={`${validation.path}-${index}`} />
            ))}
          </div>
        ) : (
          <EmptyState title="暂无验证日志" text="沙箱执行结束后，验证 Agent 的完整问题和修复建议会显示在这里。" compact />
        )}
      </section>
    </section>
  );
}

export function ExecutionLogBlock({ execution }: { execution: ExecutionAttemptLog }) {
  return (
    <article className="log-block">
      <h3>第 {execution.attempt} 次沙箱执行</h3>
      <dl className="compact-list">
        <div>
          <dt>成功</dt>
          <dd>{execution.success ? "是" : "否"}</dd>
        </div>
        <div>
          <dt>退出码</dt>
          <dd>{String(execution.exit_code ?? "-")}</dd>
        </div>
        <div>
          <dt>耗时</dt>
          <dd>{String(execution.duration_ms ?? "-")} ms</dd>
        </div>
        <div>
          <dt>结果文件</dt>
          <dd>{shortPath(execution.path)}</dd>
        </div>
      </dl>
      <details className="raw-json-details" open>
        <summary>完整 stdout / stderr</summary>
        <pre>{String(execution.stderr || execution.stdout || "暂无执行输出")}</pre>
      </details>
      <RawJsonDetails value={execution} title="查看原始执行记录" />
    </article>
  );
}

export function ValidationLogBlock({ validation }: { validation: ValidationAttemptLog }) {
  return (
    <article className="log-block">
      <h3>第 {validation.attempt} 次验证</h3>
      <dl className="compact-list">
        <div>
          <dt>是否通过</dt>
          <dd>{validation.passed ? "是" : "否"}</dd>
        </div>
        <div>
          <dt>严重级别</dt>
          <dd>{severityLabel(validation.severity)}</dd>
        </div>
        <div>
          <dt>是否重试</dt>
          <dd>{validation.should_retry ? "是" : "否"}</dd>
        </div>
        <div>
          <dt>验证文件</dt>
          <dd>{shortPath(validation.path)}</dd>
        </div>
      </dl>
      <details className="raw-json-details" open>
        <summary>完整问题列表</summary>
        <pre>{JSON.stringify(validation.issues ?? [], null, 2)}</pre>
      </details>
      <details className="raw-json-details" open>
        <summary>完整修复建议</summary>
        <pre>{JSON.stringify(validation.repair_suggestions ?? [], null, 2)}</pre>
      </details>
      <RawJsonDetails value={validation} title="查看原始验证记录" />
    </article>
  );
}

export function ResultList({ title, items }: { title: string; items?: unknown[] | null }) {
  const normalizedItems = Array.isArray(items) ? items.map((item) => formatListItem(item)).filter(Boolean) : [];
  if (!normalizedItems.length) {
    return null;
  }
  return (
    <div className="finding-list">
      <h3>{title}</h3>
      {normalizedItems.map((item, index) => (
        <div className="finding-item" key={`${title}-${index}-${item}`}>
          <p>{item}</p>
        </div>
      ))}
    </div>
  );
}

export function PptOutline({ outline }: { outline: ExplanationResult["ppt_outline"] }) {
  const normalizedOutline = normalizePptOutline(outline);
  if (!normalizedOutline.length) {
    return null;
  }
  return (
    <div className="finding-list">
      <h3>PPT 大纲</h3>
      {normalizedOutline.map((slide, index) => (
        <div className="finding-item" key={`${slide.title}-${index}`}>
          <strong>{slide.title}</strong>
          <p>{slide.bullets.join("；")}</p>
        </div>
      ))}
    </div>
  );
}

export function JsonSummary({ title, value }: { title: string; value: AnyRecord | null }) {
  return (
    <article className="info-card">
      <strong>{title}</strong>
      {value ? <pre>{JSON.stringify(value, null, 2)}</pre> : <p>等待输出生成。</p>}
    </article>
  );
}

export function EventLogList({ events }: { events: ExecutionLogEvent[] }) {
  if (!events.length) {
    return <EmptyState title="暂无日志" text="任务启动后，Agent 事件会实时追加到这里。" compact />;
  }
  return (
    <div className="log-event-list">
      {events.map((event, index) => (
        <article className="log-event" key={`${event.timestamp}-${index}`}>
          <span>
            {stageLabel(event.stage)} · {eventStatusLabel(event.status)}
            {event.attempt ? ` · 第 ${event.attempt} 次尝试` : ""}
          </span>
          <strong>{event.message}</strong>
          <p>{formatTime(event.timestamp)}</p>
        </article>
      ))}
    </div>
  );
}

export function EmptyState({ title, text, compact = false }: { title: string; text: string; compact?: boolean }) {
  return (
    <div className={compact ? "empty-state compact" : "empty-state"}>
      <h2>{title}</h2>
      <p>{text}</p>
    </div>
  );
}












