// frontend/src/pages/WorkbenchPage.tsx
import React, { useState, useEffect } from "react";
import type { AuthUser } from "../types";

type ViewMode = "home" | "tasks" | "agent" | "knowledge" | "chat" | "results";

const WorkbenchStyles = () => (
  <style>{`
    .workbench-layout {
      display: flex;
      height: calc(100vh - 72px);
      background-color: #F5FBFF; 
      color: #0f172a;
      overflow: hidden;
      font-family: 'Segoe UI', Roboto, -apple-system, sans-serif;
    }

    /* 左侧导航栏 - 游戏侧边栏风格 */
    .sidebar-nav {
      width: 240px;
      background: rgba(245, 251, 255, 0.7);
      backdrop-filter: blur(12px);
      border-right: 2px solid #bae6fd;
      padding: 24px 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      z-index: 10;
      box-shadow: 4px 0 24px rgba(14, 165, 233, 0.05);
    }

    .nav-item {
      padding: 14px 20px;
      border-radius: 14px;
      cursor: pointer;
      font-weight: 600;
      color: #0369a1;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      display: flex;
      align-items: center;
      gap: 12px;
      border: 2px solid transparent;
      background: transparent;
      position: relative;
      overflow: hidden;
    }

    .nav-item:hover {
      background: rgba(14, 165, 233, 0.08);
      transform: translateX(6px);
    }

    .nav-item.active {
      background: #e0f2fe;
      border-color: #7dd3fc;
      color: #0284c7;
      box-shadow: 0 4px 15px rgba(14, 165, 233, 0.15);
    }

    .nav-item.active::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      width: 4px;
      height: 100%;
      background: #0ea5e9;
      border-radius: 0 4px 4px 0;
    }

    /* 主舞台区域 */
    .main-quest-area {
      flex: 1;
      padding: 32px 40px;
      overflow-y: auto;
      position: relative;
      background: #F5FBFF;
    }

    .quest-card {
      background: rgba(255, 255, 255, 0.85);
      backdrop-filter: blur(16px);
      border: 2px solid #bae6fd;
      border-radius: 24px;
      padding: 32px;
      box-shadow: 0 10px 40px -10px rgba(14, 165, 233, 0.15);
      animation: slideUpFade 0.6s cubic-bezier(0.16, 1, 0.3, 1);
      margin-bottom: 24px;
    }

    /* 动态动效集 */
    @keyframes slideUpFade {
      from { opacity: 0; transform: translateY(30px); }
      to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes floatSpirit {
      0%, 100% { transform: translateY(0) scale(1); }
      50% { transform: translateY(-12px) scale(1.02); filter: drop-shadow(0 10px 15px rgba(14,165,233,0.3)); }
    }
    
    @keyframes radarScan {
      0% { top: -100%; }
      100% { top: 100%; }
    }

    .data-spirit-svg {
      animation: floatSpirit 4s ease-in-out infinite;
    }

    /* 拖拽上传舱 */
    .upload-zone {
      border: 3px dashed #7dd3fc;
      border-radius: 20px;
      padding: 60px 40px;
      text-align: center;
      cursor: pointer;
      transition: all 0.4s ease;
      background: #F5FBFF;
      position: relative;
      overflow: hidden;
    }

    .upload-zone:hover {
      border-color: #0ea5e9;
      background: #e0f2fe;
      transform: translateY(-4px);
      box-shadow: 0 12px 30px rgba(14, 165, 233, 0.15);
    }

    .upload-zone::after {
      content: '';
      position: absolute;
      top: -100%;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(to bottom, transparent, rgba(14, 165, 233, 0.15), transparent);
      animation: radarScan 3s infinite linear;
      pointer-events: none;
    }

    /* 示例与知识库卡片网络 */
    .card-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 20px;
      margin-top: 20px;
    }

    .interactive-card {
      background: #F5FBFF;
      border: 2px solid #e0f2fe;
      border-radius: 16px;
      padding: 20px;
      cursor: pointer;
      transition: all 0.3s;
      position: relative;
      overflow: hidden;
    }

    .interactive-card:hover {
      border-color: #38bdf8;
      box-shadow: 0 8px 24px rgba(14, 165, 233, 0.12);
      transform: translateY(-3px);
    }

    /* 任务时间轴 */
    .task-timeline {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    
    .task-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 20px;
      background: #ffffff;
      border: 1px solid #bae6fd;
      border-radius: 16px;
      transition: transform 0.2s;
    }
    
    .task-row:hover {
      transform: scale(1.01);
      box-shadow: 0 6px 20px rgba(14, 165, 233, 0.1);
    }

    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 13px;
      font-weight: bold;
    }
    
    .status-success { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .status-running { background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }
    .status-failed { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }

    /* Agent 控制台终端 */
    .agent-terminal {
      background: #0f172a;
      border: 2px solid #0369a1;
      border-radius: 16px;
      padding: 24px;
      color: #7dd3fc;
      font-family: 'Fira Code', monospace;
      height: 400px;
      overflow-y: auto;
      box-shadow: inset 0 0 20px rgba(3, 105, 161, 0.5);
    }

    .terminal-line {
      margin: 8px 0;
      display: flex;
      align-items: flex-start;
      gap: 12px;
      animation: typeLine 0.3s ease-out forwards;
      opacity: 0;
    }

    @keyframes typeLine {
      to { opacity: 1; }
    }

    .cursor-blink {
      display: inline-block;
      width: 8px;
      height: 16px;
      background: #38bdf8;
      animation: blink 1s step-end infinite;
      vertical-align: middle;
    }

    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0; }
    }

    /* 对话气泡与通知 */
    .chat-panel {
      display: flex;
      flex-direction: column;
      height: 100%;
      gap: 16px;
    }

    .chat-bubble {
      background: #ffffff;
      border: 2px solid #bae6fd;
      border-radius: 18px;
      padding: 16px 20px;
      max-width: 75%;
      box-shadow: 0 4px 15px rgba(14, 165, 233, 0.08);
      line-height: 1.6;
    }

    .chat-bubble.ai {
      background: #F5FBFF;
      border-color: #7dd3fc;
      align-self: flex-start;
      border-top-left-radius: 4px;
    }

    .chat-bubble.user {
      background: linear-gradient(135deg, #0ea5e9, #0284c7);
      color: white;
      align-self: flex-end;
      border-top-right-radius: 4px;
      border: none;
    }

    .friendly-error-toast {
      background: #fff1f2;
      color: #e11d48;
      border: 1px solid #fecdd3;
      padding: 14px 24px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 500;
      margin: 10px auto;
      width: fit-content;
    }

    /* 自定义滚动条 */
    ::-webkit-scrollbar {
      width: 8px;
    }
    ::-webkit-scrollbar-track {
      background: #F5FBFF;
    }
    ::-webkit-scrollbar-thumb {
      background: #bae6fd;
      border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: #7dd3fc;
    }
  `}</style>
);

