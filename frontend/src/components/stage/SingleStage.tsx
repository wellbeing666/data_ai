import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";

import type { AgentCardView } from "../../utils/workbenchUtils";
import { fullBodyPortraitPath } from "./stageAssets";

type SingleScene = {
  label: string;
  headline: string;
  opening: string;
  accent: string;
  accentRgb: string;
  orbitLabel: string;
  nodes: string[];
};

const SCENES: Record<string, SingleScene> = {
  visual: {
    label: "视觉扫描台",
    headline: "图像结构抽取",
    opening: "锁定图片区域、表格边界与关键数值。",
    accent: "#0ea5e9",
    accentRgb: "14, 165, 233",
    orbitLabel: "视觉模型",
    nodes: ["图像", "表格", "字段", "CSV"]
  },
  rag: {
    label: "知识星图",
    headline: "业务上下文检索",
    opening: "从知识库中召回业务口径和分析约束。",
    accent: "#2563eb",
    accentRgb: "37, 99, 235",
    orbitLabel: "向量检索",
    nodes: ["画像", "目标", "召回", "上下文"]
  },
  controller: {
    label: "主控调度塔",
    headline: "任务分流与路线选择",
    opening: "汇总目标、画像与知识上下文，确定执行路线。",
    accent: "#0284c7",
    accentRgb: "2, 132, 199",
    orbitLabel: "Master Plan",
    nodes: ["目标", "类型", "路线", "任务"]
  },
  understanding: {
    label: "字段雷达",
    headline: "数据语义识别",
    opening: "扫描字段类型、维度、指标和潜在质量问题。",
    accent: "#0891b2",
    accentRgb: "8, 145, 178",
    orbitLabel: "Schema Scan",
    nodes: ["字段", "指标", "维度", "质量"]
  },
  analysis: {
    label: "方法沙盘",
    headline: "统计方案编排",
    opening: "选择指标、分组维度、分析方法和图表计划。",
    accent: "#4f46e5",
    accentRgb: "79, 70, 229",
    orbitLabel: "Plan Engine",
    nodes: ["方法", "指标", "分组", "图表"]
  },
  hypothesis: {
    label: "假设解析舱",
    headline: "情景变量抽取",
    opening: "识别干预变量、目标指标与预测对象。",
    accent: "#7c3aed",
    accentRgb: "124, 58, 237",
    orbitLabel: "What-if",
    nodes: ["假设", "变量", "目标", "对象"]
  },
  prediction_plan: {
    label: "预测控制室",
    headline: "模拟方案生成",
    opening: "确定预测方法、基准口径和影响对象。",
    accent: "#3b82f6",
    accentRgb: "59, 130, 246",
    orbitLabel: "Predictor",
    nodes: ["基准", "模型", "影响", "输出"]
  },
  safety: {
    label: "安全闸门",
    headline: "脚本风险审查",
    opening: "检查危险导入、系统命令和越权路径。",
    accent: "#0f766e",
    accentRgb: "15, 118, 110",
    orbitLabel: "Safety Gate",
    nodes: ["导入", "命令", "路径", "权限"]
  },
  validation: {
    label: "验证审计台",
    headline: "产物一致性验证",
    opening: "校验结果结构、图表产物和业务合理性。",
    accent: "#10b981",
    accentRgb: "16, 185, 129",
    orbitLabel: "Validator",
    nodes: ["结构", "图表", "指标", "结论"]
  },
  explanation: {
    label: "叙事生成室",
    headline: "结论与建议组织",
    opening: "把验证通过的发现转化为面向业务的表达。",
    accent: "#6366f1",
    accentRgb: "99, 102, 241",
    orbitLabel: "Narrative",
    nodes: ["发现", "证据", "建议", "报告"]
  },
  quality_review: {
    label: "质检审查室",
    headline: "因果与证据护栏",
    opening: "审查结论支撑，避免过度归因和口径漂移。",
    accent: "#0ea5e9",
    accentRgb: "14, 165, 233",
    orbitLabel: "Review",
    nodes: ["证据", "风险", "护栏", "修订"]
  },
  cross_artifact_consistency: {
    label: "一致性矩阵",
    headline: "多产物口径同步",
    opening: "同步图表、报告、Dashboard 和 PPT 的指标口径。",
    accent: "#1d4ed8",
    accentRgb: "29, 78, 216",
    orbitLabel: "Consistency",
    nodes: ["图表", "报告", "PPT", "口径"]
  },
  generic: {
    label: "单体执行舱",
    headline: "Agent 节点推演",
    opening: "加载上下文并执行当前节点动作。",
    accent: "#0ea5e9",
    accentRgb: "14, 165, 233",
    orbitLabel: "Agent Core",
    nodes: ["输入", "动作", "证据", "输出"]
  }
};

function sceneForAgent(key: string): SingleScene {
  return SCENES[key] ?? SCENES.generic;
}

function normalizeText(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function buildActionFrames(agent: AgentCardView, scene: SingleScene): string[] {
  const frames = [
    scene.opening,
    `输入聚焦：${agent.inputSource}`,
    `正在执行：${agent.action}`,
    ...agent.evidence.slice(0, 3).map((item) => `依据校验：${item}`),
    agent.output ? `输出摘要：${agent.output}` : "生成阶段性执行记录。"
  ];
  const uniqueFrames = Array.from(new Set(frames.map(normalizeText).filter(Boolean)));
  return uniqueFrames.slice(0, 7);
}

export function SingleStage({ agent }: { agent: AgentCardView }) {
  const scene = useMemo(() => sceneForAgent(agent.key), [agent.key]);
  const frames = useMemo(() => buildActionFrames(agent, scene), [agent, scene]);
  const [frameIndex, setFrameIndex] = useState(0);

  useEffect(() => {
    setFrameIndex(0);
    if (frames.length <= 1) return undefined;
    const timer = window.setInterval(() => {
      setFrameIndex((current) => (current + 1 >= frames.length ? current : current + 1));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [frames]);

  const progress = Math.round(((frameIndex + 1) / Math.max(frames.length, 1)) * 100);
  const style = {
    "--agent-stage-accent": scene.accent,
    "--agent-stage-accent-rgb": scene.accentRgb
  } as CSSProperties;

  return (
    <div className="single-stage" style={style}>
      <section className="single-stage-core" aria-label={scene.label}>
        <span className="single-stage-orbit single-stage-orbit-one" aria-hidden="true" />
        <span className="single-stage-orbit single-stage-orbit-two" aria-hidden="true" />
        <span className="single-stage-orbit single-stage-orbit-three" aria-hidden="true" />
        <div className="single-stage-avatar-wrap">
          <img src={fullBodyPortraitPath(agent.key)} alt={`${agent.agentName} 全身形象`} />
          <span aria-hidden="true" />
        </div>
        <div className="single-stage-orbit-label">{scene.orbitLabel}</div>
      </section>

      <section className="single-stage-console">
        <p>{scene.label}</p>
        <h3>{scene.headline}</h3>
        <div className="single-stage-frame" key={`${agent.key}-${frameIndex}`}>
          {frames[frameIndex]}
        </div>
        <div className="single-stage-progress" aria-label={`推演进度 ${progress}%`}>
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="single-stage-node-row" aria-label="节点链路">
          {scene.nodes.map((node, index) => (
            <span key={`${agent.key}-${node}`} className={index <= frameIndex % scene.nodes.length ? "active" : ""}>
              {node}
            </span>
          ))}
        </div>
      </section>
    </div>
  );
}

