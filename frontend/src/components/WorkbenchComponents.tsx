import { useEffect, useMemo, useState } from "react";

import { toStorageUrl } from "../api";
import type {
  AnalysisRoadmap,
  AnalysisResult,
  DatasetProfile,
  ExecutionAttemptLog,
  ExecutionLogEvent,
  ExplanationResult,
  HealthStatus,
  KnowledgeDocument,
  KnowledgeSearchResponse,
  PredictionExplanationResult,
  PredictionResult,
  PreflightAssessment,
  QualityReview,
  ReportGenerateResponse,
  SampleDatasetResponse,
  ValidationAttemptLog,
  VisualParseResult,
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
  onCancel
}: {
  sample: SampleDatasetResponse;
  rowCount: number;
  columns: string[];
  rows: AnyRecord[];
  goal: string;
  onGoalChange: (goal: string) => void;
  onConfirm: () => void;
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
            <strong>可视化执行路线</strong>
            <RoadmapRenderedDiagram steps={roadmap.steps} />
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

export function MermaidDiagram({ code }: { code: string }) {
  const nodes = parseMermaidFlowchart(code);

  if (!nodes.length) {
    return <pre className="mermaid-diagram mermaid-code-fallback">{code}</pre>;
  }

  return (
    <div className="mermaid-diagram mermaid-flow-render">
      {nodes.map((node, index) => (
        <div className="mermaid-flow-node-wrap" key={node.id}>
          <div className="mermaid-flow-node">
            <span>{index + 1}</span>
            <div>
              <strong>{node.title}</strong>
              {node.agent ? <small>{node.agent}</small> : null}
            </div>
          </div>
          {index < nodes.length - 1 ? <div className="mermaid-flow-edge">↓</div> : null}
        </div>
      ))}
    </div>
  );
}

function parseMermaidFlowchart(code: string): Array<{ id: string; title: string; agent: string }> {
  const nodes = new Map<string, { id: string; title: string; agent: string }>();
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

  if (!order.length) {
    return [];
  }

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
  return finalOrder.map((id) => nodes.get(id)).filter((node): node is { id: string; title: string; agent: string } => Boolean(node));
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
  qualityReview,
  isPredictionWorkflow,
  events
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
  qualityReview: QualityReview | null;
  isPredictionWorkflow: boolean;
  events: ExecutionLogEvent[];
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
    qualityReview,
    isPredictionWorkflow
  });
  const attemptViews = buildAttemptProgressViews({
    job,
    log,
    events
  });

  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>Agent 对话过程</h2>
        {job ? <span>{workflowLabel(job.workflow_type || job.task_type)} · Job {job.job_id}</span> : <span>等待任务启动</span>}
      </div>
      <div className="agent-chat-list">
        {cards.length ? (
          cards.map((card) => <AgentMessageCard card={card} key={card.key} />)
        ) : (
          <EmptyState title="等待 Agent 接入" text="任务启动后，实际参与工作的 Agent 会按执行顺序逐个出现在这里。" compact />
        )}
      </div>
      <QualityReviewPanel review={qualityReview} />
      <AttemptProgressSection attempts={attemptViews} isPredictionWorkflow={isPredictionWorkflow} />
    </section>
  );
}

