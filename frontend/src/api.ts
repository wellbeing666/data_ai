import type {
  AnalysisJobResponse,
  AnalysisResult,
  AuthCurrentUserResponse,
  AuthLoginResponse,
  AuthMessageResponse,
  AuthRegisterResponse,
  AuthUserListResponse,
  AutoRepairAnalysisJobResponse,
  ChartConfigResponse,
  ChartDeleteResponse,
  ChartSelectionSpec,
  CleaningPlanResponse,
  DashboardConfig,
  DashboardConfigResponse,
  CleaningReportResponse,
  ChartRefineResponse,
  ChartSuggestionResponse,
  DatasetProfile,
  DatasetUploadResponse,
  DatasetDataMapResponse,
  ExecutionLog,
  HealthStatus,
  KnowledgeDeleteResponse,
  KnowledgeDocument,
  KnowledgeDocumentListResponse,
  KnowledgeSearchResponse,
  PredictionJobResponse,
  PredictionLogResponse,
  PreflightAssessment,
  ReportGenerateResponse,
  SampleDatasetResponse,
  SampleDatasetTypeListResponse,
  WorkflowAgentConsoleResponse,
  WorkflowAgentUpdateRequest,
  WorkflowControlResponse,
  WorkflowFollowUpResponse,
  WorkflowSelectionQuestionResponse,
  WorkflowJobDeleteResponse,
  WorkflowJobListResponse,
  WorkflowJobResponse,
  WorkflowLogResponse,
  WorkflowPptxGenerateResponse
} from "./types";

export const AUTH_TOKEN_STORAGE_KEY = "agent_workbench_auth_token";

export function getStoredAuthToken(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "";
}

export function setStoredAuthToken(token: string | null): void {
  if (typeof window === "undefined") {
    return;
  }
  if (token) {
    window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
  }
}

function authHeaders(headers?: HeadersInit): Headers {
  const result = new Headers(headers);
  const token = getStoredAuthToken();
  if (token) {
    result.set("Authorization", `Bearer ${token}`);
  }
  return result;
}

function jsonHeaders(): Headers {
  const headers = authHeaders({ "Content-Type": "application/json" });
  return headers;
}


function fieldLabelFromLocation(loc: unknown): string {
  const map: Record<string, string> = {
    login_account: "登录账号",
    username: "用户名",
    password: "密码",
    old_password: "原密码",
    new_password: "新密码",
    register_reason: "申请说明",
    query: "检索问题",
    top_k: "返回数量",
    dataset_id: "数据文件",
    user_goal: "分析目标",
    file: "文件"
  };
  const parts = Array.isArray(loc) ? loc : [loc];
  const filtered = parts.filter(Boolean);
  const key = String(filtered[filtered.length - 1] || "");
  return map[key] || "输入内容";
}

function translateValidationIssue(item: { msg?: string; loc?: unknown; type?: string; ctx?: Record<string, unknown> }): string {
  const field = fieldLabelFromLocation(item.loc);
  const msg = String(item.msg || "");
  const type = String(item.type || "");
  const limit = item.ctx?.min_length ?? item.ctx?.max_length ?? item.ctx?.ge ?? item.ctx?.le;

  if (type.includes("string_too_short") || /at least \d+ characters/i.test(msg)) {
    return `${field}至少需要 ${limit || "规定数量的"} 个字符。`;
  }
  if (type.includes("string_too_long") || /at most \d+ characters/i.test(msg)) {
    return `${field}不能超过 ${limit || "规定数量的"} 个字符。`;
  }
  if (type.includes("missing") || /field required/i.test(msg)) {
    return `请填写${field}。`;
  }
  if (type.includes("greater_than_equal") || /greater than or equal/i.test(msg)) {
    return `${field}不能小于 ${limit || "要求值"}。`;
  }
  if (type.includes("less_than_equal") || /less than or equal/i.test(msg)) {
    return `${field}不能大于 ${limit || "要求值"}。`;
  }
  return friendlyErrorMessage(msg);
}

