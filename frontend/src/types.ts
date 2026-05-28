export interface DatasetUploadResponse {
  dataset_id: string;
  filename: string;
  file_type: string;
  file_path: string;
  asset_type?: "tabular" | "image";
  preview_url?: string | null;
}

export interface MissingValueSummary {
  count: number;
  ratio: number;
}

export interface NumericColumnSummary {
  min: number | null;
  max: number | null;
  mean: number | null;
}

export interface TextColumnSummary {
  unique_values: string[];
}

export interface DatasetProfile {
  dataset_id: string;
  filename: string;
  file_type: string;
  file_path: string;
  profile_path: string;
  row_count: number;
  column_count: number;
  columns: string[];
  dtypes: Record<string, string>;
  missing_values: Record<string, MissingValueSummary>;
  numeric_summary: Record<string, NumericColumnSummary>;
  text_summary: Record<string, TextColumnSummary>;
  sample_rows: Record<string, unknown>[];
}

export interface AnalysisJobResponse {
  job_id: string;
  analysis_type: string;
  result_path: string;
  charts_dir: string;
}

export interface HealthStatus {
  status: string;
  llm_mode: string;
  deepseek_configured: boolean;
  doubao_configured?: boolean;
  message: string;
}

export type TaskStatus =
  | "pending"
  | "planning"
  | "running_code"
  | "validating"
  | "generating_report"
  | "success"
  | "failed";

export interface GradeSummaryRow {
  class_name: string;
  student_count: number;
  average_score: number;
  max_score: number;
  min_score: number;
  pass_rate: number;
  excellent_rate: number;
}

export interface AnalysisResult {
  success?: boolean;
  task_type?: string;
  analysis_type?: string;
  analysis_plan?: {
    task_type?: string;
    task_name?: string;
    steps?: Array<{
      step_id?: string;
      name?: string;
      description?: string;
    }>;
  };
  summary?: GradeSummaryRow[] | string;
  charts?: string[];
  thresholds?: {
    pass_score?: number;
    excellent_score?: number;
  };
  [key: string]: unknown;
}

export interface ReportGenerateResponse {
  report_path: string;
  analysis_result_path: string;
  chart_paths: string[];
}

export interface AutoRepairAttemptResult {
  attempt: number;
  script_path: string;
  safety_result_path?: string | null;
  execution_result_path: string;
  validation_result_path: string;
  passed: boolean;
  should_retry: boolean;
  severity: string;
  safety_issues?: string[] | null;
}

export interface AutoRepairAnalysisJobResponse {
  job_id: string;
  status: string;
  current_stage?: string | null;
  attempts: AutoRepairAttemptResult[];
  final_result_path: string | null;
  final_report_data_path: string | null;
  final_validation_result_path: string | null;
  job_dir: string;
  controller_plan_path?: string | null;
  rag_retrieval_path?: string | null;
  dataset_profile_path?: string | null;
  data_understanding_path?: string | null;
  analysis_plan_path?: string | null;
  explanation_path?: string | null;
  effective_max_retries?: number | null;
  events?: ExecutionLogEvent[];
  error?: Record<string, unknown> | null;
}

export interface KnowledgeDocument {
  doc_id: string;
  filename: string;
  file_type: string;
  raw_path: string;
  created_at: string;
  chunk_count: number;
  indexed: boolean;
  index_error?: string | null;
}

export interface KnowledgeDocumentListResponse {
  documents: KnowledgeDocument[];
}

export interface KnowledgeDeleteResponse {
  doc_id: string;
  deleted: boolean;
}

export interface KnowledgeSearchResult {
  doc_id: string;
  filename: string;
  source: string;
  chunk_index: number;
  chunk: string;
  score?: number | null;
  distance?: number | null;
}

export interface KnowledgeSearchResponse {
  query: string;
  expanded_query: string;
  available: boolean;
  message: string;
  results: KnowledgeSearchResult[];
}

export interface ExplanationResult {
  summary: string;
  key_findings: string[];
  chart_explanations: Array<{
    chart?: string;
    explanation?: string;
  }>;
  recommendations: string[];
  limitations: string[];
  ppt_outline: Array<{
    title: string;
    bullets: string[];
    chart?: string;
  }>;
}

export interface ExecutionLogEvent {
  timestamp: string;
  stage: string;
  status: string;
  message: string;
  attempt?: number | null;
}

export interface ExecutionAttemptLog {
  attempt: number;
  path: string;
  exit_code?: number | null;
  stdout?: string;
  stderr?: string;
  success?: boolean;
  timed_out?: boolean;
  duration_ms?: number | null;
}

export interface ValidationAttemptLog {
  attempt: number;
  path: string;
  passed: boolean;
  severity: string;
  issues: Array<Record<string, unknown>>;
  repair_suggestions: Array<Record<string, unknown>>;
  should_retry: boolean;
}

