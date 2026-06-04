import type {
  AnalysisJobResponse,
  AnalysisResult,
  AutoRepairAnalysisJobResponse,
  ChartDeleteResponse,
  DatasetProfile,
  DatasetUploadResponse,
  ExecutionLog,
  HealthStatus,
  KnowledgeDeleteResponse,
  KnowledgeDocument,
  KnowledgeDocumentListResponse,
  KnowledgeSearchResponse,
  PredictionJobResponse,
  PredictionLogResponse,
  ReportGenerateResponse,
  WorkflowJobListResponse,
  WorkflowJobResponse,
  WorkflowLogResponse
} from "./types";

async function parseResponse<T>(response: Response): Promise<T> {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const message =
      data && typeof data.detail === "string"
        ? data.detail
        : "请求失败，请检查后端服务是否正常运行。";
    throw new Error(message);
  }

  return data as T;
}

export async function uploadDataset(file: File): Promise<DatasetUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/datasets/upload", {
    method: "POST",
    body: formData
  });

  return parseResponse<DatasetUploadResponse>(response);
}

export async function fetchDatasetProfile(datasetId: string): Promise<DatasetProfile> {
  const response = await fetch(`/api/datasets/${datasetId}/profile`);
  return parseResponse<DatasetProfile>(response);
}

export async function createAnalysisJob(
  datasetId: string,
  userGoal: string
): Promise<AnalysisJobResponse> {
  const response = await fetch("/api/analysis/jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
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
  const response = await fetch("/api/analysis/auto-repair-jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
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
  const response = await fetch("/api/analysis/auto-repair-jobs/async", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
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
  const response = await fetch(`/api/analysis/auto-repair-jobs/${jobId}`);
  return parseResponse<AutoRepairAnalysisJobResponse>(response);
}

export async function createPredictionJobAsync(
  datasetId: string,
  userGoal: string,
  maxRetries = 3
): Promise<PredictionJobResponse> {
  const response = await fetch("/api/predictions/jobs/async", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
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
  const response = await fetch(`/api/predictions/jobs/${jobId}`);
  return parseResponse<PredictionJobResponse>(response);
}

export async function fetchPredictionLog(jobId: string): Promise<PredictionLogResponse> {
  const response = await fetch(`/api/predictions/jobs/${jobId}/logs`);
  return parseResponse<PredictionLogResponse>(response);
}

export async function createWorkflowJobAsync(
  datasetId: string,
  userGoal: string,
  maxRetries = 3
): Promise<WorkflowJobResponse> {
  const response = await fetch("/api/workflows/jobs/async", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      dataset_id: datasetId,
      user_goal: userGoal,
      max_retries: maxRetries,
      timeout_seconds: 90
    })
  });

  return parseResponse<WorkflowJobResponse>(response);
}

export async function fetchWorkflowJobs(limit = 30): Promise<WorkflowJobListResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  const response = await fetch(`/api/workflows/jobs?${params.toString()}`);
  return parseResponse<WorkflowJobListResponse>(response);
}

export async function fetchWorkflowJobStatus(jobId: string): Promise<WorkflowJobResponse> {
  const response = await fetch(`/api/workflows/jobs/${jobId}`);
  return parseResponse<WorkflowJobResponse>(response);
}

export async function fetchWorkflowLog(jobId: string): Promise<WorkflowLogResponse> {
  const response = await fetch(`/api/workflows/jobs/${jobId}/logs`);
  return parseResponse<WorkflowLogResponse>(response);
}

export async function deleteWorkflowChart(
  jobId: string,
  chartPath: string
): Promise<ChartDeleteResponse> {
  const params = new URLSearchParams({ chart_path: chartPath });
  const response = await fetch(`/api/workflows/jobs/${jobId}/charts?${params.toString()}`, {
    method: "DELETE"
  });
  return parseResponse<ChartDeleteResponse>(response);
}

export async function fetchAnalysisResult(resultPath: string): Promise<AnalysisResult> {
  const response = await fetch(toStorageUrl(resultPath));
  return parseResponse<AnalysisResult>(response);
}

export async function fetchJsonFile<T>(path: string): Promise<T> {
  const response = await fetch(toStorageUrl(path));
  return parseResponse<T>(response);
}

export async function fetchExecutionLog(jobId: string): Promise<ExecutionLog> {
  const response = await fetch(`/api/analysis/jobs/${jobId}/logs`);
  return parseResponse<ExecutionLog>(response);
}

export async function fetchHealthStatus(): Promise<HealthStatus> {
  const response = await fetch("/health");
  return parseResponse<HealthStatus>(response);
}

export async function uploadKnowledgeDocument(file: File): Promise<KnowledgeDocument> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/knowledge/documents", {
    method: "POST",
    body: formData
  });

  return parseResponse<KnowledgeDocument>(response);
}

export async function fetchKnowledgeDocuments(): Promise<KnowledgeDocumentListResponse> {
  const response = await fetch("/api/knowledge/documents");
  return parseResponse<KnowledgeDocumentListResponse>(response);
}

export async function deleteKnowledgeDocument(docId: string): Promise<KnowledgeDeleteResponse> {
  const response = await fetch(`/api/knowledge/documents/${docId}`, {
    method: "DELETE"
  });
  return parseResponse<KnowledgeDeleteResponse>(response);
}

export async function searchKnowledge(
  query: string,
  topK = 5
): Promise<KnowledgeSearchResponse> {
  const response = await fetch("/api/knowledge/search", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
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
  const response = await fetch("/api/reports/generate", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      analysis_result_path: analysisResultPath,
      chart_paths: chartPaths
    })
  });

  return parseResponse<ReportGenerateResponse>(response);
}

export function toStorageUrl(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const storageIndex = normalized.indexOf("storage/");
  if (storageIndex >= 0) {
    return `/${normalized.slice(storageIndex)}`;
  }
  return normalized.startsWith("/") ? normalized : `/${normalized}`;
}
