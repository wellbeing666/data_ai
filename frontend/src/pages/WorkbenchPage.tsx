import { type DragEvent, useEffect, useMemo, useState } from "react";

import {
  createAutoRepairAnalysisJobAsync,
  createPredictionJobAsync,
  createPreflightAssessment,
  createSampleDataset,
  createWorkflowJobAsync,
  deleteWorkflowChart,
  deleteWorkflowJob,
  fetchAnalysisResult,
  fetchAutoRepairAnalysisJobStatus,
  fetchDatasetProfile,
  fetchExecutionLog,
  fetchHealthStatus,
  fetchJsonFile,
  fetchKnowledgeDocuments,
  fetchPredictionJobStatus,
  fetchPredictionLog,
  fetchWorkflowChartSuggestions,
  fetchWorkflowJobs,
  fetchWorkflowJobStatus,
  fetchWorkflowLog,
  generateReport,
  refineWorkflowChart,
  deleteKnowledgeDocument,
  searchKnowledge,
  toStorageUrl,
  uploadKnowledgeDocument,
  uploadDataset
} from "../api";
import type {
  AnalysisRoadmap,
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
  PreflightAssessment,
  QualityReview,
  ReportGenerateResponse,
  SampleDatasetResponse,
  ValidationAttemptLog,
  VisualParseResult,
  WorkflowJobListItem,
  WorkflowJobResponse,
  WorkflowLogResponse
} from "../types";

import {
  ChartPreviewModal,
  ChartsPage,
  HistoryPanel,
  InsightsPage,
  KnowledgePage,
  LogsPage,
  PreflightPanel,
  ProcessPage,
  RoadmapPage,
  SampleDataPanel,
  SamplePreviewModal,
  SetupPage
} from "../components/WorkbenchComponents";
import {
  buildAgentSteps,
  buildPredictionSteps,
  emptyExplanation,
  emptyPredictionExplanation,
  getChartPaths,
  isSupportedAnalysisFile,
  mergeWorkflowEvents,
  messageFromJob,
  normalizeExplanationResult,
  predictionMessageFromJob,
  stageLabel,
  statusFromJob,
  statusLabel,
  terminalStatuses,
  toExplanationResult,
  workflowLabel
} from "../utils/workbenchUtils";
import type { AnyRecord, PageKey } from "../utils/workbenchUtils";

interface SamplePreviewState {
  sample: SampleDatasetResponse;
  profile: DatasetProfile;
  columns: string[];
  rows: AnyRecord[];
}

