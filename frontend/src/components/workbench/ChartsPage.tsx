import { toStorageUrl } from "../../api";
import type { AnalysisResult, PredictionResult, WorkflowJobResponse } from "../../types";
import { buildNoChartReason, chartTitle } from "../../utils/workbenchUtils";
import { buildChartRefineSuggestions, toVersionedStorageUrl } from "./charts/chartHelpers";

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
                <ChartFigure
                  chartPath={chartPath}
                  index={index}
                  chartRefreshToken={chartRefreshToken}
                  onOpenChart={onOpenChart}
                  onDeleteChart={onDeleteChart}
                />
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

function ChartFigure({
  chartPath,
  index,
  chartRefreshToken,
  onOpenChart,
  onDeleteChart
}: {
  chartPath: string;
  index: number;
  chartRefreshToken: number;
  onOpenChart: (chartPath: string) => void;
  onDeleteChart: (chartPath: string) => void;
}) {
  return (
    <>
      <button
        className="chart-image-button"
        type="button"
        onClick={() => onOpenChart(chartPath)}
        aria-label={`放大查看${chartTitle(chartPath, index)}`}
      >
        <img
          alt={`分析图表 ${index + 1}`}
          src={toVersionedStorageUrl(chartPath, chartRefreshToken)}
          draggable={false}
        />
      </button>
      <figcaption>{chartTitle(chartPath, index)}</figcaption>
      <div className="chart-actions chart-tools">
        <a href={toStorageUrl(chartPath)} download>下载 PNG</a>
        <button type="button" onClick={() => onOpenChart(chartPath)}>放大查看</button>
        <button className="danger-button" type="button" onClick={() => onDeleteChart(chartPath)}>删除</button>
      </div>
    </>
  );
}

function DataSourceNotice({ job }: { job: WorkflowJobResponse | null }) {
  if (job?.asset_type !== "image") {
    return null;
  }
  return (
    <div className="source-notice">
      本次数据来源于视觉解析，图片抽取可能存在识别误差，建议结合原图核对关键字段和数值。
    </div>
  );
}

function EmptyState({ title, text, compact = false }: { title: string; text: string; compact?: boolean }) {
  return (
    <div className={`empty-state ${compact ? "compact" : ""}`}>
      <div>
        <h2>{title}</h2>
        <p>{text}</p>
      </div>
    </div>
  );
}
