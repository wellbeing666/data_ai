
import { type DragEvent, useEffect, useMemo, useState } from "react";

import {
  createAutoRepairAnalysisJobAsync,
  createPredictionJobAsync,
  createWorkflowJobAsync,
  deleteWorkflowChart,
  fetchAnalysisResult,
  fetchAutoRepairAnalysisJobStatus,
  fetchDatasetProfile,
  fetchExecutionLog,
  fetchHealthStatus,
  fetchJsonFile,
  fetchKnowledgeDocuments,
  fetchPredictionJobStatus,
  fetchPredictionLog,
  fetchWorkflowJobs,
  fetchWorkflowJobStatus,
  fetchWorkflowLog,
  generateReport,
  deleteKnowledgeDocument,
  searchKnowledge,
  toStorageUrl,
  uploadKnowledgeDocument,
  uploadDataset
} from "./api";
import type {
  AnalysisResult,
  AutoRepairAnalysisJobResponse,
  AutoRepairAttemptResult,
  DatasetProfile,
  DatasetUploadResponse,
  ExecutionAttemptLog,
  ExecutionLog,
  ExecutionLogEvent,
  ExplanationResult,
  HealthStatus,
  KnowledgeDocument,
  KnowledgeSearchResponse,
  PredictionExplanationResult,
  PredictionJobResponse,
  PredictionLogResponse,
  PredictionResult,
  ReportGenerateResponse,
  ValidationAttemptLog,
  VisualParseResult,
  WorkflowJobListItem,
  WorkflowJobResponse,
  WorkflowLogResponse
} from "./types";

type AnyRecord = Record<string, unknown>;
type PageKey = "setup" | "knowledge" | "prediction" | "process" | "charts" | "insights" | "logs";

interface StepView {
  key: string;
  title: string;
  stageNames: string[];
  status: "pending" | "active" | "done" | "failed";
  summary: string;
}

type ArtifactKind =
  | "visual"
  | "rag"
  | "controller"
  | "understanding"
  | "analysis"
  | "hypothesis"
  | "prediction_plan"
  | "code"
  | "execution"
  | "validation"
  | "explanation"
  | "generic";

interface AgentCardView extends StepView {
  agentName: string;
  inputSource: string;
  action: string;
  evidence: string[];
  output: string;
  artifactKind: ArtifactKind;
  artifactLabel?: string;
  artifactPath?: string | null;
  raw?: unknown;
}

interface AttemptProgressView {
  attempt: number;
  codeStatus?: string;
  safetyStatus?: string;
  sandboxStatus?: string;
  validationStatus?: string;
  repairStatus?: string;
  attemptResult?: AutoRepairAttemptResult;
  execution?: ExecutionAttemptLog;
  validation?: ValidationAttemptLog;
}

const emptyExplanation: ExplanationResult = {
  summary: "",
  key_findings: [],
  chart_explanations: [],
  recommendations: [],
  limitations: [],
  ppt_outline: []
};

const emptyPredictionExplanation: PredictionExplanationResult = {
  summary: "",
  key_findings: [],
  top_impacted_entities: [],
  recommendations: [],
  limitations: [],
  ppt_outline: []
};

const terminalStatuses = new Set(["success", "failed"]);
const analysisFileExtensions = new Set(["csv", "xlsx", "xls", "png", "jpg", "jpeg", "webp"]);

function isSupportedAnalysisFile(file: File): boolean {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return analysisFileExtensions.has(extension);
}

