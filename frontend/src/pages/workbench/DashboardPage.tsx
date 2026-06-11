import { toStorageUrl } from "../../api";
import type { DashboardConfig } from "../../types";
import { Empty, isBusy } from "./shared";

export function DashboardPage({ dashboard, busy, onRefresh, onSave }: { dashboard: DashboardConfig | null; busy: string; onRefresh: () => void; onSave: () => void }) {
  return (
    <div className="content-grid">
      <section className="card">
        <div className="card-header horizontal">
          <div><h2>{dashboard?.title || "Dashboard"}</h2><p>{dashboard?.description || "任务完成后可读取、保存和刷新 Dashboard 配置。"}</p></div>
          <div className="row-actions">
            <button type="button" disabled={!dashboard || isBusy(busy)} onClick={onRefresh}>刷新</button>
            <button type="button" disabled={!dashboard || isBusy(busy)} onClick={onSave}>保存</button>
          </div>
        </div>
        <div className="content-grid three">
          {(dashboard?.widgets || []).slice(0, 9).map((widget) => (
            <article className="dashboard-widget" key={widget.id}>
              <h3>{widget.title}</h3>
              {widget.value !== undefined ? <strong>{String(widget.value)}{widget.unit || ""}</strong> : null}
              {widget.description ? <p>{widget.description}</p> : null}
              {widget.chart_path ? <img src={toStorageUrl(widget.chart_path)} alt={widget.title} /> : null}
            </article>
          ))}
        </div>
        {!dashboard ? <Empty text="打开成功任务后可查看 Dashboard。" /> : null}
      </section>
    </div>
  );
}
