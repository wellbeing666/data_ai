import { useEffect, useMemo, useState } from "react";

import { toStorageUrl } from "../../api";
import type { WorkflowAgentConsoleResponse, WorkflowAgentUpdateRequest, WorkflowJobResponse } from "../../types";
import { agentInitial, formatDateTime, stageLabel } from "../../utils/workbenchUtils";
import { EmptyState } from "../WorkbenchComponents";

type AgentFilter = "all" | "online" | "output" | "empty" | "error";

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
  const [filter, setFilter] = useState<AgentFilter>("all");
  const [draft, setDraft] = useState<WorkflowAgentUpdateRequest>({});
  const [allOutputsOpen, setAllOutputsOpen] = useState(false);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? agents[0] ?? null;
  const selectedMessages = selectedAgent?.messages?.slice().reverse() ?? [];
  const isOnline = (status = "") => ["running", "success", "completed", "active"].includes(status);
  const isError = (status = "") => ["failed", "error"].includes(status);
  const outputCount = (agent: (typeof agents)[number]) => agent.message_count ?? agent.messages?.length ?? 0;
  const onlineCount = agents.filter((agent) => isOnline(agent.status)).length;
  const errorCount = agents.filter((agent) => isError(agent.status)).length;
  const totalOutputs = agents.reduce((total, agent) => total + outputCount(agent), 0);
  const filteredAgents = useMemo(() => agents.filter((agent) => {
    if (filter === "online") return isOnline(agent.status);
    if (filter === "output") return outputCount(agent) > 0;
    if (filter === "empty") return outputCount(agent) === 0;
    if (filter === "error") return isError(agent.status);
    return true;
  }), [agents, filter]);

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
    setAllOutputsOpen(false);
    if (!selectedAgent) {
      setDraft({});
      return;
    }
    setDraft({
      display_name: selectedAgent.display_name,
      role: selectedAgent.role || "",
      avatar: selectedAgent.avatar || "",
      description: selectedAgent.description || "",
      tags: selectedAgent.tags ?? [],
      notes: selectedAgent.notes || ""
    });
  }, [selectedAgent?.agent_id]);

  const submitAgentEdit = () => {
    if (selectedAgent && canManageAgents) onUpdateAgent?.(selectedAgent.agent_id, draft);
  };

  const filters: Array<[AgentFilter, string, number]> = [
    ["all", "全部", agents.length],
    ["online", "在线", onlineCount],
    ["output", "有输出", agents.filter((agent) => outputCount(agent) > 0).length],
    ["empty", "无输出", agents.filter((agent) => outputCount(agent) === 0).length],
    ["error", "异常", errorCount]
  ];

  return (
    <section className="page-section agents-page">
      <div className="section-heading dashboard-heading">
        <div>
          <h2>Agent 画像</h2>
          <span>{canManageAgents ? "查看、管理 Agent 展示信息及历史输出。" : "查看参与当前任务的 Agent 及历史输出。"}</span>
        </div>
        <button className="secondary-button agent-refresh-btn" type="button" disabled={!job?.job_id || loading} onClick={onRefresh}>
          {loading ? "同步中" : "刷新 Agent"}
        </button>
      </div>
      {message ? <p className="message success">{message}</p> : null}
      {!job?.job_id ? (
        <EmptyState title="暂无 Agent 实体" text="启动或打开一个分析任务后，这里会展示参与本轮流程的所有 Agent。" />
      ) : (
        <>
          <div className="agent-overview-grid">
            <article><strong>{agents.length}</strong><span>Agent 总数</span></article>
            <article><strong>{onlineCount}</strong><span>在线 / 正常</span></article>
            <article><strong>{errorCount}</strong><span>异常</span></article>
            <article><strong>{totalOutputs}</strong><span>总输出数</span></article>
          </div>
          <div className="agents-console-layout">
            <aside className="agent-directory">
              <div className="agent-directory-filters" aria-label="Agent 筛选">
                {filters.map(([key, label, count]) => (
                  <button key={key} type="button" className={filter === key ? "active" : ""} onClick={() => setFilter(key)}>
                    {label}<span>{count}</span>
                  </button>
                ))}
              </div>
              <div className="agent-persona-grid">
                {filteredAgents.map((agent) => (
                  <button
                    key={agent.agent_id}
                    type="button"
                    className={`agent-persona-card status-${agent.status || "idle"} ${selectedAgent?.agent_id === agent.agent_id ? "selected" : ""}`}
                    onClick={() => setSelectedAgentId(agent.agent_id)}
                  >
                    <span className="agent-persona-avatar">{agent.avatar || agentInitial(agent.display_name)}</span>
                    <strong title={agent.display_name}>{agent.display_name}</strong>
                    <small title={agent.role}>{agent.role}</small>
                    <em>{outputCount(agent)} 条输出</em>
                    <i aria-label={`状态 ${agent.status || "idle"}`} />
                  </button>
                ))}
                {!filteredAgents.length ? <p className="agent-muted">当前筛选下没有 Agent。</p> : null}
              </div>
            </aside>
            {selectedAgent ? (
              <section className="agent-persona-detail">
                <div className="agent-persona-hero">
                  <span>{selectedAgent.avatar || agentInitial(selectedAgent.display_name)}</span>
                  <div>
                    <h3>{selectedAgent.display_name}</h3>
                    <p>{selectedAgent.description || "暂无简介"}</p>
                    <div className="agent-detail-meta">
                      <span>状态 {selectedAgent.status || "idle"}</span>
                      <span>{outputCount(selectedAgent)} 条输出</span>
                      <span>最近活跃 {selectedMessages[0]?.timestamp ? formatDateTime(selectedMessages[0].timestamp) : "暂无"}</span>
                    </div>
                    <div className="tag-row">{(selectedAgent.tags ?? []).map((tag) => <small key={tag}>{tag}</small>)}</div>
                  </div>
                </div>
                <details className={`agent-edit-box ${canManageAgents ? "" : "read-only"}`}>
                  <summary>{canManageAgents ? "编辑这个 Agent 的展示信息" : "查看 Agent 展示信息"}</summary>
                  {canManageAgents ? (
                    <>
                      <label>名称<input value={draft.display_name ?? ""} onChange={(event) => setDraft((value) => ({ ...value, display_name: event.target.value }))} /></label>
                      <label>头像<input value={draft.avatar ?? ""} onChange={(event) => setDraft((value) => ({ ...value, avatar: event.target.value }))} /></label>
                      <label>角色<input value={draft.role ?? ""} onChange={(event) => setDraft((value) => ({ ...value, role: event.target.value }))} /></label>
                      <label>简介<textarea rows={3} value={draft.description ?? ""} onChange={(event) => setDraft((value) => ({ ...value, description: event.target.value }))} /></label>
                      <label>标签（用逗号分隔）<input value={(draft.tags ?? []).join("，")} onChange={(event) => setDraft((value) => ({ ...value, tags: event.target.value.split(/[，,]/).map((item) => item.trim()).filter(Boolean) }))} /></label>
                      <button className="primary-button" type="button" onClick={submitAgentEdit}>保存 Agent 信息</button>
                    </>
                  ) : (
                    <dl className="agent-readonly-grid">
                      <div><dt>名称</dt><dd>{selectedAgent.display_name}</dd></div>
                      <div><dt>角色</dt><dd>{selectedAgent.role || "未设置"}</dd></div>
                      <div><dt>简介</dt><dd>{selectedAgent.description || "暂无简介"}</dd></div>
                      <div><dt>标签</dt><dd>{(selectedAgent.tags ?? []).join("，") || "无"}</dd></div>
                    </dl>
                  )}
                </details>
                <div className="agent-message-timeline">
                  <div className="section-heading compact-heading"><h2>最近会话输出</h2><span>{selectedMessages.length} 条</span></div>
                  {selectedMessages.length ? selectedMessages.slice(0, 3).map((item) => (
                    <article key={item.message_id} className={`agent-session-card status-${item.status || "info"}`}>
                      <header><strong>{item.title || stageLabel(item.stage || "")}</strong><span>{item.timestamp ? formatDateTime(item.timestamp) : ""}</span></header>
                      <p>{item.content || "该步骤已产生输出。"}</p>
                      {item.artifact_path ? <a href={toStorageUrl(item.artifact_path)} target="_blank" rel="noreferrer">打开产物</a> : null}
                      {canManageAgents ? <button className="danger-link" type="button" onClick={() => onDeleteMessage?.(selectedAgent.agent_id, item.message_id)}>删除这条输出</button> : null}
                    </article>
                  )) : <p className="agent-muted">该 Agent 在当前任务中暂无可展示输出。</p>}
                  {selectedMessages.length > 3 ? <button className="secondary-button agent-view-all" type="button" onClick={() => setAllOutputsOpen(true)}>查看全部输出（{selectedMessages.length}）</button> : null}
                </div>
              </section>
            ) : null}
          </div>
          {allOutputsOpen && selectedAgent ? (
            <div className="agent-output-modal-backdrop" role="presentation" onMouseDown={() => setAllOutputsOpen(false)}>
              <section className="agent-output-modal" role="dialog" aria-modal="true" aria-label={`${selectedAgent.display_name} 全部输出`} onMouseDown={(event) => event.stopPropagation()}>
                <header><div><h2>{selectedAgent.display_name} 的全部输出</h2><p>{selectedMessages.length} 条记录，按时间倒序排列</p></div><button className="secondary-button" type="button" onClick={() => setAllOutputsOpen(false)}>关闭</button></header>
                <div className="agent-output-modal-list">
                  {selectedMessages.map((item) => (
                    <article key={item.message_id} className={`agent-session-card status-${item.status || "info"}`}>
                      <header><strong>{item.title || stageLabel(item.stage || "")}</strong><span>{item.timestamp ? formatDateTime(item.timestamp) : ""}</span></header>
                      <p>{item.content || "该步骤已产生输出。"}</p>
                      {item.artifact_path ? <a href={toStorageUrl(item.artifact_path)} target="_blank" rel="noreferrer">打开产物</a> : null}
                    </article>
                  ))}
                </div>
              </section>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