export default function App() {
  const [activePage, setActivePage] = useState<PageKey>("setup");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isAnalysisFileDragActive, setIsAnalysisFileDragActive] = useState(false);
  const [userGoal, setUserGoal] = useState("把这批 Excel 成绩按班级统计并生成图表");
  const [uploadInfo, setUploadInfo] = useState<DatasetUploadResponse | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [job, setJob] = useState<WorkflowJobResponse | null>(null);
  const [executionLog, setExecutionLog] = useState<WorkflowLogResponse | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [controllerPlan, setControllerPlan] = useState<AnyRecord | null>(null);
  const [ragRetrieval, setRagRetrieval] = useState<AnyRecord | null>(null);
  const [dataUnderstanding, setDataUnderstanding] = useState<AnyRecord | null>(null);
  const [analysisPlan, setAnalysisPlan] = useState<AnyRecord | null>(null);
  const [visualParseResult, setVisualParseResult] = useState<VisualParseResult | null>(null);
  const [explanation, setExplanation] = useState<ExplanationResult>(emptyExplanation);
  const [report, setReport] = useState<ReportGenerateResponse | null>(null);
  const [reportGeneratedFor, setReportGeneratedFor] = useState("");
  const [status, setStatus] = useState<"idle" | "uploading" | "running" | "success" | "failed">("idle");
  const [message, setMessage] = useState("");
  const [knowledgeDocs, setKnowledgeDocs] = useState<KnowledgeDocument[]>([]);
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null);
  const [knowledgeQuery, setKnowledgeQuery] = useState("成绩分析的及格率和优秀率口径");
  const [knowledgeSearch, setKnowledgeSearch] = useState<KnowledgeSearchResponse | null>(null);
  const [knowledgeMessage, setKnowledgeMessage] = useState("");
  const [predictionFile, setPredictionFile] = useState<File | null>(null);
  const [predictionGoal, setPredictionGoal] = useState("如果下个月营销预算增加 20%，哪些商品的销量最可能提升？");
  const [predictionJob, setPredictionJob] = useState<WorkflowJobResponse | null>(null);
  const [predictionLog, setPredictionLog] = useState<WorkflowLogResponse | null>(null);
  const [predictionResult, setPredictionResult] = useState<PredictionResult | null>(null);
  const [predictionExplanation, setPredictionExplanation] = useState<PredictionExplanationResult>(emptyPredictionExplanation);
  const [hypothesisPlan, setHypothesisPlan] = useState<AnyRecord | null>(null);
  const [predictionPlan, setPredictionPlan] = useState<AnyRecord | null>(null);
  const [predictionStatus, setPredictionStatus] = useState<"idle" | "uploading" | "running" | "success" | "failed">("idle");
  const [predictionMessage, setPredictionMessage] = useState("");
  const [hiddenChartPaths, setHiddenChartPaths] = useState<string[]>([]);
  const [chartPreviewPath, setChartPreviewPath] = useState<string | null>(null);
  const [chartMessage, setChartMessage] = useState("");
  const [workflowHistory, setWorkflowHistory] = useState<WorkflowJobListItem[]>([]);
  const [historyMessage, setHistoryMessage] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);

  useEffect(() => {
    fetchHealthStatus()
      .then(setHealth)
      .catch(() => {
        setHealth({
          status: "unknown",
          llm_mode: "mock/fallback",
          deepseek_configured: false,
          doubao_configured: false,
          message: "无法读取 DeepSeek 配置状态。"
        });
      });
  }, []);

  useEffect(() => {
    refreshKnowledgeDocuments();
    refreshWorkflowHistory();
  }, []);

  useEffect(() => {
    if (!job?.job_id || terminalStatuses.has(job.status)) {
      return;
    }

    let cancelled = false;
    const tick = async () => {
      try {
        const latest = await fetchWorkflowJobStatus(job.job_id);
        if (!cancelled) {
          await applyJobUpdate(latest);
        }
      } catch (error) {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "刷新任务状态失败。");
        }
      }
    };

    tick();
    const timer = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [job?.job_id, job?.status]);

  useEffect(() => {
    if (!predictionJob?.job_id || predictionJob.job_id === job?.job_id || terminalStatuses.has(predictionJob.status)) {
      return;
    }

    let cancelled = false;
    const tick = async () => {
      try {
        const latest = await fetchWorkflowJobStatus(predictionJob.job_id);
        if (!cancelled) {
          await applyPredictionJobUpdate(latest);
        }
      } catch (error) {
        if (!cancelled) {
          setPredictionMessage(error instanceof Error ? error.message : "刷新预测任务状态失败。");
        }
      }
    };

    tick();
    const timer = window.setInterval(tick, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [predictionJob?.job_id, predictionJob?.status]);

  useEffect(() => {
    if (
      job?.status !== "success" ||
      !job.final_result_path ||
      !analysisResult ||
      reportGeneratedFor === job.job_id
    ) {
      return;
    }

    const chartPaths = getChartPaths(analysisResult, job);
    generateReport(job.final_result_path, chartPaths)
      .then((reportData) => {
        setReport(reportData);
        setReportGeneratedFor(job.job_id);
      })
      .catch(() => {
        setReportGeneratedFor(job.job_id);
      });
  }, [analysisResult, job, reportGeneratedFor]);

  const isFallbackMode = !health?.deepseek_configured || health.llm_mode !== "deepseek";
  const isPredictionWorkflow = job?.workflow_type === "what_if_prediction" || job?.task_type === "what_if_prediction";
  const events = mergeWorkflowEvents(job?.events, executionLog?.events);
  const hiddenChartPathSet = useMemo(() => new Set(hiddenChartPaths), [hiddenChartPaths]);
  const chartPaths = (isPredictionWorkflow
    ? getChartPaths(predictionResult, job)
    : getChartPaths(analysisResult, job, report?.chart_paths)
  ).filter((chartPath) => !hiddenChartPathSet.has(chartPath));

  const steps = useMemo(
    () => {
      if (isPredictionWorkflow) {
        return buildPredictionSteps({
          job,
          log: executionLog,
          controllerPlan,
          ragRetrieval,
          visualParseResult,
          hypothesisPlan,
          predictionPlan,
          predictionResult,
          explanation: predictionExplanation,
          events
        });
      }
      return buildAgentSteps({
        job,
        controllerPlan,
        ragRetrieval,
        visualParseResult,
        dataUnderstanding,
        analysisPlan,
        executionLog,
        explanation,
        events
      });
    },
    [
      job,
      isPredictionWorkflow,
      executionLog,
      hypothesisPlan,
      predictionPlan,
      predictionResult,
      predictionExplanation,
      events,
      controllerPlan,
      ragRetrieval,
      visualParseResult,
      dataUnderstanding,
      analysisPlan,
      explanation
    ]
  );

  async function refreshKnowledgeDocuments() {
    try {
      const response = await fetchKnowledgeDocuments();
      setKnowledgeDocs(response.documents);
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "读取知识库失败。");
    }
  }

  async function refreshWorkflowHistory() {
    setLoadingHistory(true);
    try {
      const response = await fetchWorkflowJobs(30);
      setWorkflowHistory(response.jobs);
      setHistoryMessage("");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "读取历史分析列表失败。");
    } finally {
      setLoadingHistory(false);
    }
  }

  async function handleOpenHistoryJob(jobId: string) {
    setHistoryMessage("正在载入历史分析结果。");
    const historyItem = workflowHistory.find((item) => item.job_id === jobId) ?? null;
    setJob(null);
    setExecutionLog(null);
    setAnalysisResult(null);
    setControllerPlan(null);
    setRagRetrieval(null);
    setDataUnderstanding(null);
    setAnalysisPlan(null);
    setVisualParseResult(null);
    setExplanation(emptyExplanation);
    setReport(null);
    setReportGeneratedFor("");
    setPredictionJob(null);
    setPredictionLog(null);
    setPredictionResult(null);
    setPredictionExplanation(emptyPredictionExplanation);
    setHypothesisPlan(null);
    setPredictionPlan(null);
    setHiddenChartPaths([]);
    setChartPreviewPath(null);
    setChartMessage("");
    if (historyItem?.dataset_id) {
      setUploadInfo({
        dataset_id: historyItem.dataset_id,
        filename: historyItem.dataset_filename || "历史数据集",
        file_type: historyItem.file_type || "",
        file_path: "",
        asset_type: historyItem.asset_type === "image" ? "image" : "tabular",
        preview_url: null
      });
    }
    try {
      const latest = await fetchWorkflowJobStatus(jobId);
      setStatus(statusFromJob(latest.status));
      await applyJobUpdate(latest);
      setActivePage("process");
      setHistoryMessage("已载入历史分析结果。");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "载入历史分析失败。");
    }
  }

  async function handleKnowledgeUpload() {
    if (!knowledgeFile) {
      setKnowledgeMessage("请先选择 .txt 或 .md 知识文档。");
      return;
    }
    try {
      const document = await uploadKnowledgeDocument(knowledgeFile);
      setKnowledgeMessage(
        document.indexed
          ? "知识文档已上传并写入向量库。"
          : `文档已保存，但 RAG 暂不可用：${document.index_error ?? "未完成向量索引"}`
      );
      setKnowledgeFile(null);
      await refreshKnowledgeDocuments();
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "上传知识文档失败。");
    }
  }

  async function handleKnowledgeSearch() {
    if (!knowledgeQuery.trim()) {
      setKnowledgeMessage("请输入检索问题。");
      return;
    }
    try {
      const result = await searchKnowledge(knowledgeQuery, 5);
      setKnowledgeSearch(result);
      setKnowledgeMessage(result.message);
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "知识库检索失败。");
    }
  }

  async function handleKnowledgeDelete(docId: string) {
    try {
      await deleteKnowledgeDocument(docId);
      setKnowledgeMessage("知识文档已删除。");
      await refreshKnowledgeDocuments();
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "删除知识文档失败。");
    }
  }

  async function handleRunPrediction() {
    if (!predictionFile) {
      setPredictionMessage("请先选择 CSV / Excel 文件。");
      return;
    }
    if (!predictionGoal.trim()) {
      setPredictionMessage("请输入假设性预测问题。");
      return;
    }

    setPredictionStatus("uploading");
    setActivePage("prediction");
    setPredictionMessage("正在上传数据并创建情景预测任务。");
    setPredictionJob(null);
    setPredictionLog(null);
    setPredictionResult(null);
    setPredictionExplanation(emptyPredictionExplanation);
    setHypothesisPlan(null);
    setPredictionPlan(null);
    setHiddenChartPaths([]);
    setChartPreviewPath(null);
    setChartMessage("");

    try {
      const uploaded = await uploadDataset(predictionFile);
      setUploadInfo(uploaded);
      const datasetProfile = await fetchDatasetProfile(uploaded.dataset_id);
      setProfile(datasetProfile);
      setPredictionStatus("running");
      setPredictionMessage("情景预测任务已启动，状态将实时刷新。");
      const createdJob = await createWorkflowJobAsync(uploaded.dataset_id, predictionGoal, 3);
      await applyPredictionJobUpdate(createdJob);
    } catch (error) {
      setPredictionStatus("failed");
      setPredictionMessage(error instanceof Error ? error.message : "情景预测任务启动失败。");
    }
  }

  async function applyPredictionJobUpdate(nextJob: WorkflowJobResponse) {
    setPredictionJob(nextJob);
    setPredictionStatus(statusFromJob(nextJob.status));
    setPredictionMessage(predictionMessageFromJob(nextJob));

    await Promise.allSettled([
      refreshPredictionLog(nextJob.job_id),
      refreshJsonPath(nextJob.hypothesis_plan_path, setHypothesisPlan),
      refreshJsonPath(nextJob.prediction_plan_path, setPredictionPlan),
      refreshPredictionResult(nextJob.final_prediction_result_path),
      refreshPredictionExplanation(nextJob.prediction_explanation_path)
    ]);

    if (terminalStatuses.has(nextJob.status)) {
      void refreshWorkflowHistory();
    }
  }

  async function refreshPredictionLog(jobId: string) {
    try {
      setPredictionLog(await fetchWorkflowLog(jobId));
    } catch {
      // The prediction log appears shortly after the background workflow writes progress.
    }
  }

  async function refreshPredictionResult(path: string | null | undefined) {
    if (!path) {
      return;
    }
    try {
      setPredictionResult(await fetchJsonFile<PredictionResult>(path));
    } catch {
      // Ignore transient polling reads.
    }
  }

  async function refreshPredictionExplanation(path: string | null | undefined) {
    if (!path) {
      return;
    }
    try {
      setPredictionExplanation(await fetchJsonFile<PredictionExplanationResult>(path));
    } catch {
      // Ignore transient polling reads.
    }
  }

  function handleAnalysisFileDragEnter(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setIsAnalysisFileDragActive(true);
  }

  function handleAnalysisFileDragOver(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "copy";
    setIsAnalysisFileDragActive(true);
  }

  function handleAnalysisFileDragLeave(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();

    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && event.currentTarget.contains(nextTarget)) {
      return;
    }

    setIsAnalysisFileDragActive(false);
  }

  function handleAnalysisFileDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    event.stopPropagation();
    setIsAnalysisFileDragActive(false);

    const file = event.dataTransfer.files.item(0);
    if (!file) {
      return;
    }

    if (!isSupportedAnalysisFile(file)) {
      setSelectedFile(null);
      setMessage("仅支持 CSV、XLSX、XLS、PNG、JPG、JPEG、WEBP 文件。");
      return;
    }

    setSelectedFile(file);
  }

  async function handleRunAnalysis() {
    if (!selectedFile) {
      setMessage("请先选择 CSV / Excel 文件或图片。");
      return;
    }
    if (!userGoal.trim()) {
      setMessage("请输入自然语言分析目标。");
      return;
    }

    setStatus("uploading");
    setActivePage("process");
    setMessage("正在上传数据并创建分析任务。");
    setJob(null);
    setExecutionLog(null);
    setAnalysisResult(null);
    setControllerPlan(null);
    setRagRetrieval(null);
    setDataUnderstanding(null);
    setAnalysisPlan(null);
    setVisualParseResult(null);
    setExplanation(emptyExplanation);
    setReport(null);
    setReportGeneratedFor("");
    setPredictionJob(null);
    setPredictionLog(null);
    setPredictionResult(null);
    setPredictionExplanation(emptyPredictionExplanation);
    setHypothesisPlan(null);
    setPredictionPlan(null);
    setPredictionStatus("idle");
    setPredictionMessage("");
    setHiddenChartPaths([]);
    setChartPreviewPath(null);
    setChartMessage("");

    try {
      const uploaded = await uploadDataset(selectedFile);
      setUploadInfo(uploaded);

      if (uploaded.asset_type === "image") {
        setProfile(null);
      } else {
        const datasetProfile = await fetchDatasetProfile(uploaded.dataset_id);
        setProfile(datasetProfile);
      }

      setStatus("running");
      setMessage("任务已启动，Agent 状态将实时刷新。");
      const createdJob = await createWorkflowJobAsync(uploaded.dataset_id, userGoal, 3);
      await applyJobUpdate(createdJob);
    } catch (error) {
      setStatus("failed");
      setMessage(error instanceof Error ? error.message : "分析任务启动失败。");
    }
  }

  async function applyJobUpdate(nextJob: WorkflowJobResponse) {
    setJob(nextJob);
    setStatus(statusFromJob(nextJob.status));
    setMessage(messageFromJob(nextJob));
    const predictionWorkflow = nextJob.workflow_type === "what_if_prediction" || nextJob.task_type === "what_if_prediction";
    if (predictionWorkflow) {
      setPredictionJob(nextJob);
      setPredictionStatus(statusFromJob(nextJob.status));
      setPredictionMessage(predictionMessageFromJob(nextJob));
    }

    await Promise.allSettled([
      refreshExecutionLog(nextJob.job_id),
      refreshJsonPath(nextJob.controller_plan_path, setControllerPlan),
      refreshJsonPath(nextJob.rag_retrieval_path, setRagRetrieval),
      refreshJsonPath(nextJob.visual_parse_result_path, setVisualParseResult),
      refreshJsonPath(nextJob.data_understanding_path, setDataUnderstanding),
      refreshJsonPath(nextJob.dataset_profile_path, setProfile),
      refreshJsonPath(nextJob.analysis_plan_path, setAnalysisPlan),
      refreshAnalysisResult(nextJob.final_result_path),
      refreshExplanation(nextJob.explanation_path),
      refreshJsonPath(nextJob.hypothesis_plan_path, setHypothesisPlan),
      refreshJsonPath(nextJob.prediction_plan_path, setPredictionPlan),
      refreshPredictionResult(nextJob.final_prediction_result_path),
      refreshPredictionExplanation(nextJob.prediction_explanation_path)
    ]);

    if (terminalStatuses.has(nextJob.status)) {
      void refreshWorkflowHistory();
    }
  }

  async function refreshExecutionLog(jobId: string) {
    try {
      setExecutionLog(await fetchWorkflowLog(jobId));
    } catch {
      // The log file appears shortly after the background workflow writes progress.
    }
  }

  async function refreshJsonPath<T>(path: string | null | undefined, setter: (value: T) => void) {
    if (!path) {
      return;
    }
    try {
      setter(await fetchJsonFile<T>(path));
    } catch {
      // A status update may arrive a few milliseconds before the static file is ready.
    }
  }

  async function refreshAnalysisResult(path: string | null | undefined) {
    if (!path) {
      return;
    }
    try {
      setAnalysisResult(await fetchAnalysisResult(path));
    } catch {
      // Ignore transient polling reads.
    }
  }

  async function refreshExplanation(path: string | null | undefined) {
    if (!path) {
      return;
    }
    try {
      setExplanation(await fetchJsonFile<ExplanationResult>(path));
    } catch {
      // Ignore transient polling reads.
    }
  }

  async function handleDeleteChart(chartPath: string) {
    setChartMessage("");
    if (!job?.job_id) {
      setHiddenChartPaths((current: string[]) => Array.from(new Set([...current, chartPath])));
      setChartPreviewPath((current: string | null) => (current === chartPath ? null : current));
      setChartMessage("图表已从当前页面移除。");
      return;
    }

    try {
      await deleteWorkflowChart(job.job_id, chartPath);
      setHiddenChartPaths((current: string[]) => Array.from(new Set([...current, chartPath])));
      setChartPreviewPath((current: string | null) => (current === chartPath ? null : current));
      setChartMessage("图表已删除。");
      const latest = await fetchWorkflowJobStatus(job.job_id);
      await applyJobUpdate(latest);
    } catch (error) {
      setChartMessage(error instanceof Error ? error.message : "删除图表失败。");
    }
  }

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AI Native Data Analysis Workbench</p>
          <h1>DeepSeek 多 Agent 数据分析工作台</h1>
        </div>
        <span className={`status-pill status-${status}`}>{statusLabel(status)}</span>
      </header>

      <section className="layout-grid">
        <aside className="left-panel">
          <section className="panel">
            <div className="panel-header">
              <h2>任务配置</h2>
              <span>CSV / XLSX / XLS / 图片</span>
            </div>
            <label
              className={`upload-zone ${isAnalysisFileDragActive ? "drag-active" : ""}`}
              onDragEnter={handleAnalysisFileDragEnter}
              onDragOver={handleAnalysisFileDragOver}
              onDragLeave={handleAnalysisFileDragLeave}
              onDrop={handleAnalysisFileDrop}
            >
              <input
                type="file"
                accept=".csv,.xlsx,.xls,.png,.jpg,.jpeg,.webp"
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
              />
              <strong>{selectedFile ? selectedFile.name : "选择数据文件或图片"}</strong>
              <span>支持点击选择或拖拽上传表格、图片截图；图片会先由视觉解析 Agent 抽取结构化数据。</span>
            </label>

            <label className="form-label" htmlFor="goal-input">
              分析目标
            </label>
            <textarea
              id="goal-input"
              rows={5}
              value={userGoal}
              onChange={(event) => setUserGoal(event.target.value)}
            />
            <button
              className="primary-button"
              type="button"
              disabled={status === "uploading" || status === "running"}
              onClick={handleRunAnalysis}
            >
              启动 DeepSeek Agent 分析
            </button>
            {message ? (
              <p className={`message ${status === "failed" ? "error" : "success"}`}>{message}</p>
            ) : null}
          </section>

          <section className="panel">
            <h2>运行模式</h2>
            {isFallbackMode ? (
              <p className="mode-banner">当前使用规则分析模式</p>
            ) : (
              <p className="mode-banner mode-live">DeepSeek API 已启用</p>
            )}
            <dl className="info-list">
              <div>
                <dt>LLM 模式</dt>
                <dd>{health?.llm_mode ?? "读取中"}</dd>
              </div>
              <div>
                <dt>当前阶段</dt>
                <dd>{stageLabel(job?.current_stage ?? status)}</dd>
              </div>
              {uploadInfo ? (
                <div>
                  <dt>数据集</dt>
                  <dd>{uploadInfo.filename}</dd>
                </div>
              ) : null}
              {uploadInfo?.asset_type ? (
                <div>
                  <dt>输入类型</dt>
                  <dd>{uploadInfo.asset_type === "image" ? "图片解析" : "表格数据"}</dd>
                </div>
              ) : null}
            </dl>
            {uploadInfo?.preview_url ? (
              <img className="image-preview" alt="上传图片预览" src={uploadInfo.preview_url} />
            ) : null}
          </section>

          {profile ? (
            <section className="panel">
              <h2>数据概览</h2>
              <div className="metric-row">
                <div>
                  <strong>{profile.row_count}</strong>
                  <span>行</span>
                </div>
                <div>
                  <strong>{profile.column_count}</strong>
                  <span>列</span>
                </div>
              </div>
            </section>
          ) : null}

          <HistoryPanel
            items={workflowHistory}
            activeJobId={job?.job_id ?? null}
            loading={loadingHistory}
            message={historyMessage}
            onRefresh={refreshWorkflowHistory}
            onOpen={handleOpenHistoryJob}
          />
        </aside>

        <section className="content-panel">
          <nav className="page-tabs" aria-label="工作台页面">
            {[
              ["setup", "任务配置"],
              ["knowledge", "知识库"],
              ["process", "Agent 过程"],
              ["charts", "图表结果"],
              ["insights", "结论报告"],
              ["logs", "执行日志"]
            ].map(([key, label]) => (
              <button
                className={activePage === key ? "active" : ""}
                key={key}
                type="button"
                onClick={() => setActivePage(key as PageKey)}
              >
                {label}
              </button>
            ))}
          </nav>

          {activePage === "setup" ? (
            <SetupPage profile={profile} health={health} isFallbackMode={isFallbackMode} />
          ) : null}

          {activePage === "knowledge" ? (
            <KnowledgePage
              documents={knowledgeDocs}
              selectedFile={knowledgeFile}
              query={knowledgeQuery}
              searchResult={knowledgeSearch}
              message={knowledgeMessage}
              onFileChange={setKnowledgeFile}
              onQueryChange={setKnowledgeQuery}
              onUpload={handleKnowledgeUpload}
              onSearch={handleKnowledgeSearch}
              onDelete={handleKnowledgeDelete}
            />
          ) : null}

          {activePage === "process" ? (
            <ProcessPage
              job={job}
              log={executionLog}
              steps={steps}
              controllerPlan={controllerPlan}
              ragRetrieval={ragRetrieval}
              visualParseResult={visualParseResult}
              dataUnderstanding={dataUnderstanding}
              analysisPlan={analysisPlan}
              hypothesisPlan={hypothesisPlan}
              predictionPlan={predictionPlan}
              explanation={isPredictionWorkflow ? toExplanationResult(predictionExplanation) : normalizeExplanationResult(explanation)}
              isPredictionWorkflow={isPredictionWorkflow}
              events={events}
            />
          ) : null}

          {activePage === "charts" ? (
            <ChartsPage
              analysisResult={analysisResult}
              chartPaths={chartPaths}
              job={job}
              predictionResult={isPredictionWorkflow ? predictionResult : null}
              isPredictionWorkflow={isPredictionWorkflow}
              message={chartMessage}
              onOpenChart={setChartPreviewPath}
              onDeleteChart={handleDeleteChart}
            />
          ) : null}

          {activePage === "insights" ? (
            <InsightsPage
              explanation={isPredictionWorkflow ? toExplanationResult(predictionExplanation) : normalizeExplanationResult(explanation)}
              report={isPredictionWorkflow ? null : report}
              job={job}
            />
          ) : null}

          {activePage === "logs" ? (
            <LogsPage job={job} log={executionLog} events={events} />
          ) : null}
        </section>
      </section>
      {chartPreviewPath ? (
        <ChartPreviewModal
          chartPath={chartPreviewPath}
          onClose={() => setChartPreviewPath(null)}
          onDelete={() => handleDeleteChart(chartPreviewPath)}
        />
      ) : null}
    </main>
  );
}

