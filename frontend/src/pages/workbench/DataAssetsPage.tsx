import type { ChangeEvent, FormEvent } from "react";
import { Button, Card, Space, Table, Tag, type TableColumnsType } from "antd";

import type { CleaningPlanResponse, CleaningReportResponse, DatasetDataMapResponse, DatasetProfile, DatasetUploadResponse, SampleDatasetType } from "../../types";
import { Empty, formatNumber, isBusy, Metric } from "./shared";

export function DataAssetsPage(props: {
  busy: string;
  selectedFile: File | null;
  dataset: DatasetUploadResponse | null;
  profile: DatasetProfile | null;
  dataMap: DatasetDataMapResponse | null;
  samples: SampleDatasetType[];
  cleaningPlan: CleaningPlanResponse | null;
  cleaningReport: CleaningReportResponse | null;
  onFileChange: (event: ChangeEvent<HTMLInputElement>) => void;
  onUpload: (event?: FormEvent) => void;
  onUseSample: (sampleType: string) => void;
  onCreateCleaningPlan: () => void;
  onApplyCleaning: () => void;
}) {
  const { busy, selectedFile, dataset, profile, dataMap, samples, cleaningPlan, cleaningReport } = props;
  const previewRows = (profile?.sample_rows || []).map((row, index) => ({ ...row, __rowKey: `sample-${index}` }));
  const previewColumns: TableColumnsType<Record<string, unknown>> = (profile?.columns || []).slice(0, 6).map((column) => ({
    title: column,
    dataIndex: column,
    ellipsis: true,
    width: 140,
    render: (value: unknown) => value === null || value === undefined ? "-" : String(value)
  }));
  const issueColumns: TableColumnsType<NonNullable<CleaningPlanResponse["issues"]>[number]> = [
    { title: "字段", dataIndex: "column", width: 140, render: (value: string | null | undefined, record) => value || record.issue_type },
    { title: "问题", dataIndex: "message", ellipsis: true },
    { title: "影响行数", dataIndex: "affected_count", width: 100 },
    { title: "严重度", dataIndex: "severity", width: 100, render: (value: string) => <Tag color={value === "high" ? "red" : "gold"}>{value}</Tag> },
    { title: "推荐策略", dataIndex: "default_strategy_id", width: 150, render: (value: string) => <Tag>{value}</Tag> }
  ];

  return (
    <div className="content-grid">
      <Card className="operation-card" variant="outlined">
        <div className="card-header">
          <div>
            <h2>数据入口</h2>
            <p>上传 Excel、CSV 或图片表格，也可以选择内置示例数据。</p>
          </div>
        </div>
        <form className="upload-zone upload-zone-feature" onSubmit={props.onUpload}>
          <div className="upload-icon">D</div>
          <div className="upload-copy">
            <strong>{selectedFile?.name || "选择一个数据文件"}</strong>
            <span>支持 Excel、CSV 和图片表格，读取后自动生成画像、字段地图和清洗建议。</span>
          </div>
          <div className="upload-actions">
            <label className="file-picker">
              选择文件
              <input type="file" accept=".csv,.xlsx,.xls,.png,.jpg,.jpeg,.webp" onChange={props.onFileChange} />
            </label>
            <Button type="primary" htmlType="submit" loading={isBusy(busy)}>上传并读取</Button>
          </div>
        </form>
        <div className="sample-list">
          {samples.map((sample) => (
            <button key={sample.sample_type} type="button" onClick={() => props.onUseSample(sample.sample_type)}>
              <strong>{sample.filename}</strong>
              <span>{sample.description}</span>
            </button>
          ))}
        </div>
      </Card>
      <Card className="operation-card" variant="outlined">
        <div className="card-header horizontal">
          <div>
            <h2>数据画像</h2>
            <p>{dataset?.filename || "等待数据集"}</p>
          </div>
          <Tag color="blue">{dataset?.asset_type || dataset?.file_type || "-"}</Tag>
        </div>
        <div className="kpi-grid">
          <Metric label="行数" value={profile ? formatNumber(profile.row_count) : "-"} />
          <Metric label="字段" value={profile ? String(profile.column_count) : "-"} />
          <Metric label="数值字段" value={profile ? String(Object.keys(profile.numeric_summary || {}).length) : "-"} />
        </div>
        <Table
          rowKey="__rowKey"
          className="dense-ant-table"
          size="small"
          columns={previewColumns}
          dataSource={previewRows}
          pagination={false}
          scroll={{ x: 560, y: 220 }}
        />
      </Card>
      <Card className="operation-card" variant="outlined">
        <div className="card-header horizontal">
          <div>
            <h2>数据清洗</h2>
            <p>生成清洗计划后，可一键应用推荐策略。</p>
          </div>
          <Space>
            <Button size="small" disabled={!dataset || isBusy(busy)} onClick={props.onCreateCleaningPlan}>生成计划</Button>
            <Button size="small" type="primary" disabled={!cleaningPlan || isBusy(busy)} onClick={props.onApplyCleaning}>应用推荐</Button>
          </Space>
        </div>
        <Table
          rowKey="issue_id"
          className="dense-ant-table"
          size="small"
          columns={issueColumns}
          dataSource={cleaningPlan?.issues || []}
          pagination={false}
          scroll={{ x: 760 }}
        />
        {cleaningReport ? <p className="notice">{cleaningReport.message}</p> : null}
        {!cleaningPlan ? <Empty text="还没有清洗计划。" /> : null}
      </Card>
      <Card className="operation-card" variant="outlined">
        <div className="card-header">
          <div>
            <h2>数据地图</h2>
            <p>按实体、指标、维度、时间字段理解数据结构。</p>
          </div>
        </div>
        <div className="tag-cloud">
          {[
            ...(dataMap?.data_map?.data_map?.entities || []),
            ...(dataMap?.data_map?.data_map?.metrics || []),
            ...(dataMap?.data_map?.data_map?.dimensions || []),
            ...(dataMap?.data_map?.data_map?.time_dimensions || [])
          ].slice(0, 24).map((item) => <span key={item}>{item}</span>)}
          {!dataMap ? <Empty text="上传数据后自动生成数据地图。" /> : null}
        </div>
      </Card>
    </div>
  );
}
