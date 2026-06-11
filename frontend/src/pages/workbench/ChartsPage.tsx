import type { FormEvent } from "react";

import { toStorageUrl } from "../../api";
import type { WorkflowFollowUpResponse } from "../../types";
import { chartTitle, Empty, isBusy } from "./shared";

export function ChartsPage(props: {
  chartPaths: string[];
  refineInstruction: string;
  busy: string;
  onRefineInstructionChange: (value: string) => void;
  onRefine: (chartPath: string) => void;
  onDelete: (chartPath: string) => void;
  followUpQuestion: string;
  followUps: WorkflowFollowUpResponse[];
  onFollowUpQuestionChange: (value: string) => void;
  onFollowUp: (event: FormEvent) => void;
}) {
  return (
    <div className="content-grid">
      <section className="card">
        <div className="card-header">
          <div><h2>图表结果</h2><p>支持下载、删除、按自然语言重新优化，以及围绕图表继续追问。</p></div>
        </div>
        <textarea className="goal-textarea small" value={props.refineInstruction} onChange={(event) => props.onRefineInstructionChange(event.target.value)} />
        <div className="chart-grid">
          {props.chartPaths.map((chartPath, index) => (
            <figure className="chart-card" key={chartPath}>
              <img src={toStorageUrl(chartPath)} alt={`图表 ${index + 1}`} />
              <figcaption>{chartTitle(chartPath, index)}</figcaption>
              <div className="row-actions">
                <a href={toStorageUrl(chartPath)} download>下载</a>
                <button type="button" disabled={isBusy(props.busy)} onClick={() => props.onRefine(chartPath)}>优化</button>
                <button type="button" disabled={isBusy(props.busy)} onClick={() => props.onDelete(chartPath)}>删除</button>
              </div>
            </figure>
          ))}
        </div>
        {!props.chartPaths.length ? <Empty text="任务成功后会显示图表。" /> : null}
      </section>
      <section className="card">
        <div className="card-header"><div><h2>图表追问</h2><p>对当前任务继续提问，系统会结合产物回答。</p></div></div>
        <form className="inline-form" onSubmit={props.onFollowUp}>
          <label>
            追问
            <input value={props.followUpQuestion} onChange={(event) => props.onFollowUpQuestionChange(event.target.value)} />
          </label>
          <button className="button button-primary" type="submit" disabled={isBusy(props.busy)}>提交追问</button>
        </form>
        <div className="list">
          {props.followUps.map((item) => (
            <div className="list-row" key={`${item.created_at}-${item.question}`}>
              <div><strong>{item.question}</strong><span>{item.answer}</span></div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