function SetupPage({
  profile,
  health,
  isFallbackMode
}: {
  profile: DatasetProfile | null;
  health: HealthStatus | null;
  isFallbackMode: boolean;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>开始一次分析</h2>
        <span>{isFallbackMode ? "规则 fallback" : "DeepSeek live"}</span>
      </div>
      <div className="setup-grid">
        <article className="info-card">
          <strong>1. 上传数据</strong>
          <p>支持 CSV、XLSX、XLS 和图片截图。图片会先抽取为结构化数据，再进入 Agent 工作流。</p>
        </article>
        <article className="info-card">
          <strong>2. 输入目标</strong>
          <p>例如“按班级统计成绩并生成图表”或“找出影响销量下降的可能原因”。</p>
        </article>
        <article className="info-card">
          <strong>3. 查看过程</strong>
          <p>启动后会立即进入 Agent 过程页，状态和日志会按秒级轮询刷新。</p>
        </article>
      </div>
      <dl className="info-list wide">
        <div>
          <dt>DeepSeek 状态</dt>
          <dd>{health?.message ?? "正在读取配置"}</dd>
        </div>
        {profile ? (
          <div>
            <dt>字段</dt>
            <dd>{profile.columns.join("、")}</dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

function HistoryPanel({
  items,
  activeJobId,
  loading,
  message,
  onRefresh,
  onOpen
}: {
  items: WorkflowJobListItem[];
  activeJobId: string | null;
  loading: boolean;
  message: string;
  onRefresh: () => void;
  onOpen: (jobId: string) => void;
}) {
  return (
    <section className="panel history-panel">
      <div className="panel-header">
        <h2>分析对话列表</h2>
        <button className="text-button" type="button" disabled={loading} onClick={onRefresh}>
          {loading ? "刷新中" : "刷新"}
        </button>
      </div>
      {message ? <p className="history-message">{message}</p> : null}
      {items.length ? (
        <div className="history-list">
          {items.map((item) => {
            const active = item.job_id === activeJobId;
            return (
              <button
                className={`history-item ${active ? "active" : ""}`}
                key={item.job_id}
                type="button"
                onClick={() => onOpen(item.job_id)}
              >
                <span className="history-item-title">{workflowLabel(item.workflow_type || item.task_type)}</span>
                <span className="history-item-goal">{item.user_goal || "未记录分析目标"}</span>
                <span className="history-item-meta">
                  {item.dataset_filename || item.dataset_id || "未知数据集"} · {statusLabel(item.status)} · {formatDateTime(item.updated_at || item.created_at || "")}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="history-empty">暂无可复看的分析对话。</p>
      )}
    </section>
  );
}

function KnowledgePage({
  documents,
  selectedFile,
  query,
  searchResult,
  message,
  onFileChange,
  onQueryChange,
  onUpload,
  onSearch,
  onDelete
}: {
  documents: KnowledgeDocument[];
  selectedFile: File | null;
  query: string;
  searchResult: KnowledgeSearchResponse | null;
  message: string;
  onFileChange: (file: File | null) => void;
  onQueryChange: (query: string) => void;
  onUpload: () => void;
  onSearch: () => void;
  onDelete: (docId: string) => void;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>全局业务知识库</h2>
        <span>{documents.length} 个文档</span>
      </div>

      <div className="knowledge-grid">
        <article className="info-card">
          <strong>上传知识文档</strong>
          <label className="upload-zone compact-upload">
            <input
              type="file"
              accept=".txt,.md"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
            <span>{selectedFile ? selectedFile.name : "选择 .txt / .md 文件"}</span>
          </label>
          <button className="primary-button" type="button" onClick={onUpload}>
            写入知识库
          </button>
          {message ? <p className="message success">{message}</p> : null}
        </article>

        <article className="info-card">
          <strong>测试检索</strong>
          <textarea
            rows={4}
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
          <button className="secondary-button" type="button" onClick={onSearch}>
            检索知识库
          </button>
        </article>
      </div>

      <div className="knowledge-grid">
        <section className="info-card">
          <strong>文档列表</strong>
          {documents.length ? (
            <div className="document-list">
              {documents.map((document) => (
                <article className="document-item" key={document.doc_id}>
                  <div>
                    <strong>{document.filename}</strong>
                    <p>
                      {document.chunk_count} chunks · {document.indexed ? "已索引" : "未索引"}
                    </p>
                    {document.index_error ? <p>{document.index_error}</p> : null}
                  </div>
                  <button type="button" onClick={() => onDelete(document.doc_id)}>
                    删除
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <p>暂无知识文档。</p>
          )}
        </section>

        <section className="info-card">
          <strong>检索结果</strong>
          {searchResult ? (
            <>
              <p>{searchResult.message}</p>
              <div className="document-list">
                {searchResult.results.map((item, index) => (
                  <article className="document-item result" key={`${item.doc_id}-${item.chunk_index}-${index}`}>
                    <div>
                      <strong>{item.filename || `片段 ${index + 1}`}</strong>
                      <p>{item.chunk}</p>
                      <span>score {item.score ?? "-"}</span>
                    </div>
                  </article>
                ))}
              </div>
            </>
          ) : (
            <p>输入问题后可以查看 top-k 知识片段。</p>
          )}
        </section>
      </div>
    </section>
  );
}

function PredictionPage({
  file,
  goal,
  status,
  message,
  job,
  log,
  hypothesisPlan,
  predictionPlan,
  predictionResult,
  explanation,
  onFileChange,
  onGoalChange,
  onRun
}: {
  file: File | null;
  goal: string;
  status: string;
  message: string;
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  predictionResult: PredictionResult | null;
  explanation: PredictionExplanationResult;
  onFileChange: (file: File | null) => void;
  onGoalChange: (goal: string) => void;
  onRun: () => void;
}) {
  const events = log?.events?.length ? log.events : job?.events ?? [];
  const chartPaths = getChartPaths(predictionResult, job);
  const unsupportedReason = predictionResult?.status === "unsupported"
    ? stringValue(predictionResult.unsupported_reason, "当前数据缺少完成该情景预测所需的字段。")
    : "";
  const steps = buildPredictionSteps({
    job,
    log,
    controllerPlan: null,
    ragRetrieval: null,
    visualParseResult: null,
    hypothesisPlan,
    predictionPlan,
    predictionResult,
    explanation,
    events
  });

  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>情景预测</h2>
        <span>{job ? `Job ${job.job_id}` : "What-if Simulation"}</span>
      </div>

      <div className="knowledge-grid">
        <article className="info-card">
          <strong>上传预测数据</strong>
          <label className="upload-zone compact-upload">
            <input
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={(event) => onFileChange(event.target.files?.[0] ?? null)}
            />
            <span>{file ? file.name : "选择 CSV / Excel 文件"}</span>
          </label>
          <label className="form-label" htmlFor="prediction-goal">
            假设性问题
          </label>
          <textarea
            id="prediction-goal"
            rows={4}
            value={goal}
            onChange={(event) => onGoalChange(event.target.value)}
          />
          <button
            className="primary-button"
            type="button"
            disabled={status === "uploading" || status === "running"}
            onClick={onRun}
          >
            启动情景预测
          </button>
          {message ? <p className={`message ${status === "failed" ? "error" : "success"}`}>{message}</p> : null}
        </article>

        <article className="info-card">
          <strong>示例问题</strong>
          <p>如果下个月营销预算增加 20%，哪些商品的销量最可能提升？</p>
          <p>如果将平时成绩权重提升 10%，不及格率会发生什么变化？</p>
          <p>预测结果是基于当前数据的模拟估计，不代表确定因果。</p>
        </article>
      </div>

      <section className="result-section">
        <div className="section-heading">
          <h2>预测 Agent 过程</h2>
          <span>{job ? job.current_stage ?? job.status : "等待启动"}</span>
        </div>
        <div className="agent-timeline">
          {steps.map((step) => (
            <article className={`agent-step ${step.status}`} key={step.key}>
              <span className="agent-dot" />
              <div>
                <strong>{step.title}</strong>
                <p>{step.summary}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      {predictionResult ? (
        unsupportedReason ? (
          <section className="result-section">
            <div className="section-heading">
              <h2>情景预测无法计算</h2>
              <span>{predictionResult.model_info?.method ? String(predictionResult.model_info.method) : "unsupported"}</span>
            </div>
            <p className="summary-text">{unsupportedReason}</p>
            <ResultList title="限制说明" items={arrayValue(predictionResult.limitations).map(String)} />
          </section>
        ) : (
          <section className="result-section">
            <div className="section-heading">
              <h2>预测影响 Top 对象</h2>
              <span>{predictionResult.model_info?.method ? String(predictionResult.model_info.method) : "model"}</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>对象</th>
                    <th>基准值</th>
                    <th>预测值</th>
                    <th>变化</th>
                    <th>变化率</th>
                  </tr>
                </thead>
                <tbody>
                  {predictionResult.top_impacted_entities.map((item) => (
                    <tr key={`${item.entity}-${item.absolute_change}`}>
                      <td>{item.entity}</td>
                      <td>{formatNumber(item.baseline_value)}</td>
                      <td>{formatNumber(item.predicted_value)}</td>
                      <td>{formatNumber(item.absolute_change)}</td>
                      <td>{formatPercent(item.percent_change)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )
      ) : null}

      {chartPaths.length ? (
        <section className="result-section">
          <div className="section-heading">
            <h2>预测图表</h2>
            <span>{chartPaths.length} 个图表</span>
          </div>
          <div className="chart-grid">
            {chartPaths.map((chartPath, index) => (
              <figure className="chart-card" key={chartPath}>
                <img alt={`预测图表 ${index + 1}`} src={toStorageUrl(chartPath)} />
                <figcaption>{chartTitle(chartPath, index)}</figcaption>
              </figure>
            ))}
          </div>
        </section>
      ) : null}

      {explanation.summary ? (
        <section className="result-section">
          <div className="section-heading">
            <h2>预测解释</h2>
            <span>谨慎表述</span>
          </div>
          <p className="summary-text">{explanation.summary}</p>
          <ResultList title="关键发现" items={explanation.key_findings} />
          <ResultList title="建议动作" items={explanation.recommendations} />
          <ResultList title="限制说明" items={explanation.limitations} />
        </section>
      ) : null}

      <div className="agent-output-grid">
        <JsonSummary title="假设解析 Agent 输出" value={hypothesisPlan} />
        <JsonSummary title="预测计划 Agent 输出" value={predictionPlan} />
      </div>
    </section>
  );
}

function ProcessPage({
  job,
  log,
  steps,
  controllerPlan,
  ragRetrieval,
  visualParseResult,
  dataUnderstanding,
  analysisPlan,
  hypothesisPlan,
  predictionPlan,
  explanation,
  isPredictionWorkflow,
  events
}: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  steps: StepView[];
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  visualParseResult: VisualParseResult | null;
  dataUnderstanding: AnyRecord | null;
  analysisPlan: AnyRecord | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  explanation: ExplanationResult;
  isPredictionWorkflow: boolean;
  events: ExecutionLogEvent[];
}) {
  const cards = buildAgentCards({
    job,
    log,
    steps,
    controllerPlan,
    ragRetrieval,
    visualParseResult,
    dataUnderstanding,
    analysisPlan,
    hypothesisPlan,
    predictionPlan,
    explanation,
    isPredictionWorkflow
  });
  const attemptViews = buildAttemptProgressViews({
    job,
    log,
    events
  });

  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>Agent 对话过程</h2>
        {job ? <span>{workflowLabel(job.workflow_type || job.task_type)} · Job {job.job_id}</span> : <span>等待任务启动</span>}
      </div>
      <div className="agent-chat-list">
        {cards.length ? (
          cards.map((card) => <AgentMessageCard card={card} key={card.key} />)
        ) : (
          <EmptyState title="等待 Agent 接入" text="任务启动后，实际参与工作的 Agent 会按执行顺序逐个出现在这里。" compact />
        )}
      </div>
      <AttemptProgressSection attempts={attemptViews} isPredictionWorkflow={isPredictionWorkflow} />
    </section>
  );
}

function AgentMessageCard({ card }: { card: AgentCardView }) {
  return (
    <article className={`agent-message-card ${card.status}`}>
      <div className="agent-avatar">{agentInitial(card.agentName)}</div>
      <div className="agent-message-body">
        <div className="agent-message-head">
          <div>
            <strong>{card.agentName}</strong>
            <span>{card.title}</span>
          </div>
          <span className={`agent-status-badge ${card.status}`}>{stepStatusLabel(card.status)}</span>
        </div>

        <dl className="agent-detail-grid">
          <div>
            <dt>输入来源</dt>
            <dd>{card.inputSource}</dd>
          </div>
          <div>
            <dt>当前动作</dt>
            <dd>{card.action}</dd>
          </div>
          <div>
            <dt>输出摘要</dt>
            <dd>{card.output}</dd>
          </div>
        </dl>

        {card.evidence.length ? (
          <div className="agent-evidence">
            <span>可审计依据</span>
            <ul>
              {card.evidence.map((item, index) => (
                <li key={`${card.key}-evidence-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}

        <ArtifactSummary card={card} />

        {card.artifactPath ? (
          <a className="artifact-link" href={toStorageUrl(card.artifactPath)} target="_blank" rel="noreferrer">
            查看产物：{card.artifactLabel ?? shortPath(card.artifactPath)}
          </a>
        ) : null}

        <RawJsonDetails value={card.raw} title="查看原始输出" />
      </div>
    </article>
  );
}

function AttemptProgressSection({
  attempts,
  isPredictionWorkflow
}: {
  attempts: AttemptProgressView[];
  isPredictionWorkflow: boolean;
}) {
  if (!attempts.length) {
    return null;
  }
  return (
    <section className="attempt-section">
      <div className="section-heading">
        <h2>{isPredictionWorkflow ? "预测脚本生成与验证" : "代码生成与验证"}</h2>
        <span>{attempts.length} 次尝试</span>
      </div>
      <div className="attempt-list">
        {attempts.map((attempt) => (
          <AttemptProgressCard attempt={attempt} key={attempt.attempt} />
        ))}
      </div>
    </section>
  );
}

function AttemptProgressCard({ attempt }: { attempt: AttemptProgressView }) {
  const validationIssues = attempt.validation?.issues ?? [];
  const repairSuggestions = attempt.validation?.repair_suggestions ?? [];
  return (
    <article className="attempt-card">
      <div className="attempt-card-head">
        <strong>第 {attempt.attempt} 次尝试</strong>
        <span className={`agent-status-badge ${attemptStatusClass(attempt)}`}>
          {attemptStatusText(attempt)}
        </span>
      </div>
      <div className="attempt-stage-row">
        <AttemptStage label="脚本生成" status={attempt.codeStatus} />
        <AttemptStage label="安全检查" status={attempt.safetyStatus} />
        <AttemptStage label="沙箱执行" status={attempt.sandboxStatus} />
        <AttemptStage label="结果验证" status={attempt.validationStatus} />
      </div>

      <dl className="compact-list attempt-meta">
        <div>
          <dt>脚本路径</dt>
          <dd>{attempt.attemptResult?.script_path ? shortPath(attempt.attemptResult.script_path) : "生成中或等待生成"}</dd>
        </div>
        <div>
          <dt>执行结果</dt>
          <dd>{attempt.execution ? (attempt.execution.success ? "执行成功" : "执行失败") : "等待执行"}</dd>
        </div>
        <div>
          <dt>验证结果</dt>
          <dd>{attempt.validation ? (attempt.validation.passed ? "验证通过" : `验证未通过，严重级别 ${severityLabel(attempt.validation.severity)}`) : "等待验证"}</dd>
        </div>
      </dl>

      {validationIssues.length ? (
        <IssueList title="验证发现的问题" items={validationIssues} />
      ) : null}
      {repairSuggestions.length ? (
        <IssueList title="修复建议" items={repairSuggestions} />
      ) : null}
      {attempt.attemptResult?.safety_issues?.length ? (
        <ChipList title="安全检查问题" items={attempt.attemptResult.safety_issues} tone="warning" />
      ) : null}
    </article>
  );
}

function AttemptStage({ label, status }: { label: string; status?: string }) {
  return (
    <div className={`attempt-stage ${attemptStageClass(status)}`}>
      <span>{label}</span>
      <strong>{attemptStageText(status)}</strong>
    </div>
  );
}

function IssueList({ title, items }: { title: string; items: Array<Record<string, unknown>> }) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="issue-list">
      <span>{title}</span>
      {items.map((item, index) => (
        <article key={`${title}-${index}`}>
          <strong>{stringValue(item.issue_type ?? item.target_agent, `问题 ${index + 1}`)}</strong>
          <p>{stringValue(item.message, formatListItem(item))}</p>
          {item.location ? <small>{String(item.location)}</small> : null}
        </article>
      ))}
    </div>
  );
}

function ArtifactSummary({ card }: { card: AgentCardView }) {
  if (!card.raw) {
    return <p className="agent-muted">等待该 Agent 生成输出。</p>;
  }

  if (card.artifactKind === "visual") {
    return <VisualArtifactSummary value={card.raw as VisualParseResult} />;
  }
  if (card.artifactKind === "rag") {
    return <RagArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "controller") {
    return <ControllerArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "understanding") {
    return <UnderstandingArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "analysis") {
    return <AnalysisPlanArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "hypothesis") {
    return <HypothesisArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "prediction_plan") {
    return <PredictionPlanArtifactSummary value={card.raw as AnyRecord} />;
  }
  if (card.artifactKind === "execution") {
    return <ExecutionArtifactSummary value={card.raw as ExecutionAttemptLog} />;
  }
  if (card.artifactKind === "validation") {
    return <ValidationArtifactSummary value={card.raw as ValidationAttemptLog} />;
  }
  if (card.artifactKind === "explanation") {
    return <ExplanationArtifactSummary value={card.raw as ExplanationResult} />;
  }
  return <GenericArtifactSummary value={card.raw} />;
}

function ControllerArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["任务类型", stringValue(value.task_type, "-")],
          ["任务名称", stringValue(value.task_name, "-")],
          ["分流结果", workflowLabel(value.task_type)]
        ]}
      />
      <SummaryParagraph label="判断依据" text={stringValue(value.reasoning_summary, "主控 Agent 已生成任务计划。")} />
      <ChipList title="执行步骤" items={arrayValue(value.steps).slice(0, 6)} />
    </div>
  );
}

function VisualArtifactSummary({ value }: { value: VisualParseResult }) {
  const warnings = [...(value.warnings ?? []), ...(value.limitations ?? [])].filter(Boolean);
  return (
    <div className="artifact-summary">
      <div className="metric-row">
        <div>
          <strong>{value.columns?.length ?? 0}</strong>
          <span>抽取列数</span>
        </div>
        <div>
          <strong>{value.rows?.length ?? 0}</strong>
          <span>抽取行数</span>
        </div>
        <div>
          <strong>{Number.isFinite(value.confidence) ? `${Math.round(value.confidence * 100)}%` : "-"}</strong>
          <span>置信度</span>
        </div>
      </div>
      <ChipList title="字段" items={value.columns ?? []} />
      {warnings.length ? <ChipList title="警告与限制" items={warnings} tone="warning" /> : null}
      <DataPreviewTable rows={value.rows ?? []} columns={value.columns ?? []} />
    </div>
  );
}

function RagArtifactSummary({ value }: { value: AnyRecord }) {
  const results = Array.isArray(value.results) ? value.results.slice(0, 3) : [];
  return (
    <div className="artifact-summary">
      <SummaryParagraph label="检索结果" text={ragSummary(value)} />
      {results.length ? (
        <div className="mini-list">
          {results.map((item, index) => {
            const record = item as AnyRecord;
            return (
              <article key={`rag-${index}`}>
                <strong>{stringValue(record.filename, `知识片段 ${index + 1}`)}</strong>
                <p>{stringValue(record.chunk, stringValue(record.source, "已命中相关知识。"))}</p>
              </article>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function UnderstandingArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["适用性评分", value.suitability_score === undefined ? "-" : String(value.suitability_score)],
          ["日期字段", arrayValue(value.date_columns).join("、") || "-"]
        ]}
      />
      <ChipList title="目标字段" items={arrayValue(value.target_columns)} />
      <ChipList title="维度字段" items={arrayValue(value.dimension_columns)} />
      <ChipList title="数值字段" items={arrayValue(value.numeric_columns)} />
      <ChipList title="质量问题" items={arrayValue(value.quality_issues)} tone="warning" />
    </div>
  );
}

function AnalysisPlanArtifactSummary({ value }: { value: AnyRecord }) {
  const chartPlan = Array.isArray(value.chart_plan) ? value.chart_plan.slice(0, 4) : [];
  return (
    <div className="artifact-summary">
      <SummaryParagraph label="分析目标" text={stringValue(value.analysis_goal, "已生成分析计划。")} />
      <ChipList title="分析方法" items={arrayValue(value.methods)} />
      <ChipList title="分组维度" items={arrayValue(value.grouping_dimensions)} />
      <ChipList title="分析指标" items={arrayValue(value.metrics)} />
      {chartPlan.length ? <GenericArtifactSummary value={chartPlan} title="图表计划" /> : null}
      <ChipList title="限制说明" items={arrayValue(value.limitations)} tone="warning" />
    </div>
  );
}

function HypothesisArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["目标指标", structuredFieldValue(value.target_metric)],
          ["对象维度", structuredFieldValue(value.entity_dimension)],
          ["干预变量", interventionDisplay(value.intervention)],
          ["干预方向", stringValue(value.intervention_direction, "-")]
        ]}
      />
      <SummaryParagraph label="假设摘要" text={stringValue(value.scenario_summary, stringValue(value.hypothesis, "已完成假设解析。"))} />
      <ChipList title="限制说明" items={arrayValue(value.limitations)} tone="warning" />
    </div>
  );
}

function PredictionPlanArtifactSummary({ value }: { value: AnyRecord }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["目标指标", stringValue(value.target_metric, "-")],
          ["对象维度", stringValue(value.entity_dimension, "-")],
          ["干预字段", interventionDisplay(value.intervention)],
          ["候选模型", arrayValue(value.model_candidates).join("、") || "-"]
        ]}
      />
      <ChipList title="预测步骤" items={arrayValue(value.steps)} />
      <ChipList title="限制说明" items={arrayValue(value.limitations)} tone="warning" />
    </div>
  );
}

function ExecutionArtifactSummary({ value }: { value: ExecutionAttemptLog }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["是否成功", value.success ? "是" : "否"],
          ["退出码", value.exit_code === undefined || value.exit_code === null ? "-" : String(value.exit_code)],
          ["耗时", `${value.duration_ms ?? "-"} ms`]
        ]}
      />
      <details className="raw-json-details">
        <summary>查看沙箱输出</summary>
        <pre>{String(value.stderr || value.stdout || "暂无执行输出")}</pre>
      </details>
    </div>
  );
}

function ValidationArtifactSummary({ value }: { value: ValidationAttemptLog }) {
  return (
    <div className="artifact-summary">
      <KeyValueGrid
        items={[
          ["是否通过", value.passed ? "是" : "否"],
          ["严重级别", severityLabel(value.severity)],
          ["是否建议重试", value.should_retry ? "是" : "否"]
        ]}
      />
      <GenericArtifactSummary value={value.issues ?? []} title="问题列表" />
      <GenericArtifactSummary value={value.repair_suggestions ?? []} title="修复建议" />
    </div>
  );
}

function ExplanationArtifactSummary({ value }: { value: ExplanationResult }) {
  return (
    <div className="artifact-summary">
      <SummaryParagraph label="结论摘要" text={value.summary || "等待解释 Agent 输出结论。"} />
      <ChipList title="关键发现" items={value.key_findings ?? []} />
      <ChipList title="建议动作" items={value.recommendations ?? []} />
      <ChipList title="限制说明" items={value.limitations ?? []} tone="warning" />
    </div>
  );
}

function GenericArtifactSummary({ value, title = "结构化输出" }: { value: unknown; title?: string }) {
  if (value === null || value === undefined) {
    return null;
  }
  return (
    <details className="raw-json-details compact" open={false}>
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function RawJsonDetails({ value, title }: { value: unknown; title: string }) {
  if (value === null || value === undefined) {
    return null;
  }
  return (
    <details className="raw-json-details">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function DataPreviewTable({ rows, columns }: { rows: Array<Record<string, unknown>>; columns: string[] }) {
  const previewRows = rows.slice(0, 5);
  const visibleColumns = columns.slice(0, 6);
  if (!previewRows.length || !visibleColumns.length) {
    return null;
  }
  return (
    <div className="table-wrap compact-table">
      <table>
        <thead>
          <tr>
            {visibleColumns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {previewRows.map((row, rowIndex) => (
            <tr key={`preview-${rowIndex}`}>
              {visibleColumns.map((column) => (
                <td key={`${rowIndex}-${column}`}>{formatCell(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function KeyValueGrid({ items }: { items: Array<[string, string]> }) {
  return (
    <dl className="compact-list artifact-kv">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function SummaryParagraph({ label, text }: { label: string; text: string }) {
  return (
    <div className="summary-block">
      <span>{label}</span>
      <p>{text}</p>
    </div>
  );
}

function ChipList({ title, items, tone = "default" }: { title: string; items: string[]; tone?: "default" | "warning" }) {
  const cleanItems = items.filter(Boolean);
  if (!cleanItems.length) {
    return null;
  }
  return (
    <div className="chip-section">
      <span>{title}</span>
      <div className="chip-row">
        {cleanItems.map((item, index) => (
          <span className={`summary-chip ${tone}`} key={`${title}-${index}-${item}`}>
            {item}
          </span>
        ))}
      </div>
    </div>
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

function ChartsPage({
  analysisResult,
  chartPaths,
  job,
  predictionResult,
  isPredictionWorkflow,
  message,
  onOpenChart,
  onDeleteChart
}: {
  analysisResult: AnalysisResult | null;
  chartPaths: string[];
  job: WorkflowJobResponse | null;
  predictionResult: PredictionResult | null;
  isPredictionWorkflow: boolean;
  message: string;
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
          {chartPaths.map((chartPath, index) => (
            <figure className="chart-card" key={chartPath}>
              <button
                className="chart-image-button"
                type="button"
                onClick={() => onOpenChart(chartPath)}
                aria-label={`放大查看${chartTitle(chartPath, index)}`}
              >
                <img alt={`分析图表 ${index + 1}`} src={toStorageUrl(chartPath)} />
              </button>
              <figcaption>{chartTitle(chartPath, index)}</figcaption>
              <div className="chart-actions">
                <button type="button" onClick={() => onOpenChart(chartPath)}>
                  放大查看
                </button>
                <button className="danger-button" type="button" onClick={() => onDeleteChart(chartPath)}>
                  删除
                </button>
              </div>
            </figure>
          ))}
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

function ChartPreviewModal({
  chartPath,
  onClose,
  onDelete
}: {
  chartPath: string;
  onClose: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="chart-modal-backdrop" role="dialog" aria-modal="true" aria-label="图表预览">
      <div className="chart-modal">
        <div className="chart-modal-head">
          <strong>{chartTitle(chartPath, 0)}</strong>
          <div className="chart-modal-actions">
            <button className="danger-button" type="button" onClick={onDelete}>
              删除
            </button>
            <button type="button" onClick={onClose}>
              关闭
            </button>
          </div>
        </div>
        <div className="chart-modal-body">
          <img alt="放大图表" src={toStorageUrl(chartPath)} />
        </div>
      </div>
    </div>
  );
}

function InsightsPage({
  explanation,
  report,
  job
}: {
  explanation: ExplanationResult;
  report: ReportGenerateResponse | null;
  job: WorkflowJobResponse | null;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>结论与报告</h2>
        {report ? (
          <a className="download-button" href={toStorageUrl(report.report_path)} download>
            下载报告
          </a>
        ) : (
          <span>等待报告生成</span>
        )}
      </div>
      <DataSourceNotice job={job} />
      {explanation.summary ? (
        <>
          <p className="summary-text">{explanation.summary}</p>
          <ResultList title="关键发现" items={explanation.key_findings} />
          <ResultList title="建议动作" items={explanation.recommendations} />
          <ResultList title="限制说明" items={explanation.limitations} />
          <PptOutline outline={explanation.ppt_outline} />
        </>
      ) : (
        <EmptyState title="暂无结论" text="验证 Agent 通过后，解释 Agent 会生成结论、建议和 PPT 大纲。" />
      )}
    </section>
  );
}

function LogsPage({
  job,
  log,
  events
}: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  events: ExecutionLogEvent[];
}) {
  const executionResults = log?.execution_results ?? [];
  const validationResults = log?.validation_results ?? [];

  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>执行日志</h2>
        <span>{job ? statusLabel(statusFromJob(job.status)) : "等待任务启动"}</span>
      </div>

      <div className="log-summary-grid">
        <div>
          <span>事件数量</span>
          <strong>{events.length}</strong>
        </div>
        <div>
          <span>沙箱执行次数</span>
          <strong>{executionResults.length}</strong>
        </div>
        <div>
          <span>验证次数</span>
          <strong>{validationResults.length}</strong>
        </div>
      </div>

      <section className="result-section">
        <div className="section-heading">
          <h2>完整事件流</h2>
          <span>{events.length} 条事件</span>
        </div>
        <EventLogList events={events} />
      </section>

      <section className="result-section">
        <div className="section-heading">
          <h2>沙箱执行日志</h2>
          <span>{executionResults.length} 次执行</span>
        </div>
        {executionResults.length ? (
          <div className="log-stack">
            {executionResults.map((execution, index) => (
              <ExecutionLogBlock execution={execution} key={`${execution.path}-${index}`} />
            ))}
          </div>
        ) : (
          <EmptyState title="暂无沙箱执行日志" text="代码 Agent 生成脚本并进入沙箱后，这里会显示完整 stdout / stderr。" compact />
        )}
      </section>

      <section className="result-section">
        <div className="section-heading">
          <h2>验证 Agent 日志</h2>
          <span>{validationResults.length} 次验证</span>
        </div>
        {validationResults.length ? (
          <div className="log-stack">
            {validationResults.map((validation, index) => (
              <ValidationLogBlock validation={validation} key={`${validation.path}-${index}`} />
            ))}
          </div>
        ) : (
          <EmptyState title="暂无验证日志" text="沙箱执行结束后，验证 Agent 的完整问题和修复建议会显示在这里。" compact />
        )}
      </section>
    </section>
  );
}

function ExecutionLogBlock({ execution }: { execution: ExecutionAttemptLog }) {
  return (
    <article className="log-block">
      <h3>第 {execution.attempt} 次沙箱执行</h3>
      <dl className="compact-list">
        <div>
          <dt>成功</dt>
          <dd>{execution.success ? "是" : "否"}</dd>
        </div>
        <div>
          <dt>退出码</dt>
          <dd>{String(execution.exit_code ?? "-")}</dd>
        </div>
        <div>
          <dt>耗时</dt>
          <dd>{String(execution.duration_ms ?? "-")} ms</dd>
        </div>
        <div>
          <dt>结果文件</dt>
          <dd>{shortPath(execution.path)}</dd>
        </div>
      </dl>
      <details className="raw-json-details" open>
        <summary>完整 stdout / stderr</summary>
        <pre>{String(execution.stderr || execution.stdout || "暂无执行输出")}</pre>
      </details>
      <RawJsonDetails value={execution} title="查看原始执行记录" />
    </article>
  );
}

function ValidationLogBlock({ validation }: { validation: ValidationAttemptLog }) {
  return (
    <article className="log-block">
      <h3>第 {validation.attempt} 次验证</h3>
      <dl className="compact-list">
        <div>
          <dt>是否通过</dt>
          <dd>{validation.passed ? "是" : "否"}</dd>
        </div>
        <div>
          <dt>严重级别</dt>
          <dd>{severityLabel(validation.severity)}</dd>
        </div>
        <div>
          <dt>是否重试</dt>
          <dd>{validation.should_retry ? "是" : "否"}</dd>
        </div>
        <div>
          <dt>验证文件</dt>
          <dd>{shortPath(validation.path)}</dd>
        </div>
      </dl>
      <details className="raw-json-details" open>
        <summary>完整问题列表</summary>
        <pre>{JSON.stringify(validation.issues ?? [], null, 2)}</pre>
      </details>
      <details className="raw-json-details" open>
        <summary>完整修复建议</summary>
        <pre>{JSON.stringify(validation.repair_suggestions ?? [], null, 2)}</pre>
      </details>
      <RawJsonDetails value={validation} title="查看原始验证记录" />
    </article>
  );
}

function ResultList({ title, items }: { title: string; items?: unknown[] | null }) {
  const normalizedItems = Array.isArray(items) ? items.map((item) => formatListItem(item)).filter(Boolean) : [];
  if (!normalizedItems.length) {
    return null;
  }
  return (
    <div className="finding-list">
      <h3>{title}</h3>
      {normalizedItems.map((item, index) => (
        <div className="finding-item" key={`${title}-${index}-${item}`}>
          <p>{item}</p>
        </div>
      ))}
    </div>
  );
}

function PptOutline({ outline }: { outline: ExplanationResult["ppt_outline"] }) {
  const normalizedOutline = normalizePptOutline(outline);
  if (!normalizedOutline.length) {
    return null;
  }
  return (
    <div className="finding-list">
      <h3>PPT 大纲</h3>
      {normalizedOutline.map((slide, index) => (
        <div className="finding-item" key={`${slide.title}-${index}`}>
          <strong>{slide.title}</strong>
          <p>{slide.bullets.join("；")}</p>
        </div>
      ))}
    </div>
  );
}

function JsonSummary({ title, value }: { title: string; value: AnyRecord | null }) {
  return (
    <article className="info-card">
      <strong>{title}</strong>
      {value ? <pre>{JSON.stringify(value, null, 2)}</pre> : <p>等待输出生成。</p>}
    </article>
  );
}

function EventLogList({ events }: { events: ExecutionLogEvent[] }) {
  if (!events.length) {
    return <EmptyState title="暂无日志" text="任务启动后，Agent 事件会实时追加到这里。" compact />;
  }
  return (
    <div className="log-event-list">
      {events.map((event, index) => (
        <article className="log-event" key={`${event.timestamp}-${index}`}>
          <span>
            {stageLabel(event.stage)} · {eventStatusLabel(event.status)}
            {event.attempt ? ` · 第 ${event.attempt} 次尝试` : ""}
          </span>
          <strong>{event.message}</strong>
          <p>{formatTime(event.timestamp)}</p>
        </article>
      ))}
    </div>
  );
}

function EmptyState({ title, text, compact = false }: { title: string; text: string; compact?: boolean }) {
  return (
    <div className={compact ? "empty-state compact" : "empty-state"}>
      <h2>{title}</h2>
      <p>{text}</p>
    </div>
  );
}

function buildAgentCards(input: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  steps: StepView[];
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  visualParseResult: VisualParseResult | null;
  dataUnderstanding: AnyRecord | null;
  analysisPlan: AnyRecord | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  explanation: ExplanationResult;
  isPredictionWorkflow: boolean;
}): AgentCardView[] {
  const latestAttempt = lastItem(input.job?.attempts);
  const latestExecution = lastItem(input.log?.execution_results);
  const latestValidation = lastItem(input.log?.validation_results);
  const explanationRaw = input.explanation.summary ? input.explanation : null;

  return input.steps.map((step): AgentCardView => {
    const base = cardBase(step, input.isPredictionWorkflow);
    const card: AgentCardView = {
      ...step,
      ...base,
      output: step.summary,
      artifactKind: base.artifactKind,
      evidence: base.evidence
    };

    if (step.key === "visual") {
      return {
        ...card,
        raw: input.visualParseResult,
        artifactPath: input.job?.visual_parse_result_path,
        artifactLabel: "visual_parse_result.json",
        evidence: visualEvidence(input.visualParseResult, input.job)
      };
    }
    if (step.key === "rag") {
      return {
        ...card,
        raw: input.ragRetrieval,
        artifactPath: input.job?.rag_retrieval_path,
        artifactLabel: "rag_retrieval.json",
        evidence: ragEvidence(input.ragRetrieval)
      };
    }
    if (step.key === "controller") {
      return {
        ...card,
        raw: input.controllerPlan,
        artifactPath: input.job?.controller_plan_path,
        artifactLabel: "controller_plan.json",
        evidence: controllerEvidence(input.controllerPlan, input.job)
      };
    }
    if (step.key === "understanding") {
      return {
        ...card,
        raw: input.dataUnderstanding,
        artifactPath: input.job?.data_understanding_path,
        artifactLabel: "data_understanding.json",
        evidence: understandingEvidence(input.dataUnderstanding)
      };
    }
    if (step.key === "analysis") {
      return {
        ...card,
        raw: input.analysisPlan,
        artifactPath: input.job?.analysis_plan_path,
        artifactLabel: "analysis_plan.json",
        evidence: analysisEvidence(input.analysisPlan)
      };
    }
    if (step.key === "hypothesis") {
      return {
        ...card,
        raw: input.hypothesisPlan,
        artifactPath: input.job?.hypothesis_plan_path,
        artifactLabel: "hypothesis_plan.json",
        evidence: hypothesisEvidence(input.hypothesisPlan)
      };
    }
    if (step.key === "prediction_plan") {
      return {
        ...card,
        raw: input.predictionPlan,
        artifactPath: input.job?.prediction_plan_path,
        artifactLabel: "prediction_plan.json",
        evidence: predictionEvidence(input.predictionPlan)
      };
    }
    if (step.key === "code" || step.key === "safety") {
      return {
        ...card,
        raw: latestAttempt ?? null,
        artifactPath: step.key === "code" ? latestAttempt?.script_path : latestAttempt?.safety_result_path,
        artifactLabel: step.key === "code" ? "generated_script.py" : "safety_result.json",
        evidence: attemptEvidence(latestAttempt)
      };
    }
    if (step.key === "sandbox") {
      return {
        ...card,
        raw: latestExecution ?? null,
        artifactKind: "execution",
        artifactPath: latestExecution?.path,
        artifactLabel: "execution_result.json",
        evidence: executionEvidence(latestExecution)
      };
    }
    if (step.key === "validation") {
      return {
        ...card,
        raw: latestValidation ?? null,
        artifactKind: "validation",
        artifactPath: latestValidation?.path,
        artifactLabel: "validation_result.json",
        evidence: validationEvidence(latestValidation)
      };
    }
    if (step.key === "explanation") {
      return {
        ...card,
        raw: explanationRaw,
        artifactKind: "explanation",
        artifactPath: input.isPredictionWorkflow ? input.job?.prediction_explanation_path : input.job?.explanation_path,
        artifactLabel: input.isPredictionWorkflow ? "prediction_explanation.json" : "explanation.json",
        evidence: explanationEvidence(input.explanation)
      };
    }
    return card;
  }).filter((card) => shouldShowAgentCard(card, input.job));
}

function buildAttemptProgressViews(input: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  events: ExecutionLogEvent[];
}): AttemptProgressView[] {
  const attemptIds = new Set<number>();
  for (const attempt of input.job?.attempts ?? []) {
    if (attempt.attempt) {
      attemptIds.add(attempt.attempt);
    }
  }
  for (const execution of input.log?.execution_results ?? []) {
    if (execution.attempt) {
      attemptIds.add(execution.attempt);
    }
  }
  for (const validation of input.log?.validation_results ?? []) {
    if (validation.attempt) {
      attemptIds.add(validation.attempt);
    }
  }
  for (const event of input.events) {
    if (event.attempt) {
      attemptIds.add(event.attempt);
    }
  }

  return Array.from(attemptIds)
    .sort((left, right) => left - right)
    .map((attemptNumber) => ({
      attempt: attemptNumber,
      codeStatus: latestAttemptStageStatus(input.events, attemptNumber, ["code_generation"]),
      safetyStatus: latestAttemptStageStatus(input.events, attemptNumber, ["code_safety"]),
      sandboxStatus: latestAttemptStageStatus(input.events, attemptNumber, ["sandbox"]),
      validationStatus: latestAttemptStageStatus(input.events, attemptNumber, ["validation"]),
      repairStatus: latestAttemptStageStatus(input.events, attemptNumber, ["repair"]),
      attemptResult: (input.job?.attempts ?? []).find((item) => item.attempt === attemptNumber),
      execution: (input.log?.execution_results ?? []).find((item) => item.attempt === attemptNumber),
      validation: (input.log?.validation_results ?? []).find((item) => item.attempt === attemptNumber)
    }));
}

function latestAttemptStageStatus(events: ExecutionLogEvent[], attempt: number, stages: string[]): string | undefined {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.attempt === attempt && stages.includes(event.stage)) {
      return event.status;
    }
  }
  return undefined;
}

function attemptStageText(status: string | undefined): string {
  if (!status) {
    return "等待中";
  }
  return eventStatusLabel(status);
}

function attemptStageClass(status: string | undefined): string {
  if (status === "success" || status === "fallback") {
    return "done";
  }
  if (status === "running" || status === "retrying") {
    return "active";
  }
  if (status === "failed") {
    return "failed";
  }
  return "pending";
}

function attemptStatusClass(attempt: AttemptProgressView): StepView["status"] {
  if (attempt.validation?.passed) {
    return "done";
  }
  if (attempt.validation && !attempt.validation.passed) {
    return attempt.validation.should_retry ? "active" : "failed";
  }
  if (attempt.sandboxStatus === "failed" || attempt.validationStatus === "failed") {
    return "failed";
  }
  if (attempt.codeStatus || attempt.safetyStatus || attempt.sandboxStatus || attempt.validationStatus) {
    return "active";
  }
  return "pending";
}

function attemptStatusText(attempt: AttemptProgressView): string {
  if (attempt.validation?.passed) {
    return "验证通过";
  }
  if (attempt.validation && !attempt.validation.passed) {
    return attempt.validation.should_retry ? "已反馈修复" : "验证失败";
  }
  if (attempt.validationStatus === "running") {
    return "验证中";
  }
  if (attempt.sandboxStatus === "running") {
    return "执行中";
  }
  if (attempt.safetyStatus === "running") {
    return "安全检查中";
  }
  if (attempt.codeStatus === "running") {
    return "生成中";
  }
  return "等待中";
}

function shouldShowAgentCard(card: AgentCardView, job: WorkflowJobResponse | null): boolean {
  if (!job) {
    return false;
  }
  if (card.key === "visual" && job.asset_type !== "image") {
    return false;
  }
  if (card.status === "active" || card.status === "failed" || card.status === "done") {
    return true;
  }
  if (card.raw !== null && card.raw !== undefined) {
    return true;
  }
  if (card.artifactPath) {
    return true;
  }
  return card.stageNames.includes(job.current_stage ?? "");
}

function cardBase(step: StepView, isPredictionWorkflow: boolean): Omit<AgentCardView, keyof StepView | "output"> {
  const prediction = isPredictionWorkflow;
  const byKey: Record<string, Omit<AgentCardView, keyof StepView | "output">> = {
    visual: {
      agentName: "视觉解析 Agent",
      inputSource: "上传图片或表格输入状态",
      action: "识别图片中的表格、图表和业务字段，并转成结构化数据。",
      evidence: [],
      artifactKind: "visual"
    },
    rag: {
      agentName: "RAG 检索",
      inputSource: "数据画像和用户目标",
      action: "检索业务知识库，给主控和后续 Agent 补充上下文。",
      evidence: [],
      artifactKind: "rag"
    },
    controller: {
      agentName: "主控 Agent",
      inputSource: "用户目标、数据画像和 RAG 上下文",
      action: "判断任务类型，并选择普通数据分析或情景预测工作流。",
      evidence: [],
      artifactKind: "controller"
    },
    understanding: {
      agentName: "数据理解 Agent",
      inputSource: "数据画像与字段样例",
      action: "识别目标字段、维度字段、数值字段和潜在质量问题。",
      evidence: [],
      artifactKind: "understanding"
    },
    analysis: {
      agentName: "分析计划 Agent",
      inputSource: "字段语义、主控计划和用户目标",
      action: "选择统计方法、指标、分组维度和图表计划。",
      evidence: [],
      artifactKind: "analysis"
    },
    hypothesis: {
      agentName: "假设解析 Agent",
      inputSource: "用户的 if/假设/预测问题",
      action: "抽取干预变量、目标指标、对象维度和预测假设。",
      evidence: [],
      artifactKind: "hypothesis"
    },
    prediction_plan: {
      agentName: "预测计划 Agent",
      inputSource: "结构化假设和数据画像",
      action: "选择预测方法、基准口径、影响对象和输出格式。",
      evidence: [],
      artifactKind: "prediction_plan"
    },
    code: {
      agentName: prediction ? "预测 Code Agent" : "代码 Agent",
      inputSource: prediction ? "预测计划" : "分析计划",
      action: "生成可在沙箱中执行的数据处理脚本。",
      evidence: [],
      artifactKind: "code"
    },
    safety: {
      agentName: "代码安全检查",
      inputSource: "生成的 Python 脚本",
      action: "检查危险导入、系统命令、越权路径和不安全操作。",
      evidence: [],
      artifactKind: "code"
    },
    sandbox: {
      agentName: "沙箱执行器",
      inputSource: "通过安全检查的脚本",
      action: "在隔离环境中运行脚本并收集 stdout、stderr、图表和 JSON 产物。",
      evidence: [],
      artifactKind: "execution"
    },
    validation: {
      agentName: prediction ? "预测验证 Agent" : "验证 Agent",
      inputSource: prediction ? "prediction_result.json" : "analysis_result.json",
      action: "检查输出结构、业务合理性、图表产物和是否需要修复。",
      evidence: [],
      artifactKind: "validation"
    },
    explanation: {
      agentName: prediction ? "预测解释 Agent" : "解释 Agent",
      inputSource: "通过验证的结果、图表和限制说明",
      action: "生成面向用户的结论、发现、建议和限制说明。",
      evidence: [],
      artifactKind: "explanation"
    }
  };
  return byKey[step.key] ?? {
    agentName: step.title,
    inputSource: "上一步 Agent 输出",
    action: step.summary,
    evidence: [],
    artifactKind: "generic"
  };
}

function buildAgentSteps(input: {
  job: WorkflowJobResponse | null;
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  visualParseResult: VisualParseResult | null;
  dataUnderstanding: AnyRecord | null;
  analysisPlan: AnyRecord | null;
  executionLog: WorkflowLogResponse | null;
  explanation: ExplanationResult;
  events: ExecutionLogEvent[];
}): StepView[] {
  const currentStage = input.job?.current_stage ?? "";
  const terminalFailed = input.job?.status === "failed";
  const attempts = input.job?.attempts ?? [];
  const attempt = lastItem(attempts);
  const execution = lastItem(input.executionLog?.execution_results);
  const validation = lastItem(input.executionLog?.validation_results);

  const definitions = [
    {
      key: "visual",
      title: "视觉解析 Agent 正在抽取图片数据",
      stageNames: ["visual_parsing"],
      done: Boolean(input.visualParseResult || input.job?.visual_parse_result_path || input.job?.asset_type !== "image"),
      summary: visualSummary(input.visualParseResult, input.job)
    },
    {
      key: "rag",
      title: "RAG 正在检索业务知识库",
      stageNames: ["rag_retrieval"],
      done: Boolean(input.ragRetrieval),
      summary: ragSummary(input.ragRetrieval)
    },
    {
      key: "controller",
      title: "主控 Agent 正在规划",
      stageNames: ["controller"],
      done: Boolean(input.controllerPlan),
      summary: controllerSummary(input.controllerPlan)
    },
    {
      key: "understanding",
      title: "数据理解 Agent 正在识别字段",
      stageNames: ["data_understanding"],
      done: Boolean(input.dataUnderstanding),
      summary: understandingSummary(input.dataUnderstanding)
    },
    {
      key: "analysis",
      title: "分析 Agent 正在选择方法",
      stageNames: ["analysis"],
      done: Boolean(input.analysisPlan),
      summary: analysisSummary(input.analysisPlan)
    },
    {
      key: "code",
      title: "代码 Agent 正在生成脚本",
      stageNames: ["code_generation", "repair"],
      done: Boolean(attempt?.script_path),
      summary: attempt?.script_path ? shortPath(attempt.script_path) : "等待分析计划。"
    },
    {
      key: "safety",
      title: "代码安全检查正在运行",
      stageNames: ["code_safety"],
      done: Boolean(attempt?.safety_issues),
      summary: attempt?.safety_issues?.length
        ? `发现 ${attempt.safety_issues.length} 个安全问题，准备修复。`
        : "检查脚本是否包含危险导入、系统命令或越权路径访问。"
    },
    {
      key: "sandbox",
      title: "沙箱正在执行",
      stageNames: ["sandbox"],
      done: Boolean(execution),
      summary: execution
        ? `执行${execution.success ? "成功" : "失败"}，耗时 ${execution.duration_ms ?? "-"} ms`
        : "等待安全检查通过后执行。"
    },
    {
      key: "validation",
      title: "验证 Agent 正在检查结果",
      stageNames: ["validation"],
      done: Boolean(validation),
      summary: validation
        ? `验证${validation.passed ? "通过" : "未通过"}，严重级别 ${validation.severity}`
        : "等待沙箱产物。"
    },
    {
      key: "explanation",
      title: "解释 Agent 正在生成结论",
      stageNames: ["explanation"],
      done: Boolean(input.explanation.summary),
      summary: input.explanation.summary || "等待验证通过后生成结论。"
    }
  ];

  return definitions.map((definition) => {
    const eventState = latestStageEvent(input.events, definition.stageNames);
    return {
      ...definition,
      status: stepStatus({
        done: definition.done || isDoneEventStatus(eventState?.status),
        active: definition.stageNames.includes(currentStage) || isActiveEventStatus(eventState?.status),
        failed: terminalFailed && (eventState?.status === "failed" || hasFailedEvent(input.events, definition.stageNames))
      })
    };
  });
}

function buildPredictionSteps(input: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  visualParseResult: VisualParseResult | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  predictionResult: PredictionResult | null;
  explanation: PredictionExplanationResult;
  events: ExecutionLogEvent[];
}): StepView[] {
  const currentStage = input.job?.current_stage ?? "";
  const terminalFailed = input.job?.status === "failed";
  const attempt = lastItem(input.job?.attempts);
  const execution = lastItem(input.log?.execution_results);
  const validation = lastItem(input.log?.validation_results);
  const definitions = [
    {
      key: "visual",
      title: "视觉解析 Agent 正在抽取图片数据",
      stageNames: ["visual_parsing"],
      done: Boolean(input.visualParseResult || input.job?.visual_parse_result_path || input.job?.asset_type !== "image"),
      summary: visualSummary(input.visualParseResult, input.job)
    },
    {
      key: "rag",
      title: "RAG 正在检索业务知识库",
      stageNames: ["rag_retrieval"],
      done: Boolean(input.ragRetrieval || input.job?.rag_retrieval_path),
      summary: ragSummary(input.ragRetrieval)
    },
    {
      key: "controller",
      title: "主控 Agent 正在判断工作流",
      stageNames: ["controller"],
      done: Boolean(input.controllerPlan || input.job?.controller_plan_path),
      summary: controllerSummary(input.controllerPlan)
    },
    {
      key: "hypothesis",
      title: "假设解析 Agent 正在解析问题",
      stageNames: ["hypothesis"],
      done: Boolean(input.hypothesisPlan),
      summary: input.hypothesisPlan ? "已识别干预变量、目标指标和对象维度。" : "等待数据画像和 RAG 上下文。"
    },
    {
      key: "prediction_plan",
      title: "预测 Agent 正在选择模型",
      stageNames: ["prediction_plan"],
      done: Boolean(input.predictionPlan),
      summary: input.predictionPlan ? predictionPlanSummary(input.predictionPlan) : "等待结构化假设。"
    },
    {
      key: "code",
      title: "预测 Code Agent 正在生成脚本",
      stageNames: ["code_generation", "repair"],
      done: Boolean(attempt?.script_path),
      summary: attempt?.script_path ? shortPath(attempt.script_path) : "等待预测计划。"
    },
    {
      key: "sandbox",
      title: "沙箱正在执行预测脚本",
      stageNames: ["sandbox"],
      done: Boolean(execution),
      summary: execution ? `执行${execution.success ? "成功" : "失败"}，耗时 ${execution.duration_ms ?? "-"} ms` : "等待安全检查通过。"
    },
    {
      key: "validation",
      title: "预测验证 Agent 正在检查结果",
      stageNames: ["validation"],
      done: Boolean(validation),
      summary: validation ? `验证${validation.passed ? "通过" : "未通过"}，严重级别 ${validation.severity}` : "等待 prediction_result.json。"
    },
    {
      key: "explanation",
      title: "预测解释 Agent 正在生成结论",
      stageNames: ["explanation"],
      done: Boolean(input.explanation.summary),
      summary: input.explanation.summary || "等待预测结果验证通过。"
    }
  ];
  return definitions.map((definition) => {
    const eventState = latestStageEvent(input.events, definition.stageNames);
    return {
      ...definition,
      status: stepStatus({
        done: definition.done || isDoneEventStatus(eventState?.status),
        active: definition.stageNames.includes(currentStage) || isActiveEventStatus(eventState?.status),
        failed: terminalFailed && (eventState?.status === "failed" || hasFailedEvent(input.events, definition.stageNames))
      })
    };
  });
}

function stepStatus(input: { done: boolean; active: boolean; failed: boolean }): StepView["status"] {
  if (input.done) {
    return "done";
  }
  if (input.failed) {
    return "failed";
  }
  if (input.active) {
    return "active";
  }
  return "pending";
}

function hasFailedEvent(events: ExecutionLogEvent[], stages: string[]): boolean {
  return events.some((event) => stages.includes(event.stage) && event.status === "failed");
}

function latestStageEvent(events: ExecutionLogEvent[], stages: string[]): ExecutionLogEvent | undefined {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (stages.includes(event.stage)) {
      return event;
    }
  }
  return undefined;
}

function isActiveEventStatus(status: string | undefined): boolean {
  return status === "running" || status === "retrying";
}

function isDoneEventStatus(status: string | undefined): boolean {
  return status === "success" || status === "fallback" || status === "failed";
}

function visualEvidence(result: VisualParseResult | null, job: WorkflowJobResponse | null): string[] {
  if (job?.asset_type !== "image") {
    return ["输入是表格文件，视觉解析步骤自动跳过。"];
  }
  if (!result) {
    return ["等待豆包视觉模型返回结构化抽取结果。"];
  }
  const evidence = [
    `图片类型：${imageTypeLabel(result.image_type)}`,
    `抽取规模：${result.columns.length} 列、${result.rows.length} 行`,
    `置信度：${Number.isFinite(result.confidence) ? `${Math.round(result.confidence * 100)}%` : "-"}`
  ];
  return [...evidence, ...result.warnings.slice(0, 2)];
}

function ragEvidence(result: AnyRecord | null): string[] {
  if (!result) {
    return ["等待知识库检索结果。"];
  }
  const results = Array.isArray(result.results) ? result.results : [];
  return [`命中知识片段：${results.length} 条`, stringValue(result.message, "已完成知识库检索。")];
}

function controllerEvidence(plan: AnyRecord | null, job: WorkflowJobResponse | null): string[] {
  if (!plan) {
    return ["等待主控 Agent 输出任务类型。"];
  }
  return [
    `任务类型：${stringValue(plan.task_type, stringValue(job?.task_type, "-"))}`,
    `工作流：${workflowLabel(job?.workflow_type || plan.task_type)}`,
    stringValue(plan.reasoning_summary, "已根据用户目标和数据画像完成分流。")
  ];
}

function understandingEvidence(result: AnyRecord | null): string[] {
  if (!result) {
    return ["等待字段语义识别结果。"];
  }
  return [
    `目标字段：${arrayValue(result.target_columns).join("、") || "-"}`,
    `维度字段：${arrayValue(result.dimension_columns).join("、") || "-"}`,
    `质量问题：${arrayValue(result.quality_issues).length} 项`
  ];
}

function analysisEvidence(plan: AnyRecord | null): string[] {
  if (!plan) {
    return ["等待分析计划。"];
  }
  return [
    `分析方法：${arrayValue(plan.methods).join("、") || "-"}`,
    `指标：${arrayValue(plan.metrics).join("、") || "-"}`,
    `图表数量：${Array.isArray(plan.chart_plan) ? plan.chart_plan.length : 0}`
  ];
}

function hypothesisEvidence(plan: AnyRecord | null): string[] {
  if (!plan) {
    return ["等待假设解析。"];
  }
  return [
    `目标指标：${structuredFieldValue(plan.target_metric)}`,
    `对象维度：${structuredFieldValue(plan.entity_dimension)}`,
    `干预变量：${stringValue(plan.intervention_variable, interventionDisplay(plan.intervention))}`
  ];
}

function predictionEvidence(plan: AnyRecord | null): string[] {
  if (!plan) {
    return ["等待预测计划。"];
  }
  return [
    `目标指标：${stringValue(plan.target_metric, "-")}`,
    `对象维度：${stringValue(plan.entity_dimension, "-")}`,
    `干预字段：${interventionDisplay(plan.intervention)}`,
    `候选模型：${arrayValue(plan.model_candidates).join("、") || "-"}`
  ];
}

function attemptEvidence(attempt: AutoRepairAttemptResult | undefined): string[] {
  if (!attempt) {
    return ["等待代码生成。"];
  }
  return [
    `尝试次数：第 ${attempt.attempt} 次`,
    `脚本：${attempt.script_path ? shortPath(attempt.script_path) : "-"}`,
    `当前验证：${attempt.passed ? "通过" : "未通过"}`
  ];
}

function executionEvidence(execution: ExecutionAttemptLog | undefined): string[] {
  if (!execution) {
    return ["等待沙箱执行。"];
  }
  return [
    `执行结果：${execution.success ? "成功" : "失败"}`,
    `退出码：${execution.exit_code ?? "-"}`,
    `耗时：${execution.duration_ms ?? "-"} ms`
  ];
}

function validationEvidence(validation: ValidationAttemptLog | undefined): string[] {
  if (!validation) {
    return ["等待验证 Agent 输出。"];
  }
  return [
    `验证结果：${validation.passed ? "通过" : "未通过"}`,
    `严重级别：${severityLabel(validation.severity)}`,
    `问题数量：${validation.issues.length}`
  ];
}

function explanationEvidence(explanation: ExplanationResult): string[] {
  if (!explanation.summary) {
    return ["等待解释 Agent 生成结论。"];
  }
  return [
    `关键发现：${explanation.key_findings.length} 条`,
    `建议动作：${explanation.recommendations.length} 条`,
    `限制说明：${explanation.limitations.length} 条`
  ];
}

function controllerSummary(plan: AnyRecord | null): string {
  if (!plan) {
    return "等待主控 Agent 判断任务类型。";
  }
  return `${stringValue(plan.task_type, "unknown")}，${stringValue(plan.task_name, "已生成任务计划")}`;
}

function ragSummary(result: AnyRecord | null): string {
  if (!result) {
    return "等待数据画像生成后检索全局知识库。";
  }
  const results = Array.isArray(result.results) ? result.results : [];
  const message = stringValue(result.message, "RAG 检索完成。");
  return results.length ? `命中 ${results.length} 条知识片段。${message}` : message;
}

function visualSummary(result: VisualParseResult | null, job: WorkflowJobResponse | null): string {
  if (job?.asset_type !== "image") {
    return "当前输入是表格数据，无需视觉解析。";
  }
  if (!result) {
    return "等待豆包视觉模型从图片中抽取表格或图表数据。";
  }
  const columnCount = result.columns?.length ?? 0;
  const rowCount = result.rows?.length ?? 0;
  const confidence = Number.isFinite(result.confidence) ? `${Math.round(result.confidence * 100)}%` : "-";
  return result.success
    ? `已抽取 ${columnCount} 列、${rowCount} 行，置信度 ${confidence}。`
    : result.warnings?.[0] || "图片未能抽取出可靠结构化数据。";
}

function understandingSummary(result: AnyRecord | null): string {
  if (!result) {
    return "等待字段语义识别。";
  }
  const targets = arrayValue(result.target_columns);
  const dimensions = arrayValue(result.dimension_columns);
  return `目标字段 ${targets.join("、") || "-"}；维度字段 ${dimensions.slice(0, 4).join("、") || "-"}`;
}

function analysisSummary(plan: AnyRecord | null): string {
  if (!plan) {
    return "等待分析方法选择。";
  }
  const metrics = arrayValue(plan.metrics);
  const methods = arrayValue(plan.methods);
  return `指标 ${metrics.join("、") || "-"}；方法 ${methods.slice(0, 2).join("；") || "-"}`;
}

function predictionPlanSummary(plan: AnyRecord): string {
  const target = stringValue(plan.target_metric, "-");
  const entity = stringValue(plan.entity_dimension, "-");
  const models = arrayValue(plan.model_candidates).slice(0, 2).join("、") || "-";
  return `目标 ${target}；对象 ${entity}；候选模型 ${models}`;
}

function getChartPaths(
  result: Pick<AnalysisResult, "charts"> | Pick<PredictionResult, "charts"> | null,
  job?: WorkflowJobResponse | null,
  fallbackCharts: unknown[] = []
): string[] {
  const candidates = [
    ...(result && Array.isArray(result.charts) ? result.charts : []),
    ...(Array.isArray(job?.chart_paths) ? job.chart_paths : []),
    ...(Array.isArray(fallbackCharts) ? fallbackCharts : [])
  ];

  const normalized = candidates
    .map((chart) => normalizeChartPath(chart, job))
    .filter((path): path is string => Boolean(path));

  return Array.from(new Set(normalized));
}

function normalizeChartPath(chart: unknown, job?: WorkflowJobResponse | null): string | null {
  if (typeof chart === "string") {
    return normalizeChartPathString(chart, job);
  }
  if (!isRecord(chart)) {
    return null;
  }

  const rawPath =
    stringValue(chart.path, "") ||
    stringValue(chart.file_path, "") ||
    stringValue(chart.chart_path, "") ||
    stringValue(chart.url, "") ||
    stringValue(chart.file, "") ||
    stringValue(chart.filename, "");

  return rawPath ? normalizeChartPathString(rawPath, job) : null;
}

function normalizeChartPathString(path: string, job?: WorkflowJobResponse | null): string {
  const normalized = path.replace(/\\/g, "/").trim();
  if (!normalized) {
    return "";
  }
  if (
    normalized.startsWith("/") ||
    normalized.startsWith("http://") ||
    normalized.startsWith("https://") ||
    normalized.includes("storage/")
  ) {
    return normalized;
  }
  if (normalized.startsWith("charts/")) {
    return job?.job_dir ? `${job.job_dir.replace(/\\/g, "/")}/${normalized}` : normalized;
  }
  if (!normalized.includes("/") && job?.job_dir) {
    return `${job.job_dir.replace(/\\/g, "/")}/charts/${normalized}`;
  }
  return normalized;
}

function isRecord(value: unknown): value is AnyRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toExplanationResult(predictionExplanation: PredictionExplanationResult): ExplanationResult {
  return normalizeExplanationResult({
    summary: predictionExplanation.summary,
    key_findings: predictionExplanation.key_findings,
    chart_explanations: [],
    recommendations: predictionExplanation.recommendations,
    limitations: predictionExplanation.limitations,
    ppt_outline: predictionExplanation.ppt_outline
  });
}

function normalizeExplanationResult(value: Partial<ExplanationResult> | null | undefined): ExplanationResult {
  return {
    summary: typeof value?.summary === "string" ? value.summary : "",
    key_findings: normalizeStringArray(value?.key_findings),
    chart_explanations: Array.isArray(value?.chart_explanations) ? value.chart_explanations : [],
    recommendations: normalizeStringArray(value?.recommendations),
    limitations: normalizeStringArray(value?.limitations),
    ppt_outline: normalizePptOutline(value?.ppt_outline)
  };
}

function normalizePptOutline(value: unknown): ExplanationResult["ppt_outline"] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item, index) => {
      if (typeof item === "string") {
        const [title, ...rest] = item.split(/[：:]/);
        return {
          title: title.trim() || `第 ${index + 1} 页`,
          bullets: [rest.join("：").trim() || item.trim()]
        };
      }
      if (item && typeof item === "object") {
        const record = item as Record<string, unknown>;
        const bullets = normalizeStringArray(record.bullets);
        const fallbackText = formatListItem(record.content ?? record.description ?? record.text);
        return {
          title: stringValue(record.title, `第 ${index + 1} 页`),
          bullets: bullets.length ? bullets : fallbackText ? [fallbackText] : [],
          chart: typeof record.chart === "string" ? record.chart : undefined
        };
      }
      return null;
    })
    .filter((item): item is ExplanationResult["ppt_outline"][number] => Boolean(item && item.title));
}

function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => formatListItem(item)).filter(Boolean);
}

function formatListItem(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return localizeUiText(value.trim());
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function chartTitle(path: string, index: number): string {
  const filename = path.replace(/\\/g, "/").split("/").pop();
  return filename || `图表 ${index + 1}`;
}

function statusFromJob(value: string): "idle" | "uploading" | "running" | "success" | "failed" {
  if (value === "success") {
    return "success";
  }
  if (value === "failed") {
    return "failed";
  }
  return "running";
}

function messageFromJob(job: WorkflowJobResponse): string {
  if (job.status === "success") {
    return "分析完成。";
  }
  if (job.status === "failed") {
    return job.error?.message ? String(job.error.message) : "分析失败，请查看执行日志。";
  }
  return `${stageLabel(job.current_stage ?? "running")}，状态实时刷新中。`;
}

function predictionMessageFromJob(job: WorkflowJobResponse): string {
  if (job.status === "success") {
    return "情景预测完成。";
  }
  if (job.status === "failed") {
    return job.error?.message ? String(job.error.message) : "情景预测失败，请查看日志。";
  }
  return `${stageLabel(job.current_stage ?? "running")}，预测状态实时刷新中。`;
}

function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    idle: "待开始",
    uploading: "上传中",
    running: "Agent 运行中",
    success: "已完成",
    failed: "失败"
  };
  return labels[value] ?? value;
}

function stepStatusLabel(value: StepView["status"]): string {
  const labels: Record<StepView["status"], string> = {
    pending: "等待中",
    active: "运行中",
    done: "已完成",
    failed: "失败"
  };
  return labels[value];
}

function workflowLabel(value: unknown): string {
  const text = String(value ?? "");
  if (text === "what_if_prediction") {
    return "情景预测工作流";
  }
  if (text === "auto_repair") {
    return "数据分析工作流";
  }
  if (text) {
    return text;
  }
  return "等待主控分流";
}

function imageTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    table: "表格截图",
    chart: "图表截图",
    dashboard: "业务看板",
    other: "其他图片"
  };
  return labels[value] ?? value;
}

function severityLabel(value: string): string {
  const labels: Record<string, string> = {
    none: "无问题",
    info: "提示",
    low: "低",
    medium: "中",
    high: "高",
    critical: "严重"
  };
  return labels[value] ?? value ?? "-";
}

function stageLabel(value: string): string {
  const labels: Record<string, string> = {
    idle: "待开始",
    pending: "等待启动",
    queued: "任务排队",
    loading_dataset: "读取数据",
    rag_retrieval: "RAG 检索",
    hypothesis: "假设解析",
    prediction_plan: "预测计划",
    controller: "主控规划",
    data_understanding: "字段理解",
    analysis: "分析计划",
    code_generation: "代码生成",
    code_safety: "安全检查",
    sandbox: "沙箱执行",
    validation: "结果验证",
    repair: "脚本修复",
    explanation: "结论生成",
    success: "已完成",
    failed: "失败",
    running: "运行中",
    uploading: "上传中"
  };
  return labels[value] ?? value;
}

function eventStatusLabel(value: string): string {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "运行中",
    success: "已完成",
    failed: "失败",
    fallback: "降级继续",
    retrying: "准备重试"
  };
  return labels[value] ?? value;
}

function mergeWorkflowEvents(
  primary: ExecutionLogEvent[] | undefined,
  secondary: ExecutionLogEvent[] | undefined
): ExecutionLogEvent[] {
  const merged = [...(primary ?? []), ...(secondary ?? [])];
  const seen = new Set<string>();
  return merged
    .filter((event) => {
      const key = `${event.timestamp}|${event.stage}|${event.status}|${event.attempt ?? ""}|${event.message}`;
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    })
    .sort((left, right) => eventTime(left) - eventTime(right));
}

function eventTime(event: ExecutionLogEvent): number {
  const value = new Date(event.timestamp).getTime();
  return Number.isNaN(value) ? 0 : value;
}

function agentInitial(name: string): string {
  if (name.includes("视觉")) {
    return "视";
  }
  if (name.includes("主控")) {
    return "控";
  }
  if (name.includes("预测")) {
    return "预";
  }
  if (name.includes("验证")) {
    return "验";
  }
  if (name.includes("解释")) {
    return "释";
  }
  if (name.includes("代码") || name.includes("Code")) {
    return "码";
  }
  if (name.includes("沙箱")) {
    return "箱";
  }
  if (name.includes("RAG")) {
    return "R";
  }
  return name.slice(0, 1) || "A";
}

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}

function formatPercent(value: number): string {
  return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "-";
}

function stringValue(value: unknown, fallback: string): string {
  if (typeof value === "string" && value) {
    return localizeUiText(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => formatListItem(item)).filter(Boolean) : [];
}

function structuredFieldValue(value: unknown, fallback = "-"): string {
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return stringValue(value, fallback);
  }
  if (value && typeof value === "object") {
    const record = value as AnyRecord;
    return (
      stringValue(record.matched_column, "") ||
      stringValue(record.column, "") ||
      stringValue(record.variable, "") ||
      stringValue(record.raw_text, "") ||
      fallback
    );
  }
  return fallback;
}

function interventionDisplay(value: unknown): string {
  if (!value || typeof value !== "object") {
    return structuredFieldValue(value);
  }
  const record = value as AnyRecord;
  const variable = stringValue(record.variable ?? record.raw_text, "");
  const column = stringValue(record.column ?? record.matched_column, "");
  const changeType = stringValue(record.change_type, "");
  const changeValue = stringValue(record.change_value, "");
  const unit = stringValue(record.unit, "");
  const pieces = [variable || column || "-", column ? `字段：${column}` : "", changeValue ? `${changeType || "变化"} ${changeValue}${unit}` : ""].filter(Boolean);
  return pieces.join("；");
}

function buildNoChartReason(
  isPredictionWorkflow: boolean,
  predictionResult: PredictionResult | null,
  analysisResult: AnalysisResult | null
): string {
  if (isPredictionWorkflow && predictionResult?.status === "unsupported") {
    return stringValue(
      predictionResult.no_chart_reason ?? predictionResult.chart_notice ?? predictionResult.unsupported_reason,
      "当前情景变量字段缺失，无法生成基于预测数值的图表；图表模块无需绘制文字拼装图片。"
    );
  }
  if (isPredictionWorkflow && predictionResult) {
    return stringValue(
      predictionResult.no_chart_reason ?? predictionResult.chart_notice,
      "本次情景预测结果未生成可解释图表，系统仅展示结论报告和执行日志。"
    );
  }
  if (analysisResult) {
    return stringValue(
      analysisResult.no_chart_reason ?? analysisResult.chart_notice,
      "本次分析未生成图表，系统仅展示结论报告和执行日志。"
    );
  }
  return "";
}

function localizeUiText(value: string): string {
  let text = String(value || "").trim();
  if (!text) {
    return "";
  }
  const compact = text.replace(/\s+/g, " ");
  const exact: Record<string, string> = {
    "Knowledge base is empty or no document is indexed.": "知识库为空或尚未索引任何文档。",
    "No column representing floor level(楼层) exists in the dataset. Thus, the direct what-if intervention of changing floor from low to mid-high cannot be modeled. Predictions will be based on available features without this intervention.": "当前数据集中没有表示房源所在楼层高低的字段，因此无法直接模拟“从低层调整为中高层”这一情景。系统不会用其他不等价字段替代该变量。",
    "unsupported_missing_required_column": "缺少情景变量字段"
  };
  if (exact[compact]) {
    return exact[compact];
  }
  const replacements: Array<[RegExp, string]> = [
    [/Knowledge base is empty or no document is indexed\./g, "知识库为空或尚未索引任何文档。"],
    [/unsupported_missing_required_column/g, "缺少情景变量字段"],
    [/linear_regression/g, "线性回归"],
    [/ridge_regression/g, "岭回归"],
    [/rule_based_simulation/g, "规则化模拟"],
    [/random_forest/g, "随机森林"],
    [/No numeric target metric was identified; prediction cannot be computed from the uploaded data\./g, "未识别到可用于预测的数值型目标指标，无法基于当前上传数据计算预测。"],
    [/No entity dimension was identified; only aggregate output can be shown when prediction is supported\./g, "未识别到对象维度；如果其他字段满足预测条件，只能展示总体汇总结果。"]
  ];
  replacements.forEach(([pattern, replacement]) => {
    text = text.replace(pattern, replacement);
  });
  return text;
}

function formatDateTime(value: string): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function shortPath(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts.slice(-3).join("/");
}

function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString();
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function lastItem<T>(items: T[] | undefined): T | undefined {
  if (!items?.length) {
    return undefined;
  }
  return items[items.length - 1];
}
