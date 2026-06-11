import { type FormEvent, useEffect, useMemo, useState } from "react";

import {
  applyCleaningPlan,
  controlWorkflowJob,
  createCleaningPlan,
  createPreflightAssessment,
  createSampleDataset,
  createWorkflowFollowUp,
  createWorkflowJobAsync,
  deleteKnowledgeDocument,
  deleteWorkflowChart,
  deleteWorkflowJob,
  fetchAnalysisResult,
  fetchCleaningReport,
  fetchDatasetDataMap,
  fetchDatasetProfile,
  fetchHealthStatus,
  fetchJsonFile,
  fetchKnowledgeDocuments,
  fetchSampleDatasetTypes,
  fetchWorkflowAgents,
  fetchWorkflowDashboard,
  fetchWorkflowJobStatus,
  fetchWorkflowJobs,
  fetchWorkflowLog,
  generateReport,
  generateWorkflowPptx,
  refreshWorkflowDashboard,
  refineWorkflowChart,
  saveWorkflowDashboard,
  searchKnowledge,
  uploadDataset,
  uploadKnowledgeDocument,
  createPredictionJobAsync,
  fetchPredictionJobStatus,
  fetchPredictionLog
} from "../api";
import type { WorkbenchPageKey } from "../navigation";
import type {
  AnalysisIR,
  AnalysisResult,
  AuthUser,
  CleaningPlanResponse,
  CleaningReportResponse,
  DashboardConfig,
  DatasetDataMapResponse,
  DatasetProfile,
  DatasetUploadResponse,
  ExecutionLogEvent,
  HealthStatus,
  KnowledgeDocument,
  KnowledgeSearchResponse,
  PredictionJobResponse,
  PredictionLogResponse,
  PreflightAssessment,
  ReportGenerateResponse,
  SampleDatasetType,
  WorkflowAgentConsoleResponse,
  WorkflowFollowUpResponse,
  WorkflowJobListItem,
  WorkflowJobResponse,
  WorkflowLogResponse
} from "../types";
import { AgentsConsolePage } from "./workbench/AgentsConsolePage";
import { ChartsPage } from "./workbench/ChartsPage";
import { DashboardPage } from "./workbench/DashboardPage";
import { DataAssetsPage } from "./workbench/DataAssetsPage";
import { KnowledgeBasePage } from "./workbench/KnowledgeBasePage";
import { LogsPage } from "./workbench/LogsPage";
import { OverviewPage } from "./workbench/OverviewPage";
import { PredictionPage } from "./workbench/PredictionPage";
import { ReportsPage } from "./workbench/ReportsPage";
import { WorkflowRunPage } from "./workbench/WorkflowRunPage";

const DEFAULT_GOAL = "请分析这份数据的关键趋势、异常点和可汇报结论，并生成图表、Dashboard、报告和 PPT。";
const SMART_INSIGHT_GOAL = "智能洞察挖掘：系统自动扫描数据，挖掘潜在规律、高价值异常和下一步建议。";

