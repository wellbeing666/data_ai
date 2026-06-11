import { Button, Card, Space, Table, Tag, type TableColumnsType } from "antd";

import type { HealthStatus, WorkflowJobListItem } from "../../types";
import { Metric, shortId, statusText } from "./shared";

export function OverviewPage({
  health,
  jobs,
  chartPaths,
  knowledgeCount,
  onOpenJob
}: {
  health: HealthStatus | null;
  jobs: WorkflowJobListItem[];
  chartPaths: string[];
  knowledgeCount: number;
  onOpenJob: (jobId: string) => void;
}) {
  const totalJobs = jobs.length;
  const successJobs = jobs.filter((item) => item.status === "success").length;
  const runningJobs = jobs.filter((item) => !["success", "failed", "cancelled"].includes(item.status)).length;
  const failedJobs = jobs.filter((item) => item.status === "failed").length;
  const datasetCount = new Set(jobs.map((item) => item.dataset_id || item.dataset_filename).filter(Boolean)).size;
  const tabularJobs = jobs.filter((item) => item.asset_type === "tabular").length;
  const imageJobs = jobs.filter((item) => item.asset_type === "image").length;
  const totalCharts = jobs.reduce((sum, item) => sum + (item.chart_count || 0), 0);
  const latestUpdatedAt = jobs
    .map((item) => item.updated_at)
    .filter((value): value is string => Boolean(value))
    .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0];

  const taskColumns: TableColumnsType<WorkflowJobListItem> = [
    {
      title: "任务",
      dataIndex: "user_goal",
      ellipsis: true,
      width: 360
    },
    {
      title: "数据",
      dataIndex: "dataset_filename",
      ellipsis: true,
      width: 180,
      render: (value: string | undefined, record) => value || record.dataset_id || "-"
    },
    {
      title: "状态",
      dataIndex: "status",
      width: 100,
      render: (value: string) => <Tag>{statusText(value)}</Tag>
    },
    {
      title: "图表",
      dataIndex: "chart_count",
      width: 80
    },
    {
      title: "更新时间",
      dataIndex: "updated_at",
      width: 180,
      render: (value?: string | null) => value ? new Date(value).toLocaleString() : "-"
    },
    {
      title: "操作",
      key: "actions",
      fixed: "right",
      width: 90,
      render: (_, item) => <Button size="small" type="link" onClick={() => onOpenJob(item.job_id)}>打开</Button>
    }
  ];

  return (
    <div className="content-grid">
      <section className="card span-two">
        <div className="overview-data-grid">
          <Metric label="任务总数" value={`${totalJobs}`} />
          <Metric label="成功任务" value={`${successJobs}`} />
          <Metric label="运行中任务" value={`${runningJobs}`} />
          <Metric label="失败任务" value={`${failedJobs}`} />
          <Metric label="数据集总数" value={`${datasetCount}`} />
          <Metric label="表格任务" value={`${tabularJobs}`} />
          <Metric label="图片任务" value={`${imageJobs}`} />
          <Metric label="图表总数" value={`${totalCharts}`} />
          <Metric label="知识文档" value={`${knowledgeCount}`} />
          <Metric label="系统状态" value={health?.status || "-"} />
          <Metric label="模型模式" value={health?.llm_mode || "-"} />
          <Metric label="最近更新" value={latestUpdatedAt ? new Date(latestUpdatedAt).toLocaleString() : "-"} />
        </div>
      </section>
      <Card className="operation-card span-two" variant="outlined">
        <div className="operation-toolbar">
          <div>
            <h2>最近分析任务</h2>
          </div>
          <Space>
            <Tag color="blue">{jobs.length} 个任务</Tag>
            <Tag color="purple">{chartPaths.length} 张图表</Tag>
          </Space>
        </div>
        <Table
          rowKey="job_id"
          className="dense-ant-table"
          size="small"
          columns={taskColumns}
          dataSource={jobs.slice(0, 8)}
          pagination={false}
          scroll={{ x: 980 }}
        />
      </Card>
      <section className="card span-two">
        <div className="card-header">
          <div>
            <h2>结果概览</h2>
          </div>
        </div>
        <div className="kpi-grid">
          <Metric label="图表总数" value={`${totalCharts || chartPaths.length}`} />
          <Metric label="最近任务状态" value={jobs[0] ? statusText(jobs[0].status) : "-"} />
          <Metric label="最近任务 ID" value={jobs[0] ? shortId(jobs[0].job_id) : "-"} />
        </div>
      </section>
    </div>
  );
}