function translateKnownMessage(message: string): string {
  const compact = message.trim().replace(/\s+/g, " ");
  const exact: Record<string, string> = {
    "String should have at least 3 characters": "输入内容至少需要 3 个字符。",
    "String should have at least 6 characters": "密码至少需要 6 个字符。",
    "Knowledge base is empty or no document is indexed.": "知识库中暂无可检索文档，请先上传业务知识文档。",
    "RAG is disabled by configuration.": "知识库向量检索未启用，系统将使用文本检索。",
    "Only .txt and .md knowledge documents are supported.": "仅支持上传 .txt 或 .md 格式的知识文档。",
    "Knowledge document is empty after text cleanup.": "知识文档内容为空，请补充文本后重新上传。",
    "Job not found.": "未找到对应的分析任务。",
    "Job status not found.": "未找到对应的任务状态。",
    "Workflow job not found.": "未找到对应的分析任务。",
    "Chart not found.": "未找到对应图表。"
  };
  if (exact[compact]) {
    return exact[compact];
  }
  const replacements: Array<[RegExp, string]> = [
    [/String should have at least (\d+) characters?/gi, "输入内容至少需要 $1 个字符。"],
    [/String should have at most (\d+) characters?/gi, "输入内容不能超过 $1 个字符。"],
    [/Knowledge base is empty or no document is indexed\./gi, "知识库中暂无可检索文档，请先上传业务知识文档。"],
    [/Embedding model is not available locally:[^；。]*/gi, "当前运行环境未启用向量索引"],
    [/RAG search unavailable:[^；。]*/gi, "知识库检索暂时不可用"],
    [/failed to fetch/gi, "网络连接暂时不可用"],
    [/backend service/gi, "分析服务"]
  ];
  return replacements.reduce((current, [pattern, replacement]) => current.replace(pattern, replacement), message);
}

function friendlyErrorMessage(rawMessage: string, status?: number): string {
  const message = translateKnownMessage(rawMessage.trim());
  const lower = message.toLowerCase();
  const technicalSignals = [
    "backend",
    "server",
    "traceback",
    "stack",
    "sql",
    "database",
    "mysql",
    "pymysql",
    "timeout",
    "failed to fetch",
    "networkerror",
    "后端",
    "数据库",
    "服务器",
    "连接超时"
  ];

  if (status === 401) {
    return "登录状态已过期，请重新登录后继续使用。";
  }
  if (status === 403) {
    return "当前账号暂无执行此操作的权限。";
  }
  if (status === 404) {
    return "没有找到对应的数据或分析任务，请刷新列表后重试。";
  }
  if (status && status >= 500) {
    return "分析服务暂时繁忙，请稍后重新尝试。";
  }
  if (!message) {
    return "操作未完成，请稍后重试。";
  }
  if (technicalSignals.some((keyword) => lower.includes(keyword))) {
    return "分析链路暂时不可用，请稍后重新尝试。";
  }
  return message;
}

function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  return fetch(input, {
    ...init,
    headers: authHeaders(init.headers)
  }).catch(() => {
    throw new Error("网络连接暂时不可用，请检查网络后重试。");
  });
}

async function parseResponse<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    let message = "操作未完成，请稍后重试。";
    if (data && typeof data.detail === "string") {
      message = data.detail;
    } else if (data && Array.isArray(data.detail)) {
      message = data.detail
        .map((item: { msg?: string; loc?: unknown; type?: string; ctx?: Record<string, unknown> }) => translateValidationIssue(item))
        .join("");
    } else if (data && typeof data.message === "string") {
      message = data.message;
    }
    throw new Error(friendlyErrorMessage(message, response.status));
  }

  return data as T;
}

