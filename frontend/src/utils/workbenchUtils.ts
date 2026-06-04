import type {
  AnalysisResult,
  AutoRepairAttemptResult,
  ExecutionAttemptLog,
  ExecutionLogEvent,
  ExplanationResult,
  PredictionExplanationResult,
  PredictionResult,
  QualityReview,
  ValidationAttemptLog,
  VisualParseResult,
  WorkflowJobResponse,
  WorkflowLogResponse
} from "../types";

export type AnyRecord = Record<string, unknown>;
export type PageKey = "setup" | "knowledge" | "prediction" | "roadmap" | "process" | "charts" | "insights" | "logs";

export interface StepView {
  key: string;
  title: string;
  stageNames: string[];
  status: "pending" | "active" | "done" | "failed";
  summary: string;
}

export type ArtifactKind =
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
  | "quality_review"
  | "generic";

export interface AgentCardView extends StepView {
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

export interface AttemptProgressView {
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

export const emptyExplanation: ExplanationResult = {
  summary: "",
  key_findings: [],
  chart_explanations: [],
  recommendations: [],
  limitations: [],
  ppt_outline: []
};

export const emptyPredictionExplanation: PredictionExplanationResult = {
  summary: "",
  key_findings: [],
  top_impacted_entities: [],
  recommendations: [],
  limitations: [],
  ppt_outline: []
};

export const terminalStatuses = new Set(["success", "failed", "cancelled"]);
const analysisFileExtensions = new Set(["csv", "xlsx", "xls", "png", "jpg", "jpeg", "webp"]);

export function isSupportedAnalysisFile(file: File): boolean {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return analysisFileExtensions.has(extension);
}

export function buildAgentCards(input: {
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
  qualityReview: QualityReview | null;
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
    if (step.key === "quality_review") {
      return {
        ...card,
        raw: input.qualityReview,
        artifactKind: "quality_review",
        artifactPath: input.job?.quality_review_path,
        artifactLabel: "quality_review.json",
        evidence: qualityReviewEvidence(input.qualityReview)
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

export function buildAttemptProgressViews(input: {
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

export function latestAttemptStageStatus(events: ExecutionLogEvent[], attempt: number, stages: string[]): string | undefined {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.attempt === attempt && stages.includes(event.stage)) {
      return event.status;
    }
  }
  return undefined;
}

export function attemptStageText(status: string | undefined): string {
  if (!status) {
    return "等待中";
  }
  return eventStatusLabel(status);
}

export function attemptStageClass(status: string | undefined): string {
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

export function attemptStatusClass(attempt: AttemptProgressView): StepView["status"] {
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

export function attemptStatusText(attempt: AttemptProgressView): string {
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

export function shouldShowAgentCard(card: AgentCardView, job: WorkflowJobResponse | null): boolean {
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

export function cardBase(step: StepView, isPredictionWorkflow: boolean): Omit<AgentCardView, keyof StepView | "output"> {
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
    },
    quality_review: {
      agentName: "质检 Agent",
      inputSource: "验证结果、图表产物和解释结论",
      action: "检查结论是否有数据支撑，识别因果误写、样本量和不确定性风险。",
      evidence: [],
      artifactKind: "quality_review"
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

export function buildAgentSteps(input: {
  job: WorkflowJobResponse | null;
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  visualParseResult: VisualParseResult | null;
  dataUnderstanding: AnyRecord | null;
  analysisPlan: AnyRecord | null;
  executionLog: WorkflowLogResponse | null;
  explanation: ExplanationResult;
  qualityReview: QualityReview | null;
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
    },
    {
      key: "quality_review",
      title: "质检 Agent 正在审查结论",
      stageNames: ["quality_review"],
      done: Boolean(input.qualityReview),
      summary: qualityReviewSummary(input.qualityReview)
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

export function buildPredictionSteps(input: {
  job: WorkflowJobResponse | null;
  log: WorkflowLogResponse | null;
  controllerPlan: AnyRecord | null;
  ragRetrieval: AnyRecord | null;
  visualParseResult: VisualParseResult | null;
  hypothesisPlan: AnyRecord | null;
  predictionPlan: AnyRecord | null;
  predictionResult: PredictionResult | null;
  explanation: PredictionExplanationResult;
  qualityReview: QualityReview | null;
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
    },
    {
      key: "quality_review",
      title: "质检 Agent 正在审查预测结论",
      stageNames: ["quality_review"],
      done: Boolean(input.qualityReview),
      summary: qualityReviewSummary(input.qualityReview)
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

export function stepStatus(input: { done: boolean; active: boolean; failed: boolean }): StepView["status"] {
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

export function hasFailedEvent(events: ExecutionLogEvent[], stages: string[]): boolean {
  return events.some((event) => stages.includes(event.stage) && event.status === "failed");
}

export function latestStageEvent(events: ExecutionLogEvent[], stages: string[]): ExecutionLogEvent | undefined {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (stages.includes(event.stage)) {
      return event;
    }
  }
  return undefined;
}

export function isActiveEventStatus(status: string | undefined): boolean {
  return status === "running" || status === "retrying";
}

export function isDoneEventStatus(status: string | undefined): boolean {
  return status === "success" || status === "fallback" || status === "failed";
}

export function visualEvidence(result: VisualParseResult | null, job: WorkflowJobResponse | null): string[] {
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

export function ragEvidence(result: AnyRecord | null): string[] {
  if (!result) {
    return ["等待知识库检索结果。"];
  }
  const results = Array.isArray(result.results) ? result.results : [];
  return [`命中知识片段：${results.length} 条`, stringValue(result.message, "已完成知识库检索。")];
}

export function controllerEvidence(plan: AnyRecord | null, job: WorkflowJobResponse | null): string[] {
  if (!plan) {
    return ["等待主控 Agent 输出任务类型。"];
  }
  return [
    `任务类型：${stringValue(plan.task_type, stringValue(job?.task_type, "-"))}`,
    `工作流：${workflowLabel(job?.workflow_type || plan.task_type)}`,
    stringValue(plan.reasoning_summary, "已根据用户目标和数据画像完成分流。")
  ];
}

export function understandingEvidence(result: AnyRecord | null): string[] {
  if (!result) {
    return ["等待字段语义识别结果。"];
  }
  return [
    `目标字段：${arrayValue(result.target_columns).join("、") || "-"}`,
    `维度字段：${arrayValue(result.dimension_columns).join("、") || "-"}`,
    `质量问题：${arrayValue(result.quality_issues).length} 项`
  ];
}

export function analysisEvidence(plan: AnyRecord | null): string[] {
  if (!plan) {
    return ["等待分析计划。"];
  }
  return [
    `分析方法：${arrayValue(plan.methods).join("、") || "-"}`,
    `指标：${arrayValue(plan.metrics).join("、") || "-"}`,
    `图表数量：${Array.isArray(plan.chart_plan) ? plan.chart_plan.length : 0}`
  ];
}

export function hypothesisEvidence(plan: AnyRecord | null): string[] {
  if (!plan) {
    return ["等待假设解析。"];
  }
  return [
    `目标指标：${structuredFieldValue(plan.target_metric)}`,
    `对象维度：${structuredFieldValue(plan.entity_dimension)}`,
    `干预变量：${stringValue(plan.intervention_variable, interventionDisplay(plan.intervention))}`
  ];
}

export function predictionEvidence(plan: AnyRecord | null): string[] {
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

export function attemptEvidence(attempt: AutoRepairAttemptResult | undefined): string[] {
  if (!attempt) {
    return ["等待代码生成。"];
  }
  return [
    `尝试次数：第 ${attempt.attempt} 次`,
    `脚本：${attempt.script_path ? shortPath(attempt.script_path) : "-"}`,
    `当前验证：${attempt.passed ? "通过" : "未通过"}`
  ];
}

export function executionEvidence(execution: ExecutionAttemptLog | undefined): string[] {
  if (!execution) {
    return ["等待沙箱执行。"];
  }
  return [
    `执行结果：${execution.success ? "成功" : "失败"}`,
    `退出码：${execution.exit_code ?? "-"}`,
    `耗时：${execution.duration_ms ?? "-"} ms`
  ];
}

export function validationEvidence(validation: ValidationAttemptLog | undefined): string[] {
  if (!validation) {
    return ["等待验证 Agent 输出。"];
  }
  return [
    `验证结果：${validation.passed ? "通过" : "未通过"}`,
    `严重级别：${severityLabel(validation.severity)}`,
    `问题数量：${validation.issues.length}`
  ];
}

export function explanationEvidence(explanation: ExplanationResult): string[] {
  if (!explanation.summary) {
    return ["等待解释 Agent 生成结论。"];
  }
  return [
    `关键发现：${explanation.key_findings.length} 条`,
    `建议动作：${explanation.recommendations.length} 条`,
    `限制说明：${explanation.limitations.length} 条`
  ];
}


export function qualityReviewEvidence(review: QualityReview | null): string[] {
  if (!review) {
    return ["等待质检 Agent 审查解释结论。"];
  }
  return [
    `质检结果：${review.passed ? "通过" : "存在风险"}`,
    `风险级别：${severityLabel(review.risk_level)}`,
    `问题数量：${review.issues?.length ?? 0}`
  ];
}

export function qualityReviewSummary(review: QualityReview | null): string {
  if (!review) {
    return "等待解释结论生成后进行自检。";
  }
  if (review.passed) {
    return review.revised_summary || "质检通过，未发现需要阻断的问题。";
  }
  return review.revised_summary || `发现 ${review.issues?.length ?? 0} 个结论风险，需要谨慎表述。`;
}

export function controllerSummary(plan: AnyRecord | null): string {
  if (!plan) {
    return "等待主控 Agent 判断任务类型。";
  }
  return `${stringValue(plan.task_type, "unknown")}，${stringValue(plan.task_name, "已生成任务计划")}`;
}

export function ragSummary(result: AnyRecord | null): string {
  if (!result) {
    return "等待数据画像生成后检索全局知识库。";
  }
  const results = Array.isArray(result.results) ? result.results : [];
  const message = stringValue(result.message, "RAG 检索完成。");
  return results.length ? `命中 ${results.length} 条知识片段。${message}` : message;
}

export function visualSummary(result: VisualParseResult | null, job: WorkflowJobResponse | null): string {
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

export function understandingSummary(result: AnyRecord | null): string {
  if (!result) {
    return "等待字段语义识别。";
  }
  const targets = arrayValue(result.target_columns);
  const dimensions = arrayValue(result.dimension_columns);
  return `目标字段 ${targets.join("、") || "-"}；维度字段 ${dimensions.slice(0, 4).join("、") || "-"}`;
}

export function analysisSummary(plan: AnyRecord | null): string {
  if (!plan) {
    return "等待分析方法选择。";
  }
  const metrics = arrayValue(plan.metrics);
  const methods = arrayValue(plan.methods);
  return `指标 ${metrics.join("、") || "-"}；方法 ${methods.slice(0, 2).join("；") || "-"}`;
}

export function predictionPlanSummary(plan: AnyRecord): string {
  const target = stringValue(plan.target_metric, "-");
  const entity = stringValue(plan.entity_dimension, "-");
  const models = arrayValue(plan.model_candidates).slice(0, 2).join("、") || "-";
  return `目标 ${target}；对象 ${entity}；候选模型 ${models}`;
}

export function getChartPaths(
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

export function normalizeChartPath(chart: unknown, job?: WorkflowJobResponse | null): string | null {
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

export function normalizeChartPathString(path: string, job?: WorkflowJobResponse | null): string {
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

export function isRecord(value: unknown): value is AnyRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function toExplanationResult(predictionExplanation: PredictionExplanationResult): ExplanationResult {
  return normalizeExplanationResult({
    summary: predictionExplanation.summary,
    key_findings: predictionExplanation.key_findings,
    chart_explanations: [],
    recommendations: predictionExplanation.recommendations,
    limitations: predictionExplanation.limitations,
    ppt_outline: predictionExplanation.ppt_outline
  });
}

export function normalizeExplanationResult(value: Partial<ExplanationResult> | null | undefined): ExplanationResult {
  return {
    summary: typeof value?.summary === "string" ? value.summary : "",
    key_findings: normalizeStringArray(value?.key_findings),
    chart_explanations: Array.isArray(value?.chart_explanations) ? value.chart_explanations : [],
    recommendations: normalizeStringArray(value?.recommendations),
    limitations: normalizeStringArray(value?.limitations),
    ppt_outline: normalizePptOutline(value?.ppt_outline)
  };
}

export function normalizePptOutline(value: unknown): ExplanationResult["ppt_outline"] {
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

export function normalizeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map((item) => formatListItem(item)).filter(Boolean);
}

export function formatListItem(value: unknown): string {
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

export function chartTitle(path: string, index: number): string {
  const filename = path.replace(/\\/g, "/").split("/").pop();
  return filename || `图表 ${index + 1}`;
}

export function statusFromJob(value: string): "idle" | "uploading" | "running" | "success" | "failed" {
  if (value === "success") {
    return "success";
  }
  if (value === "failed" || value === "cancelled") {
    return "failed";
  }
  return "running";
}

export function messageFromJob(job: WorkflowJobResponse): string {
  if (job.status === "success") {
    return "分析完成。";
  }
  if (job.status === "failed") {
    return job.error?.message ? String(job.error.message) : "分析未完成，请查看执行日志。";
  }
  if (job.status === "cancelled") {
    return "分析任务已取消。";
  }
  return `${stageLabel(job.current_stage ?? "running")}，状态实时刷新中。`;
}

export function predictionMessageFromJob(job: WorkflowJobResponse): string {
  if (job.status === "success") {
    return "情景预测完成。";
  }
  if (job.status === "failed") {
    return job.error?.message ? String(job.error.message) : "情景预测未完成，请查看日志。";
  }
  if (job.status === "cancelled") {
    return "情景预测任务已取消。";
  }
  return `${stageLabel(job.current_stage ?? "running")}，预测状态实时刷新中。`;
}

export function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    idle: "待开始",
    uploading: "上传中",
    running: "Agent 运行中",
    success: "已完成",
    failed: "未完成",
    cancelled: "已取消"
  };
  return labels[value] ?? value;
}

export function stepStatusLabel(value: StepView["status"]): string {
  const labels: Record<StepView["status"], string> = {
    pending: "等待中",
    active: "运行中",
    done: "已完成",
    failed: "失败"
  };
  return labels[value];
}

export function workflowLabel(value: unknown): string {
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

export function imageTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    table: "表格截图",
    chart: "图表截图",
    dashboard: "业务看板",
    other: "其他图片"
  };
  return labels[value] ?? value;
}

export function severityLabel(value: string): string {
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

export function stageLabel(value: string): string {
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
    quality_review: "质检自检",
    success: "已完成",
    failed: "失败",
    running: "运行中",
    uploading: "上传中"
  };
  return labels[value] ?? value;
}

export function eventStatusLabel(value: string): string {
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

export function mergeWorkflowEvents(
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

export function eventTime(event: ExecutionLogEvent): number {
  const value = new Date(event.timestamp).getTime();
  return Number.isNaN(value) ? 0 : value;
}

export function agentInitial(name: string): string {
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
  if (name.includes("质检")) {
    return "检";
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

export function formatNumber(value: number): string {
  return Number.isFinite(value) ? value.toFixed(2) : "-";
}

export function formatPercent(value: number): string {
  return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : "-";
}

export function stringValue(value: unknown, fallback: string): string {
  if (typeof value === "string" && value) {
    return localizeUiText(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

export function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => formatListItem(item)).filter(Boolean) : [];
}

export function structuredFieldValue(value: unknown, fallback = "-"): string {
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

export function interventionDisplay(value: unknown): string {
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

export function buildNoChartReason(
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

export function localizeUiText(value: string): string {
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

export function formatDateTime(value: string): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

export function shortPath(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts.slice(-3).join("/");
}

export function formatTime(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString();
}

export function formatCell(value: unknown): string {
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