// 动态角色组件 - Data Spirit
const DataSpirit = ({ message }: { message: string }) => (
  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '20px', marginBottom: '32px' }}>
    <svg className="data-spirit-svg" viewBox="0 0 100 100" width="70" height="70" style={{ flexShrink: 0 }}>
      <defs>
        <radialGradient id="spiritCore" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="40%" stopColor="#e0f2fe" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0.8" />
        </radialGradient>
      </defs>
      <circle cx="50" cy="50" r="40" fill="url(#spiritCore)" />
      <path d="M 30 45 Q 50 65 70 45" fill="none" stroke="#0369a1" strokeWidth="4" strokeLinecap="round" />
      <circle cx="35" cy="38" r="5" fill="#0369a1" />
      <circle cx="65" cy="38" r="5" fill="#0369a1" />
      <path d="M 40 20 Q 50 10 60 20" fill="none" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" />
      <circle cx="50" cy="50" r="48" fill="none" stroke="#bae6fd" strokeWidth="1" strokeDasharray="4 4">
        <animateTransform attributeName="transform" type="rotate" from="0 50 50" to="360 50 50" dur="10s" repeatCount="indefinite" />
      </circle>
    </svg>
    <div style={{ 
      background: '#ffffff', 
      padding: '16px 24px', 
      borderRadius: '20px', 
      borderTopLeftRadius: '4px', 
      border: '2px solid #bae6fd', 
      boxShadow: '0 8px 24px rgba(14,165,233,0.12)', 
      color: '#0369a1', 
      fontWeight: '600', 
      fontSize: '16px',
      position: 'relative', 
      top: '10px' 
    }}>
      {message}
    </div>
  </div>
);

