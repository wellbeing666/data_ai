export interface AuthUser {
  id: string;
  login_account: string;
  username: string;
  role: "user" | "admin" | string;
  status: "pending" | "active" | "frozen" | "rejected" | string;
  created_at?: string | null;
  updated_at?: string | null;
  approved_at?: string | null;
  last_login_at?: string | null;
  audit_reason?: string | null;
}

export interface AuthLoginResponse {
  token: string;
  token_type: string;
  expires_at: string;
  user: AuthUser;
}

export interface AuthRegisterResponse {
  user: AuthUser;
  message: string;
}

export interface AuthCurrentUserResponse {
  user: AuthUser;
}

export interface AuthUserListResponse {
  users: AuthUser[];
}

export interface AuthMessageResponse {
  message: string;
  data?: Record<string, unknown>;
}

export interface DatasetUploadResponse {
  dataset_id: string;
  filename: string;
  file_type: string;
  file_path: string;
  asset_type?: "tabular" | "image";
  preview_url?: string | null;
}

export interface SampleDatasetResponse extends DatasetUploadResponse {
  sample_type: string;
  recommended_goal: string;
  description: string;
  suggested_goals: string[];
}

export interface SampleDatasetType {
  sample_type: string;
  filename: string;
  description: string;
  recommended_goal: string;
  suggested_goals: string[];
}

