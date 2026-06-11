import { Card, Table, Tag, type TableColumnsType } from "antd";

import type { ExecutionLogEvent, PredictionLogResponse, WorkflowLogResponse } from "../../types";
import { EventList, stageText, statusText } from "./shared";

export function LogsPage({ workflowLog, predictionLog, events }: { workflowLog: WorkflowLogResponse | null; predictionLog: PredictionLogResponse | null; events: ExecutionLogEvent[] }) {
  const executionResults = workflowLog?.execution_results || predictionLog?.execution_results || [];
  const validationResults = workflowLog?.validation_results || predictionLog?.validation_results || [];
  const eventRows = events.map((event, index) => ({ ...event, event_key: `${event.timestamp}-${event.stage}-${index}` }));
  const eventColumns: TableColumnsType<ExecutionLogEvent> = [
    { title: "时间", dataIndex: "timestamp", width: 120, render: (value: string) => new Date(value).toLocaleTimeString() },
    { title: "阶段", dataIndex: "stage", width: 120, render: (value: string) => <Tag>{stageText(value)}</Tag> },
    { title: "状态", dataIndex: "status", width: 100, render: (value: string) => <Tag color={value === "failed" ? "red" : value === "success" ? "green" : "blue"}>{statusText(value)}</Tag> },
    { title: "消息", dataIndex: "message", ellipsis: true }
  ];
  const executionColumns = [
    { title: "尝试", dataIndex: "attempt", width: 90 },
    { title: "退出码", dataIndex: "exit_code", width: 100, render: (value: number | null | undefined) => value ?? "-" },
    { title: "结果", dataIndex: "success", width: 100, render: (value: boolean) => <Tag color={value ? "green" : "red"}>{value ? "成功" : "未通过"}</Tag> }
  ];
  const validationColumns = [
    { title: "尝试", dataIndex: "attempt", width: 90 },
    { title: "严重度", dataIndex: "severity", width: 120, render: (value: string) => <Tag color={value === "error" ? "red" : "gold"}>{value}</Tag> },
    { title: "结果", dataIndex: "passed", width: 100, render: (value: boolean) => <Tag color={value ? "green" : "red"}>{value ? "通过" : "未通过"}</Tag> }
  ];

  return (
    <div className="content-grid two">
      <Card className="operation-card" variant="outlined">
        <div className="card-header"><div><h2>执行事件</h2><p>展示分析任务和预测任务的实时事件。</p></div></div>
        <Table
          rowKey="event_key"
          className="dense-ant-table"
          size="small"
          columns={eventColumns}
          dataSource={eventRows}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          scroll={{ x: 720 }}
          locale={{ emptyText: <EventList events={[]} /> }}
        />
      </Card>
      <Card className="operation-card" variant="outlined">
        <div className="card-header"><div><h2>执行与验证</h2><p>查看代码执行、验证、自动修复尝试。</p></div></div>
        <div className="stacked-tables">
          <Table
            rowKey="attempt"
            className="dense-ant-table"
            size="small"
            columns={executionColumns}
            dataSource={executionResults}
            pagination={false}
          />
          <Table
            rowKey="attempt"
            className="dense-ant-table"
            size="small"
            columns={validationColumns}
            dataSource={validationResults}
            pagination={false}
          />
        </div>
      </Card>
    </div>
  );
}