export async function uploadDataset(file: File): Promise<DatasetUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch("/api/datasets/upload", {
    method: "POST",
    body: formData
  });

  return parseResponse<DatasetUploadResponse>(response);
}

export async function createSampleDataset(sampleType: string): Promise<SampleDatasetResponse> {
  const response = await apiFetch("/api/datasets/samples", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ sample_type: sampleType })
  });

  return parseResponse<SampleDatasetResponse>(response);
}

export async function fetchSampleDatasetTypes(): Promise<SampleDatasetTypeListResponse> {
  const response = await apiFetch("/api/datasets/samples");
  return parseResponse<SampleDatasetTypeListResponse>(response);
}

export async function fetchDatasetProfile(datasetId: string): Promise<DatasetProfile> {
  const response = await apiFetch(`/api/datasets/${datasetId}/profile`);
  return parseResponse<DatasetProfile>(response);
}


export async function fetchDatasetDataMap(datasetId: string): Promise<DatasetDataMapResponse> {
  const response = await apiFetch(`/api/datasets/${datasetId}/data-map`);
  return parseResponse<DatasetDataMapResponse>(response);
}

export async function createCleaningPlan(datasetId: string): Promise<CleaningPlanResponse> {
  const response = await apiFetch(`/api/datasets/${datasetId}/cleaning-plan`, {
    method: "POST"
  });
  return parseResponse<CleaningPlanResponse>(response);
}

export async function applyCleaningPlan(
  datasetId: string,
  selectedStrategies: Record<string, string>
): Promise<CleaningReportResponse> {
  const response = await apiFetch(`/api/datasets/${datasetId}/apply-cleaning`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ selected_strategies: selectedStrategies })
  });
  return parseResponse<CleaningReportResponse>(response);
}

export async function fetchCleaningReport(datasetId: string): Promise<CleaningReportResponse> {
  const response = await apiFetch(`/api/datasets/${datasetId}/cleaning-report`);
  return parseResponse<CleaningReportResponse>(response);
}

export async function createAnalysisJob(
  datasetId: string,
  userGoal: string
): Promise<AnalysisJobResponse> {
  const response = await apiFetch("/api/analysis/jobs", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      dataset_id: datasetId,
      user_goal: userGoal
    })
  });

  return parseResponse<AnalysisJobResponse>(response);
}

export async function createAutoRepairAnalysisJob(
  datasetId: string,
  userGoal: string,
  maxRetries = 3
): Promise<AutoRepairAnalysisJobResponse> {
  const response = await apiFetch("/api/analysis/auto-repair-jobs", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      dataset_id: datasetId,
      user_goal: userGoal,
      max_retries: maxRetries,
      timeout_seconds: 60
    })
  });

  return parseResponse<AutoRepairAnalysisJobResponse>(response);
}

export async function createAutoRepairAnalysisJobAsync(
  datasetId: string,
  userGoal: string,
  maxRetries = 3
): Promise<AutoRepairAnalysisJobResponse> {
  const response = await apiFetch("/api/analysis/auto-repair-jobs/async", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      dataset_id: datasetId,
      user_goal: userGoal,
      max_retries: maxRetries,
      timeout_seconds: 60
    })
  });

  return parseResponse<AutoRepairAnalysisJobResponse>(response);
}

export async function fetchAutoRepairAnalysisJobStatus(
  jobId: string
): Promise<AutoRepairAnalysisJobResponse> {
  const response = await apiFetch(`/api/analysis/auto-repair-jobs/${jobId}`);
  return parseResponse<AutoRepairAnalysisJobResponse>(response);
}

export async function createPredictionJobAsync(
  datasetId: string,
  userGoal: string,
  maxRetries = 3
): Promise<PredictionJobResponse> {
  const response = await apiFetch("/api/predictions/jobs/async", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      dataset_id: datasetId,
      user_goal: userGoal,
      max_retries: maxRetries,
      timeout_seconds: 90
    })
  });

  return parseResponse<PredictionJobResponse>(response);
}