export interface SampleDatasetTypeListResponse {
  samples: SampleDatasetType[];
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
  charts?: unknown[];
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
  pptx_path?: string | null;
  pptx_preview_path?: string | null;
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
  owner_user_id?: string | null;
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

export interface IntentQuestionOption {
  value: string;
  label: string;
  append_text: string;
}

export interface IntentQuestion {
  question_id: string;
  question: string;
  options: IntentQuestionOption[];
}

export interface PreflightAssessment {
  dataset_id: string;
  user_goal: string;
  asset_type?: string;
  preflight_path?: string | null;
  intent_type: string;
  is_task_clear: boolean;
  clarity_score: number;
  detected_fields: Array<Record<string, unknown>>;
  data_quality_report: Record<string, unknown>;
  clarifying_questions: string[];
  intent_questions: IntentQuestion[];
  suggested_goals: string[];
  optimized_goal: string;
  next_action: string;
  data_understanding: Record<string, unknown>;
}

export interface AnalysisRoadmapStep {
  step_id: string;
  title: string;
  agent: string;
  stage: string;
  description: string;
  inputs: string[];
  outputs: string[];
  status_hint: string;
}

export interface AnalysisRoadmap {
  title: string;
  user_goal: string;
  workflow_type: string;
  task_type: string;
  graph_type?: string;
  summary: string;
  steps: AnalysisRoadmapStep[];
  mermaid_code?: string;
  dot_code?: string;
  dot_path?: string | null;
  mermaid_path?: string | null;
  render_script_path?: string | null;
  rendered_image_path?: string | null;
  rendered_image_url?: string | null;
}

export interface QualityReviewIssue {
  issue_type: string;
  severity: string;
  finding: string;
  evidence: string;
  suggestion: string;
}

export interface QualityReview {
  passed: boolean;
  risk_level: string;
  issues: QualityReviewIssue[];
  checked_items: Array<Record<string, unknown>>;
  revised_summary: string;
  safe_language_suggestions: string[];
  missing_evidence: string[];
}

export interface ChartSuggestionResponse {
  job_id: string;
  chart_path: string;
  suggestions: string[];
}


export interface ChartConfigResponse {
  chart_id: string;
  title: string;
  description: string;
  echarts_option: Record<string, unknown>;
  data_preview: Array<Record<string, unknown>>;
  applied_filters: string[];
  warnings: string[];
  config_path?: string | null;
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
  owner_user_id?: string | null;
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
  owner_user_id?: string | null;
  status: string;
  current_stage?: string | null;
  attempts: PredictionAttemptResult[];
  final_prediction_result_path: string | null;
  final_report_data_path: string | null;
  chart_paths?: string[];
  final_validation_result_path: string | null;
  job_dir: string;
  dataset_profile_path?: string | null;
  rag_retrieval_path?: string | null;
  hypothesis_plan_path?: string | null;
  prediction_plan_path?: string | null;
  prediction_explanation_path?: string | null;
  quality_review_path?: string | null;
  effective_max_retries?: number | null;
  events?: ExecutionLogEvent[];
  error?: Record<string, unknown> | null;
}

export interface PredictionResult {
  task_type: "what_if_prediction";
  status?: "unsupported" | string;
  unsupported_reason?: string;
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
  charts: unknown[];
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
  owner_user_id?: string | null;
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
  owner_user_id?: string | null;
  dataset_id?: string | null;
  user_goal?: string | null;
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
  analysis_roadmap_path?: string | null;
  quality_review_path?: string | null;
  cleaning_report_path?: string | null;
  evidence_chain_path?: string | null;
  report_path?: string | null;
  pptx_path?: string | null;
  pptx_preview_path?: string | null;
  job_control_path?: string | null;
  control_state?: Record<string, unknown>;
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
  insight_result_path?: string | null;
  debate_reflection_path?: string | null;
  chart_paths?: string[];
  effective_max_retries?: number | null;
  events?: ExecutionLogEvent[];
  error?: Record<string, unknown> | null;
}

export interface WorkflowJobListItem {
  job_id: string;
  owner_user_id?: string | null;
  dataset_id?: string | null;
  dataset_filename?: string | null;
  file_type?: string | null;
  user_goal: string;
  status: string;
  current_stage?: string | null;
  workflow_type?: string | null;
  task_type?: string | null;
  asset_type?: "tabular" | "image" | string | null;
  chart_count: number;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkflowJobListResponse {
  jobs: WorkflowJobListItem[];
}

export interface WorkflowJobDeleteResponse {
  deleted: boolean;
  job_id: string;
}


export interface WorkflowLogResponse {
  job_id: string;
  owner_user_id?: string | null;
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





export interface ChartRefineResponse {
  success: boolean;
  message: string;
  job_id: string;
  chart_path: string;
  instruction: string;
  source_script_path?: string | null;
  refined_script_path?: string | null;
  execution_result_path?: string | null;
  chart_paths: string[];
  safety_issues: string[];
}

export interface ChartDeleteResponse {
  deleted: boolean;
  chart_path: string;
  chart_paths: string[];
}






export interface CleaningStrategyOption {
  strategy_id: string;
  label: string;
  description: string;
  recommended: boolean;
}

export interface CleaningIssue {
  issue_id: string;
  issue_type: string;
  column?: string | null;
  message: string;
  affected_count: number;
  severity: string;
  default_strategy_id: string;
  strategies: CleaningStrategyOption[];
  examples?: unknown[];
  metadata?: Record<string, unknown>;
}

export interface CleaningPreview {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}

export interface CleaningPlanResponse {
  dataset_id: string;
  asset_type: string;
  source_file?: string | null;
  plan_path?: string | null;
  created_at?: string | null;
  row_count: number;
  column_count: number;
  columns: string[];
  has_issues: boolean;
  issues: CleaningIssue[];
  recommended_strategy_ids: Record<string, string>;
  preview: CleaningPreview;
  message: string;
}

export interface CleaningAppliedStrategy {
  issue_id: string;
  issue_type?: string | null;
  column?: string | null;
  strategy_id: string;
  strategy_label: string;
  description: string;
  rows_before: number;
  rows_after: number;
  columns_before: number;
  columns_after: number;
}

export interface CleaningReportResponse {
  dataset_id: string;
  source_file?: string | null;
  cleaned_dataset_path?: string | null;
  cleaning_report_path?: string | null;
  created_at?: string | null;
  row_count_before: number;
  row_count_after: number;
  column_count_before: number;
  column_count_after: number;
  applied_strategies: CleaningAppliedStrategy[];
  preview: CleaningPreview;
  message: string;
}

export interface EvidenceItem {
  number?: string;
  source_file?: string;
  json_path?: string;
  value?: unknown;
  row_context?: Record<string, unknown> | null;
  calculation?: string;
}

export interface EvidenceFinding {
  finding_id: string;
  text: string;
  numbers: Array<Record<string, unknown>>;
  has_evidence: boolean;
  risk_level: string;
  evidence_items: EvidenceItem[];
  charts: string[];
  calculation_note: string;
}

export interface EvidenceChain {
  evidence_version: string;
  risk_level: string;
  high_risk_count: number;
  source_files: string[];
  findings: EvidenceFinding[];
  summary: string;
}

export interface WorkflowControlResponse {
  job_id: string;
  action: string;
  accepted: boolean;
  message: string;
  status?: string | null;
}

export interface WorkflowPptxGenerateResponse {
  job_id: string;
  pptx_path?: string | null;
  pptx_preview_path?: string | null;
  message: string;
  status?: string | null;
}

export interface WorkflowFollowUpResponse {
  job_id: string;
  question: string;
  answer: string;
  follow_up_path?: string | null;
  created_at?: string | null;
  used_artifacts: string[];
}

export interface PptPreviewSlide {
  page: number;
  title: string;
  subtitle?: string;
  section_label?: string;
  bullets: string[];
  chart?: string;
}

export interface PptPreview {
  pptx_path?: string | null;
  slides: PptPreviewSlide[];
}


