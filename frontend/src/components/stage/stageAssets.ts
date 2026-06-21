const AGENT_STAGE_IMAGE_KEYS = new Set([
  "visual",
  "rag",
  "controller",
  "understanding",
  "analysis",
  "hypothesis",
  "prediction_plan",
  "code",
  "safety",
  "sandbox",
  "validation",
  "debate_matrix",
  "explanation",
  "quality_review",
  "cross_artifact_consistency",
  "generic"
]);

type StageAccent = {
  accent: string;
  accentRgb: string;
};

const STAGE_ACCENTS: Record<string, StageAccent> = {
  visual: { accent: "#0f766e", accentRgb: "15, 118, 110" },
  rag: { accent: "#2563eb", accentRgb: "37, 99, 235" },
  controller: { accent: "#14b8a6", accentRgb: "20, 184, 166" },
  understanding: { accent: "#7c3aed", accentRgb: "124, 58, 237" },
  analysis: { accent: "#ea580c", accentRgb: "234, 88, 12" },
  hypothesis: { accent: "#7c3aed", accentRgb: "124, 58, 237" },
  prediction_plan: { accent: "#15803d", accentRgb: "21, 128, 61" },
  code: { accent: "#1d4ed8", accentRgb: "29, 78, 216" },
  safety: { accent: "#be123c", accentRgb: "190, 18, 60" },
  sandbox: { accent: "#334155", accentRgb: "51, 65, 85" },
  validation: { accent: "#0f766e", accentRgb: "15, 118, 110" },
  debate_matrix: { accent: "#7c2d12", accentRgb: "124, 45, 18" },
  explanation: { accent: "#4338ca", accentRgb: "67, 56, 202" },
  quality_review: { accent: "#0f766e", accentRgb: "15, 118, 110" },
  cross_artifact_consistency: { accent: "#0f172a", accentRgb: "15, 23, 42" },
  generic: { accent: "#0f766e", accentRgb: "15, 118, 110" }
};

function normalizeAgentKey(agentKey: string): string {
  return AGENT_STAGE_IMAGE_KEYS.has(agentKey) ? agentKey : "generic";
}

export function fullBodyPortraitPath(agentKey: string): string {
  return `/agent-portraits/full-body/${normalizeAgentKey(agentKey)}.svg`;
}

export function stageAccentForAgent(agentKey: string): StageAccent {
  return STAGE_ACCENTS[normalizeAgentKey(agentKey)] ?? STAGE_ACCENTS.generic;
}