export interface ExecutionLog {
  job_id: string;
  dataset_id?: string | null;
  status: string;
  workflow_type: string;
  user_goal: string;
  analysis_plan?: Record<string, unknown> | null;
  generated_python_code_paths: string[];
  executor_code_path?: string | null;
  execution_results: ExecutionAttemptLog[];
  validation_results: ValidationAttemptLog[];
  retry_count: number;
  max_retries: number;
  artifacts: Record<string, unknown>;
  events: ExecutionLogEvent[];
}

export interface PredictionAttemptResult {
  attempt: number;
  script_path: string;
  safety_result_path?: string | null;
  execution_result_path: string;
  validation_result_path: string;
  passed: boolean;
  should_retry: boolean;
  severity: string;
  safety_issues?: string[] | null;
}

export interface PredictionJobResponse {
  job_id: string;
  status: string;
  current_stage?: string | null;
  attempts: PredictionAttemptResult[];
  final_prediction_result_path: string | null;
  final_report_data_path: string | null;
  final_validation_result_path: string | null;
  job_dir: string;
  dataset_profile_path?: string | null;
  rag_retrieval_path?: string | null;
  hypothesis_plan_path?: string | null;
  prediction_plan_path?: string | null;
  prediction_explanation_path?: string | null;
  effective_max_retries?: number | null;
  events?: ExecutionLogEvent[];
  error?: Record<string, unknown> | null;
}

export interface PredictionResult {
  task_type: "what_if_prediction";
  scenario_summary: string;
  target_metric: string;
  intervention: Record<string, unknown>;
  entity_dimension: string;
  top_impacted_entities: Array<{
    entity: string;
    baseline_value: number;
    predicted_value: number;
    absolute_change: number;
    percent_change: number;
    direction: string;
    explanation: string;
  }>;
  baseline_summary: Record<string, unknown>;
  predicted_summary: Record<string, unknown>;
  model_info: Record<string, unknown>;
  limitations: string[];
  charts: string[];
  [key: string]: unknown;
}

export interface PredictionExplanationResult {
  summary: string;
  key_findings: string[];
  top_impacted_entities: Array<Record<string, unknown>>;
  recommendations: string[];
  limitations: string[];
  ppt_outline: Array<{
    title: string;
    bullets: string[];
    chart?: string;
  }>;
}

export interface PredictionLogResponse {
  job_id: string;
  dataset_id?: string | null;
  status: string;
  workflow_type: string;
  user_goal: string;
  prediction_plan?: Record<string, unknown> | null;
  generated_python_code_paths: string[];
  execution_results: ExecutionAttemptLog[];
  validation_results: ValidationAttemptLog[];
  retry_count: number;
  max_retries: number;
  artifacts: Record<string, unknown>;
  events: ExecutionLogEvent[];
}

export interface WorkflowJobResponse {
  job_id: string;
  status: string;
  current_stage?: string | null;
  workflow_type?: string | null;
  task_type?: string | null;
  asset_type?: string | null;
  attempts: AutoRepairAttemptResult[];
  job_dir: string;
  controller_plan_path?: string | null;
  rag_retrieval_path?: string | null;
  dataset_profile_path?: string | null;
  visual_parse_result_path?: string | null;
  visual_extracted_dataset_path?: string | null;
  visual_extraction_confidence?: number | null;
  data_understanding_path?: string | null;
  analysis_plan_path?: string | null;
  explanation_path?: string | null;
  hypothesis_plan_path?: string | null;
  prediction_plan_path?: string | null;
  prediction_explanation_path?: string | null;
  final_result_path: string | null;
  final_prediction_result_path: string | null;
  final_report_data_path: string | null;
  final_validation_result_path: string | null;
  effective_max_retries?: number | null;
  events?: ExecutionLogEvent[];
  error?: Record<string, unknown> | null;
}

export interface WorkflowLogResponse {
  job_id: string;
  dataset_id?: string | null;
  status: string;
  workflow_type: string;
  task_type?: string | null;
  asset_type?: string | null;
  user_goal: string;
  analysis_plan?: Record<string, unknown> | null;
  prediction_plan?: Record<string, unknown> | null;
  generated_python_code_paths: string[];
  executor_code_path?: string | null;
  execution_results: ExecutionAttemptLog[];
  validation_results: ValidationAttemptLog[];
  retry_count: number;
  max_retries: number;
  artifacts: Record<string, unknown>;
  events: ExecutionLogEvent[];
}

export interface VisualParseResult {
  success: boolean;
  image_type: string;
  tables: Array<Record<string, unknown>>;
  chart_data: Array<unknown>;
  selected_table: {
    columns?: string[];
    rows?: Array<Record<string, unknown>>;
    confidence?: number;
  };
  columns: string[];
  rows: Array<Record<string, unknown>>;
  confidence: number;
  warnings: string[];
  limitations: string[];
}