export async function fetchPredictionJobStatus(jobId: string): Promise<PredictionJobResponse> {
  const response = await apiFetch(`/api/predictions/jobs/${jobId}`);
  return parseResponse<PredictionJobResponse>(response);
}

export async function fetchPredictionLog(jobId: string): Promise<PredictionLogResponse> {
  const response = await apiFetch(`/api/predictions/jobs/${jobId}/logs`);
  return parseResponse<PredictionLogResponse>(response);
}

export async function createWorkflowJobAsync(
  datasetId: string,
  userGoal: string,
  maxRetries = 3,
  insightMode = false
): Promise<WorkflowJobResponse> {
  const response = await apiFetch("/api/workflows/jobs/async", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      dataset_id: datasetId,
      user_goal: userGoal,
      max_retries: maxRetries,
      timeout_seconds: 90,
      insight_mode: insightMode
    })
  });

  return parseResponse<WorkflowJobResponse>(response);
}

export async function createPreflightAssessment(
  datasetId: string,
  userGoal: string
): Promise<PreflightAssessment> {
  const response = await apiFetch("/api/workflows/preflight", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      dataset_id: datasetId,
      user_goal: userGoal
    })
  });

  return parseResponse<PreflightAssessment>(response);
}

export async function createIterativeChartConfig(
  jobId: string,
  instruction: string,
  currentConfig?: Record<string, unknown> | null
): Promise<ChartConfigResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/chart-config`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      instruction,
      current_config: currentConfig ?? null
    })
  });

  return parseResponse<ChartConfigResponse>(response);
}

export async function fetchWorkflowJobs(limit = 30, query = ""): Promise<WorkflowJobListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  const trimmedQuery = query.trim();
  if (trimmedQuery) {
    params.set("query", trimmedQuery);
  }
  const response = await apiFetch(`/api/workflows/jobs?${params.toString()}`);
  return parseResponse<WorkflowJobListResponse>(response);
}

export async function fetchWorkflowJobStatus(jobId: string): Promise<WorkflowJobResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}`);
  return parseResponse<WorkflowJobResponse>(response);
}

export async function fetchWorkflowLog(jobId: string): Promise<WorkflowLogResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/logs`);
  return parseResponse<WorkflowLogResponse>(response);
}

export async function controlWorkflowJob(jobId: string, action: string): Promise<WorkflowControlResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/control`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ action })
  });
  return parseResponse<WorkflowControlResponse>(response);
}
export async function generateWorkflowPptx(jobId: string): Promise<WorkflowPptxGenerateResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/pptx`, {
    method: "POST"
  });
  return parseResponse<WorkflowPptxGenerateResponse>(response);
}



export async function fetchWorkflowDashboard(jobId: string): Promise<DashboardConfigResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/dashboard`);
  return parseResponse<DashboardConfigResponse>(response);
}

export async function saveWorkflowDashboard(
  jobId: string,
  dashboard: DashboardConfig
): Promise<DashboardConfigResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/dashboard`, {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify({ dashboard })
  });
  return parseResponse<DashboardConfigResponse>(response);
}

export async function refreshWorkflowDashboard(jobId: string): Promise<DashboardConfigResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/dashboard/refresh`, {
    method: "POST"
  });
  return parseResponse<DashboardConfigResponse>(response);
}


