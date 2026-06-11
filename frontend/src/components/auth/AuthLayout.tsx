import type { ReactNode } from "react";

export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="auth-shell">
      <aside className="auth-visual" aria-label="产品介绍">
        <div className="auth-visual-content">
          <div className="auth-brand">
            <span className="brand-mark">AI</span>
            <div>
              <strong>AI 数据工作台</strong>
            </div>
          </div>
          <div className="auth-hero-copy">
            <p className="eyebrow">Data Intelligence Console</p>
            <h2>把上传、分析、图表、报告放进一个清晰的后台入口。</h2>
            <p>面向新手用户的分步式数据分析工作台，同时保留 Agent、知识库、预测和交付物管理等完整功能。</p>
          </div>
          <div className="auth-feature-list">
            <div><span>01</span><strong>上传数据后自动生成画像与数据地图</strong></div>
            <div><span>02</span><strong>用自然语言启动 AI 工作流与智能洞察</strong></div>
            <div><span>03</span><strong>集中管理图表、Dashboard、报告和 PPT</strong></div>
          </div>
        </div>
      </aside>
      <section className="auth-form-pane">
        <div className="auth-mobile-brand">
          <span className="brand-mark">AI</span>
          <div>
            <strong>AI 数据工作台</strong>
          </div>
        </div>
        {children}
      </section>
    </main>
  );
}

export function AuthFormCard({
  eyebrow,
  title,
  description,
  children,
  wide = false
}: {
  eyebrow?: string;
  title: string;
  description: string;
  children?: ReactNode;
  wide?: boolean;
}) {
  return (
    <section className={`auth-form-card${wide ? " wide" : ""}`}>
      <div className="auth-card-header">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {children}
    </section>
  );
}