export function WorkbenchPage({ currentUser }: { currentUser: AuthUser }) {
  const [activeTab, setActiveTab] = useState<ViewMode>("home");

  const renderContent = () => {
    switch (activeTab) {
      case "home": return <HomePanel />;
      case "tasks": return <TasksPanel />;
      case "knowledge": return <KnowledgePanel />;
      case "chat": return <AnalysisChatPanel />;
      case "agent": return <AgentConsolePanel />;
      case "results": return <ResultsPanel />;
      default: return <HomePanel />;
    }
  };

  return (
    <div className="workbench-layout">
      <WorkbenchStyles />
      <aside className="sidebar-nav">
        <p style={{ padding: '0 16px', fontSize: '12px', fontWeight: 'bold', color: '#7dd3fc', textTransform: 'uppercase', letterSpacing: '2px', marginBottom: '8px' }}>
          分析主干线
        </p>
        <button className={`nav-item ${activeTab === "home" ? "active" : ""}`} onClick={() => setActiveTab("home")}>
          <span style={{ fontSize: '20px' }}>🏠</span> 首页
        </button>
        <button className={`nav-item ${activeTab === "tasks" ? "active" : ""}`} onClick={() => setActiveTab("tasks")}>
          <span style={{ fontSize: '20px' }}>🎯</span> 探索任务日志
        </button>
        <button className={`nav-item ${activeTab === "agent" ? "active" : ""}`} onClick={() => setActiveTab("agent")}>
          <span style={{ fontSize: '20px' }}>🤖</span> Agent 监视器
        </button>
        <button className={`nav-item ${activeTab === "knowledge" ? "active" : ""}`} onClick={() => setActiveTab("knowledge")}>
          <span style={{ fontSize: '20px' }}>📚</span> 领域知识矩阵
        </button>
        <button className={`nav-item ${activeTab === "chat" ? "active" : ""}`} onClick={() => setActiveTab("chat")}>
          <span style={{ fontSize: '20px' }}>💬</span> 分析对话频道
        </button>
        <button className={`nav-item ${activeTab === "results" ? "active" : ""}`} onClick={() => setActiveTab("results")}>
          <span style={{ fontSize: '20px' }}>✨</span> 洞察结晶看板
        </button>
      </aside>

      <main className="main-quest-area">
        {renderContent()}
      </main>
    </div>
  );
}

// ---------------- 子面板实现 ----------------

