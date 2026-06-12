import { useEffect, useState } from "react";

import { toStorageUrl } from "../../api";
import type { WorkflowAgentConsoleResponse, WorkflowAgentUpdateRequest, WorkflowJobResponse } from "../../types";
import { agentInitial, formatDateTime, stageLabel } from "../../utils/workbenchUtils";
import { EmptyState } from "../WorkbenchComponents";

export function AgentsPage({
  agentConsole,
  job,
  loading,
  message,
  canManageAgents = false,
  onRefresh,
  onUpdateAgent,
  onDeleteMessage
}: {
  agentConsole: WorkflowAgentConsoleResponse | null;
  job: WorkflowJobResponse | null;
  loading?: boolean;
  message?: string;
  canManageAgents?: boolean;
  onRefresh?: () => void;
  onUpdateAgent?: (agentId: string, updates: WorkflowAgentUpdateRequest) => void;
  onDeleteMessage?: (agentId: string, messageId: string) => void;
}) {
  const agents = agentConsole?.agents ?? [];
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? agents[0] ?? null;
  const [draft, setDraft] = useState<WorkflowAgentUpdateRequest>({});

  useEffect(() => {
    if (!agents.length) {
      setSelectedAgentId("");
      return;
    }
    if (!agents.some((agent) => agent.agent_id === selectedAgentId)) {
      setSelectedAgentId(agents[0].agent_id);
    }
  }, [agents, selectedAgentId]);

  useEffect(() => {
    if (!selectedAgent) {
      setDraft({});
      return;
    }
    setDraft({
      display_name: selectedAgent.display_name,
      role: selectedAgent.role || "",
      avatar: selectedAgent.avatar || "🤖",
      description: selectedAgent.description || "",
      tags: selectedAgent.tags ?? [],
      notes: selectedAgent.notes || ""
    });
  }, [selectedAgent?.agent_id]);

  const submitAgentEdit = () => {
    if (selectedAgent && canManageAgents) {
      onUpdateAgent?.(selectedAgent.agent_id, draft);
    }
  };

  return (
    <section className="page-section agents-page">
      <div className="section-heading dashboard-heading">
        <div>
          <h2>Agent 画像</h2>
          <span>{canManageAgents ? "每个Agent都是可查看、可编辑、有历史输出的实体。" : "每个Agent都是可查看、有历史输出的实体。"}</span>
        </div>
        <button className="secondary-button" type="button" disabled={!job?.job_id || loading} onClick={onRefresh}>
          {loading ? "同步中" : "刷新 Agent"}
        </button>
      </div>
      {message ? <p className="message success">{message}</p> : null}
      {!job?.job_id ? (
        <EmptyState title="暂无 Agent 实体" text="启动或打开一个分析任务后，这里会展示参与本轮流程的所有 Agent。" />
      ) : (
        <div className="agents-console-layout">
          <div className="agent-persona-grid">
            {agents.map((agent) => (
              <button
                key={agent.agent_id}
                type="button"
                className={`agent-persona-card status-${agent.status || "idle"} ${selectedAgent?.agent_id === agent.agent_id ? "selected" : ""}`}
                onClick={() => setSelectedAgentId(agent.agent_id)}
              >
                <span className="agent-persona-avatar">{agent.avatar || agentInitial(agent.display_name)}</span>
                <strong>{agent.display_name}</strong>
                <small>{agent.role}</small>
                <em>{agent.message_count ?? 0} 条输出</em>
              </button>
            ))}
          </div>
          {selectedAgent ? (
            <section className="agent-persona-detail">
              <div className="agent-persona-hero">
                <span>{selectedAgent.avatar || "🤖"}</span>
                <div>
                  <h3>{selectedAgent.display_name}</h3>
                  <p>{selectedAgent.description}</p>
                  <div className="tag-row">
                    {(selectedAgent.tags ?? []).map((tag) => <small key={tag}>{tag}</small>)}
                  </div>
                </div>
              </div>
              <details className={`agent-edit-box ${canManageAgents ? "" : "read-only"}`}>
                <summary>{canManageAgents ? "编辑这个 Agent 的展示信息" : "显示这个Agent的展示信息"}</summary>
                {canManageAgents ? (
                  <>
                    <label>
                      名称
                      <input value={draft.display_name ?? ""} onChange={(event) => setDraft((value) => ({ ...value, display_name: event.target.value }))} />
                    </label>
                    <label>
                      头像
                      <input value={draft.avatar ?? ""} onChange={(event) => setDraft((value) => ({ ...value, avatar: event.target.value }))} />
                    </label>
                    <label>
                      角色
                      <input value={draft.role ?? ""} onChange={(event) => setDraft((value) => ({ ...value, role: event.target.value }))} />
                    </label>
                    <label>
                      简介
                      <textarea rows={3} value={draft.description ?? ""} onChange={(event) => setDraft((value) => ({ ...value, description: event.target.value }))} />
                    </label>
                    <label>
                      标签（用逗号分隔）
                      <input
                        value={(draft.tags ?? []).join("，")}
                        onChange={(event) => setDraft((value) => ({ ...value, tags: event.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) }))}
                      />
                    </label>
                    <button className="primary-button" type="button" onClick={submitAgentEdit}>保存 Agent 信息</button>
                  </>
                ) : (
                  <dl className="agent-readonly-grid">
                    <div><dt>名称</dt><dd>{selectedAgent.display_name}</dd></div>
                    <div><dt>头像</dt><dd>{selectedAgent.avatar || agentInitial(selectedAgent.display_name)}</dd></div>
                    <div><dt>角色</dt><dd>{selectedAgent.role || "未设置"}</dd></div>
                    <div><dt>简介</dt><dd>{selectedAgent.description || "暂无简介"}</dd></div>
                    <div><dt>标签</dt><dd>{(selectedAgent.tags ?? []).join("，") || "无"}</dd></div>
                  </dl>
                )}
              </details>
              <div className="agent-message-timeline">
                <div className="section-heading compact-heading">
                  <h2>最近会话输出</h2>
                  <span>{selectedAgent.messages?.length ?? 0} 条</span>
                </div>
                {(selectedAgent.messages ?? []).length ? (
                  (selectedAgent.messages ?? []).slice().reverse().map((item) => (
                    <article key={item.message_id} className={`agent-session-card status-${item.status || "info"}`}>
                      <header>
                        <strong>{item.title || stageLabel(item.stage || "")}</strong>
                        <span>{item.timestamp ? formatDateTime(item.timestamp) : ""}</span>
                      </header>
                      <p>{item.content || "该步骤已产生输出。"}</p>
                      {item.artifact_path ? <a href={toStorageUrl(item.artifact_path)} target="_blank" rel="noreferrer">打开产物</a> : null}
                      {canManageAgents ? (
                        <button className="danger-link" type="button" onClick={() => onDeleteMessage?.(selectedAgent.agent_id, item.message_id)}>
                          删除这条输出
                        </button>
                      ) : null}
                    </article>
                  ))
                ) : (
                  <p className="agent-muted">该 Agent 在当前任务中暂无可展示输出。</p>
                )}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </section>
  );
}
