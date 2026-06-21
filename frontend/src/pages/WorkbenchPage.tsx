import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  applyCleaningPlan,
  controlWorkflowJob,
  createCleaningPlan,
  createPreflightAssessment,
  createSampleDataset,
  createWorkflowFollowUp,
  createWorkflowJobAsync,
  createWorkflowSelectionFollowUp,
  createWorkflowSelectionQuestion,
  deleteKnowledgeDocument,
  deleteWorkflowAgentMessage,
  deleteWorkflowChart,
  deleteWorkflowJob,
  fetchCleaningReport,
  fetchDatasetDataMap,
  fetchDatasetProfile,
  fetchJsonFile,
  fetchKnowledgeDocuments,
  fetchWorkflowAgents,
  fetchWorkflowChartSuggestions,
  fetchWorkflowDashboard,
  fetchWorkflowJobStatus,
  fetchWorkflowJobs,
  fetchWorkflowLog,
  generateReport,
  generateWorkflowPptx,
  refineWorkflowChart,
  refreshWorkflowDashboard,
  saveWorkflowDashboard,
  searchKnowledge,
  toStorageUrl,
  updateWorkflowAgent,
  uploadDataset,
  uploadKnowledgeDocument
} from "../api";
import { DataPulseLoader } from "../components/DataPulseLoader";
import { PPTExportModal } from "../components/PPTExportModal";
import { ToastProvider, useToast } from "../components/ToastContext";
import {
  CleaningPlanModal,
  DashboardPage,
  HistoryPanel,
  InsightsPage,
  KnowledgePage,
  LogsPage,
  PreflightPanel,
  ProcessPage,
  RoadmapPage,
  SampleDataPanel,
  SamplePreviewModal,
  EmptyState
} from "../components/WorkbenchComponents";
import { AgentsPage } from "../components/workbench/AgentsPage";
import { AnalysisIrPage } from "../components/workbench/AnalysisIrPage";
import { ChartPreviewModal } from "../components/workbench/charts/ChartPreviewModal";
import { ChartsPage } from "../components/workbench/ChartsPage";
import { DataMapPage } from "../components/workbench/DataMapPage";
import type {
  AnalysisIR,
  AnalysisResult,
  AnalysisRoadmap,
  AuthUser,
  ChartConfigResponse,
  ChartSelectionSpec,
  CleaningPlanResponse,
  CleaningReportResponse,
  DashboardConfig,
  DatasetDataMap,
  DatasetProfile,
  DatasetUploadResponse,
  DebateReflection,
  EvidenceChain,
  ExplanationResult,
  FollowUpRecommendation,
  KnowledgeDocument,
  KnowledgeSearchResponse,
  PredictionExplanationResult,
  PredictionResult,
  PreflightAssessment,
  QualityReview,
  ReportGenerateResponse,
  SampleDatasetResponse,
  VisualParseResult,
  WorkflowAgentConsoleResponse,
  WorkflowAgentUpdateRequest,
  WorkflowFollowUpResponse,
  WorkflowJobListItem,
  WorkflowJobResponse,
  WorkflowLogResponse,
  WorkflowSelectionQuestionResponse
} from "../types";
import {
  buildAgentSteps,
  buildPredictionSteps,
  emptyExplanation,
  emptyPredictionExplanation,
  getChartPaths,
  isSupportedAnalysisFile,
  statusLabel,
  terminalStatuses,
  workflowLabel
} from "../utils/workbenchUtils";

export type MainTab = "home" | "agent" | "knowledge" | "chat" | "results";
type AgentTab = "process" | "agents" | "ir" | "roadmap" | "logs";
type ResultsTab = "charts" | "dashboard" | "insights" | "datamap";

type SamplePreviewState = {
  sample: SampleDatasetResponse;
  profile: DatasetProfile;
  goal: string;
};

function getDefaultCleaningStrategies(plan: CleaningPlanResponse): Record<string, string> {
  if (plan.recommended_strategy_ids && Object.keys(plan.recommended_strategy_ids).length) {
    return plan.recommended_strategy_ids;
  }
  return Object.fromEntries(
    plan.issues
      .filter((issue) => issue.default_strategy_id)
      .map((issue) => [issue.issue_id, issue.default_strategy_id])
  );
}

export const mainTabs: Array<{ key: MainTab; label: string; icon: string; description: string }> = [
  { key: "home", label: "首页", icon: "⌂", description: "上传数据并配置目标" },
  { key: "agent", label: "Agent 控制台", icon: "✦", description: "查看协作流程和执行日志" },
  { key: "knowledge", label: "知识库", icon: "▣", description: "管理业务知识与检索" },
  { key: "chat", label: "分析对话列表", icon: "✎", description: "查看任务列表和追问入口" },
  { key: "results", label: "结果中心", icon: "◆", description: "图表、报告与数据地图" }
];

const agentTabs: Array<{ key: AgentTab; label: string }> = [
  { key: "process", label: "Agent 过程" },
  { key: "agents", label: "Agent 画像" },
  { key: "ir", label: "分析专用中间表示" },
  { key: "roadmap", label: "分析路线图" },
  { key: "logs", label: "执行日志" }
];

const resultTabs: Array<{ key: ResultsTab; label: string }> = [
  { key: "charts", label: "图表结果" },
  { key: "dashboard", label: "Dashboard" },
  { key: "insights", label: "结论报告" },
  { key: "datamap", label: "数据地图" }
];

export function WorkbenchPage({
  currentUser,
  activeTab,
  onActiveTabChange
}: {
  currentUser: AuthUser;
  activeTab: MainTab;
  onActiveTabChange: (tab: MainTab) => void;
}) {
  return (
    <ToastProvider>
      <WorkbenchPageInner currentUser={currentUser} activeTab={activeTab} onActiveTabChange={onActiveTabChange} />
    </ToastProvider>
  );
}

