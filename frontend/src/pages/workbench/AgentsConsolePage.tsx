import type { AuthUser, WorkflowAgentConsoleResponse } from "../../types";
import { Empty } from "./shared";

export function AgentsConsolePage({ agents, currentUser }: { agents: WorkflowAgentConsoleResponse | null; currentUser?: AuthUser | null }) {
  return (
    <div className="content-grid">
      <section className="card">
        <div className="card-header horizontal">
          <div><h2>Agent 控制台</h2><p>查看各 Agent 画像、职责、消息和状态。管理员可在原 API 上扩展编辑能力。</p></div>
          <span className="badge badge-secondary">{currentUser?.role === "admin" ? "管理员" : "只读"}</span>
        </div>
        <div className="agent-grid">
          {(agents?.agents || []).map((agent) => (
            <article className="agent-card" key={agent.agent_id}>
              <span className="avatar">{agent.avatar || agent.display_name.slice(0, 1)}</span>
              <div>
                <h3>{agent.display_name}</h3>
                <p>{agent.role || agent.description || "AI Agent"}</p>
                <div className="tag-cloud compact">{(agent.tags || []).map((tag) => <span key={tag}>{tag}</span>)}</div>
              </div>
              <span className="badge badge-outline">{agent.status || "ready"}</span>
            </article>
          ))}
        </div>
        {!agents ? <Empty text="打开一个任务后可查看 Agent 控制台。" /> : null}
      </section>
    </div>
  );
}