function HomePanel() {
  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <section className="quest-card">
        <DataSpirit message="欢迎来到核心调度中心！我们将为您自动生成多维度的洞察报告。请先投放需要解析的数据晶体（文件或图片）吧。" />
        
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <h2 style={{ color: '#0369a1', margin: 0 }}>任务配置区</h2>
          <span style={{ background: '#dcfce7', color: '#166534', padding: '6px 16px', borderRadius: '20px', fontSize: '14px', fontWeight: 'bold', border: '1px solid #bbf7d0' }}>
            ● DeepSeek 智能分析已启用
          </span>
        </div>

        <div className="upload-zone">
          <div style={{ fontSize: '56px', marginBottom: '20px', filter: 'drop-shadow(0 4px 6px rgba(14,165,233,0.2))' }}>📤</div>
          <h3 style={{ color: '#0284c7', marginBottom: '12px', fontSize: '22px' }}>注入数据源 (CSV/Excel/图片)</h3>
          <p style={{ color: '#64748b', fontSize: '15px', maxWidth: '500px', margin: '0 auto', lineHeight: '1.6' }}>
            支持点击选择或拖拽。如投放图像，视觉解析 Agent 将优先介入提取其内部的结构化奥秘。
          </p>
        </div>
      </section>

      <section className="quest-card">
        <h3 style={{ color: '#0369a1', marginBottom: '8px' }}>预置时空锚点（快速示例）</h3>
        <p style={{ color: '#64748b', marginBottom: '24px' }}>直接连接以下示例节点，极速体验完整的智能洞察流程。</p>
        
        <div className="card-grid">
          {['销售时空陨落', '学术成绩星图', '满意度反馈回响', '生命体征律动'].map((title, idx) => (
            <div key={idx} className="interactive-card">
              <h4 style={{ color: '#0284c7', margin: '0 0 10px 0' }}>{title}</h4>
              <p style={{ color: '#64748b', fontSize: '13px', margin: 0 }}>预封装了特定的多维数据特征，可一键唤醒分析引擎。</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function TasksPanel() {
  const tasks = [
    { id: 'Q-9021', name: 'Q3 渠道转化率归因分析', time: '10分钟前', status: 'success', text: '探索成功' },
    { id: 'Q-9020', name: '用户留存异常波动诊断', time: '2小时前', status: 'failed', text: '链路中断' },
    { id: 'Q-9019', name: '大促期间商品销量预测', time: '昨天', status: 'success', text: '探索成功' }
  ];

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <section className="quest-card">
        <DataSpirit message="您的所有探索印记都在此封存。点击任务即可重新载入当时的时空状态与分析结晶。" />
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '2px solid #e0f2fe', paddingBottom: '16px' }}>
          <h2 style={{ color: '#0369a1', margin: 0 }}>探索任务日志</h2>
          <button style={{ background: '#0ea5e9', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '12px', fontWeight: 'bold', cursor: 'pointer' }}>
            + 发起新探索
          </button>
        </div>

        <div className="task-timeline">
          <div className="task-row" style={{ border: '2px dashed #7dd3fc', background: '#F5FBFF' }}>
            <div>
              <h4 style={{ margin: '0 0 4px 0', color: '#0284c7' }}>实时订单流分析</h4>
              <span style={{ fontSize: '12px', color: '#64748b' }}>编号: Q-9022 · 当前运行</span>
            </div>
            <div className="status-badge status-running">
              <span style={{ width: '8px', height: '8px', background: '#0ea5e9', borderRadius: '50%', animation: 'blink 1s infinite' }}></span>
              解析中
            </div>
          </div>

          {tasks.map(task => (
            <div key={task.id} className="task-row">
              <div>
                <h4 style={{ margin: '0 0 4px 0', color: '#0f172a' }}>{task.name}</h4>
                <span style={{ fontSize: '12px', color: '#64748b' }}>编号: {task.id} · {task.time}</span>
              </div>
              <div className={`status-badge status-${task.status}`}>
                {task.text}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function KnowledgePanel() {
  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <section className="quest-card">
        <DataSpirit message="欢迎来到领域知识矩阵。您注入的业务规则和文献资料，将作为 Agent 推理时的隐性法则。" />
        
        <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
          <input 
            placeholder="检索矩阵中的法则或文献..." 
            style={{ flex: 1, padding: '12px 20px', borderRadius: '12px', border: '2px solid #bae6fd', background: '#F5FBFF', outline: 'none' }}
          />
          <button style={{ background: '#0284c7', color: 'white', border: 'none', borderRadius: '12px', padding: '0 24px', fontWeight: 'bold', cursor: 'pointer' }}>
            上传法则文献
          </button>
        </div>

        <div className="card-grid">
          <div className="interactive-card">
            <div style={{ fontSize: '32px', marginBottom: '12px' }}>📘</div>
            <h4 style={{ color: '#0369a1', margin: '0 0 8px 0' }}>2026 财年绩效核算标准.pdf</h4>
            <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', justifyContent: 'space-between' }}>
              <span>已向量化</span>
              <span>1.2 MB</span>
            </div>
          </div>
          <div className="interactive-card">
            <div style={{ fontSize: '32px', marginBottom: '12px' }}>📗</div>
            <h4 style={{ color: '#0369a1', margin: '0 0 8px 0' }}>Q3 市场活动投放渠道字典.xlsx</h4>
            <div style={{ fontSize: '12px', color: '#64748b', display: 'flex', justifyContent: 'space-between' }}>
              <span>已解析规则</span>
              <span>45 KB</span>
            </div>
          </div>
          <div className="interactive-card" style={{ borderStyle: 'dashed', background: 'transparent', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ fontSize: '24px', color: '#0ea5e9', marginBottom: '8px' }}>+</div>
            <span style={{ color: '#0ea5e9', fontWeight: 'bold' }}>开辟新矩阵空间</span>
          </div>
        </div>
      </section>
    </div>
  );
}

function ResultsPanel() {
  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <section className="quest-card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <DataSpirit message="这里陈列着经由 Agent 深度提炼的高维数据结晶。您可以将其提取为汇报级 PPT。" />
          <button style={{ background: 'linear-gradient(135deg, #0ea5e9, #0284c7)', color: 'white', border: 'none', borderRadius: '12px', padding: '10px 20px', fontWeight: 'bold', cursor: 'pointer', boxShadow: '0 4px 15px rgba(14,165,233,0.3)' }}>
            ↓ 提取洞察结晶 (PPT)
          </button>
        </div>

        <div style={{ background: '#F5FBFF', border: '2px solid #bae6fd', borderRadius: '16px', padding: '24px', marginBottom: '24px' }}>
          <h3 style={{ color: '#0369a1', marginTop: 0 }}>核心结论概览</h3>
          <p style={{ color: '#334155', lineHeight: '1.6' }}>
            根据矩阵演算，本次数据的核心波动来源于<strong style={{ color: '#0284c7' }}> 线下分销渠道 </strong>在周末的异常流量衰减。
            预测在下个周期内，如果不进行干预，整体转化率将面临 4.2% 的下滑风险。
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div style={{ height: '200px', background: 'rgba(255,255,255,0.6)', border: '1px solid #e0f2fe', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
            [ 趋势分布结晶图渲染区 ]
          </div>
          <div style={{ height: '200px', background: 'rgba(255,255,255,0.6)', border: '1px solid #e0f2fe', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
            [ 因子对比结晶图渲染区 ]
          </div>
        </div>
      </section>
    </div>
  );
}

function AnalysisChatPanel() {
  const [messages, setMessages] = useState([
    { role: "ai", content: "数据特征提取完毕，当前包含 162 行结构化晶体。请传达您的探索意图，例如：“按区域维度计算分布规律”。" }
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;
    setMessages(prev => [...prev, { role: "user", content: input }]);
    setInput("");
    setIsTyping(true);
    setErrorMsg("");

    setTimeout(() => {
      setIsTyping(false);
      setErrorMsg("数据网络波动，暂时无法与分析中枢建立稳定连接，请检查后重试。");
    }, 1500);
  };

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto', height: '100%', display: 'flex', flexDirection: 'column' }}>
      <section className="quest-card" style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '24px' }}>
        <h3 style={{ color: '#0369a1', borderBottom: '2px solid #e0f2fe', paddingBottom: '16px', marginBottom: '24px' }}>
          💬 探索意图沟通频道
        </h3>
        <div className="chat-panel" style={{ flex: 1, overflowY: 'auto', paddingRight: '12px' }}>
          {messages.map((msg, i) => (
            <div key={i} className={`chat-bubble ${msg.role}`}>{msg.content}</div>
          ))}
          {isTyping && (
            <div className="chat-bubble ai" style={{ width: '80px', display: 'flex', justifyContent: 'space-around' }}>
              <span className="pulse-dot" style={{ width: '8px', height: '8px', background: '#0ea5e9', borderRadius: '50%', animation: 'blink 1s infinite' }}></span>
              <span className="pulse-dot" style={{ width: '8px', height: '8px', background: '#0ea5e9', borderRadius: '50%', animation: 'blink 1s infinite 0.2s' }}></span>
              <span className="pulse-dot" style={{ width: '8px', height: '8px', background: '#0ea5e9', borderRadius: '50%', animation: 'blink 1s infinite 0.4s' }}></span>
            </div>
          )}
          {errorMsg && <div className="friendly-error-toast">⚠️ {errorMsg}</div>}
        </div>
        <form onSubmit={handleSend} style={{ marginTop: '24px', display: 'flex', gap: '16px' }}>
          <input 
            value={input} onChange={(e) => setInput(e.target.value)}
            placeholder="输入您的探索指令..." 
            style={{ flex: 1, padding: '16px 20px', borderRadius: '16px', border: '2px solid #bae6fd', outline: 'none', background: '#F5FBFF', fontSize: '15px' }}
          />
          <button type="submit" style={{ background: 'linear-gradient(135deg, #0ea5e9, #0284c7)', color: 'white', border: 'none', borderRadius: '16px', padding: '0 32px', fontWeight: 'bold', cursor: 'pointer', boxShadow: '0 4px 15px rgba(14,165,233,0.3)' }}>
            发送指令
          </button>
        </form>
      </section>
    </div>
  );
}

function AgentConsolePanel() {
  const [logs] = useState([
    "INIT: 连接到分析主干网络...",
    "AUTH: 节点准入验证通过，准备唤醒多 Agent 协作组。",
    "DATA: 识别到目标数据晶体 cleaned_dataset.csv。",
    "VISUAL: 未感知到视觉信号，跳过图像矩阵提取。",
    "INTENT: 意图解析节点正在接管流程..."
  ]);

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      <section className="quest-card" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ color: '#0369a1', margin: 0, display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', background: '#10b981', borderRadius: '50%', boxShadow: '0 0 10px #10b981' }}></span>
            Agent 神经中枢监视器
          </h2>
          <span style={{ color: '#64748b', fontSize: '14px', fontWeight: 'bold' }}>中继日志呈现</span>
        </div>
        <div className="agent-terminal">
          <div style={{ color: '#38bdf8', marginBottom: '16px', borderBottom: '1px dashed #0284c7', paddingBottom: '10px' }}>
            DataQuest Agent Engine v2.0.4 (Secure Channel)
          </div>
          {logs.map((log, i) => (
            <div key={i} className="terminal-line" style={{ animationDelay: `${i * 0.2}s` }}>
              <span style={{ color: '#0ea5e9' }}>{`[SYS]`}</span><span>{log}</span>
            </div>
          ))}
          <div className="terminal-line" style={{ animationDelay: '1s' }}>
            <span style={{ color: '#10b981' }}>{`[AGENT]`}</span><span>等待下一步处理动作 <span className="cursor-blink"></span></span>
          </div>
        </div>
      </section>
    </div>
  );
}