function WorkbenchPageInner({
  currentUser,
  activeTab,
  onActiveTabChange
}: {
  currentUser: AuthUser;
  activeTab: MainTab;
  onActiveTabChange: (tab: MainTab) => void;
}) {
  const { showToast } = useToast();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const setActiveTab = onActiveTabChange;
  const [agentTab, setAgentTab] = useState<AgentTab>("process");
  const [resultsTab, setResultsTab] = useState<ResultsTab>("charts");
  const [dataset, setDataset] = useState<DatasetUploadResponse | SampleDatasetResponse | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [goal, setGoal] = useState("把这批数据按关键维度统计并生成图表");
  const [insightMode, setInsightMode] = useState(false);
  const [preflight, setPreflight] = useState<PreflightAssessment | null>(null);
  const [samplePreview, setSamplePreview] = useState<SamplePreviewState | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [homeLoading, setHomeLoading] = useState(false);
  const [homeMessage, setHomeMessage] = useState("");
  const [overviewModalOpen, setOverviewModalOpen] = useState(false);
  const [preflightModalOpen, setPreflightModalOpen] = useState(false);

  const [job, setJob] = useState<WorkflowJobResponse | null>(null);
  const [log, setLog] = useState<WorkflowLogResponse | null>(null);
  const [controllerPlan, setControllerPlan] = useState<Record<string, unknown> | null>(null);
  const [ragRetrieval, setRagRetrieval] = useState<Record<string, unknown> | null>(null);
  const [visualParseResult, setVisualParseResult] = useState<VisualParseResult | null>(null);
  const [dataUnderstanding, setDataUnderstanding] = useState<Record<string, unknown> | null>(null);
  const [analysisPlan, setAnalysisPlan] = useState<Record<string, unknown> | null>(null);
  const [analysisIr, setAnalysisIr] = useState<AnalysisIR | null>(null);
  const [analysisRoadmap, setAnalysisRoadmap] = useState<AnalysisRoadmap | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [hypothesisPlan, setHypothesisPlan] = useState<Record<string, unknown> | null>(null);
  const [predictionPlan, setPredictionPlan] = useState<Record<string, unknown> | null>(null);
  const [predictionResult, setPredictionResult] = useState<PredictionResult | null>(null);
  const [explanation, setExplanation] = useState<ExplanationResult>(emptyExplanation);
  const [predictionExplanation, setPredictionExplanation] = useState<PredictionExplanationResult>(emptyPredictionExplanation);
  const [qualityReview, setQualityReview] = useState<QualityReview | null>(null);
  const [evidenceChain, setEvidenceChain] = useState<EvidenceChain | null>(null);
  const [debateReflection, setDebateReflection] = useState<DebateReflection | null>(null);
  const [report, setReport] = useState<ReportGenerateResponse | null>(null);
  const [dashboard, setDashboard] = useState<DashboardConfig | null>(null);
  const [dashboardMessage, setDashboardMessage] = useState("");
  const [dashboardSaving, setDashboardSaving] = useState(false);
  const [dashboardRefreshing, setDashboardRefreshing] = useState(false);
  const [agentConsole, setAgentConsole] = useState<WorkflowAgentConsoleResponse | null>(null);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentMessage, setAgentMessage] = useState("");
  const [dataMap, setDataMap] = useState<DatasetDataMap | null>(null);
  const [dataMapLoading, setDataMapLoading] = useState(false);
  const [dataMapMessage, setDataMapMessage] = useState("");
  const [cleaningPlan, setCleaningPlan] = useState<CleaningPlanResponse | null>(null);
  const [cleaningReport, setCleaningReport] = useState<CleaningReportResponse | null>(null);
  const [selectedCleaningStrategies, setSelectedCleaningStrategies] = useState<Record<string, string>>({});

  const [historyItems, setHistoryItems] = useState<WorkflowJobListItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyMessage, setHistoryMessage] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");
  const [deletingJobId, setDeletingJobId] = useState<string | null>(null);
  const [selectedJobIds, setSelectedJobIds] = useState<string[]>([]);

  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocument[]>([]);
  const [knowledgeFile, setKnowledgeFile] = useState<File | null>(null);
  const [knowledgeQuery, setKnowledgeQuery] = useState("成绩分析的及格率和优秀率口径");
  const [knowledgeResult, setKnowledgeResult] = useState<KnowledgeSearchResponse | null>(null);
  const [knowledgeMessage, setKnowledgeMessage] = useState("");

  const [chartRefreshToken, setChartRefreshToken] = useState(0);
  const [chartMessage, setChartMessage] = useState("");
  const [refineInstructions, setRefineInstructions] = useState<Record<string, string>>({});
  const [chartSuggestions, setChartSuggestions] = useState<Record<string, string[]>>({});
  const [refiningChartPath, setRefiningChartPath] = useState<string | null>(null);
  const [previewChartPath, setPreviewChartPath] = useState<string | null>(null);

  const [controlLoadingAction, setControlLoadingAction] = useState<string | null>(null);
  const [pptGenerating, setPptGenerating] = useState(false);
  const [pptMessage, setPptMessage] = useState("");
  const [pptModalOpen, setPptModalOpen] = useState(false);
  const [followUps, setFollowUps] = useState<WorkflowFollowUpResponse[]>([]);
  const [followUpQuestion, setFollowUpQuestion] = useState("");
  const [followUpLoading, setFollowUpLoading] = useState(false);

  const isPredictionWorkflow = Boolean(
    job?.workflow_type === "what_if_prediction" ||
    job?.task_type === "what_if_prediction" ||
    job?.prediction_plan_path ||
    job?.final_prediction_result_path
  );
  const events = useMemo(() => log?.events?.length ? log.events : job?.events ?? [], [job?.events, log?.events]);
  const chartPaths = useMemo(
    () => getChartPaths(isPredictionWorkflow ? predictionResult : analysisResult, job),
    [analysisResult, isPredictionWorkflow, job, predictionResult]
  );
  const activeExplanation = useMemo<ExplanationResult>(() => {
    if (!isPredictionWorkflow) return explanation;
    return {
      summary: predictionExplanation.summary,
      key_findings: predictionExplanation.key_findings,
      chart_explanations: [],
      recommendations: predictionExplanation.recommendations,
      limitations: predictionExplanation.limitations,
      ppt_outline: predictionExplanation.ppt_outline
    };
  }, [explanation, isPredictionWorkflow, predictionExplanation]);
  const steps = useMemo(() => {
    if (isPredictionWorkflow) {
      return buildPredictionSteps({
        job,
        log,
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
      executionLog: log,
      explanation,
      debateReflection,
      qualityReview,
      events
    });
  }, [analysisPlan, controllerPlan, dataUnderstanding, debateReflection, events, explanation, hypothesisPlan, isPredictionWorkflow, job, log, predictionExplanation, predictionPlan, predictionResult, qualityReview, ragRetrieval, visualParseResult]);

  const pptDownloadPath = report?.pptx_path || job?.pptx_path || null;
  const pptDownloadUrl = pptDownloadPath ? toStorageUrl(pptDownloadPath) : null;

  const loadHistory = useCallback(async (query = historyQuery) => {
    setHistoryLoading(true);
    try {
      const response = await fetchWorkflowJobs(30, query);
      setHistoryItems(response.jobs);
      setHistoryMessage("");
      setSelectedJobIds((current) => current.filter((jobId) => response.jobs.some((item) => item.job_id === jobId)));
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "分析对话列表加载失败，请稍后重试。");
    } finally {
      setHistoryLoading(false);
    }
  }, [historyQuery]);

  const loadKnowledgeDocuments = useCallback(async () => {
    try {
      const response = await fetchKnowledgeDocuments();
      setKnowledgeDocuments(response.documents);
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "知识文档加载失败，请稍后重试。");
    }
  }, []);

  const loadDataMap = useCallback(async (datasetId?: string | null) => {
    const targetDatasetId = datasetId || job?.dataset_id || profile?.dataset_id || dataset?.dataset_id;
    if (!targetDatasetId) return;
    setDataMapLoading(true);
    try {
      const response = await fetchDatasetDataMap(targetDatasetId);
      setDataMap(response.data_map);
      setDataMapMessage(response.message || "数据地图已生成。");
    } catch (error) {
      setDataMapMessage(error instanceof Error ? error.message : "数据地图生成失败，请稍后重试。");
    } finally {
      setDataMapLoading(false);
    }
  }, [dataset?.dataset_id, job?.dataset_id, profile?.dataset_id]);

  const loadAgentConsole = useCallback(async (jobId?: string | null) => {
    const targetJobId = jobId || job?.job_id;
    if (!targetJobId) return;
    setAgentLoading(true);
    try {
      const response = await fetchWorkflowAgents(targetJobId);
      setAgentConsole(response);
      setAgentMessage(response.message || "Agent 状态已同步。");
    } catch (error) {
      setAgentMessage(error instanceof Error ? error.message : "Agent 信息同步失败，请稍后重试。");
    } finally {
      setAgentLoading(false);
    }
  }, [job?.job_id]);

  const resetArtifacts = useCallback(() => {
    setLog(null);
    setControllerPlan(null);
    setRagRetrieval(null);
    setVisualParseResult(null);
    setDataUnderstanding(null);
    setAnalysisPlan(null);
    setAnalysisIr(null);
    setAnalysisRoadmap(null);
    setAnalysisResult(null);
    setHypothesisPlan(null);
    setPredictionPlan(null);
    setPredictionResult(null);
    setExplanation(emptyExplanation);
    setPredictionExplanation(emptyPredictionExplanation);
    setQualityReview(null);
    setEvidenceChain(null);
    setDebateReflection(null);
    setReport(null);
    setDashboard(null);
    setAgentConsole(null);
    setFollowUps([]);
  }, []);

  const fetchOptionalJson = useCallback(async <T,>(path?: string | null): Promise<T | null> => {
    if (!path) return null;
    try {
      return await fetchJsonFile<T>(path);
    } catch {
      return null;
    }
  }, []);

  const loadWorkflowArtifacts = useCallback(async (nextJob: WorkflowJobResponse) => {
    const [
      nextLog,
      nextController,
      nextRag,
      nextVisual,
      nextUnderstanding,
      nextAnalysisPlan,
      nextIr,
      nextRoadmap,
      nextAnalysisResult,
      nextHypothesis,
      nextPredictionPlan,
      nextPredictionResult,
      nextExplanation,
      nextPredictionExplanation,
      nextQuality,
      nextEvidence,
      nextDebate,
      nextPptPreview
    ] = await Promise.all([
      fetchWorkflowLog(nextJob.job_id).catch(() => null),
      fetchOptionalJson<Record<string, unknown>>(nextJob.controller_plan_path),
      fetchOptionalJson<Record<string, unknown>>(nextJob.rag_retrieval_path),
      fetchOptionalJson<VisualParseResult>(nextJob.visual_parse_result_path),
      fetchOptionalJson<Record<string, unknown>>(nextJob.data_understanding_path),
      fetchOptionalJson<Record<string, unknown>>(nextJob.analysis_plan_path),
      fetchOptionalJson<AnalysisIR>(nextJob.analysis_ir_path),
      fetchOptionalJson<AnalysisRoadmap>(nextJob.analysis_roadmap_path),
      fetchOptionalJson<AnalysisResult>(nextJob.final_result_path),
      fetchOptionalJson<Record<string, unknown>>(nextJob.hypothesis_plan_path),
      fetchOptionalJson<Record<string, unknown>>(nextJob.prediction_plan_path),
      fetchOptionalJson<PredictionResult>(nextJob.final_prediction_result_path),
      fetchOptionalJson<ExplanationResult>(nextJob.explanation_path),
      fetchOptionalJson<PredictionExplanationResult>(nextJob.prediction_explanation_path),
      fetchOptionalJson<QualityReview>(nextJob.quality_review_path),
      fetchOptionalJson<EvidenceChain>(nextJob.evidence_chain_path),
      fetchOptionalJson<DebateReflection>(nextJob.debate_reflection_path),
      fetchOptionalJson<{ slides?: unknown[]; pptx_path?: string | null }>(nextJob.pptx_preview_path)
    ]);

    setLog(nextLog);
    setControllerPlan(nextController);
    setRagRetrieval(nextRag);
    setVisualParseResult(nextVisual);
    setDataUnderstanding(nextUnderstanding);
    setAnalysisPlan(nextAnalysisPlan);
    setAnalysisIr(nextIr);
    setAnalysisRoadmap(nextRoadmap);
    setAnalysisResult(nextAnalysisResult);
    setHypothesisPlan(nextHypothesis);
    setPredictionPlan(nextPredictionPlan);
    setPredictionResult(nextPredictionResult);
    setExplanation(nextExplanation || emptyExplanation);
    setPredictionExplanation(nextPredictionExplanation || emptyPredictionExplanation);
    setQualityReview(nextQuality);
    setEvidenceChain(nextEvidence);
    setDebateReflection(nextDebate);
    if (nextPptPreview?.pptx_path && !nextJob.pptx_path) {
      setJob((current) => current?.job_id === nextJob.job_id ? { ...current, pptx_path: nextPptPreview.pptx_path } : current);
    }

    if (nextJob.dataset_id && !profile) {
      const nextProfile = await fetchDatasetProfile(nextJob.dataset_id).catch(() => null);
      if (nextProfile) setProfile(nextProfile);
    }

    if (nextJob.status === "success") {
      const [nextDashboard, nextAgents, nextDataMap] = await Promise.all([
        fetchWorkflowDashboard(nextJob.job_id).catch(() => null),
        fetchWorkflowAgents(nextJob.job_id).catch(() => null),
        nextJob.dataset_id ? fetchDatasetDataMap(nextJob.dataset_id).catch(() => null) : Promise.resolve(null)
      ]);
      if (nextDashboard?.dashboard) setDashboard(nextDashboard.dashboard);
      if (nextAgents) setAgentConsole(nextAgents);
      if (nextDataMap?.data_map) setDataMap(nextDataMap.data_map);
    }
  }, [fetchOptionalJson, profile]);

  const refreshActiveJob = useCallback(async (jobId?: string | null) => {
    const targetJobId = jobId || job?.job_id;
    if (!targetJobId) return;
    const nextJob = await fetchWorkflowJobStatus(targetJobId);
    setJob(nextJob);
    await loadWorkflowArtifacts(nextJob);
  }, [job?.job_id, loadWorkflowArtifacts]);

  useEffect(() => {
    loadKnowledgeDocuments();
    loadHistory("");
  }, []);

  useEffect(() => {
    if (!overviewModalOpen && !preflightModalOpen) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOverviewModalOpen(false);
        setPreflightModalOpen(false);
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [overviewModalOpen, preflightModalOpen]);

  useEffect(() => {
    if (!job?.job_id || terminalStatuses.has(job.status)) return undefined;
    const timer = window.setInterval(() => {
      refreshActiveJob(job.job_id).catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [job?.job_id, job?.status, refreshActiveJob]);

  const handleFileSelected = async (selectedFile: File) => {
    if (!isSupportedAnalysisFile(selectedFile)) {
      setHomeMessage("当前文件类型暂不支持，请选择 CSV、Excel 或常见图片文件。");
      return;
    }
    setHomeLoading(true);
    setHomeMessage("正在读取数据文件...");
    setFile(selectedFile);
    setPreflight(null);
    setPreflightModalOpen(false);
    setCleaningPlan(null);
    setCleaningReport(null);
    setSelectedCleaningStrategies({});
    resetArtifacts();
    try {
      const uploaded = await uploadDataset(selectedFile);
      setDataset(uploaded);
      const nextProfile = await fetchDatasetProfile(uploaded.dataset_id).catch(() => null);
      setProfile(nextProfile);
      if (uploaded.asset_type === "image") {
        setHomeMessage("图片已接收，启动分析后将先进行视觉解析。");
      } else {
        setHomeMessage("数据文件已就绪，可以继续确认分析目标。");
        try {
          const plan = await createCleaningPlan(uploaded.dataset_id);
          setCleaningPlan(plan);
          setSelectedCleaningStrategies(getDefaultCleaningStrategies(plan));
        } catch {
          setHomeMessage("数据文件已就绪，可以直接启动分析；暂未生成数据修复建议。");
        }
      }
      showToast("数据文件已就绪", "success");
    } catch (error) {
      setHomeMessage(error instanceof Error ? error.message : "文件读取失败，请更换文件后重试。");
      showToast("数据文件读取失败", "error");
    } finally {
      setHomeLoading(false);
    }
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    const selectedFile = event.dataTransfer.files?.[0];
    if (selectedFile) handleFileSelected(selectedFile);
  };

  const handleCreateSample = async (sampleType: string) => {
    setHomeLoading(true);
    setHomeMessage("正在准备示例数据...");
    try {
      const sample = await createSampleDataset(sampleType);
      const sampleProfile = await fetchDatasetProfile(sample.dataset_id);
      setSamplePreview({ sample, profile: sampleProfile, goal: sample.recommended_goal });
      setHomeMessage("示例数据已生成，请预览后选择是否启动分析。");
    } catch (error) {
      setHomeMessage(error instanceof Error ? error.message : "示例数据生成失败，请稍后重试。");
    } finally {
      setHomeLoading(false);
    }
  };

  const applySamplePreview = (preview: SamplePreviewState) => {
    setDataset(preview.sample);
    setProfile(preview.profile);
    setGoal(preview.goal);
    setFile(null);
    setPreflight(null);
    setPreflightModalOpen(false);
    setCleaningPlan(null);
    setCleaningReport(null);
    setSelectedCleaningStrategies({});
    setSamplePreview(null);
    resetArtifacts();
    setHomeMessage("示例数据已选中，可以继续调整分析目标。");
  };

  const startWorkflow = async (nextGoal = goal) => {
    if (!dataset?.dataset_id) {
      setHomeMessage("请先上传数据文件或选择示例数据。");
      return;
    }
    const effectiveGoal = nextGoal.trim() || "请自动识别数据中的关键洞察，并生成图表和报告。";
    setHomeLoading(true);
    setHomeMessage("正在启动多 Agent 分析任务...");
    resetArtifacts();
    try {
      const createdJob = await createWorkflowJobAsync(dataset.dataset_id, effectiveGoal, 3, insightMode || !nextGoal.trim());
      setJob(createdJob);
      setActiveTab("agent");
      setAgentTab("process");
      setHomeMessage("任务已启动，Agent 正在接管流程。");
      showToast("Agent 分析任务已启动", "success");
      loadHistory("");
      await loadWorkflowArtifacts(createdJob);
    } catch (error) {
      setHomeMessage(error instanceof Error ? error.message : "任务启动失败，请稍后重试。");
      showToast("任务启动失败", "error");
    } finally {
      setHomeLoading(false);
    }
  };

  const handlePreflight = async () => {
    if (!dataset?.dataset_id) {
      setHomeMessage("请先上传数据文件或选择示例数据。");
      return;
    }
    const trimmedGoal = goal.trim();
    if (!trimmedGoal) {
      setHomeMessage("请输入分析目标，或勾选智能洞察模式后直接启动分析。");
      return;
    }
    setHomeLoading(true);
    setHomeMessage("正在识别分析意图...");
    try {
      const assessment = await createPreflightAssessment(dataset.dataset_id, trimmedGoal);
      setPreflight(assessment);
      setPreflightModalOpen(true);
      setHomeMessage("意图识别完成，请确认优化后的目标。");
      showToast("意图识别完成", "success");
    } catch (error) {
      setHomeMessage(error instanceof Error ? error.message : "意图识别失败，请稍后重试。");
    } finally {
      setHomeLoading(false);
    }
  };

  const handleOpenJob = async (jobId: string) => {
    setHistoryLoading(true);
    setHistoryMessage("正在载入分析对话...");
    resetArtifacts();
    try {
      const nextJob = await fetchWorkflowJobStatus(jobId);
      setJob(nextJob);
      setGoal(nextJob.user_goal || goal);
      setActiveTab("agent");
      setAgentTab("process");
      await loadWorkflowArtifacts(nextJob);
      setHistoryMessage("");
      showToast("分析对话已载入", "success");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "分析对话载入失败，请稍后重试。");
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    setDeletingJobId(jobId);
    try {
      await deleteWorkflowJob(jobId);
      if (job?.job_id === jobId) {
        setJob(null);
        resetArtifacts();
      }
      setSelectedJobIds((current) => current.filter((id) => id !== jobId));
      await loadHistory(historyQuery);
      showToast("分析对话已删除", "success");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "删除失败，请稍后重试。");
    } finally {
      setDeletingJobId(null);
    }
  };

  const handleDeleteSelectedJobs = async () => {
    const ids = selectedJobIds.filter((id) => historyItems.some((item) => item.job_id === id));
    if (!ids.length) return;
    setHistoryLoading(true);
    try {
      for (const id of ids) {
        await deleteWorkflowJob(id);
      }
      if (job?.job_id && ids.includes(job.job_id)) {
        setJob(null);
        resetArtifacts();
      }
      setSelectedJobIds([]);
      await loadHistory(historyQuery);
      showToast("已删除选中的分析对话", "success");
    } catch (error) {
      setHistoryMessage(error instanceof Error ? error.message : "批量删除失败，请稍后重试。");
    } finally {
      setHistoryLoading(false);
    }
  };

  const handleKnowledgeUpload = async () => {
    if (!knowledgeFile) {
      setKnowledgeMessage("请选择 TXT 或 Markdown 文档。");
      return;
    }
    setKnowledgeMessage("正在写入知识库...");
    try {
      await uploadKnowledgeDocument(knowledgeFile);
      setKnowledgeFile(null);
      await loadKnowledgeDocuments();
      setKnowledgeMessage("知识文档已写入，后续分析会优先参考相关片段。");
      showToast("知识文档已写入", "success");
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "知识文档写入失败，请稍后重试。");
    }
  };

  const handleKnowledgeSearch = async () => {
    if (!knowledgeQuery.trim()) {
      setKnowledgeMessage("请输入要检索的业务问题。");
      return;
    }
    setKnowledgeMessage("正在检索知识库...");
    try {
      const result = await searchKnowledge(knowledgeQuery, 5);
      setKnowledgeResult(result);
      setKnowledgeMessage(result.message || "检索完成。");
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "知识库检索失败，请稍后重试。");
    }
  };

  const handleKnowledgeDelete = async (docId: string) => {
    try {
      await deleteKnowledgeDocument(docId);
      await loadKnowledgeDocuments();
      showToast("知识文档已删除", "success");
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "知识文档删除失败，请稍后重试。");
    }
  };

  const handleControlJob = async (action: string) => {
    if (!job?.job_id) return;
    setControlLoadingAction(action);
    try {
      const response = await controlWorkflowJob(job.job_id, action);
      showToast(response.message || "任务控制指令已提交", response.accepted ? "success" : "warning");
      await refreshActiveJob(job.job_id);
    } catch (error) {
      showToast(error instanceof Error ? error.message : "任务控制失败，请稍后重试。", "error");
    } finally {
      setControlLoadingAction(null);
    }
  };

  const handleGenerateReport = async () => {
    const resultPath = job?.final_result_path;
    if (!resultPath) return;
    setPptGenerating(true);
    setPptModalOpen(true);
    setPptMessage("正在生成 Markdown 与 PPTX 报告...");
    try {
      const generated = await generateReport(resultPath, chartPaths);
      setReport(generated);
      setPptMessage("报告已生成，可以下载 PPTX 文件。");
      showToast("报告生成完成", "success");
    } catch (error) {
      setPptMessage(error instanceof Error ? error.message : "报告生成失败，请稍后重试。");
      showToast("报告生成失败", "error");
    } finally {
      setPptGenerating(false);
    }
  };

  const handleGenerateWorkflowPptx = async () => {
    if (!job?.job_id) {
      await handleGenerateReport();
      return;
    }
    setPptGenerating(true);
    setPptModalOpen(true);
    setPptMessage("正在生成 PPTX 报告...");
    try {
      const response = await generateWorkflowPptx(job.job_id);
      setJob((current) => current?.job_id === job.job_id ? { ...current, pptx_path: response.pptx_path || current.pptx_path, pptx_preview_path: response.pptx_preview_path || current.pptx_preview_path } : current);
      setPptMessage(response.message || "PPTX 报告已生成。");
      showToast("PPTX 报告已生成", "success");
    } catch (error) {
      setPptMessage(error instanceof Error ? error.message : "PPTX 报告生成失败，请稍后重试。");
      showToast("PPTX 报告生成失败", "error");
    } finally {
      setPptGenerating(false);
    }
  };

  const handleDashboardSave = async () => {
    if (!job?.job_id || !dashboard) return;
    setDashboardSaving(true);
    try {
      const response = await saveWorkflowDashboard(job.job_id, dashboard);
      setDashboard(response.dashboard);
      setDashboardMessage(response.message || "Dashboard 已保存。");
      showToast("Dashboard 已保存", "success");
    } catch (error) {
      setDashboardMessage(error instanceof Error ? error.message : "Dashboard 保存失败，请稍后重试。");
    } finally {
      setDashboardSaving(false);
    }
  };

  const handleDashboardRefresh = async () => {
    if (!job?.job_id) return;
    setDashboardRefreshing(true);
    try {
      const response = await refreshWorkflowDashboard(job.job_id);
      setDashboard(response.dashboard);
      setDashboardMessage(response.message || "Dashboard 已刷新。");
      setChartRefreshToken((value) => value + 1);
      showToast("Dashboard 已刷新", "success");
    } catch (error) {
      setDashboardMessage(error instanceof Error ? error.message : "Dashboard 刷新失败，请稍后重试。");
    } finally {
      setDashboardRefreshing(false);
    }
  };

  const handleRefineChart = async (chartPath: string, instruction?: string) => {
    if (!job?.job_id) return;
    const finalInstruction = (instruction ?? refineInstructions[chartPath] ?? "").trim();
    if (!finalInstruction) {
      setChartMessage("请先输入图表修改要求。");
      return;
    }
    setRefiningChartPath(chartPath);
    setChartMessage("正在重新渲染图表...");
    try {
      const response = await refineWorkflowChart(job.job_id, chartPath, finalInstruction);
      setJob((current) => current?.job_id === job.job_id ? { ...current, chart_paths: response.chart_paths } : current);
      setChartRefreshToken((value) => value + 1);
      setChartMessage(response.message || "图表已重新渲染。");
      showToast("图表已重新渲染", "success");
      await refreshActiveJob(job.job_id);
    } catch (error) {
      setChartMessage(error instanceof Error ? error.message : "图表重绘失败，请调整要求后重试。");
    } finally {
      setRefiningChartPath(null);
    }
  };

  const handleFetchChartSuggestions = async (chartPath: string) => {
    if (!job?.job_id || chartSuggestions[chartPath]?.length) return;
    try {
      const response = await fetchWorkflowChartSuggestions(job.job_id, chartPath);
      setChartSuggestions((current) => ({ ...current, [chartPath]: response.suggestions }));
    } catch {
      // 使用本地推荐项兜底。
    }
  };

  const handleDeleteChart = async (chartPath: string) => {
    if (!job?.job_id) return;
    try {
      const response = await deleteWorkflowChart(job.job_id, chartPath);
      setJob((current) => current?.job_id === job.job_id ? { ...current, chart_paths: response.chart_paths } : current);
      setPreviewChartPath(null);
      setChartRefreshToken((value) => value + 1);
      setChartMessage("图表已删除。");
      showToast("图表已删除", "success");
    } catch (error) {
      setChartMessage(error instanceof Error ? error.message : "图表删除失败，请稍后重试。");
    }
  };

  const handleCompileSelection = async (_chartPath: string, selectionSpec: ChartSelectionSpec): Promise<WorkflowSelectionQuestionResponse> => {
    if (!job?.job_id) throw new Error("请先打开一个分析任务。");
    return createWorkflowSelectionQuestion(job.job_id, selectionSpec);
  };

  const handleSubmitSelectionFollowUp = async (_chartPath: string, selectionSpec: ChartSelectionSpec, question: string): Promise<WorkflowFollowUpResponse> => {
    if (!job?.job_id) throw new Error("请先打开一个分析任务。");
    const response = await createWorkflowSelectionFollowUp(job.job_id, selectionSpec, question);
    setFollowUps((current) => [response, ...current]);
    showToast("图表追问已生成", "success");
    return response;
  };

  const handleFollowUp = async () => {
    if (!job?.job_id || !followUpQuestion.trim()) return;
    setFollowUpLoading(true);
    try {
      const response = await createWorkflowFollowUp(job.job_id, followUpQuestion.trim());
      setFollowUps((current) => [response, ...current]);
      setFollowUpQuestion("");
      showToast("追问回答已生成", "success");
    } catch (error) {
      showToast(error instanceof Error ? error.message : "追问生成失败，请稍后重试。", "error");
    } finally {
      setFollowUpLoading(false);
    }
  };

  const handleRefreshAgents = async () => {
    await loadAgentConsole(job?.job_id);
  };

  const handleUpdateAgent = async (agentId: string, updates: WorkflowAgentUpdateRequest) => {
    if (!job?.job_id) return;
    try {
      const response = await updateWorkflowAgent(job.job_id, agentId, updates);
      setAgentConsole(response);
      showToast("Agent 信息已更新", "success");
    } catch (error) {
      setAgentMessage(error instanceof Error ? error.message : "Agent 更新失败，请稍后重试。");
    }
  };

  const handleDeleteAgentMessage = async (agentId: string, messageId: string) => {
    if (!job?.job_id) return;
    try {
      const response = await deleteWorkflowAgentMessage(job.job_id, agentId, messageId);
      setAgentConsole(response);
      showToast("Agent 输出已删除", "success");
    } catch (error) {
      setAgentMessage(error instanceof Error ? error.message : "Agent 输出删除失败，请稍后重试。");
    }
  };

  const handleCreateCleaningPlan = async () => {
    if (!dataset?.dataset_id) return;
    setHomeLoading(true);
    try {
      const plan = await createCleaningPlan(dataset.dataset_id);
      setCleaningPlan(plan);
      setSelectedCleaningStrategies(getDefaultCleaningStrategies(plan));
    } catch (error) {
      setHomeMessage(error instanceof Error ? error.message : "数据修复方案生成失败，请稍后重试。");
    } finally {
      setHomeLoading(false);
    }
  };

  const handleApplyCleaningPlan = async (selectedStrategies: Record<string, string>) => {
    if (!dataset?.dataset_id) return;
    setHomeLoading(true);
    try {
      const response = await applyCleaningPlan(dataset.dataset_id, selectedStrategies);
      setCleaningReport(response);
      const updatedProfile = await fetchDatasetProfile(dataset.dataset_id).catch(() => null);
      if (updatedProfile) setProfile(updatedProfile);
      setCleaningPlan(null);
      showToast("数据修复已应用", "success");
    } catch (error) {
      setHomeMessage(error instanceof Error ? error.message : "数据修复失败，请稍后重试。");
    } finally {
      setHomeLoading(false);
    }
  };

  const handleFetchCleaningReport = async () => {
    if (!dataset?.dataset_id) return;
    try {
      const response = await fetchCleaningReport(dataset.dataset_id);
      setCleaningReport(response);
      showToast("数据修复报告已同步", "success");
    } catch (error) {
      setHomeMessage(error instanceof Error ? error.message : "数据修复报告同步失败，请稍后重试。");
    }
  };

  const renderHome = () => (
    <div className="quest-home-grid interactive-workbench-grid">
      <section className="quest-card quest-hero-card">
        <div className="quest-hero-copy">
          <p className="eyebrow">AI 原生数据分析工作台</p>
          <h2>多Agent协作系统，帮您一键处理数据</h2>
          <p>上传表格或图片，确认分析目标，系统会自动完成意图识别、数据理解、代码执行、图表生成和报告输出。</p>
          <div className="quest-hero-actions">
            <button className="primary-button" type="button" onClick={() => fileInputRef.current?.click()} disabled={homeLoading}>
              选择数据文件
            </button>
            <button className="secondary-button" type="button" onClick={() => setInsightMode((value) => !value)}>
              {insightMode ? "智能洞察已开启" : "开启智能洞察"}
            </button>
          </div>
        </div>
        <div className="data-spirit" aria-hidden="true">
          <span className="spirit-orbit" />
          <span className="spirit-core" />
          <span className="spirit-eye left" />
          <span className="spirit-eye right" />
        </div>
      </section>

      <section className="interactive-section sample-data-section sample-card-wrap">
        <SampleDataPanel onGenerate={handleCreateSample} disabled={homeLoading} />
      </section>

      <div className="grid-layout-bottom config-only-layout">
        <div className="quest-left-panel">
          <section className="interactive-section task-config-section upload-command-card">
            <div className="section-header compact-heading">
              <h2>任务配置</h2>
              <p>上传数据、确认目标并启动分析流程</p>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls,.png,.jpg,.jpeg,.webp"
              onChange={(event) => {
                const selectedFile = event.target.files?.[0];
                if (selectedFile) handleFileSelected(selectedFile);
                event.currentTarget.value = "";
              }}
              hidden
            />
            <div className="config-form">
              <div className="form-group focus-effect">
                <label>数据源选择</label>
                <div
                  className={`file-upload-area quest-upload-zone ${dragActive ? "drag-active" : ""}`}
                  onDragEnter={(event) => { event.preventDefault(); setDragActive(true); }}
                  onDragOver={(event) => { event.preventDefault(); setDragActive(true); }}
                  onDragLeave={(event) => { event.preventDefault(); setDragActive(false); }}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") fileInputRef.current?.click();
                  }}
                >
                  {homeLoading ? (
                    <DataPulseLoader text="数据读取中..." />
                  ) : (
                    <div className="upload-content">
                      <span className="upload-orb" aria-hidden="true" />
                      <strong>{dataset?.filename || file?.name || "选择数据文件或图片"}</strong>
                      <p>支持点击选择或拖拽上传。图片会先抽取结构化数据，再进入分析流程。</p>
                    </div>
                  )}
                </div>
              </div>
              <div className="form-group focus-effect">
                <label htmlFor="analysis-goal">分析目标</label>
                <textarea id="analysis-goal" rows={5} value={goal} onChange={(event) => setGoal(event.target.value)} placeholder="例如：把这批 Excel 成绩按班级统计并生成图表" />
              </div>
              <div className="quest-action-row">
                <button className="secondary-button" type="button" disabled={homeLoading || !dataset} onClick={handlePreflight}>
                  意图识别
                </button>
                <button className="primary-button" type="button" disabled={homeLoading || !dataset} onClick={() => startWorkflow(goal)}>
                  启动 Agent 分析
                </button>
              </div>
              <div className="quest-action-row subtle-row task-footer-actions">
                <button className="text-button" type="button" disabled={homeLoading || !dataset} onClick={handleCreateCleaningPlan}>生成数据修复方案</button>
                <button className="text-button" type="button" disabled={homeLoading || !dataset} onClick={handleFetchCleaningReport}>同步修复报告</button>
                <button className="text-button" type="button" disabled={homeLoading || !profile} onClick={() => setOverviewModalOpen(true)}>数据概览</button>
              </div>
              <label className="insight-switch">
                <input type="checkbox" checked={insightMode} onChange={(event) => setInsightMode(event.target.checked)} />
                不提交分析目标，进入智能洞察
              </label>
              {homeMessage ? <p className="message success">{homeMessage}</p> : null}
              {cleaningReport ? <p className="message success">{cleaningReport.message}</p> : null}
            </div>
          </section>
        </div>
      </div>
    </div>
  );

  const renderAgent = () => (
    <div className="content-panel quest-content-panel">
      <div className="page-tabs quest-subtabs" role="tablist" aria-label="Agent 控制台导航">
        {agentTabs.map((tab) => (
          <button key={tab.key} className={agentTab === tab.key ? "active" : ""} type="button" onClick={() => setAgentTab(tab.key)}>
            {tab.label}
          </button>
        ))}
      </div>
      {agentTab === "process" ? (
        <>
          <ProcessPage
            job={job}
            log={log}
            steps={steps}
            controllerPlan={controllerPlan}
            ragRetrieval={ragRetrieval}
            visualParseResult={visualParseResult}
            dataUnderstanding={dataUnderstanding}
            analysisPlan={analysisPlan}
            hypothesisPlan={hypothesisPlan}
            predictionPlan={predictionPlan}
            explanation={activeExplanation}
            debateReflection={debateReflection}
            qualityReview={qualityReview}
            isPredictionWorkflow={isPredictionWorkflow}
            events={events}
            onControlJob={handleControlJob}
            controlLoadingAction={controlLoadingAction}
          />
        </>
      ) : null}
      {agentTab === "agents" ? (
        <AgentsPage
          agentConsole={agentConsole}
          job={job}
          loading={agentLoading}
          message={agentMessage}
          canManageAgents={currentUser.role === "admin"}
          onRefresh={handleRefreshAgents}
          onUpdateAgent={handleUpdateAgent}
          onDeleteMessage={handleDeleteAgentMessage}
        />
      ) : null}
      {agentTab === "ir" ? <AnalysisIrPage analysisIr={analysisIr} job={job} /> : null}
      {agentTab === "roadmap" ? <RoadmapPage roadmap={analysisRoadmap} job={job} /> : null}
      {agentTab === "logs" ? <LogsPage job={job} log={log} events={events} /> : null}
    </div>
  );

  const renderResults = () => (
    <div className="content-panel quest-content-panel">
      <div className="page-tabs quest-subtabs" role="tablist" aria-label="结果中心导航">
        {resultTabs.map((tab) => (
          <button key={tab.key} className={resultsTab === tab.key ? "active" : ""} type="button" onClick={() => setResultsTab(tab.key)}>
            {tab.label}
          </button>
        ))}
      </div>
      {resultsTab === "charts" ? (
        <ChartsPage
          analysisResult={analysisResult}
          chartPaths={chartPaths}
          job={job}
          predictionResult={predictionResult}
          isPredictionWorkflow={isPredictionWorkflow}
          message={chartMessage}
          refineInstructions={refineInstructions}
          chartSuggestions={chartSuggestions}
          refiningChartPath={refiningChartPath}
          chartRefreshToken={chartRefreshToken}
          onRefineInstructionChange={(chartPath, value) => {
            setRefineInstructions((current) => ({ ...current, [chartPath]: value }));
            handleFetchChartSuggestions(chartPath);
          }}
          onRefineChart={(chartPath) => handleRefineChart(chartPath)}
          onQuickRefineChart={(chartPath, instruction) => {
            setRefineInstructions((current) => ({ ...current, [chartPath]: instruction }));
            handleRefineChart(chartPath, instruction);
          }}
          onOpenChart={(chartPath) => setPreviewChartPath(chartPath)}
          onDeleteChart={handleDeleteChart}
        />
      ) : null}
      {resultsTab === "dashboard" ? (
        <DashboardPage
          dashboard={dashboard}
          job={job}
          chartRefreshToken={chartRefreshToken}
          message={dashboardMessage}
          saving={dashboardSaving}
          refreshing={dashboardRefreshing}
          onDashboardChange={setDashboard}
          onSave={handleDashboardSave}
          onRefresh={handleDashboardRefresh}
        />
      ) : null}
      {resultsTab === "insights" ? (
        <InsightsPage
          explanation={activeExplanation}
          report={report}
          job={job}
          evidenceChain={evidenceChain}
          debateReflection={debateReflection}
          followUpRecommendations={[]}
          followUps={followUps}
          followUpQuestion={followUpQuestion}
          followUpLoading={followUpLoading}
          pptGenerating={pptGenerating}
          pptMessage={pptMessage}
          onGeneratePptx={handleGenerateWorkflowPptx}
          onFollowUpQuestionChange={setFollowUpQuestion}
          onSubmitFollowUp={handleFollowUp}
        />
      ) : null}
      {resultsTab === "datamap" ? (
        <DataMapPage
          dataMap={dataMap}
          profile={profile}
          loading={dataMapLoading}
          message={dataMapMessage}
          onRefresh={() => loadDataMap()}
          onUseQuestion={(question) => {
            setGoal(question);
            setActiveTab("home");
          }}
        />
      ) : null}
    </div>
  );

  const renderChat = () => (
    <div className="content-panel quest-content-panel">
      <div className="section-heading dashboard-heading">
        <div>
          <h2>分析对话列表</h2>
          <span>打开历史任务后，可以在结论报告中继续发起追问。</span>
        </div>
        <button className="secondary-button" type="button" onClick={() => loadHistory(historyQuery)} disabled={historyLoading}>
          {historyLoading ? "同步中" : "刷新列表"}
        </button>
      </div>
      <div className="chat-workspace-grid">
        <HistoryPanel
          items={historyItems}
          activeJobId={job?.job_id || null}
          loading={historyLoading}
          message={historyMessage}
          searchQuery={historyQuery}
          deletingJobId={deletingJobId}
          selectedJobIds={selectedJobIds}
          onRefresh={() => loadHistory(historyQuery)}
          onSearchQueryChange={setHistoryQuery}
          onSearch={() => loadHistory(historyQuery)}
          onClearSearch={() => { setHistoryQuery(""); loadHistory(""); }}
          onToggleSelection={(jobId, checked) => setSelectedJobIds((current) => checked ? Array.from(new Set([...current, jobId])) : current.filter((id) => id !== jobId))}
          onToggleSelectAll={() => setSelectedJobIds((current) => historyItems.length && historyItems.every((item) => current.includes(item.job_id)) ? [] : historyItems.map((item) => item.job_id))}
          onDeleteSelected={handleDeleteSelectedJobs}
          onOpen={handleOpenJob}
          onDelete={handleDeleteJob}
          embedded
        />
        <section className="panel follow-up-panel">
          <h2>继续追问</h2>
          {job?.job_id ? (
            <>
              <p>当前任务：{job.user_goal || job.job_id}</p>
              <textarea rows={5} value={followUpQuestion} onChange={(event) => setFollowUpQuestion(event.target.value)} placeholder="例如：为什么华东区域的波动更明显？" />
              <button className="primary-button" type="button" disabled={!followUpQuestion.trim() || followUpLoading} onClick={handleFollowUp}>
                {followUpLoading ? "生成中" : "提交追问"}
              </button>
              <div className="follow-up-list">
                {followUps.length ? followUps.map((item, index) => (
                  <article key={`${item.created_at || index}-${item.question}`}>
                    <strong>{item.question}</strong>
                    <p>{item.answer}</p>
                  </article>
                )) : <p>暂无追问记录。</p>}
              </div>
            </>
          ) : (
            <EmptyState title="请选择一个分析任务" text="打开任务后，这里会显示可继续追问的上下文。" compact />
          )}
        </section>
      </div>
    </div>
  );

  const renderContent = () => {
    if (activeTab === "home") return renderHome();
    if (activeTab === "agent") return renderAgent();
    if (activeTab === "knowledge") {
      return (
        <div className="content-panel quest-content-panel">
          <KnowledgePage
            documents={knowledgeDocuments}
            selectedFile={knowledgeFile}
            query={knowledgeQuery}
            searchResult={knowledgeResult}
            message={knowledgeMessage}
            onFileChange={setKnowledgeFile}
            onQueryChange={setKnowledgeQuery}
            onUpload={handleKnowledgeUpload}
            onSearch={handleKnowledgeSearch}
            onDelete={handleKnowledgeDelete}
          />
        </div>
      );
    }
    if (activeTab === "chat") return renderChat();
    return renderResults();
  };

  return (
    <main className="dq-workbench-shell">
      <section className="dq-main-stage">
        {renderContent()}
      </section>

      {samplePreview ? (
        <SamplePreviewModal
          sample={samplePreview.sample}
          rowCount={samplePreview.profile.row_count}
          columns={samplePreview.profile.columns}
          rows={samplePreview.profile.sample_rows}
          goal={samplePreview.goal}
          onGoalChange={(nextGoal) => setSamplePreview((current) => current ? { ...current, goal: nextGoal } : current)}
          onConfirm={() => {
            const preview = samplePreview;
            applySamplePreview(preview);
            setTimeout(() => startWorkflow(preview.goal), 0);
          }}
          onSelect={() => applySamplePreview(samplePreview)}
          onCancel={() => setSamplePreview(null)}
        />
      ) : null}

      {cleaningPlan ? (
        <CleaningPlanModal
          plan={cleaningPlan}
          report={cleaningReport}
          selectedStrategies={selectedCleaningStrategies}
          loading={homeLoading}
          onStrategyChange={(issueId, strategyId) => setSelectedCleaningStrategies((current) => ({ ...current, [issueId]: strategyId }))}
          onConfirm={() => {
            if (cleaningReport) {
              setCleaningPlan(null);
              return;
            }
            handleApplyCleaningPlan(selectedCleaningStrategies);
          }}
          onClose={() => setCleaningPlan(null)}
        />
      ) : null}

      {previewChartPath ? (
        <ChartPreviewModal
          chartPath={previewChartPath}
          chartIndex={chartPaths.indexOf(previewChartPath)}
          chartRefreshToken={chartRefreshToken}
          onClose={() => setPreviewChartPath(null)}
          onDelete={() => handleDeleteChart(previewChartPath)}
          onCompileSelection={handleCompileSelection}
          onSubmitSelectionFollowUp={handleSubmitSelectionFollowUp}
        />
      ) : null}

      {overviewModalOpen ? (
        <div className="workbench-modal-backdrop" role="presentation" onMouseDown={() => setOverviewModalOpen(false)}>
          <section className="workbench-modal data-overview-modal" role="dialog" aria-modal="true" aria-labelledby="data-overview-modal-title" onMouseDown={(event) => event.stopPropagation()}>
            <header className="workbench-modal-header">
              <div>
                <h2 id="data-overview-modal-title">数据概览</h2>
                <p>当前数据源的结构信息</p>
              </div>
              <button className="modal-close-button" type="button" aria-label="关闭数据概览" onClick={() => setOverviewModalOpen(false)}>×</button>
            </header>
            <div className="workbench-modal-body">
              {profile ? (
                <div className="overview-stats mini-stat-grid modal-stat-grid">
                  <article className="stat-box"><span className="stat-label">数据行数</span><strong className="stat-value counter-animate">{profile.row_count}</strong></article>
                  <article className="stat-box"><span className="stat-label">字段数量</span><strong className="stat-value counter-animate">{profile.column_count}</strong></article>
                  <article className="stat-box"><span className="stat-label">数值字段</span><strong className="stat-value counter-animate">{Object.keys(profile.numeric_summary || {}).length}</strong></article>
                </div>
              ) : (
                <EmptyState title="暂无数据概览" text="请先选择数据文件或示例数据。" compact />
              )}
            </div>
          </section>
        </div>
      ) : null}

      {preflightModalOpen && preflight ? (
        <div className="workbench-modal-backdrop" role="presentation" onMouseDown={() => setPreflightModalOpen(false)}>
          <section className="workbench-modal intent-result-modal" role="dialog" aria-modal="true" aria-labelledby="intent-result-modal-title" onMouseDown={(event) => event.stopPropagation()}>
            <header className="workbench-modal-header">
              <div>
                <h2 id="intent-result-modal-title">意图识别结果</h2>
                <p>请选择需要采用的分析口径</p>
              </div>
              <button className="modal-close-button" type="button" aria-label="关闭意图识别结果" onClick={() => setPreflightModalOpen(false)}>×</button>
            </header>
            <div className="workbench-modal-body">
              <PreflightPanel
                assessment={preflight}
                onApplyGoal={(nextGoal) => {
                  setGoal(nextGoal);
                  setPreflightModalOpen(false);
                }}
                onApplyAndRun={(nextGoal) => {
                  setGoal(nextGoal);
                  setPreflightModalOpen(false);
                  startWorkflow(nextGoal);
                }}
              />
            </div>
          </section>
        </div>
      ) : null}

      <PPTExportModal
        isOpen={pptModalOpen || pptGenerating}
        busy={pptGenerating}
        statusText={pptMessage}
        downloadUrl={pptDownloadUrl}
        onClose={() => setPptModalOpen(false)}
      />
    </main>
  );
}
