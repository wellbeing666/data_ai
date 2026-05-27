import { useEffect, useMemo, useState } from "react";

import {
  createAutoRepairAnalysisJobAsync,
  createPredictionJobAsync,
  fetchAnalysisResult,
  fetchAutoRepairAnalysisJobStatus,
  fetchDatasetProfile,
  fetchExecutionLog,
  fetchHealthStatus,
  fetchJsonFile,
  fetchKnowledgeDocuments,
  fetchPredictionJobStatus,
  fetchPredictionLog,
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
  ValidationAttemptLog
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

export default function App() {
  const [activePage, setActivePage] = useState<PageKey>("setup");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [userGoal, setUserGoal] = useState("把这批 Excel 成绩按班级统计并生成图表");
  const [uploadInfo, setUploadInfo] = useState<DatasetUploadResponse | null>(null);
  const [profile, setProfile] = useState<DatasetProfile | null>(null);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [job, setJob] = useState<AutoRepairAnalysisJobResponse | null>(null);
  const [executionLog, setExecutionLog] = useState<ExecutionLog | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [controllerPlan, setControllerPlan] = useState<AnyRecord | null>(null);
  const [ragRetrieval, setRagRetrieval] = useState<AnyRecord | null>(null);
  const [dataUnderstanding, setDataUnderstanding] = useState<AnyRecord | null>(null);
  const [analysisPlan, setAnalysisPlan] = useState<AnyRecord | null>(null);
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
  const [predictionJob, setPredictionJob] = useState<PredictionJobResponse | null>(null);
  const [predictionLog, setPredictionLog] = useState<PredictionLogResponse | null>(null);
  const [predictionResult, setPredictionResult] = useState<PredictionResult | null>(null);
  const [predictionExplanation, setPredictionExplanation] = useState<PredictionExplanationResult>(emptyPredictionExplanation);
  const [hypothesisPlan, setHypothesisPlan] = useState<AnyRecord | null>(null);
  const [predictionPlan, setPredictionPlan] = useState<AnyRecord | null>(null);
  const [predictionStatus, setPredictionStatus] = useState<"idle" | "uploading" | "running" | "success" | "failed">("idle");
  const [predictionMessage, setPredictionMessage] = useState("");

  useEffect(() => {
    fetchHealthStatus()
      .then(setHealth)
      .catch(() => {
        setHealth({
          status: "unknown",
          llm_mode: "mock/fallback",
          deepseek_configured: false,
          message: "无法读取 DeepSeek 配置状态。"
        });
      });
  }, []);

  useEffect(() => {
    refreshKnowledgeDocuments();
  }, []);

  useEffect(() => {
    if (!job?.job_id || terminalStatuses.has(job.status)) {
      return;
    }

    let cancelled = false;
    const tick = async () => {
      try {
        const latest = await fetchAutoRepairAnalysisJobStatus(job.job_id);
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
    if (!predictionJob?.job_id || terminalStatuses.has(predictionJob.status)) {
      return;
    }

    let cancelled = false;
    const tick = async () => {
      try {
        const latest = await fetchPredictionJobStatus(predictionJob.job_id);
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

    const chartPaths = getChartPaths(analysisResult);
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
  const events = executionLog?.events?.length ? executionLog.events : job?.events ?? [];
  const chartPaths = getChartPaths(analysisResult);
  const latestValidation = lastItem(executionLog?.validation_results);
  const latestExecution = lastItem(executionLog?.execution_results);

  const steps = useMemo(
    () =>
      buildAgentSteps({
        job,
        controllerPlan,
        ragRetrieval,
        dataUnderstanding,
        analysisPlan,
        executionLog,
        explanation,
        events
      }),
    [job, controllerPlan, ragRetrieval, dataUnderstanding, analysisPlan, executionLog, explanation, events]
  );

  async function refreshKnowledgeDocuments() {
    try {
      const response = await fetchKnowledgeDocuments();
      setKnowledgeDocs(response.documents);
    } catch (error) {
      setKnowledgeMessage(error instanceof Error ? error.message : "读取知识库失败。");
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

    try {
      const uploaded = await uploadDataset(predictionFile);
      setUploadInfo(uploaded);
      const datasetProfile = await fetchDatasetProfile(uploaded.dataset_id);
      setProfile(datasetProfile);
      setPredictionStatus("running");
      setPredictionMessage("情景预测任务已启动，状态将实时刷新。");
      const createdJob = await createPredictionJobAsync(uploaded.dataset_id, predictionGoal, 3);
      await applyPredictionJobUpdate(createdJob);
    } catch (error) {
      setPredictionStatus("failed");
      setPredictionMessage(error instanceof Error ? error.message : "情景预测任务启动失败。");
    }
  }

  async function applyPredictionJobUpdate(nextJob: PredictionJobResponse) {
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
  }

  async function refreshPredictionLog(jobId: string) {
    try {
      setPredictionLog(await fetchPredictionLog(jobId));
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

  async function handleRunAnalysis() {
    if (!selectedFile) {
      setMessage("请先选择 CSV / Excel 文件。");
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
    setExplanation(emptyExplanation);
    setReport(null);
    setReportGeneratedFor("");

    try {
      const uploaded = await uploadDataset(selectedFile);
      setUploadInfo(uploaded);

      const datasetProfile = await fetchDatasetProfile(uploaded.dataset_id);
      setProfile(datasetProfile);

      setStatus("running");
      setMessage("任务已启动，Agent 状态将实时刷新。");
      const createdJob = await createAutoRepairAnalysisJobAsync(uploaded.dataset_id, userGoal, 3);
      await applyJobUpdate(createdJob);
    } catch (error) {
      setStatus("failed");
      setMessage(error instanceof Error ? error.message : "分析任务启动失败。");
    }
  }

  async function applyJobUpdate(nextJob: AutoRepairAnalysisJobResponse) {
    setJob(nextJob);
    setStatus(statusFromJob(nextJob.status));
    setMessage(messageFromJob(nextJob));

    await Promise.allSettled([
      refreshExecutionLog(nextJob.job_id),
      refreshJsonPath(nextJob.controller_plan_path, setControllerPlan),
      refreshJsonPath(nextJob.rag_retrieval_path, setRagRetrieval),
      refreshJsonPath(nextJob.data_understanding_path, setDataUnderstanding),
      refreshJsonPath(nextJob.analysis_plan_path, setAnalysisPlan),
      refreshAnalysisResult(nextJob.final_result_path),
      refreshExplanation(nextJob.explanation_path)
    ]);
  }

  async function refreshExecutionLog(jobId: string) {
    try {
      setExecutionLog(await fetchExecutionLog(jobId));
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
              <span>CSV / XLSX / XLS</span>
            </div>
            <label className="upload-zone">
              <input
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
              />
              <strong>{selectedFile ? selectedFile.name : "选择数据文件"}</strong>
              <span>上传后由多 Agent 完成理解、规划、代码生成、验证和解释。</span>
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
            </dl>
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
        </aside>

        <section className="content-panel">
          <nav className="page-tabs" aria-label="工作台页面">
            {[
              ["setup", "任务配置"],
              ["knowledge", "知识库"],
              ["prediction", "情景预测"],
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

          {activePage === "prediction" ? (
            <PredictionPage
              file={predictionFile}
              goal={predictionGoal}
              status={predictionStatus}
              message={predictionMessage}
              job={predictionJob}
              log={predictionLog}
              hypothesisPlan={hypothesisPlan}
              predictionPlan={predictionPlan}
              predictionResult={predictionResult}
              explanation={predictionExplanation}
              onFileChange={setPredictionFile}
              onGoalChange={setPredictionGoal}
              onRun={handleRunPrediction}
            />
          ) : null}

          {activePage === "process" ? (
            <ProcessPage job={job} steps={steps} controllerPlan={controllerPlan} ragRetrieval={ragRetrieval} dataUnderstanding={dataUnderstanding} analysisPlan={analysisPlan} events={events} />
          ) : null}

          {activePage === "charts" ? (
            <ChartsPage analysisResult={analysisResult} chartPaths={chartPaths} />
          ) : null}

          {activePage === "insights" ? (
            <InsightsPage explanation={explanation} report={report} />
          ) : null}

          {activePage === "logs" ? (
            <LogsPage job={job} events={events} latestExecution={latestExecution} latestValidation={latestValidation} />
          ) : null}
        </section>
      </section>
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
          <p>支持 CSV、XLSX、XLS。上传后系统会生成数据画像，供各 Agent 使用。</p>
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
  job: PredictionJobResponse | null;
  log: PredictionLogResponse | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  predictionResult: PredictionResult | null;
  explanation: PredictionExplanationResult;
  onFileChange: (file: File | null) => void;
  onGoalChange: (goal: string) => void;
  onRun: () => void;
}) {
  const events = log?.events?.length ? log.events : job?.events ?? [];
  const chartPaths = predictionResult?.charts ?? [];
  const steps = buildPredictionSteps({ job, log, hypothesisPlan, predictionPlan, predictionResult, explanation, events });

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
      <RecentEvents events={events} />
    </section>
  );
}

function ProcessPage({
  job,
  steps,
  controllerPlan,
  ragRetrieval,
  dataUnderstanding,
  analysisPlan,
  events
}: {
  job: AutoRepairAnalysisJobResponse | null;
  steps: StepView[];
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  dataUnderstanding: AnyRecord | null;
  analysisPlan: AnyRecord | null;
  events: ExecutionLogEvent[];
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>Agent 工作过程</h2>
        {job ? <span>Job {job.job_id}</span> : <span>等待任务启动</span>}
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
      <div className="agent-output-grid">
        <JsonSummary title="主控 Agent 输出" value={controllerPlan} />
        <JsonSummary title="RAG 命中上下文" value={ragRetrieval} />
        <JsonSummary title="数据理解 Agent 输出" value={dataUnderstanding} />
        <JsonSummary title="分析 Agent 输出" value={analysisPlan} />
      </div>
      <RecentEvents events={events} />
    </section>
  );
}

function ChartsPage({
  analysisResult,
  chartPaths
}: {
  analysisResult: AnalysisResult | null;
  chartPaths: string[];
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>最终图表</h2>
        <span>{chartPaths.length} 个图表</span>
      </div>
      {analysisResult && chartPaths.length ? (
        <div className="chart-grid">
          {chartPaths.map((chartPath, index) => (
            <figure className="chart-card" key={chartPath}>
              <img alt={`分析图表 ${index + 1}`} src={toStorageUrl(chartPath)} />
              <figcaption>{chartTitle(chartPath, index)}</figcaption>
            </figure>
          ))}
        </div>
      ) : (
        <EmptyState title="暂无图表" text="分析脚本完成并通过验证后，图表会自动出现在这里。" />
      )}
    </section>
  );
}

function InsightsPage({
  explanation,
  report
}: {
  explanation: ExplanationResult;
  report: ReportGenerateResponse | null;
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
  events,
  latestExecution,
  latestValidation
}: {
  job: AutoRepairAnalysisJobResponse | null;
  events: ExecutionLogEvent[];
  latestExecution: ExecutionAttemptLog | undefined;
  latestValidation: ValidationAttemptLog | undefined;
}) {
  return (
    <section className="page-section">
      <div className="section-heading">
        <h2>执行日志</h2>
        <span>{job?.status ?? "unknown"}</span>
      </div>
      <div className="log-grid">
        <div className="log-block">
          <h3>沙箱执行</h3>
          <dl className="compact-list">
            <div>
              <dt>成功</dt>
              <dd>{latestExecution?.success ? "是" : latestExecution ? "否" : "-"}</dd>
            </div>
            <div>
              <dt>耗时</dt>
              <dd>{String(latestExecution?.duration_ms ?? "-")} ms</dd>
            </div>
          </dl>
          <pre>{String(latestExecution?.stderr || latestExecution?.stdout || "暂无执行输出")}</pre>
        </div>
        <div className="log-block">
          <h3>验证 Agent</h3>
          <dl className="compact-list">
            <div>
              <dt>严重级别</dt>
              <dd>{String(latestValidation?.severity ?? "-")}</dd>
            </div>
            <div>
              <dt>是否重试</dt>
              <dd>{latestValidation?.should_retry ? "是" : latestValidation ? "否" : "-"}</dd>
            </div>
          </dl>
          <pre>{JSON.stringify(latestValidation?.issues ?? [], null, 2)}</pre>
        </div>
      </div>
      <RecentEvents events={events} />
    </section>
  );
}

function ResultList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) {
    return null;
  }
  return (
    <div className="finding-list">
      <h3>{title}</h3>
      {items.map((item) => (
        <div className="finding-item" key={item}>
          <p>{item}</p>
        </div>
      ))}
    </div>
  );
}

function PptOutline({ outline }: { outline: ExplanationResult["ppt_outline"] }) {
  if (!outline.length) {
    return null;
  }
  return (
    <div className="finding-list">
      <h3>PPT 大纲</h3>
      {outline.map((slide, index) => (
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

function RecentEvents({ events }: { events: ExecutionLogEvent[] }) {
  const recent = events.slice(-8).reverse();
  if (!recent.length) {
    return <EmptyState title="暂无日志" text="任务启动后，Agent 事件会实时追加到这里。" compact />;
  }
  return (
    <div className="log-event-list">
      {recent.map((event, index) => (
        <article className="log-event" key={`${event.timestamp}-${index}`}>
          <span>
            {stageLabel(event.stage)} · {event.status}
            {event.attempt ? ` · attempt ${event.attempt}` : ""}
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

function buildAgentSteps(input: {
  job: AutoRepairAnalysisJobResponse | null;
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  dataUnderstanding: AnyRecord | null;
  analysisPlan: AnyRecord | null;
  executionLog: ExecutionLog | null;
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
      done: Boolean(attempt?.safety_result_path || attempt?.safety_issues),
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

  return definitions.map((definition) => ({
    ...definition,
    status: stepStatus({
      done: definition.done,
      active: definition.stageNames.includes(currentStage),
      failed: terminalFailed && hasFailedEvent(input.events, definition.stageNames)
    })
  }));
}

function buildPredictionSteps(input: {
  job: PredictionJobResponse | null;
  log: PredictionLogResponse | null;
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
  return definitions.map((definition) => ({
    ...definition,
    status: stepStatus({
      done: definition.done,
      active: definition.stageNames.includes(currentStage),
      failed: terminalFailed && hasFailedEvent(input.events, definition.stageNames)
    })
  }));
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

function getChartPaths(result: AnalysisResult | null): string[] {
  if (!result || !Array.isArray(result.charts)) {
    return [];
  }
  return result.charts.map((chart) => String(chart));
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

function messageFromJob(job: AutoRepairAnalysisJobResponse): string {
  if (job.status === "success") {
    return "分析完成。";
  }
  if (job.status === "failed") {
    return job.error?.message ? String(job.error.message) : "分析失败，请查看执行日志。";
  }
  return `${stageLabel(job.current_stage ?? "running")}，状态实时刷新中。`;
}

function predictionMessageFromJob(job: PredictionJobResponse): string {
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

function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}

function formatPercent(value: number): string {
  return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "-";
}

function stringValue(value: unknown, fallback: string): string {
  return typeof value === "string" && value ? value : fallback;
}

function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
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

function lastItem<T>(items: T[] | undefined): T | undefined {
  if (!items?.length) {
    return undefined;
  }
  return items[items.length - 1];
}
