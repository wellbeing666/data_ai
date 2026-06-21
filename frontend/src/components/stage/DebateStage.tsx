import { useEffect, useMemo, useState } from "react";

import type { AgentCardView } from "../../utils/workbenchUtils";
import { fullBodyPortraitPath } from "./stageAssets";

type DebateSpeaker = "left" | "right";
type DebateLine = {
  speaker: DebateSpeaker;
  text: string;
};

type DebateRoundLike = {
  aggressive_business_agent?: unknown;
  statistical_qc_agent?: unknown;
  agent_a?: unknown;
  agent_b?: unknown;
};

type DebateRawLike = {
  debate_rounds?: unknown;
  consensus_findings?: unknown;
  statistical_guardrails?: unknown;
  final_consensus?: unknown;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" ? value as Record<string, unknown> : null;
}

function stringFromUnknown(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function fallbackScript(agent: AgentCardView): DebateLine[] {
  return [
    { speaker: "left", text: `已完成结果推演：${agent.output || agent.action}` },
    { speaker: "right", text: "开始审查数据支撑、统计限制和图表口径，避免把相关性写成确定因果。" },
    { speaker: "left", text: "接受审查约束，正在保留可解释发现并标注不确定性。" },
    { speaker: "right", text: "验证通过。共识结论可以进入解释和报告生成环节。" }
  ];
}

function extractDebateLines(agent: AgentCardView): DebateLine[] {
  const raw = asRecord(agent.raw) as DebateRawLike | null;
  if (!raw) {
    return fallbackScript(agent);
  }
  const lines: DebateLine[] = [];
  const rounds = Array.isArray(raw.debate_rounds) ? raw.debate_rounds : [];
  rounds.forEach((round) => {
    const item = asRecord(round) as DebateRoundLike | null;
    if (!item) return;
    const left = stringFromUnknown(item.aggressive_business_agent) || stringFromUnknown(item.agent_a);
    const right = stringFromUnknown(item.statistical_qc_agent) || stringFromUnknown(item.agent_b);
    if (left) lines.push({ speaker: "left", text: left });
    if (right) lines.push({ speaker: "right", text: right });
  });

  const findings = Array.isArray(raw.consensus_findings) ? raw.consensus_findings.map(stringFromUnknown).filter(Boolean) : [];
  const guardrails = Array.isArray(raw.statistical_guardrails) ? raw.statistical_guardrails.map(stringFromUnknown).filter(Boolean) : [];
  const finalConsensus = stringFromUnknown(raw.final_consensus);
  if (findings.length) {
    lines.push({ speaker: "left", text: `共识发现：${findings.slice(0, 2).join("；")}` });
  }
  if (guardrails.length) {
    lines.push({ speaker: "right", text: `统计护栏：${guardrails.slice(0, 2).join("；")}` });
  }
  if (finalConsensus) {
    lines.push({ speaker: "left", text: `最终共识：${finalConsensus}` });
  }
  return lines.length ? lines : fallbackScript(agent);
}

export function DebateStage({ agent }: { agent: AgentCardView }) {
  const lines = useMemo(() => extractDebateLines(agent), [agent]);
  const [entered, setEntered] = useState(false);
  const [lineIndex, setLineIndex] = useState(0);

  useEffect(() => {
    setEntered(false);
    setLineIndex(0);
    const enterTimer = window.setTimeout(() => setEntered(true), 120);
    const lineTimer = window.setInterval(() => {
      setLineIndex((current) => (current + 1) % lines.length);
    }, 3800);
    return () => {
      window.clearTimeout(enterTimer);
      window.clearInterval(lineTimer);
    };
  }, [lines]);

  const currentLine = lines[lineIndex] ?? lines[0];
  const progress = Math.round(((lineIndex + 1) / Math.max(lines.length, 1)) * 100);
  const leftSpeaking = currentLine.speaker === "left";
  const rightSpeaking = currentLine.speaker === "right";

  return (
    <div className={`debate-stage ${entered ? "entered" : ""}`}>
      <section className={`debate-agent debate-agent-left ${leftSpeaking ? "speaking" : "listening"}`}>
        <div className="debate-bubble" aria-live={leftSpeaking ? "polite" : "off"}>
          {leftSpeaking ? currentLine.text : "等待对方论点，准备补充业务洞察。"}
        </div>
        <div className="debate-agent-avatar">
          <img src={fullBodyPortraitPath("analysis")} alt="商业洞察 Agent 全身形象" />
        </div>
        <strong>激进商业洞察 Agent</strong>
        <span>寻找增长机会和业务解释</span>
      </section>

      <section className="debate-center" aria-label="辩论进度">
        <div className="debate-vs">VS</div>
        <p>矩阵收敛对抗中</p>
        <div className="debate-progress"><span style={{ width: `${progress}%` }} /></div>
        <small>第 {lineIndex + 1} / {lines.length} 句</small>
      </section>

      <section className={`debate-agent debate-agent-right ${rightSpeaking ? "speaking" : "listening"}`}>
        <div className="debate-bubble" aria-live={rightSpeaking ? "polite" : "off"}>
          {rightSpeaking ? currentLine.text : "记录业务判断，等待统计证据复核。"}
        </div>
        <div className="debate-agent-avatar">
          <img src={fullBodyPortraitPath("validation")} alt="统计质检 Agent 全身形象" />
        </div>
        <strong>严谨统计质检 Agent</strong>
        <span>校验口径、限制和证据链</span>
      </section>
    </div>
  );
}

