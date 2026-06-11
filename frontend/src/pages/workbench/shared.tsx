import { toStorageUrl } from "../../api";
import type { ExecutionLogEvent } from "../../types";

export function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function InfoCard({ title, value, detail, tone = "muted" }: { title: string; value: string; detail: string; tone?: "success" | "muted" }) {
  return (
    <section className="card compact-card">
      <span className={`status-dot ${tone}`} />
      <h3>{title}</h3>
      <strong>{value}</strong>
      <p>{detail}</p>
    </section>
  );
}

export function Empty({ text }: { text: string }) {
  return <div className="empty-state">{text}</div>;
}

export function DataTable({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: string[] }) {
  if (!rows.length || !columns.length) {
    return <Empty text="暂无数据预览。" />;
  }
  return (
    <div className="table-wrap small-table">
      <table>
        <thead>
          <tr>{columns.slice(0, 6).map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.slice(0, 5).map((row, index) => (
            <tr key={index}>
              {columns.slice(0, 6).map((column) => <td key={column}>{formatCell(row[column])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EventList({ events }: { events: ExecutionLogEvent[] }) {
  if (!events.length) {
    return <Empty text="暂无事件。" />;
  }
  return (
    <div className="event-list">
      {events.map((event, index) => (
        <div className="event-row" key={`${event.timestamp}-${event.stage}-${index}`}>
          <time>{formatTime(event.timestamp)}</time>
          <div>
            <strong>{stageText(event.stage)} · {statusText(event.status)}</strong>
            <span>{event.message}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function ArtifactRow({ label, path }: { label: string; path?: string | null }) {
  return (
    <div className="list-row">
      <div><strong>{label}</strong><span>{path || "尚未生成"}</span></div>
      {path ? <a href={toStorageUrl(path)} target="_blank" rel="noreferrer">打开</a> : <span className="badge badge-outline">等待</span>}
    </div>
  );
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function shortId(value: string): string {
  return value.length > 8 ? value.slice(0, 8) : value;
}

export function chartTitle(path: string, index: number): string {
  return path.replace(/\\/g, "/").split("/").pop() || `图表 ${index + 1}`;
}

export function statusText(value: string): string {
  const labels: Record<string, string> = {
    pending: "等待",
    running: "运行中",
    success: "成功",
    failed: "失败",
    cancelled: "已取消",
    pass: "通过",
    warning: "警告",
    start: "开始",
    end: "结束"
  };
  return labels[value] || value;
}

export function stageText(value: string): string {
  const labels: Record<string, string> = {
    preflight: "预检",
    controller: "控制器",
    rag: "知识检索",
    data_understanding: "数据理解",
    analysis: "分析计划",
    code: "代码执行",
    validation: "验证",
    report: "报告",
    dashboard: "看板",
    prediction: "预测"
  };
  return labels[value] || value;
}

export function isBusy(value: string): boolean {
  return Boolean(value);
}
