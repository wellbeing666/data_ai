export function DataPulseLoader({ text = "数据同步中..." }: { text?: string }) {
  return (
    <div className="data-pulse-container" role="status" aria-live="polite">
      <div className="pulse-rings" aria-hidden="true">
        <div className="ring" />
        <div className="ring" />
        <div className="ring" />
        <div className="pulse-core" />
      </div>
      <div className="pulse-text">{text}</div>
    </div>
  );
}
