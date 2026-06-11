import type { ReactNode } from "react";

export function OperationPage({
  eyebrow,
  title,
  description,
  actions,
  children
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="operation-page">
      <section className="operation-hero">
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h2>{title}</h2>
          <p>{description}</p>
        </div>
        {actions ? <div className="operation-hero-actions">{actions}</div> : null}
      </section>
      {children}
    </div>
  );
}