export async function fetchWorkflowAgents(jobId: string): Promise<WorkflowAgentConsoleResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/agents`);
  return parseResponse<WorkflowAgentConsoleResponse>(response);
}

export async function updateWorkflowAgent(
  jobId: string,
  agentId: string,
  updates: WorkflowAgentUpdateRequest
): Promise<WorkflowAgentConsoleResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/agents/${agentId}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(updates)
  });
  return parseResponse<WorkflowAgentConsoleResponse>(response);
}

export async function deleteWorkflowAgentMessage(
  jobId: string,
  agentId: string,
  messageId: string
): Promise<WorkflowAgentConsoleResponse> {
  const response = await apiFetch(
    `/api/workflows/jobs/${jobId}/agents/${agentId}/messages/${encodeURIComponent(messageId)}`,
    { method: "DELETE" }
  );
  return parseResponse<WorkflowAgentConsoleResponse>(response);
}

export async function createWorkflowFollowUp(
  jobId: string,
  question: string
): Promise<WorkflowFollowUpResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/follow-up`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ question })
  });
  return parseResponse<WorkflowFollowUpResponse>(response);
}

export async function createWorkflowSelectionQuestion(
  jobId: string,
  selectionSpec: ChartSelectionSpec
): Promise<WorkflowSelectionQuestionResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/selection-question`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ selection_spec: selectionSpec })
  });
  return parseResponse<WorkflowSelectionQuestionResponse>(response);
}

export async function createWorkflowSelectionFollowUp(
  jobId: string,
  selectionSpec: ChartSelectionSpec,
  question?: string
): Promise<WorkflowFollowUpResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/selection-follow-up`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ selection_spec: selectionSpec, question: question?.trim() || undefined })
  });
  return parseResponse<WorkflowFollowUpResponse>(response);
}

export async function deleteWorkflowChart(
  jobId: string,
  chartPath: string
): Promise<ChartDeleteResponse> {
  const params = new URLSearchParams({ chart_path: chartPath });
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/charts?${params.toString()}`, {
    method: "DELETE"
  });
  return parseResponse<ChartDeleteResponse>(response);
}

export async function fetchWorkflowChartSuggestions(
  jobId: string,
  chartPath: string
): Promise<ChartSuggestionResponse> {
  const params = new URLSearchParams({ chart_path: chartPath });
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/chart-suggestions?${params.toString()}`);
  return parseResponse<ChartSuggestionResponse>(response);
}