export function WorkbenchPage({
  currentUser,
  activePage,
  onPageChange
}: {
  currentUser?: AuthUser | null;
  activePage: WorkbenchPageKey;
  onPageChange: (page: WorkbenchPageKey) => void;
}) {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [statusMessage, setStatusMessage] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [dataset, setDataset] = useState<DatasetUploadResponse | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [dataMap, setDataMap] = useState<DatasetDataMapResponse | null>(null);
  const [samples, setSamples] = useState<SampleDatasetType[]>([]);
  const [goal, setGoal] = useState(DEFAULT_GOAL);
  const [preflight, setPreflight] = useState<PreflightAssessment | null>(null);
  const [cleaningPlan, setCleaningPlan] = useState<CleaningPlanResponse | null>(null);
  const [cleaningReport, setCleaningReport] = useState<CleaningReportResponse | null>(null);
  const [job, setJob] = useState<WorkflowJobResponse | null>(null);
  const [jobs, setJobs] = useState<WorkflowJobListItem[]>([]);
  const [workflowLog, setWorkflowLog] = useState<WorkflowLogResponse | null>(null);
  const [agents, setAgents] = useState<WorkflowAgentConsoleResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardConfig | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [analysisIr, setAnalysisIr] = useState<AnalysisIR | null>(null);
  const [report, setReport] = useState<ReportGenerateResponse | null>(null);
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDocument[]>([]);
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null);
  const [knowledgeQuery, setKnowledgeQuery] = useState("这份数据适合从哪些业务口径解释？");
  const [knowledgeSearch, setKnowledgeSearch] = useState<KnowledgeSearchResponse | null>(null);
  const [predictionGoal, setPredictionGoal] = useState("如果下个月预算提升 20%，哪些对象的结果最可能变化？");
  const [predictionJob, setPredictionJob] = useState<PredictionJobResponse | null>(null);
  const [predictionLog, setPredictionLog] = useState<PredictionLogResponse | null>(null);
  const [followUpQuestion, setFollowUpQuestion] = useState("为什么这张图里的最高值明显高于其他组？");
  const [followUps, setFollowUps] = useState<WorkflowFollowUpResponse[]>([]);
  const [refineInstruction, setRefineInstruction] = useState("让图表标题更业务化，突出关键差异，并提高标签可读性。");
  const [busy, setBusy] = useState("");

  const chartPaths = useMemo(() => collectChartPaths(job, analysisResult, predictionJob), [job, analysisResult, predictionJob]);
  const events = useMemo(() => mergeEvents(job?.events, workflowLog?.events, predictionJob?.events, predictionLog?.events), [job, workflowLog, predictionJob, predictionLog]);

  useEffect(() => {
    void refreshBootstrap();
  }, []);

  useEffect(() => {
    if (!job?.job_id || isTerminal(job.status)) return;
    const timer = window.setInterval(() => {
      void refreshWorkflow(job.job_id, false);
    }, 2400);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (!predictionJob?.job_id || isTerminal(predictionJob.status)) return;
    const timer = window.setInterval(() => {
      void refreshPrediction(predictionJob.job_id, false);
    }, 2600);
    return () => window.clearInterval(timer);
  }, [predictionJob?.job_id, predictionJob?.status]);

  async function refreshBootstrap() {
    await runBusy("bootstrap", async () => {
      const [healthResult, sampleResult, knowledgeResult, jobResult] = await Promise.all([
        fetchHealthStatus().catch(() => null),
        fetchSampleDatasetTypes().catch(() => ({ samples: [] })),
        fetchKnowledgeDocuments().catch(() => ({ documents: [] })),
        fetchWorkflowJobs().catch(() => ({ jobs: [] }))
      ]);
      setHealth(healthResult);
      setSamples(sampleResult.samples);
      setKnowledgeDocs(knowledgeResult.documents);
      setJobs(jobResult.jobs);
      await restoreLatestDataset(jobResult.jobs);
    });
  }

  async function restoreLatestDataset(jobItems: WorkflowJobListItem[]) {
    const latestDatasetJob = jobItems.find((item) => item.dataset_id);
    if (!latestDatasetJob?.dataset_id) return;

    const restoredDataset: DatasetUploadResponse = {
      dataset_id: latestDatasetJob.dataset_id,
      filename: latestDatasetJob.dataset_filename || latestDatasetJob.dataset_id,
      file_type: latestDatasetJob.file_type || "csv",
      file_path: "",
      asset_type: latestDatasetJob.asset_type === "image" ? "image" : "tabular"
    };

    try {
      const [nextProfile, nextDataMap] = await Promise.all([
        fetchDatasetProfile(restoredDataset.dataset_id),
        fetchDatasetDataMap(restoredDataset.dataset_id).catch(() => null)
      ]);
      setDataset(restoredDataset);
      setProfile(nextProfile);
      setDataMap(nextDataMap);
    } catch {
      setDataset(null);
      setProfile(null);
      setDataMap(null);
    }
  }

  async function handleUpload(event?: FormEvent) {
    event?.preventDefault();
    if (!selectedFile) {
      setStatusMessage("请先选择一个 Excel、CSV 或图片文件。");
      return;
    }
    await runBusy("upload", async () => {
      const uploaded = await uploadDataset(selectedFile);
      await applyDataset(uploaded);
      setStatusMessage(`已上传 ${uploaded.filename}，并完成数据画像读取。`);
      onPageChange("data");
    });
  }

  async function handleUseSample(sampleType: string) {
    await runBusy(`sample-${sampleType}`, async () => {
      const sample = await createSampleDataset(sampleType);
      setGoal(sample.recommended_goal || sample.suggested_goals?.[0] || DEFAULT_GOAL);
      await applyDataset(sample);
      setStatusMessage(`已载入示例数据：${sample.description}`);
      onPageChange("data");
    });
  }

  async function applyDataset(nextDataset: DatasetUploadResponse) {
    setDataset(nextDataset);
    const [nextProfile, nextDataMap] = await Promise.all([
      fetchDatasetProfile(nextDataset.dataset_id),
      fetchDatasetDataMap(nextDataset.dataset_id).catch(() => null)
    ]);
    setProfile(nextProfile);
    setDataMap(nextDataMap);
    setPreflight(null);
    setCleaningPlan(null);
    setCleaningReport(null);
    setAnalysisResult(null);
    setAnalysisIr(null);
    setReport(null);
  }

  async function handlePreflight() {
    if (!dataset) {
      setStatusMessage("请先上传数据或选择示例数据。");
      return;
    }
    await runBusy("preflight", async () => {
      const result = await createPreflightAssessment(dataset.dataset_id, goal);
      setPreflight(result);
      if (result.optimized_goal) setGoal(result.optimized_goal);
      setStatusMessage("预检完成：已识别字段、任务清晰度和下一步建议。");
      onPageChange("workflow");
    });
  }

  async function handleCreateCleaningPlan() {
    if (!dataset) {
      setStatusMessage("请先准备数据集。");
      return;
    }
    await runBusy("cleaning-plan", async () => {
      const plan = await createCleaningPlan(dataset.dataset_id);
      setCleaningPlan(plan);
      setStatusMessage(plan.message || "已生成数据清洗计划。");
      onPageChange("data");
    });
  }

  async function handleApplyCleaning() {
    if (!dataset || !cleaningPlan) {
      setStatusMessage("请先生成清洗计划。");
      return;
    }
    await runBusy("cleaning-apply", async () => {
      const reportResult = await applyCleaningPlan(dataset.dataset_id, cleaningPlan.recommended_strategy_ids);
      const fetched = await fetchCleaningReport(dataset.dataset_id).catch(() => reportResult);
      setCleaningReport(fetched);
      setStatusMessage(fetched.message || "已应用推荐清洗策略。");
    });
  }

  async function handleRunWorkflow(insightMode = false) {
    if (!dataset) {
      setStatusMessage("请先准备数据集。");
      return;
    }
    await runBusy(insightMode ? "workflow-insight" : "workflow-run", async () => {
      const nextJob = await createWorkflowJobAsync(dataset.dataset_id, insightMode ? SMART_INSIGHT_GOAL : goal, 3, insightMode);
      setJob(nextJob);
      setStatusMessage("AI 工作流已启动，系统会自动刷新 Agent 过程和产物。");
      onPageChange("workflow");
      await refreshWorkflow(nextJob.job_id);
      await refreshJobs();
    });
  }

  async function refreshWorkflow(jobId: string, loud = true) {
    const nextJob = await fetchWorkflowJobStatus(jobId);
    setJob(nextJob);
    const loaders = [
      fetchWorkflowLog(jobId).then(setWorkflowLog).catch(() => undefined),
      fetchWorkflowAgents(jobId).then(setAgents).catch(() => undefined),
      fetchWorkflowDashboard(jobId).then((response) => setDashboard(response.dashboard)).catch(() => undefined)
    ];
    if (nextJob.final_result_path) {
      loaders.push(fetchAnalysisResult(nextJob.final_result_path).then(setAnalysisResult).catch(() => undefined));
    }
    if (nextJob.analysis_ir_path) {
      loaders.push(fetchJsonFile<AnalysisIR>(nextJob.analysis_ir_path).then(setAnalysisIr).catch(() => undefined));
    }
    await Promise.all(loaders);
    if (loud) setStatusMessage(`已刷新任务 ${shortId(jobId)}。`);
  }

  async function refreshJobs() {
    const result = await fetchWorkflowJobs();
    setJobs(result.jobs);
  }

  async function handleOpenJob(jobId: string) {
    await runBusy(`job-${jobId}`, async () => {
      await refreshWorkflow(jobId);
      onPageChange("workflow");
    });
  }

  async function handleControl(action: string) {
    if (!job?.job_id) return;
    await runBusy(`control-${action}`, async () => {
      const result = await controlWorkflowJob(job.job_id, action);
      setStatusMessage(result.message);
      await refreshWorkflow(job.job_id);
    });
  }

  async function handleDeleteCurrentJob() {
    if (!job?.job_id) return;
    await runBusy("delete-job", async () => {
      await deleteWorkflowJob(job.job_id);
      setJob(null);
      setWorkflowLog(null);
      setAgents(null);
      setDashboard(null);
      setAnalysisResult(null);
      await refreshJobs();
      setStatusMessage("当前任务已删除。");
    });
  }

  async function handleRefreshDashboard() {
    if (!job?.job_id) return;
    await runBusy("dashboard-refresh", async () => {
      const response = await refreshWorkflowDashboard(job.job_id);
      setDashboard(response.dashboard);
      setStatusMessage(response.message);
    });
  }

  async function handleSaveDashboard() {
    if (!job?.job_id || !dashboard) return;
    await runBusy("dashboard-save", async () => {
      const response = await saveWorkflowDashboard(job.job_id, dashboard);
      setDashboard(response.dashboard);
      setStatusMessage(response.message);
    });
  }

  async function handleRefineChart(chartPath: string) {
    if (!job?.job_id) return;
    await runBusy(`refine-${chartPath}`, async () => {
      const result = await refineWorkflowChart(job.job_id, chartPath, refineInstruction);
      setStatusMessage(result.message);
      await refreshWorkflow(job.job_id);
    });
  }

  async function handleDeleteChart(chartPath: string) {
    if (!job?.job_id) return;
    await runBusy(`delete-chart-${chartPath}`, async () => {
      await deleteWorkflowChart(job.job_id, chartPath);
      setStatusMessage("图表已删除。");
      await refreshWorkflow(job.job_id);
    });
  }

  async function handleFollowUp(event: FormEvent) {
    event.preventDefault();
    if (!job?.job_id || !followUpQuestion.trim()) return;
    await runBusy("follow-up", async () => {
      const result = await createWorkflowFollowUp(job.job_id, followUpQuestion);
      setFollowUps((current) => [result, ...current]);
      setStatusMessage("追问答案已生成。");
    });
  }

  async function handleGenerateReport() {
    if (!job?.final_result_path && !analysisResult) {
      setStatusMessage("需要成功的分析结果后才能生成报告。");
      return;
    }
    await runBusy("report", async () => {
      if (job?.job_id) {
        const ppt = await generateWorkflowPptx(job.job_id);
        setStatusMessage(ppt.message || "PPT 已生成。");
        await refreshWorkflow(job.job_id);
      }
      if (job?.final_result_path) {
        const generated = await generateReport(job.final_result_path, chartPaths);
        setReport(generated);
      }
      onPageChange("reports");
    });
  }

  async function handleKnowledgeUpload(event: FormEvent) {
    event.preventDefault();
    if (!knowledgeFile) {
      setStatusMessage("请先选择知识文档。");
      return;
    }
    await runBusy("knowledge-upload", async () => {
      await uploadKnowledgeDocument(knowledgeFile);
      const result = await fetchKnowledgeDocuments();
      setKnowledgeDocs(result.documents);
      setKnowledgeFile(null);
      setStatusMessage("知识文档已上传并索引。");
    });
  }

  async function handleKnowledgeSearch(event: FormEvent) {
    event.preventDefault();
    await runBusy("knowledge-search", async () => {
      const result = await searchKnowledge(knowledgeQuery, 5);
      setKnowledgeSearch(result);
      setStatusMessage(result.message);
    });
  }

  async function handleKnowledgeDelete(docId: string) {
    await runBusy(`knowledge-delete-${docId}`, async () => {
      await deleteKnowledgeDocument(docId);
      const result = await fetchKnowledgeDocuments();
      setKnowledgeDocs(result.documents);
      setStatusMessage("知识文档已删除。");
    });
  }

  async function handleRunPrediction() {
    if (!dataset) {
      setStatusMessage("请先准备数据集。");
      return;
    }
    await runBusy("prediction", async () => {
      const result = await createPredictionJobAsync(dataset.dataset_id, predictionGoal);
      setPredictionJob(result);
      setStatusMessage("预测分析任务已启动。");
      onPageChange("prediction");
      await refreshPrediction(result.job_id);
    });
  }

  async function refreshPrediction(jobId: string, loud = true) {
    const [nextJob, nextLog] = await Promise.all([
      fetchPredictionJobStatus(jobId),
      fetchPredictionLog(jobId).catch(() => null)
    ]);
    setPredictionJob(nextJob);
    setPredictionLog(nextLog);
    if (loud) setStatusMessage(`已刷新预测任务 ${shortId(jobId)}。`);
  }

  async function runBusy(name: string, action: () => Promise<void>) {
    setBusy(name);
    try {
      await action();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "操作未完成，请稍后重试。");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="workspace">
      {activePage === "overview" ? (
        <OverviewPage
          health={health}
          jobs={jobs}
          chartPaths={chartPaths}
          knowledgeCount={knowledgeDocs.length}
          onOpenJob={handleOpenJob}
        />
      ) : null}

      {activePage === "data" ? (
        <DataAssetsPage
          busy={busy}
          selectedFile={selectedFile}
          dataset={dataset}
          profile={profile}
          dataMap={dataMap}
          samples={samples}
          cleaningPlan={cleaningPlan}
          cleaningReport={cleaningReport}
          onFileChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
          onUpload={handleUpload}
          onUseSample={handleUseSample}
          onCreateCleaningPlan={handleCreateCleaningPlan}
          onApplyCleaning={handleApplyCleaning}
        />
      ) : null}

      {activePage === "workflow" ? (
        <WorkflowRunPage
          busy={busy}
          dataset={dataset}
          goal={goal}
          preflight={preflight}
          job={job}
          analysisIr={analysisIr}
          events={events}
          onGoalChange={setGoal}
          onPreflight={handlePreflight}
          onRunWorkflow={() => handleRunWorkflow(false)}
          onRunInsight={() => handleRunWorkflow(true)}
          onControl={handleControl}
          onDeleteJob={handleDeleteCurrentJob}
        />
      ) : null}

      {activePage === "agents" ? <AgentsConsolePage agents={agents} currentUser={currentUser} /> : null}

      {activePage === "charts" ? (
        <ChartsPage
          chartPaths={chartPaths}
          refineInstruction={refineInstruction}
          busy={busy}
          onRefineInstructionChange={setRefineInstruction}
          onRefine={handleRefineChart}
          onDelete={handleDeleteChart}
          followUpQuestion={followUpQuestion}
          followUps={followUps}
          onFollowUpQuestionChange={setFollowUpQuestion}
          onFollowUp={handleFollowUp}
        />
      ) : null}

      {activePage === "dashboard" ? (
        <DashboardPage dashboard={dashboard} busy={busy} onRefresh={handleRefreshDashboard} onSave={handleSaveDashboard} />
      ) : null}

      {activePage === "knowledge" ? (
        <KnowledgeBasePage
          documents={knowledgeDocs}
          file={knowledgeFile}
          query={knowledgeQuery}
          search={knowledgeSearch}
          busy={busy}
          onFileChange={(event) => setKnowledgeFile(event.target.files?.[0] ?? null)}
          onQueryChange={setKnowledgeQuery}
          onUpload={handleKnowledgeUpload}
          onSearch={handleKnowledgeSearch}
          onDelete={handleKnowledgeDelete}
        />
      ) : null}

      {activePage === "prediction" ? (
        <PredictionPage
          goal={predictionGoal}
          job={predictionJob}
          log={predictionLog}
          busy={busy}
          onGoalChange={setPredictionGoal}
          onRun={handleRunPrediction}
          onRefresh={() => predictionJob?.job_id && refreshPrediction(predictionJob.job_id)}
        />
      ) : null}

      {activePage === "reports" ? (
        <ReportsPage job={job} report={report} chartPaths={chartPaths} busy={busy} onGenerate={handleGenerateReport} />
      ) : null}

      {activePage === "logs" ? <LogsPage workflowLog={workflowLog} predictionLog={predictionLog} events={events} /> : null}
    </div>
  );
}

function collectChartPaths(job: WorkflowJobResponse | null, analysisResult: AnalysisResult | null, predictionJob: PredictionJobResponse | null): string[] {
  const paths = new Set<string>();
  for (const path of job?.chart_paths || []) paths.add(path);
  for (const path of predictionJob?.chart_paths || []) paths.add(path);
  for (const chart of analysisResult?.charts || []) {
    if (typeof chart === "string") {
      paths.add(chart);
    } else if (chart && typeof chart === "object") {
      const maybePath = (chart as Record<string, unknown>).path || (chart as Record<string, unknown>).chart_path;
      if (typeof maybePath === "string") paths.add(maybePath);
    }
  }
  return Array.from(paths);
}

function mergeEvents(...groups: Array<ExecutionLogEvent[] | undefined>): ExecutionLogEvent[] {
  return groups
    .flatMap((group) => group || [])
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
}

function isTerminal(status: string): boolean {
  return ["success", "failed", "cancelled"].includes(status);
}

function shortId(value: string): string {
  return value.length > 8 ? value.slice(0, 8) : value;
}
