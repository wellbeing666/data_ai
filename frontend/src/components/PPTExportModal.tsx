import { useEffect, useState } from "react";

interface PPTExportModalProps {
  isOpen: boolean;
  onClose: () => void;
  statusText?: string;
  downloadUrl?: string | null;
  downloadName?: string;
  busy?: boolean;
}

const progressSteps = [
  "整理分析结论",
  "匹配图表与证据",
  "生成演示结构",
  "准备下载文件"
];

export function PPTExportModal({
  isOpen,
  onClose,
  statusText,
  downloadUrl,
  downloadName = "智能洞察报告.pptx",
  busy = false
}: PPTExportModalProps) {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (!isOpen) {
      setProgress(0);
      return;
    }
    if (downloadUrl) {
      setProgress(100);
      return;
    }
    const timer = window.setInterval(() => {
      setProgress((current) => Math.min(92, current + Math.max(2, Math.round(Math.random() * 8))));
    }, 260);
    return () => window.clearInterval(timer);
  }, [downloadUrl, isOpen]);

  if (!isOpen) return null;

  const currentStep = downloadUrl
    ? "报告已准备好"
    : progressSteps[Math.min(progressSteps.length - 1, Math.floor(progress / 25))];

  return (
    <div className="ppt-modal-overlay" role="presentation" onMouseDown={onClose}>
      <section className="ppt-modal-content" role="dialog" aria-modal="true" aria-label="生成 PPTX 报告" onMouseDown={(event) => event.stopPropagation()}>
        <button className="ppt-modal-close" type="button" onClick={onClose} aria-label="关闭弹窗">×</button>
        <div className="magic-circle" aria-hidden="true">
          <span />
          <span />
          <i />
        </div>
        <h2>生成洞察报告</h2>
        <p>{statusText || "正在把分析结论、图表和建议整理为可汇报的 PPTX 文件。"}</p>
        <div className="ppt-progress-track" aria-hidden="true">
          <div className="ppt-progress-bar" style={{ width: `${downloadUrl ? 100 : progress}%` }} />
        </div>
        <div className="ppt-step-text">{currentStep}</div>
        {downloadUrl ? (
          <a className="ppt-download-button" href={downloadUrl} download={downloadName} onClick={onClose}>
            下载 PPTX 报告
          </a>
        ) : (
          <button className="ppt-download-button" type="button" disabled>
            {busy ? "生成中" : "等待文件"}
          </button>
        )}
      </section>
    </div>
  );
}