export async function refineWorkflowChart(
  jobId: string,
  chartPath: string,
  instruction: string
): Promise<ChartRefineResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}/chart-refine`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      chart_path: chartPath,
      instruction
    })
  });
  return parseResponse<ChartRefineResponse>(response);
}


export async function deleteWorkflowJob(jobId: string): Promise<WorkflowJobDeleteResponse> {
  const response = await apiFetch(`/api/workflows/jobs/${jobId}`, {
    method: "DELETE"
  });
  return parseResponse<WorkflowJobDeleteResponse>(response);
}

export async function fetchAnalysisResult(resultPath: string): Promise<AnalysisResult> {
  const response = await apiFetch(toStorageUrl(resultPath));
  return parseResponse<AnalysisResult>(response);
}

export async function fetchJsonFile<T>(path: string): Promise<T> {
  const response = await apiFetch(toStorageUrl(path));
  return parseResponse<T>(response);
}

export async function fetchExecutionLog(jobId: string): Promise<ExecutionLog> {
  const response = await apiFetch(`/api/analysis/jobs/${jobId}/logs`);
  return parseResponse<ExecutionLog>(response);
}

export async function fetchHealthStatus(): Promise<HealthStatus> {
  const response = await apiFetch("/health");
  return parseResponse<HealthStatus>(response);
}

export async function uploadKnowledgeDocument(file: File): Promise<KnowledgeDocument> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await apiFetch("/api/knowledge/documents", {
    method: "POST",
    body: formData
  });

  return parseResponse<KnowledgeDocument>(response);
}

export async function fetchKnowledgeDocuments(): Promise<KnowledgeDocumentListResponse> {
  const response = await apiFetch("/api/knowledge/documents");
  return parseResponse<KnowledgeDocumentListResponse>(response);
}

export async function deleteKnowledgeDocument(docId: string): Promise<KnowledgeDeleteResponse> {
  const response = await apiFetch(`/api/knowledge/documents/${docId}`, {
    method: "DELETE"
  });
  return parseResponse<KnowledgeDeleteResponse>(response);
}

export async function searchKnowledge(
  query: string,
  topK = 5
): Promise<KnowledgeSearchResponse> {
  const response = await apiFetch("/api/knowledge/search", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      query,
      top_k: topK
    })
  });

  return parseResponse<KnowledgeSearchResponse>(response);
}

export async function generateReport(
  analysisResultPath: string,
  chartPaths: string[] = []
): Promise<ReportGenerateResponse> {
  const response = await apiFetch("/api/reports/generate", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      analysis_result_path: analysisResultPath,
      chart_paths: chartPaths,
      include_pptx: true
    })
  });

  return parseResponse<ReportGenerateResponse>(response);
}

export async function login(loginAccount: string, password: string): Promise<AuthLoginResponse> {
  const response = await apiFetch("/api/auth/login", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      login_account: loginAccount,
      password
    })
  });
  return parseResponse<AuthLoginResponse>(response);
}

export async function registerUser(
  loginAccount: string,
  username: string,
  password: string,
  registerReason = ""
): Promise<AuthRegisterResponse> {
  const response = await apiFetch("/api/auth/register", {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({
      login_account: loginAccount,
      username,
      password,
      register_reason: registerReason
    })
  });
  return parseResponse<AuthRegisterResponse>(response);
}

export async function fetchCurrentUser(): Promise<AuthCurrentUserResponse> {
  const response = await apiFetch("/api/auth/me");
  return parseResponse<AuthCurrentUserResponse>(response);
}

export async function logout(): Promise<AuthMessageResponse> {
  const response = await apiFetch("/api/auth/logout", { method: "POST" });
  return parseResponse<AuthMessageResponse>(response);
}

export async function updateMyProfile(username: string): Promise<AuthCurrentUserResponse> {
  const response = await apiFetch("/api/auth/me/profile", {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify({ username })
  });
  return parseResponse<AuthCurrentUserResponse>(response);
}

export async function changeMyPassword(oldPassword: string, newPassword: string): Promise<AuthMessageResponse> {
  const response = await apiFetch("/api/auth/me/password", {
    method: "PUT",
    headers: jsonHeaders(),
    body: JSON.stringify({
      old_password: oldPassword,
      new_password: newPassword
    })
  });
  return parseResponse<AuthMessageResponse>(response);
}

export async function fetchAdminUsers(status = "", query = ""): Promise<AuthUserListResponse> {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  if (query.trim()) {
    params.set("query", query.trim());
  }
  const response = await apiFetch(`/api/auth/admin/users${params.toString() ? `?${params.toString()}` : ""}`);
  return parseResponse<AuthUserListResponse>(response);
}

export async function reviewAdminUser(userId: string, action: "approve" | "reject", reason = ""): Promise<AuthCurrentUserResponse> {
  const response = await apiFetch(`/api/auth/admin/users/${userId}/review`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ action, reason })
  });
  return parseResponse<AuthCurrentUserResponse>(response);
}

export async function freezeAdminUser(userId: string, frozen: boolean, reason = ""): Promise<AuthCurrentUserResponse> {
  const response = await apiFetch(`/api/auth/admin/users/${userId}/freeze`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ frozen, reason })
  });
  return parseResponse<AuthCurrentUserResponse>(response);
}

export async function changeAdminUserRole(userId: string, role: "user" | "admin"): Promise<AuthCurrentUserResponse> {
  const response = await apiFetch(`/api/auth/admin/users/${userId}/role`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify({ role })
  });
  return parseResponse<AuthCurrentUserResponse>(response);
}

export function toStorageUrl(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const storageIndex = normalized.indexOf("storage/");
  if (storageIndex >= 0) {
    return `/${normalized.slice(storageIndex)}`;
  }
  return normalized.startsWith("/") ? normalized : `/${normalized}`;
}