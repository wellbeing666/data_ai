import type { PredictionJobResponse, PredictionLogResponse } from "../../types";
import { EventList, isBusy, Metric, shortId, statusText } from "./shared";

export function PredictionPage(props: {
  goal: string;
  job: PredictionJobResponse | null;
  log: PredictionLogResponse | null;
  busy: string;
  onGoalChange: (value: string) => void;
  onRun: () => void;
  onRefresh: () => void;
}) {
  return (
    <div className="content-grid two">
      <section className="card">
        <div className="card-header horizontal">
          <div><h2>预测分析</h2><p>用于预算提升、情景模拟、what-if 预测等任务。</p></div>
          <button className="button button-primary" type="button" disabled={isBusy(props.busy)} onClick={props.onRun}>启动预测</button>
        </div>
        <textarea className="goal-textarea" value={props.goal} onChange={(event) => props.onGoalChange(event.target.value)} />
      </section>
      <section className="card">
        <div className="card-header horizontal">
          <div><h2>预测任务状态</h2><p>{props.job?.job_id ? shortId(props.job.job_id) : "尚未启动"}</p></div>
          <button type="button" disabled={!props.job || isBusy(props.busy)} onClick={props.onRefresh}>刷新</button>
        </div>
        <div className="kpi-grid">
          <Metric label="状态" value={props.job ? statusText(props.job.status) : "-"} />
          <Metric label="阶段" value={props.job?.current_stage || "-"} />
          <Metric label="图表" value={String(props.job?.chart_paths?.length || 0)} />
        </div>
        <EventList events={(props.job?.events || props.log?.events || []).slice(0, 8)} />
      </section>
    </div>
  );
}
