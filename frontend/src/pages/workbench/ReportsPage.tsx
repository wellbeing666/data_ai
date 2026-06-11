import type { ReportGenerateResponse, WorkflowJobResponse } from "../../types";
import { ArtifactRow, isBusy } from "./shared";

export function ReportsPage({ job, report, chartPaths, busy, onGenerate }: { job: WorkflowJobResponse | null; report: ReportGenerateResponse | null; chartPaths: string[]; busy: string; onGenerate: () => void }) {
  return (
    <div className="content-grid two">
      <section className="card">
        <div className="card-header horizontal">
          <div><h2>报告与 PPT</h2><p>将分析结果转为可交付报告、PPTX 和图表附件。</p></div>
          <button className="button button-primary" type="button" disabled={isBusy(busy) || !job} onClick={onGenerate}>生成交付物</button>
        </div>
        <div className="list">
          <ArtifactRow label="Markdown 报告" path={report?.report_path || job?.report_path} />
          <ArtifactRow label="PPTX 文件" path={report?.pptx_path || job?.pptx_path} />
          <ArtifactRow label="PPT 预览" path={report?.pptx_preview_path || job?.pptx_preview_path} />
          <div className="list-row"><div><strong>图表附件</strong><span>{chartPaths.length} 张</span></div></div>
        </div>
      </section>
      <section className="card">
        <div className="card-header"><div><h2>结论状态</h2><p>成功任务会保留最终结果、验证结果和报告数据。</p></div></div>
        <div className="kv-list">
          <div><span>最终结果</span><strong>{job?.final_result_path ? "已生成" : "-"}</strong></div>
          <div><span>验证结果</span><strong>{job?.final_validation_result_path ? "已生成" : "-"}</strong></div>
          <div><span>报告数据</span><strong>{job?.final_report_data_path ? "已生成" : "-"}</strong></div>
        </div>
      </section>
    </div>
  );
}