export function AgentMessageCard({ card }: { card: AgentCardView }) {
  return (
    <article className={`agent-message-card ${card.status}`}>
      <div className="agent-avatar">{agentInitial(card.agentName)}</div>
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
  if (card.artifactKind === "explanation") {
    return <ExplanationArtifactSummary value={card.raw as ExplanationResult} />;
  }
  if (card.artifactKind === "quality_review") {
    return <QualityReviewArtifactSummary value={card.raw as QualityReview} />;
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

export function ChipList({ title, items, tone = "default" }: { title: string; items: string[]; tone?: "default" | "warning" }) {
  const cleanItems = items.filter(Boolean);
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

export function ChartsPage({
  analysisResult,
  chartPaths,
  job,
  predictionResult,
  isPredictionWorkflow,
  message,
  refineInstructions,
  chartSuggestions,
  refiningChartPath,
  chartRefreshToken,
  onRefineInstructionChange,
  onRefineChart,
  onQuickRefineChart,
  onOpenChart,
  onDeleteChart
}: {
  analysisResult: AnalysisResult | null;
  chartPaths: string[];
  job: WorkflowJobResponse | null;
  predictionResult: PredictionResult | null;
  isPredictionWorkflow: boolean;
  message: string;
  refineInstructions: Record<string, string>;
  chartSuggestions: Record<string, string[]>;
  refiningChartPath: string | null;
  chartRefreshToken: number;
  onRefineInstructionChange: (chartPath: string, value: string) => void;
  onRefineChart: (chartPath: string) => void;
  onQuickRefineChart: (chartPath: string, instruction: string) => void;
  onOpenChart: (chartPath: string) => void;
  onDeleteChart: (chartPath: string) => void;
}) {
  const resultChartCount = Array.isArray(analysisResult?.charts) ? analysisResult.charts.length : 0;
  const noChartReason = chartPaths.length ? "" : buildNoChartReason(isPredictionWorkflow, predictionResult, analysisResult);
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>最终图表</h2>
        <span>{chartPaths.length || resultChartCount} 个图表</span>
      </div>
      <DataSourceNotice job={job} />
      {message ? <p className="chart-message">{message}</p> : null}
      {chartPaths.length ? (
        <div className="chart-grid">
          {chartPaths.map((chartPath, index) => {
            const suggestions = chartSuggestions[chartPath]?.length
              ? chartSuggestions[chartPath]
              : buildChartRefineSuggestions(chartPath, isPredictionWorkflow, analysisResult, predictionResult, job);
            return (
              <figure className="chart-card" key={chartPath}>
                <button
                  className="chart-image-button"
                  type="button"
                  onClick={() => onOpenChart(chartPath)}
                  aria-label={`放大查看${chartTitle(chartPath, index)}`}
                >
                  <img alt={`分析图表 ${index + 1}`} src={toVersionedStorageUrl(chartPath, chartRefreshToken)} />
                </button>
                <figcaption>{chartTitle(chartPath, index)}</figcaption>
                <div className="chart-actions">
                  <button type="button" onClick={() => onOpenChart(chartPath)}>
                    放大查看
                  </button>
                  <button className="danger-button" type="button" onClick={() => onDeleteChart(chartPath)}>
                    删除
                  </button>
                </div>
                <div className="chart-refine-panel">
                  <label htmlFor={`chart-refine-${index}`}>针对这张图输入修改要求</label>
                  <textarea
                    id={`chart-refine-${index}`}
                    rows={3}
                    value={refineInstructions[chartPath] ?? ""}
                    placeholder="例如：改成折线图，只保留华东地区，并把标题改成月度销量趋势"
                    onChange={(event) => onRefineInstructionChange(chartPath, event.target.value)}
                  />
                  <div className="chart-suggestion-row" aria-label="智能推荐的图表修改选项">
                    {suggestions.map((suggestion) => (
                      <button
                        key={suggestion}
                        type="button"
                        disabled={!job?.job_id || refiningChartPath === chartPath}
                        onClick={() => onQuickRefineChart(chartPath, suggestion)}
                      >
                        {suggestion}
                      </button>
                    ))}
                  </div>
                  <button
                    className="secondary-button"
                    type="button"
                    disabled={!job?.job_id || refiningChartPath === chartPath}
                    onClick={() => onRefineChart(chartPath)}
                  >
                    {refiningChartPath === chartPath ? "重新渲染中" : "按要求重新渲染"}
                  </button>
                </div>
              </figure>
            );
          })}
        </div>
      ) : (
        <EmptyState
          title={noChartReason ? "本次无需图表" : "暂无图表"}
          text={noChartReason || "分析脚本完成并通过验证后，图表会自动出现在这里。"}
        />
      )}
    </section>
  );
}

function buildChartRefineSuggestions(
  chartPath: string,
  isPredictionWorkflow: boolean,
  analysisResult?: AnalysisResult | null,
  predictionResult?: PredictionResult | null,
  job?: WorkflowJobResponse | null
): string[] {
  const chartType = inferChartType(chartPath);
  const field = friendlyFieldName(extractChartField(chartPath));
  const target = friendlyFieldName(inferTargetMetric(analysisResult, predictionResult));
  const goal = (job?.user_goal || "本轮分析目标").slice(0, 24);

  if (isPredictionWorkflow) {
    return [
      `改为${target}的基准值与预测值并列柱状图，并按预测变化绝对值从高到低排序。`,
      `只展示${target}变化最大的前 5 个对象，并在柱尾标注变化量和变化率。`,
      "把预测提升和预测下降分开表达，并在标题中写清当前情景假设。",
      "增加模型限制说明到图表副标题，提示预测结果不是确定因果。"
    ];
  }

  if (chartType === "heatmap") {
    return [
      `只展示与${target}相关性最高的前 10 个字段，并按相关系数绝对值排序。`,
      "将热力图色阶固定为 -1 到 1，并放大字段标签，便于比较强弱关系。",
      "隐藏 Id 等标识类字段，只保留面积、质量、年份和配套等可解释变量。",
      `改为${target}相关系数横向柱状图，突出正相关和负相关最明显的变量。`
    ];
  }

  if (chartType === "scatter") {
    const discreteField = ["整体质量（OverallQual）", "车库容量（GarageCars）", "全卫数量（FullBath）", "地上房间数（TotRmsAbvGrd）"].includes(field);
    return [
      `保留${field}与${target}散点关系，增加线性趋势线、相关系数和样本量标注。`,
      `剔除${field}或${target}的极端离群点后重绘，并在标题中说明过滤口径。`,
      discreteField
        ? `改为箱线图，比较不同${field}等级下${target}的中位数、分位数和异常点。`
        : `改为分箱柱状图，将${field}按区间分组后展示${target}均值和中位数。`,
      `按社区/区域分组着色，只保留样本量最高的前 5 组，减少视觉干扰。`
    ];
  }

  if (chartType === "line") {
    return [
      `保留时间顺序并增加${target}趋势线，同时标注最高点和最低点。`,
      "改为按关键分组拆分的多折线图，只保留样本量最高的前 5 组。",
      `增加环比变化标签，突出${target}波动最大的区间。`,
      "优化标题和横轴刻度密度，使趋势图更适合汇报展示。"
    ];
  }

  if (chartType === "bar" || chartType === "barh") {
    const dimension = field === "目标指标" ? "当前分组" : field;
    return [
      `按${target}均值从高到低重排${dimension}，并只保留前 10 组。`,
      `增加${target}中位数或样本量标签，避免只看均值造成误判。`,
      `改为横向柱状图展示${dimension}差异，长标签保持完整可读。`,
      `突出最高和最低的${dimension}，并在标题中说明对比口径。`
    ];
  }

  return [
    `围绕${target}重绘图表，明确维度、指标和排序口径。`,
    `只保留与“${goal}”最相关的前 8 个分组。`,
    "增加样本量、均值或中位数标签，让图表结论更可核对。",
    "优化标题、副标题和坐标轴单位，使图表可以直接放入报告。"
  ];
}

function inferChartType(chartPath: string): "heatmap" | "scatter" | "line" | "bar" | "barh" | "chart" {
  const lower = chartPath.toLowerCase();
  if (lower.includes("heatmap") || lower.includes("corr")) {
    return "heatmap";
  }
  if (lower.includes("scatter")) {
    return "scatter";
  }
  if (lower.includes("line") || lower.includes("trend") || lower.includes("monthly") || chartPath.includes("月")) {
    return "line";
  }
  if (lower.includes("barh")) {
    return "barh";
  }
  if (lower.includes("bar") || lower.includes("top") || lower.includes("rank")) {
    return "bar";
  }
  return "chart";
}

function extractChartField(chartPath: string): string {
  const filename = chartPath.replace(/\\/g, "/").split("/").pop() || "";
  const stem = filename.replace(/\.[^.]+$/, "");
  const scatterMatch = stem.match(/scatter[_-]([^._-]+)/i);
  if (scatterMatch?.[1]) {
    return scatterMatch[1];
  }
  const pieces = stem.split(/[_-]+/).filter(Boolean);
  const ignored = new Set(["chart", "plot", "heatmap", "correlation", "refined"]);
  for (let index = pieces.length - 1; index >= 0; index -= 1) {
    const piece = pieces[index];
    if (!ignored.has(piece.toLowerCase())) {
      return piece;
    }
  }
  return "";
}

function inferTargetMetric(analysisResult?: AnalysisResult | null, predictionResult?: PredictionResult | null): string {
  if (predictionResult?.target_metric) {
    return predictionResult.target_metric;
  }
  const candidateKeys = ["target_metric", "target_column", "metric"];
  for (const key of candidateKeys) {
    const value = analysisResult?.[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  const text = JSON.stringify(analysisResult || {});
  if (text.includes("SalePrice")) {
    return "SalePrice";
  }
  if (text.includes("销量")) {
    return "销量";
  }
  if (text.includes("销售额")) {
    return "销售额";
  }
  if (text.includes("成绩")) {
    return "成绩";
  }
  return "目标指标";
}

function friendlyFieldName(value: string): string {
  const text = (value || "").trim();
  const normalized = text.toLowerCase().replace(/[^0-9a-z\u4e00-\u9fff]/g, "");
  const labels: Record<string, string> = {
    saleprice: "房价（SalePrice）",
    overallqual: "整体质量（OverallQual）",
    grlivarea: "地上居住面积（GrLivArea）",
    totalbsmtsf: "地下室总面积（TotalBsmtSF）",
    "1stflrsf": "一层面积（1stFlrSF）",
    garagecars: "车库容量（GarageCars）",
    garagearea: "车库面积（GarageArea）",
    neighborhood: "社区/区域（Neighborhood）",
    mszoning: "住宅分区（MSZoning）",
    yearbuilt: "建造年份（YearBuilt）",
    fullbath: "全卫数量（FullBath）",
    totrmsabvgrd: "地上房间数（TotRmsAbvGrd）"
  };
  return labels[normalized] || text || "目标指标";
}

export function ChartPreviewModal({
  chartPath,
  chartRefreshToken,
  onClose,
  onDelete
}: {
  chartPath: string;
  chartRefreshToken: number;
  onClose: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="chart-modal-backdrop" role="dialog" aria-modal="true" aria-label="图表预览">
      <div className="chart-modal">
        <div className="chart-modal-head">
          <strong>{chartTitle(chartPath, 0)}</strong>
          <div className="chart-modal-actions">
            <button className="danger-button" type="button" onClick={onDelete}>
              删除
            </button>
            <button type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
        <div className="chart-modal-body">
          <img alt="放大图表" src={toVersionedStorageUrl(chartPath, chartRefreshToken)} />
        </div>
      </div>
    </div>
  );
}

function toVersionedStorageUrl(path: string, token: number): string {
  const url = toStorageUrl(path);
  if (!token) {
    return url;
  }
  return `${url}${url.includes("?") ? "&" : "?"}v=${token}`;
}

export function InsightsPage({
  explanation,
  report,
  job
}: {
  explanation: ExplanationResult;
  report: ReportGenerateResponse | null;
  job: WorkflowJobResponse | null;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>结论与报告</h2>
        {report ? (
          <a className="download-button" href={toStorageUrl(report.report_path)} download>
            下载报告
          </a>
        ) : (
          <span>等待报告生成</span>
        )}
      </div>
      <DataSourceNotice job={job} />
      {explanation.summary ? (
        <>
          <p className="summary-text">{explanation.summary}</p>
          <ResultList title="关键发现" items={explanation.key_findings} />
          <ResultList title="建议动作" items={explanation.recommendations} />
          <ResultList title="限制说明" items={explanation.limitations} />
          <PptOutline outline={explanation.ppt_outline} />
        </>
      ) : (
        <EmptyState title="暂无结论" text="验证 Agent 通过后，解释 Agent 会生成结论、建议和 PPT 大纲。" />
      )}
    </section>
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