export function WorkbenchPage() {
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
  const [analysisRoadmap, setAnalysisRoadmap] = useState<AnalysisRoadmap | null>(null);
  const [qualityReview, setQualityReview] = useState<QualityReview | null>(null);
  const [visualParseResult, setVisualParseResult] = useState<VisualParseResult | null>(null);
  const [preflight, setPreflight] = useState<PreflightAssessment | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
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
  const [chartRefreshToken, setChartRefreshToken] = useState(0);
  const [chartPreviewPath, setChartPreviewPath] = useState<string | null>(null);
  const [chartMessage, setChartMessage] = useState("");
  const [chartRefineInstructions, setChartRefineInstructions] = useState<Record<string, string>>({});
  const [chartSuggestions, setChartSuggestions] = useState<Record<string, string[]>>({});
  const [refiningChartPath, setRefiningChartPath] = useState<string | null>(null);
  const [workflowHistory, setWorkflowHistory] = useState<WorkflowJobListItem[]>([]);
  const [selectedHistoryJobIds, setSelectedHistoryJobIds] = useState<string[]>([]);
  const [historyMessage, setHistoryMessage] = useState("");
  const [historySearchQuery, setHistorySearchQuery] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [deletingHistoryJobId, setDeletingHistoryJobId] = useState<string | null>(null);
  const [samplePreview, setSamplePreview] = useState<SamplePreviewState | null>(null);
  const [samplePreviewGoal, setSamplePreviewGoal] = useState("");
  const [samplePreviewLoading, setSamplePreviewLoading] = useState(false);

  useEffect(() => {
    fetchHealthStatus()
      .then(setHealth)
      .catch(() => {
        setHealth({
          status: "unknown",
          llm_mode: "mock/fallback",
          deepseek_configured: false,
          doubao_configured: false,
          message: "当前无法读取智能分析状态。"
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
  const chartPathsKey = chartPaths.join("|");

  useEffect(() => {
    setChartSuggestions({});
  }, [job?.job_id]);

  useEffect(() => {
    if (!job?.job_id || !chartPaths.length) {
      return;
    }

    let cancelled = false;
    const missingChartPaths = chartPaths.filter((chartPath) => !(chartSuggestions[chartPath]?.length));
    if (!missingChartPaths.length) {
      return;
    }

    missingChartPaths.forEach((chartPath) => {
      fetchWorkflowChartSuggestions(job.job_id, chartPath)
        .then((result) => {
          if (!cancelled && result.suggestions?.length) {
            setChartSuggestions((current) => ({
              ...current,
              [chartPath]: result.suggestions
            }));
          }
        })
        .catch(() => {
          // Keep the local rule-based suggestions when the smart suggestion service is unavailable.
        });
    });

    return () => {
      cancelled = true;
    };
  }, [chartPathsKey, chartSuggestions, job?.job_id]);

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
          qualityReview,
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
        qualityReview,
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
      explanation,
      qualityReview
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

  async function refreshWorkflowHistory(query = historySearchQuery) {
    setLoadingHistory(true);
    try {
      const response = await fetchWorkflowJobs(100, query);
      setWorkflowHistory(response.jobs);
      setSelectedHistoryJobIds((current) => current.filter((jobId) => response.jobs.some((item) => item.job_id === jobId)));
      setHistoryMessage("");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "读取历史分析列表失败。");
    } finally {
      setLoadingHistory(false);
    }
  }


  function handleSelectAnalysisFile(file: File | null) {
    setSelectedFile(file);
    setUploadInfo(null);
    setProfile(null);
    setPreflight(null);
    setMessage("");
  }

  async function ensureAnalysisDataset(): Promise<DatasetUploadResponse> {
    if (uploadInfo?.dataset_id && !selectedFile) {
      return uploadInfo;
    }
    if (!selectedFile) {
      throw new Error("请先选择 CSV / Excel 文件、图片，或生成一份样例数据。");
    }
    const uploaded = await uploadDataset(selectedFile);
    setUploadInfo(uploaded);
    if (uploaded.asset_type === "image") {
      setProfile(null);
    } else {
      setProfile(await fetchDatasetProfile(uploaded.dataset_id));
    }
    return uploaded;
  }

  async function handleRunPreflight() {
    const effectiveGoal = userGoal.trim();
    if (!effectiveGoal) {
      setMessage("请输入自然语言分析目标。");
      return;
    }
    setPreflightLoading(true);
    setMessage("AI 正在识别意图并优化分析目标。");
    try {
      const dataset = await ensureAnalysisDataset();
      const result = await createPreflightAssessment(dataset.dataset_id, effectiveGoal);
      setPreflight(result);
      setMessage(result.is_task_clear ? "意图识别完成，已生成更清晰的分析目标。" : "意图识别完成，请先选择关键口径后再分析。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "意图识别失败，请稍后重试。");
    } finally {
      setPreflightLoading(false);
    }
  }

  async function handleGenerateSampleAndRun(sampleType: string) {
    clearCurrentWorkflowView();
    setSelectedFile(null);
    setStatus("uploading");
    setActivePage("setup");
    setSamplePreview(null);
    setSamplePreviewLoading(true);
    setMessage("正在生成演示数据，稍后可先预览再决定是否分析。");
    try {
      const sample = await createSampleDataset(sampleType);
      const datasetProfile = await fetchDatasetProfile(sample.dataset_id);
      const rows = await fetchSampleCsvRows(sample.file_path);
      setUploadInfo(sample);
      setUserGoal(sample.recommended_goal);
      setSamplePreviewGoal(sample.recommended_goal);
      setProfile(datasetProfile);
      setSamplePreview({
        sample,
        profile: datasetProfile,
        columns: datasetProfile.columns,
        rows
      });
      setStatus("idle");
      setMessage("演示数据已生成，请预览确认后再开始分析。");
    } catch (error) {
      setStatus("failed");
      setMessage(error instanceof Error ? error.message : "生成演示数据失败。");
    } finally {
      setSamplePreviewLoading(false);
    }
  }

  async function handleConfirmSampleAnalysis() {
    if (!samplePreview) {
      return;
    }
    const finalGoal = samplePreviewGoal.trim() || samplePreview.sample.recommended_goal;
    clearCurrentWorkflowView();
    setUploadInfo(samplePreview.sample);
    setProfile(samplePreview.profile);
    setUserGoal(finalGoal);
    setSamplePreview(null);
    setStatus("running");
    setActivePage("process");
    setMessage("示例数据已确认，Agent 分析任务已启动。");
    try {
      const createdJob = await createWorkflowJobAsync(samplePreview.sample.dataset_id, finalGoal, 3);
      await applyJobUpdate(createdJob);
    } catch (error) {
      setStatus("failed");
      setMessage(error instanceof Error ? error.message : "分析任务启动失败。");
    }
  }


  function handleCancelSamplePreview() {
    setSamplePreview(null);
    setStatus("idle");
    setMessage("已保留演示数据，您可以调整目标后手动启动分析。");
  }

  async function fetchSampleCsvRows(filePath: string): Promise<AnyRecord[]> {
    const response = await fetch(toStorageUrl(filePath));
    if (!response.ok) {
      throw new Error("演示数据已生成，但暂时无法读取预览内容。");
    }
    const csvText = await response.text();
    return parseCsvPreview(csvText);
  }

  function parseCsvPreview(csvText: string): AnyRecord[] {
    const rows = parseCsvRows(csvText.replace(/^\uFEFF/, ""));
    if (rows.length <= 1) {
      return [];
    }
    const headers = rows[0].map((header, index) => header || `字段${index + 1}`);
    return rows.slice(1).map((row) => {
      const record: AnyRecord = {};
      headers.forEach((header, index) => {
        record[header] = row[index] ?? "";
      });
      return record;
    });
  }

  function parseCsvRows(csvText: string): string[][] {
    const rows: string[][] = [];
    let currentRow: string[] = [];
    let currentValue = "";
    let inQuotes = false;

    for (let index = 0; index < csvText.length; index += 1) {
      const char = csvText[index];
      const nextChar = csvText[index + 1];

      if (char === '"') {
        if (inQuotes && nextChar === '"') {
          currentValue += '"';
          index += 1;
        } else {
          inQuotes = !inQuotes;
        }
        continue;
      }

      if (char === "," && !inQuotes) {
        currentRow.push(currentValue);
        currentValue = "";
        continue;
      }

      if ((char === "\n" || char === "\r") && !inQuotes) {
        if (char === "\r" && nextChar === "\n") {
          index += 1;
        }
        currentRow.push(currentValue);
        if (currentRow.some((value) => value !== "")) {
          rows.push(currentRow);
        }
        currentRow = [];
        currentValue = "";
        continue;
      }

      currentValue += char;
    }

    currentRow.push(currentValue);
    if (currentRow.some((value) => value !== "")) {
      rows.push(currentRow);
    }
    return rows;
  }

  function clearCurrentWorkflowView() {
    setJob(null);
    setExecutionLog(null);
    setAnalysisResult(null);
    setControllerPlan(null);
    setRagRetrieval(null);
    setDataUnderstanding(null);
    setAnalysisPlan(null);
    setAnalysisRoadmap(null);
    setQualityReview(null);
    setVisualParseResult(null);
    setPreflight(null);
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
    setChartRefreshToken(0);
    setChartPreviewPath(null);
    setChartMessage("");
    setChartRefineInstructions({});
    setRefiningChartPath(null);
  }

  async function handleClearHistorySearch() {
    setHistorySearchQuery("");
    await refreshWorkflowHistory("");
  }

  function handleToggleHistorySelection(jobId: string, checked: boolean) {
    setSelectedHistoryJobIds((current) => {
      if (checked) {
        return Array.from(new Set([...current, jobId]));
      }
      return current.filter((item) => item !== jobId);
    });
  }

  function handleToggleSelectAllHistory() {
    const visibleIds = workflowHistory.map((item) => item.job_id);
    const allSelected = visibleIds.length > 0 && visibleIds.every((jobId) => selectedHistoryJobIds.includes(jobId));
    setSelectedHistoryJobIds(allSelected ? [] : visibleIds);
  }

  async function handleDeleteSelectedHistoryJobs() {
    const visibleIds = selectedHistoryJobIds.filter((jobId) => workflowHistory.some((item) => item.job_id === jobId));
    if (!visibleIds.length) {
      setHistoryMessage("请先选择要删除的分析对话。");
      return;
    }
    const confirmed = window.confirm(`确定删除选中的 ${visibleIds.length} 条分析对话吗？删除后将无法在列表中复看这些任务结果。`);
    if (!confirmed) {
      return;
    }
    setHistoryMessage("正在删除选中的分析对话。");
    try {
      for (const jobId of visibleIds) {
        setDeletingHistoryJobId(jobId);
        await deleteWorkflowJob(jobId);
      }
      if (visibleIds.some((jobId) => job?.job_id === jobId || predictionJob?.job_id === jobId)) {
        clearCurrentWorkflowView();
        setStatus("idle");
        setPredictionStatus("idle");
        setMessage("");
        setPredictionMessage("");
        setUploadInfo(null);
        setProfile(null);
        setActivePage("setup");
      }
      setSelectedHistoryJobIds([]);
      setWorkflowHistory((current) => current.filter((item) => !visibleIds.includes(item.job_id)));
      setHistoryMessage("选中的分析对话已删除。");
      await refreshWorkflowHistory();
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "删除选中的分析对话失败。");
    } finally {
      setDeletingHistoryJobId(null);
    }
  }

  async function handleDeleteHistoryJob(jobId: string) {
    const historyItem = workflowHistory.find((item) => item.job_id === jobId) ?? null;
    const displayName = historyItem?.user_goal || historyItem?.dataset_filename || jobId;
    const confirmed = window.confirm(`确定删除“${displayName}”这条分析对话吗？删除后将无法在列表中复看该任务结果。`);
    if (!confirmed) {
      return;
    }

    setDeletingHistoryJobId(jobId);
    setHistoryMessage("正在删除分析对话。");
    try {
      await deleteWorkflowJob(jobId);
      setWorkflowHistory((current) => current.filter((item) => item.job_id !== jobId));
      setSelectedHistoryJobIds((current) => current.filter((item) => item !== jobId));
      if (job?.job_id === jobId || predictionJob?.job_id === jobId) {
        clearCurrentWorkflowView();
        setStatus("idle");
        setPredictionStatus("idle");
        setMessage("");
        setPredictionMessage("");
        setUploadInfo(null);
        setProfile(null);
        setActivePage("setup");
      }
      setHistoryMessage("分析对话已删除。");
      await refreshWorkflowHistory();
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "删除分析对话失败。");
    } finally {
      setDeletingHistoryJobId(null);
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
    setAnalysisRoadmap(null);
    setQualityReview(null);
    setVisualParseResult(null);
    setPreflight(null);
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
    setChartRefreshToken(0);
    setChartPreviewPath(null);
    setChartMessage("");
    setChartRefineInstructions({});
    setRefiningChartPath(null);
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
    setChartRefreshToken(0);
    setChartPreviewPath(null);
    setChartMessage("");
    setChartRefineInstructions({});
    setRefiningChartPath(null);

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
    setJob(nextJob);
    setPredictionJob(nextJob);
    setPredictionStatus(statusFromJob(nextJob.status));
    setPredictionMessage(predictionMessageFromJob(nextJob));

    await Promise.allSettled([
      refreshPredictionLog(nextJob.job_id),
      refreshExecutionLog(nextJob.job_id),
      refreshJsonPath(nextJob.hypothesis_plan_path, setHypothesisPlan),
      refreshJsonPath(nextJob.prediction_plan_path, setPredictionPlan),
      refreshJsonPath(nextJob.analysis_roadmap_path, setAnalysisRoadmap),
      refreshJsonPath(nextJob.quality_review_path, setQualityReview),
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
      handleSelectAnalysisFile(null);
      setMessage("仅支持 CSV、XLSX、XLS、PNG、JPG、JPEG、WEBP 文件。");
      return;
    }

    handleSelectAnalysisFile(file);
  }

  function handleApplyOptimizedGoal(finalGoal: string) {
    const cleanGoal = finalGoal.trim();
    if (!cleanGoal) {
      setMessage("当前没有可应用的优化目标。");
      return;
    }
    setUserGoal(cleanGoal);
    setMessage("已将优化后的分析目标写入任务配置。");
  }

  async function handleApplyOptimizedGoalAndRun(finalGoal: string) {
    const cleanGoal = finalGoal.trim();
    if (!cleanGoal) {
      setMessage("当前没有可应用的优化目标。");
      return;
    }
    setUserGoal(cleanGoal);
    await handleRunAnalysis(cleanGoal);
  }

  async function handleRunAnalysis(goalOverride?: string) {
    const effectiveGoal = (goalOverride ?? userGoal).trim();
    if (!selectedFile && !uploadInfo?.dataset_id) {
      setMessage("请先选择 CSV / Excel 文件、图片，或生成一份样例数据。");
      return;
    }
    if (!effectiveGoal) {
      setMessage("请输入自然语言分析目标。");
      return;
    }

    setStatus("uploading");
    setActivePage("process");
    setMessage("正在准备数据并创建分析任务。");
    setJob(null);
    setExecutionLog(null);
    setAnalysisResult(null);
    setControllerPlan(null);
    setRagRetrieval(null);
    setDataUnderstanding(null);
    setAnalysisPlan(null);
    setAnalysisRoadmap(null);
    setQualityReview(null);
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
    setChartRefreshToken(0);
    setChartPreviewPath(null);
    setChartMessage("");
    setChartRefineInstructions({});
    setRefiningChartPath(null);

    try {
      const uploaded = await ensureAnalysisDataset();
      setUserGoal(effectiveGoal);
      setStatus("running");
      setMessage("任务已启动，Agent 状态将实时刷新。");
      const createdJob = await createWorkflowJobAsync(uploaded.dataset_id, effectiveGoal, 3);
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
      refreshJsonPath(nextJob.analysis_roadmap_path, setAnalysisRoadmap),
      refreshJsonPath(nextJob.quality_review_path, setQualityReview),
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

  function handleChartRefineInstructionChange(chartPath: string, value: string) {
    setChartRefineInstructions((current) => ({
      ...current,
      [chartPath]: value
    }));
  }

  async function runChartRefinement(chartPath: string, instructionText: string) {
    if (!job?.job_id) {
      setChartMessage("请先完成一次分析，再调整图表。");
      return;
    }
    const instruction = instructionText.trim();
    if (!instruction) {
      setChartMessage("请先输入这张图的修改要求，或选择下方推荐选项。");
      return;
    }

    setRefiningChartPath(chartPath);
    setChartMessage("正在根据修改要求重新渲染图表。");
    try {
      const result = await refineWorkflowChart(job.job_id, chartPath, instruction);
      setChartMessage(result.message);
      setChartRefreshToken(Date.now());
      setHiddenChartPaths((current) => current.filter((hiddenPath) => hiddenPath !== chartPath));
      setChartSuggestions((current) => {
        const next = { ...current };
        delete next[chartPath];
        return next;
      });
      if (result.chart_paths?.length) {
        setJob((current) => current && current.job_id === job.job_id ? { ...current, chart_paths: result.chart_paths } : current);
        if (isPredictionWorkflow) {
          setPredictionResult((current) => current ? { ...current, charts: result.chart_paths } : current);
        } else {
          setAnalysisResult((current) => current ? { ...current, charts: result.chart_paths } : current);
        }
      }
      const latest = await fetchWorkflowJobStatus(job.job_id);
      await applyJobUpdate(latest);
      setChartRefreshToken(Date.now());
      setActivePage("charts");
    } catch (error) {
      setChartMessage(error instanceof Error ? error.message : "图表调整失败，请修改要求后重试。");
    } finally {
      setRefiningChartPath(null);
    }
  }

  async function handleRefineChart(chartPath: string) {
    await runChartRefinement(chartPath, chartRefineInstructions[chartPath] ?? "");
  }

  async function handleQuickRefineChart(chartPath: string, instruction: string) {
    setChartRefineInstructions((current) => ({ ...current, [chartPath]: instruction }));
    await runChartRefinement(chartPath, instruction);
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
      setChartRefreshToken(Date.now());
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
                onChange={(event) => handleSelectAnalysisFile(event.target.files?.[0] ?? null)}
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
            <div className="button-row">
              <button
                className="secondary-button"
                type="button"
                disabled={preflightLoading || status === "uploading" || status === "running"}
                onClick={handleRunPreflight}
              >
                {preflightLoading ? "识别中" : "意图识别"}
              </button>
              <button
                className="primary-button"
                type="button"
                disabled={status === "uploading" || status === "running" || samplePreviewLoading}
                onClick={() => handleRunAnalysis()}
              >
                启动 Agent 分析
              </button>
            </div>
            {message ? (
              <p className={`message ${status === "failed" ? "error" : "success"}`}>{message}</p>
            ) : null}
            {preflight ? <PreflightPanel assessment={preflight} onApplyGoal={handleApplyOptimizedGoal} onApplyAndRun={handleApplyOptimizedGoalAndRun} /> : null}
            <SampleDataPanel onGenerate={handleGenerateSampleAndRun} disabled={status === "uploading" || status === "running" || samplePreviewLoading} />
          </section>

          <section className="panel">
            <h2>运行模式</h2>
            {isFallbackMode ? (
              <p className="mode-banner">当前使用规则分析模式</p>
            ) : (
              <p className="mode-banner mode-live">DeepSeek 智能分析已启用</p>
            )}
            <dl className="info-list">
              <div>
                <dt>智能模式</dt>
                <dd>{isFallbackMode ? "规则分析模式" : "DeepSeek 智能分析"}</dd>
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
            activeJobId={job?.job_id ?? predictionJob?.job_id ?? null}
            loading={loadingHistory}
            message={historyMessage}
            searchQuery={historySearchQuery}
            deletingJobId={deletingHistoryJobId}
            selectedJobIds={selectedHistoryJobIds}
            onRefresh={() => refreshWorkflowHistory()}
            onSearchQueryChange={setHistorySearchQuery}
            onSearch={() => refreshWorkflowHistory()}
            onClearSearch={handleClearHistorySearch}
            onToggleSelection={handleToggleHistorySelection}
            onToggleSelectAll={handleToggleSelectAllHistory}
            onDeleteSelected={handleDeleteSelectedHistoryJobs}
            onOpen={handleOpenHistoryJob}
            onDelete={handleDeleteHistoryJob}
          />
        </aside>

        <section className="content-panel">
          <nav className="page-tabs" aria-label="工作台页面">
            {[
              ["setup", "任务配置"],
              ["knowledge", "知识库"],
              ["roadmap", "分析路线图"],
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

          {activePage === "roadmap" ? (
            <RoadmapPage roadmap={analysisRoadmap} job={job} />
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
              qualityReview={qualityReview}
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
              refineInstructions={chartRefineInstructions}
              chartSuggestions={chartSuggestions}
              refiningChartPath={refiningChartPath}
              chartRefreshToken={chartRefreshToken}
              onRefineInstructionChange={handleChartRefineInstructionChange}
              onRefineChart={handleRefineChart}
              onQuickRefineChart={handleQuickRefineChart}
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
      {samplePreview ? (
        <SamplePreviewModal
          sample={samplePreview.sample}
          rowCount={samplePreview.profile.row_count}
          columns={samplePreview.columns}
          rows={samplePreview.rows}
          goal={samplePreviewGoal}
          onGoalChange={setSamplePreviewGoal}
          onConfirm={handleConfirmSampleAnalysis}
          onCancel={handleCancelSamplePreview}
        />
      ) : null}
      {chartPreviewPath ? (
        <ChartPreviewModal
          chartPath={chartPreviewPath}
          chartRefreshToken={chartRefreshToken}
          onClose={() => setChartPreviewPath(null)}
          onDelete={() => handleDeleteChart(chartPreviewPath)}
        />
      ) : null}
    </main>
  );
}



