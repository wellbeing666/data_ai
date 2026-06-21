import { useEffect, useMemo } from "react";
import { createPortal } from "react-dom";

import type { AgentCardView } from "../../utils/workbenchUtils";
import { DebateStage } from "./DebateStage";
import { RenderStage } from "./RenderStage";
import { SingleStage } from "./SingleStage";

type StageMode = "single" | "debate" | "render";

function stageModeFromAgent(agent: AgentCardView): StageMode {
  if (agent.key === "debate_matrix") {
    return "debate";
  }
  if (agent.key === "code" || agent.key === "sandbox") {
    return "render";
  }
  return "single";
}

function stageModeLabel(mode: StageMode): string {
  if (mode === "debate") {
    return "双 Agent 对抗推演";
  }
  if (mode === "render") {
    return "代码与产物渲染推演";
  }
  return "单 Agent 执行推演";
}

function statusText(status: AgentCardView["status"]): string {
  const map: Record<AgentCardView["status"], string> = {
    pending: "等待中",
    active: "运行中",
    done: "已完成",
    failed: "需关注"
  };
  return map[status] ?? "执行中";
}

export function AgentStageModal({
  agent,
  open,
  onClose
}: {
  agent: AgentCardView | null;
  open: boolean;
  onClose: () => void;
}) {
  const mode = useMemo(() => (agent ? stageModeFromAgent(agent) : "single"), [agent]);

  useEffect(() => {
    if (!open) return undefined;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open, onClose]);

  if (!open || !agent || typeof document === "undefined") {
    return null;
  }

  return createPortal(
    <div
      className="agent-stage-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <section
        className={`agent-stage-modal agent-stage-modal-${mode}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-stage-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <img className="agent-stage-bg-grid" src="/stage-assets/tech-stage-bg.svg" alt="" aria-hidden="true" />
        <img className="agent-stage-bg-space" src="/stage-assets/tech-stage-bg-extra.svg" alt="" aria-hidden="true" />
        <span className="agent-stage-light agent-stage-light-left" aria-hidden="true" />
        <span className="agent-stage-light agent-stage-light-right" aria-hidden="true" />
        <span className="agent-stage-floor" aria-hidden="true" />

        <button className="agent-stage-close" type="button" onClick={onClose} aria-label="关闭推演舞台">
          ×
        </button>

        <header className="agent-stage-header">
          <p>{stageModeLabel(mode)} · {statusText(agent.status)}</p>
          <h2 id="agent-stage-title">{agent.agentName}</h2>
          <span>{agent.title}</span>
        </header>

        <main className="agent-stage-body">
          {mode === "debate" ? <DebateStage agent={agent} /> : null}
          {mode === "render" ? <RenderStage agent={agent} /> : null}
          {mode === "single" ? <SingleStage agent={agent} /> : null}
        </main>

        <footer className="agent-stage-footer" aria-label="当前 Agent 输入和动作">
          <div>
            <span>输入</span>
            <strong>{agent.inputSource}</strong>
          </div>
          <div>
            <span>动作</span>
            <strong>{agent.action}</strong>
          </div>
        </footer>
      </section>
    </div>,
    document.body
  );
}

