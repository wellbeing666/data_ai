import type { AnalysisIR, DatasetUploadResponse, ExecutionLogEvent, PreflightAssessment, WorkflowJobResponse } from "../../types";
import { Empty, EventList, isBusy, Metric, shortId, statusText } from "./shared";

export function WorkflowRunPage(props: {
  busy: string;
  dataset: DatasetUploadResponse | null;
  goal: string;
  preflight: PreflightAssessment | null;
  job: WorkflowJobResponse | null;
  analysisIr: AnalysisIR | null;
  events: ExecutionLogEvent[];
  onGoalChange: (value: string) => void;
  onPreflight: () => void;
  onRunWorkflow: () => void;
  onRunInsight: () => void;
  onControl: (action: string) => void;
  onDeleteJob: () => void;
}) {
  const { busy, dataset, goal, preflight, job, analysisIr, events } = props;
  return (
    <div className="content-grid two">
      <section className="card span-two">
        <div className="card-header horizontal">
          <div>
            <h2>AI 工作流</h2>
            <p>先预检，再启动分析；智能洞察模式可自动发现异常和机会点。</p>
          </div>
          <div className="row-actions">
            <button type="button" onClick={props.onPreflight} disabled={!dataset || isBusy(busy)}>预检目标</button>
            <button type="button" onClick={props.onRunWorkflow} disabled={!dataset || isBusy(busy)}>启动分析</button>
            <button type="button" onClick={props.onRunInsight} disabled={!dataset || isBusy(busy)}>智能洞察</button>
          </div>
        </div>
        <textarea className="goal-textarea" value={goal} onChange={(event) => props.onGoalChange(event.target.value)} />
      </section>
      <section className="card">
        <div className="card-header horizontal">
          <div>
            <h2>预检与任务理解</h2>
            <p>把用户目标翻译成指标、维度、过滤条件和澄清问题。</p>
          </div>
          <span className="badge badge-secondary">{preflight ? `${Math.round(preflight.clarity_score * 100)}%` : "-"}</span>
        </div>
        {preflight ? (
          <div className="list">
            <div className="list-row"><div><strong>任务类型</strong><span>{preflight.intent_type}</span></div><span className="badge badge-outline">{preflight.is_task_clear ? "清晰" : "需澄清"}</span></div>
            {preflight.clarifying_questions.map((question) => (
              <div className="list-row" key={question}><div><strong>澄清问题</strong><span>{question}</span></div></div>
            ))}
            {preflight.suggested_goals.map((item) => (
              <div className="list-row" key={item}><div><strong>建议目标</strong><span>{item}</span></div></div>
            ))}
          </div>
        ) : <Empty text="还没有预检结果。" />}
      </section>
      <section className="card">
        <div className="card-header horizontal">
          <div>
            <h2>当前任务</h2>
            <p>{job?.user_goal || "尚未启动 AI 工作流。"}</p>
          </div>
          <span className="badge badge-outline">{job ? statusText(job.status) : "-"}</span>
        </div>
        <div className="kpi-grid">
          <Metric label="任务 ID" value={job ? shortId(job.job_id) : "-"} />
          <Metric label="当前阶段" value={job?.current_stage || "-"} />
          <Metric label="尝试次数" value={String(job?.attempts?.length || 0)} />
        </div>
        <div className="row-actions">
          <button type="button" disabled={!job || isBusy(busy)} onClick={() => props.onControl("pause")}>暂停</button>
          <button type="button" disabled={!job || isBusy(busy)} onClick={() => props.onControl("resume")}>继续</button>
          <button type="button" disabled={!job || isBusy(busy)} onClick={() => props.onControl("rerun")}>重跑</button>
          <button type="button" disabled={!job || isBusy(busy)} onClick={props.onDeleteJob}>删除</button>
        </div>
      </section>
      <section className="card">
        <div className="card-header">
          <div><h2>分析 IR</h2><p>系统生成的结构化分析意图。</p></div>
        </div>
        {analysisIr ? (
          <div className="tag-cloud">
            {(analysisIr.metrics || []).map((item) => <span key={item.name}>{item.name}</span>)}
            {(analysisIr.dimensions || []).map((item) => <span key={item.name}>{item.name}</span>)}
            {(analysisIr.guardrails || []).slice(0, 6).map((item) => <span key={item}>{item}</span>)}
          </div>
        ) : <Empty text="任务运行后会显示分析 IR。" />}
      </section>
      <section className="card">
        <div className="card-header">
          <div><h2>实时事件</h2><p>按时间展示 Agent 和执行状态。</p></div>
        </div>
        <EventList events={events.slice(0, 8)} />
      </section>
    </div>
  );
}
