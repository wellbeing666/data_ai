import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { CSSProperties } from "react";

import type { AgentCardView } from "../../utils/workbenchUtils";
import { DebateStage } from "./DebateStage";
import { RenderStage } from "./RenderStage";
import { SingleStage } from "./SingleStage";
import { fullBodyPortraitPath, stageAccentForAgent } from "./stageAssets";

type OverallStageVariant = "inline" | "modal";
type StageMode = "single" | "debate" | "render";

type OverallStageContentProps = {
  cards: AgentCardView[];
  currentIndex: number;
  liveIndex: number;
  paused: boolean;
  variant: OverallStageVariant;
  onTogglePaused: () => void;
  onPrevious: () => void;
  onNext: () => void;
  onReturnToLive: () => void;
  onOpenModal?: () => void;
  onClose?: () => void;
  onJumpTo: (index: number) => void;
  onSelectAgent?: (agentKey: string) => void;
};

function compactText(value: string, fallback: string, limit = 118): string {
  const text = (value || fallback).replace(/\s+/g, " ").trim();
  if (text.length <= limit) {
    return text;
  }
  return `${text.slice(0, limit - 1)}…`;
}

function statusText(status: AgentCardView["status"]): string {
  const map: Record<AgentCardView["status"], string> = {
    pending: "等待中",
    active: "运行中",
    done: "已完成",
    failed: "需关注",
  };
  return map[status] ?? "执行中";
}

function playbackText(paused: boolean): string {
  return paused ? "继续播放" : "暂停";
}

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

function progressPercent(currentIndex: number, total: number): number {
  if (!total) {
    return 0;
  }
  return Math.round(((currentIndex + 1) / total) * 100);
}

function OverallStagePlayer({
  card,
  index,
  total,
  variant,
}: {
  card: AgentCardView;
  index: number;
  total: number;
  variant: OverallStageVariant;
}) {
  const mode = stageModeFromAgent(card);

  return (
    <article
      className={`overall-stage-player overall-stage-player-${variant} overall-stage-player-${mode}`}
      aria-label={`${card.agentName} 推演舞台`}
    >
      <header className="overall-stage-player-header">
        <p>
          {stageModeLabel(mode)} · {statusText(card.status)}
        </p>
        <div>
          <span>
            第 {index + 1} / {total} 位
          </span>
          <h3>{card.agentName}</h3>
          <small>{card.title}</small>
        </div>
      </header>

      <main className="overall-stage-player-body">
        {mode === "debate" ? <DebateStage agent={card} /> : null}
        {mode === "render" ? <RenderStage agent={card} /> : null}
        {mode === "single" ? <SingleStage agent={card} /> : null}
      </main>

      <footer
        className="overall-stage-player-footer"
        aria-label="当前 Agent 输入和动作"
      >
        <div>
          <span>输入</span>
          <strong>
            {compactText(
              card.inputSource,
              "等待输入",
              variant === "modal" ? 86 : 64,
            )}
          </strong>
        </div>
        <div>
          <span>动作</span>
          <strong>
            {compactText(
              card.action,
              "准备执行",
              variant === "modal" ? 96 : 72,
            )}
          </strong>
        </div>
      </footer>
    </article>
  );
}

function OverallStageContent({
  cards,
  currentIndex,
  liveIndex,
  paused,
  variant,
  onTogglePaused,
  onPrevious,
  onNext,
  onReturnToLive,
  onOpenModal,
  onClose,
  onJumpTo,
  onSelectAgent,
}: OverallStageContentProps) {
  const currentCard = cards[currentIndex] ?? cards[0];
  const accent = stageAccentForAgent(currentCard?.key ?? "generic");
  const style = {
    "--overall-stage-accent": accent.accent,
    "--overall-stage-accent-rgb": accent.accentRgb,
  } as CSSProperties;

  if (!currentCard) {
    return null;
  }

  const percent = progressPercent(currentIndex, cards.length);
  const liveCard = liveIndex >= 0 ? cards[liveIndex] : null;

  return (
    <section
      className={`overall-stage overall-stage-${variant} status-${currentCard.status}`}
      style={style}
      aria-label="总体推演舞台"
    >
      <header className="overall-stage-header">
        <div>
          <span>总体推演舞台</span>
          <strong>{paused ? "已暂停" : "自动播放中"}</strong>
        </div>
        <div className="overall-stage-actions">
          <button
            type="button"
            onClick={onPrevious}
            disabled={cards.length <= 1}
            aria-disabled={cards.length <= 1}
          >
            上一位
          </button>
          <button
            type="button"
            onClick={onNext}
            disabled={cards.length <= 1}
            aria-disabled={cards.length <= 1}
          >
            下一位
          </button>
          <button
            type="button"
            onClick={onReturnToLive}
            disabled={!liveCard}
            aria-disabled={!liveCard}
          >
            回到当前运行
          </button>
          <button type="button" onClick={onTogglePaused}>
            {playbackText(paused)}
          </button>
          {variant === "inline" && onOpenModal ? (
            <button type="button" onClick={onOpenModal}>
              弹窗播放
            </button>
          ) : null}
          {variant === "modal" && onClose ? (
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭总体推演舞台"
            >
              关闭
            </button>
          ) : null}
        </div>
      </header>

      <OverallStagePlayer
        card={currentCard}
        index={currentIndex}
        total={cards.length}
        variant={variant}
      />

      <div
        className="overall-stage-progress"
        aria-label={`总体推演进度 ${percent}%`}
      >
        <span style={{ width: `${percent}%` }} />
      </div>

      {variant === "modal" ? (
        <div className="overall-stage-track" aria-label="Agent 执行顺序">
          {cards.map((card, index) => (
            <button
              key={`overall-stage-${card.key}`}
              type="button"
              className={`${card.status} ${index === currentIndex ? "current" : ""}`}
              title={`${index + 1}. ${card.agentName}`}
              onClick={() => {
                onJumpTo(index);
                onSelectAgent?.(card.key);
              }}
            >
              <img
                src={fullBodyPortraitPath(card.key)}
                alt=""
                aria-hidden="true"
              />
              <span>{index + 1}</span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

export function OverallStage({
  cards,
  activeKey,
  liveKey,
  onSelectAgent,
}: {
  cards: AgentCardView[];
  activeKey?: string;
  liveKey?: string;
  onSelectAgent?: (agentKey: string) => void;
}) {
  const playableCards = useMemo(() => cards.filter(Boolean), [cards]);
  const activeIndex = playableCards.findIndex((card) => card.key === activeKey);
  const liveIndex = playableCards.findIndex((card) => card.key === liveKey);
  const initialIndex = Math.max(activeIndex, liveIndex, 0);
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [paused, setPaused] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  useEffect(() => {
    if (!playableCards.length) {
      setCurrentIndex(0);
      return;
    }
    const normalizedIndex = Math.max(
      0,
      Math.min(currentIndex, playableCards.length - 1),
    );
    if (normalizedIndex !== currentIndex) {
      setCurrentIndex(normalizedIndex);
    }
  }, [currentIndex, playableCards.length]);

  useEffect(() => {
    if (activeIndex < 0) {
      return;
    }
    setCurrentIndex(activeIndex);
    if (activeKey && liveKey && activeKey !== liveKey) {
      setPaused(true);
    }
  }, [activeIndex, activeKey, liveKey]);

  useEffect(() => {
    if (!playableCards.length || paused) {
      return undefined;
    }
    const timer = window.setInterval(
      () => {
        setCurrentIndex((index) => (index + 1) % playableCards.length);
      },
      modalOpen ? 4200 : 3600,
    );
    return () => window.clearInterval(timer);
  }, [modalOpen, paused, playableCards.length]);

  useEffect(() => {
    if (!modalOpen) {
      return undefined;
    }
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setModalOpen(false);
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [modalOpen]);

  if (!playableCards.length) {
    return null;
  }

  const returnToLive = () => {
    if (liveIndex >= 0) {
      setCurrentIndex(liveIndex);
      setPaused(false);
      onSelectAgent?.("");
    }
  };

  const jumpToIndex = (index: number) => {
    const targetIndex = Math.max(0, Math.min(index, playableCards.length - 1));
    setCurrentIndex(targetIndex);
    setPaused(true);
    const targetCard = playableCards[targetIndex];
    if (targetCard) {
      onSelectAgent?.(targetCard.key);
    }
  };

  const sharedProps = {
    cards: playableCards,
    currentIndex,
    liveIndex,
    paused,
    onTogglePaused: () => setPaused((value) => !value),
    onPrevious: () => {
      if (playableCards.length <= 1) {
        return;
      }
      jumpToIndex(
        (currentIndex - 1 + playableCards.length) % playableCards.length,
      );
    },
    onNext: () => {
      if (playableCards.length <= 1) {
        return;
      }
      jumpToIndex((currentIndex + 1) % playableCards.length);
    },
    onReturnToLive: returnToLive,
    onJumpTo: jumpToIndex,
    onSelectAgent,
  };

  const modal =
    modalOpen && typeof document !== "undefined"
      ? createPortal(
          <div
            className="overall-stage-modal-backdrop"
            role="presentation"
            onMouseDown={(event) => {
              if (event.target === event.currentTarget) {
                setModalOpen(false);
              }
            }}
          >
            <div
              className="overall-stage-modal-shell"
              role="dialog"
              aria-modal="true"
              aria-label="总体推演舞台"
              onMouseDown={(event) => event.stopPropagation()}
            >
              <img
                className="overall-stage-modal-bg"
                src="/stage-assets/tech-stage-bg-extra.svg"
                alt=""
                aria-hidden="true"
              />
              <div className="overall-stage-modal-scale-frame">
                <OverallStageContent
                  {...sharedProps}
                  variant="modal"
                  onClose={() => setModalOpen(false)}
                />
              </div>
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <>
      <OverallStageContent
        {...sharedProps}
        variant="inline"
        onOpenModal={() => setModalOpen(true)}
      />
      {modal}
    </>
  );
}
