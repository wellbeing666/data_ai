import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

import { toStorageUrl } from "../../../api";
import type { ChartSelectionSpec, WorkflowFollowUpResponse, WorkflowSelectionQuestionResponse } from "../../../types";
import { chartTitle } from "../../../utils/workbenchUtils";
import { toVersionedStorageUrl } from "./chartHelpers";

interface BrushDraft {
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
  width: number;
  height: number;
}

export function ChartPreviewModal({
  chartPath,
  chartIndex = 0,
  chartRefreshToken,
  onClose,
  onDelete,
  onCompileSelection,
  onSubmitSelectionFollowUp
}: {
  chartPath: string;
  chartIndex?: number;
  chartRefreshToken: number;
  onClose: () => void;
  onDelete: () => void;
  onCompileSelection: (chartPath: string, selectionSpec: ChartSelectionSpec) => Promise<WorkflowSelectionQuestionResponse>;
  onSubmitSelectionFollowUp: (chartPath: string, selectionSpec: ChartSelectionSpec, question: string) => Promise<WorkflowFollowUpResponse>;
}) {
  const [scale, setScale] = useState(1);
  const [brushMode, setBrushMode] = useState(false);
  const [brushDraft, setBrushDraft] = useState<BrushDraft | null>(null);
  const [selectionSpec, setSelectionSpec] = useState<ChartSelectionSpec | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<WorkflowFollowUpResponse | null>(null);
  const [message, setMessage] = useState("");
  const [compileLoading, setCompileLoading] = useState(false);
  const [answerLoading, setAnswerLoading] = useState(false);
  const [imageFailed, setImageFailed] = useState(false);
  const imageButtonRef = useRef<HTMLButtonElement | null>(null);
  const title = chartTitle(chartPath, chartIndex);
  const imageUrl = toVersionedStorageUrl(chartPath, chartRefreshToken);

  useEffect(() => {
    setScale(1);
    setBrushMode(false);
    setBrushDraft(null);
    setSelectionSpec(null);
    setQuestion("");
    setAnswer(null);
    setMessage("");
    setImageFailed(false);
  }, [imageUrl]);

  useEffect(() => {
    if (brushMode) {
      setScale(1);
      setMessage("请在图表中拖拽框选一组柱子、点或时间窗，松开后先生成可编辑追问。");
    }
  }, [brushMode]);

  const changeScale = (delta: number) => {
    if (brushMode) {
      return;
    }
    setScale((current) => Math.min(2.4, Math.max(0.6, Math.round((current + delta) * 10) / 10)));
  };

  const readLocalPoint = (event: ReactPointerEvent<HTMLButtonElement>) => {
    const rect = imageButtonRef.current?.getBoundingClientRect();
    if (!rect) {
      return null;
    }
    return {
      x: Math.min(Math.max(event.clientX - rect.left, 0), rect.width),
      y: Math.min(Math.max(event.clientY - rect.top, 0), rect.height),
      width: rect.width,
      height: rect.height
    };
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!brushMode || imageFailed || compileLoading || answerLoading || event.button !== 0) {
      return;
    }
    const point = readLocalPoint(event);
    if (!point) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    setAnswer(null);
    setBrushDraft({ startX: point.x, startY: point.y, currentX: point.x, currentY: point.y, width: point.width, height: point.height });
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!brushMode || !brushDraft) {
      return;
    }
    const point = readLocalPoint(event);
    if (!point) {
      return;
    }
    event.preventDefault();
    setBrushDraft((current) => current ? { ...current, currentX: point.x, currentY: point.y, width: point.width, height: point.height } : current);
  };

  const handlePointerUp = async (event: ReactPointerEvent<HTMLButtonElement>) => {
    if (!brushMode || !brushDraft) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    try {
      event.currentTarget.releasePointerCapture(event.pointerId);
    } catch {
      // Some browsers release automatically after pointer up.
    }

    const x0 = Math.min(brushDraft.startX, brushDraft.currentX);
    const x1 = Math.max(brushDraft.startX, brushDraft.currentX);
    const y0 = Math.min(brushDraft.startY, brushDraft.currentY);
    const y1 = Math.max(brushDraft.startY, brushDraft.currentY);
    const width = Math.max(1, brushDraft.width);
    const height = Math.max(1, brushDraft.height);
    const selectedWidth = x1 - x0;
    const selectedHeight = y1 - y0;
    setBrushDraft(null);
    if (selectedWidth < 14 || selectedHeight < 14) {
      setMessage("框选区域过小，请重新拖拽选择更明确的数据区域。");
      return;
    }

    const nextSpec: ChartSelectionSpec = {
      chart_path: chartPath,
      chart_title: title,
      x0,
      y0,
      x1,
      y1,
      width: selectedWidth,
      height: selectedHeight,
      image_width: width,
      image_height: height,
      ratio_x0: x0 / width,
      ratio_y0: y0 / height,
      ratio_x1: x1 / width,
      ratio_y1: y1 / height,
      source: "chart_brush"
    };

    setSelectionSpec(nextSpec);
    setQuestion("");
    setAnswer(null);
    setCompileLoading(true);
    setMessage("正在把图形框选动作编译为候选追问。您稍后可以继续修改问题。");
    try {
      const compiled = await onCompileSelection(chartPath, nextSpec);
      setQuestion(compiled.question || "为什么图中被圈选的数据范围值得关注？");
      setMessage("已生成候选追问，请确认或修改后再生成答案。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "图形框选问题生成失败，请重试。");
    } finally {
      setCompileLoading(false);
    }
  };

  const submitSelectionQuestion = async () => {
    const trimmedQuestion = question.trim();
    if (!selectionSpec || !trimmedQuestion) {
      setMessage("请先框选图表区域，并确认追问内容。");
      return;
    }
    setAnswerLoading(true);
    setMessage("正在基于当前框选区域和追问生成答案。弹窗内会直接展示结果。");
    try {
      const result = await onSubmitSelectionFollowUp(chartPath, selectionSpec, trimmedQuestion);
      setAnswer(result);
      setMessage("刷选追问答案已生成，也已同步到结论报告页的追问历史。这里可继续查看。 ");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "刷选追问答案生成失败，请调整问题后重试。");
    } finally {
      setAnswerLoading(false);
    }
  };

  const brushRect = brushDraft ? {
    left: Math.min(brushDraft.startX, brushDraft.currentX),
    top: Math.min(brushDraft.startY, brushDraft.currentY),
    width: Math.abs(brushDraft.currentX - brushDraft.startX),
    height: Math.abs(brushDraft.currentY - brushDraft.startY)
  } : null;

  return (
    <div className="chart-modal-backdrop" role="dialog" aria-modal="true" aria-label="图表预览与刷选追问">
      <div className="chart-modal chart-modal-with-followup">
        <div className="chart-modal-head">
          <strong>{title}</strong>
          <div className="chart-modal-actions">
            <button type="button" disabled={brushMode} onClick={() => changeScale(0.2)}>放大</button>
            <button type="button" disabled={brushMode} onClick={() => changeScale(-0.2)}>缩小</button>
            <button
              className={`chart-brush-button ${brushMode ? "active" : ""}`}
              type="button"
              disabled={compileLoading || answerLoading}
              onClick={() => setBrushMode((current) => !current)}
            >
              {brushMode ? "退出刷选" : "刷选提问"}
            </button>
            <a href={toStorageUrl(chartPath)} download>下载 PNG</a>
            <button className="danger-button" type="button" onClick={onDelete}>删除</button>
            <button type="button" onClick={onClose}>关闭</button>
          </div>
        </div>
        <div className="chart-modal-body">
          <div className="chart-modal-stage" style={{ transform: `scale(${scale})` }}>
            <button
              ref={imageButtonRef}
              className={`chart-image-button chart-modal-image-button ${brushMode ? "brush-active" : ""}`}
              type="button"
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={() => setBrushDraft(null)}
              aria-label={brushMode ? `拖拽圈选${title}中的区域生成候选追问` : `${title}图表预览`}
            >
              {imageFailed ? (
                <span className="chart-image-fallback">图表暂时无法预览，可下载 PNG 或刷新任务状态。</span>
              ) : (
                <img
                  alt="放大图表"
                  src={imageUrl}
                  draggable={false}
                  onError={() => setImageFailed(true)}
                />
              )}
              {brushMode ? <span className="chart-brush-hint">拖拽圈选区域，松开后先生成候选追问</span> : null}
              {brushRect ? (
                <span
                  className="chart-brush-rect"
                  style={{ left: brushRect.left, top: brushRect.top, width: brushRect.width, height: brushRect.height }}
                />
              ) : null}
            </button>
          </div>
          <section className="chart-selection-followup-panel" aria-label="图形刷选追问确认区">
            <div className="chart-selection-followup-head">
              <div>
                <strong>图形刷选即问题 Agent</strong>
                <p>框选图表区域后，系统先把手势编译为可编辑追问；确认后才生成答案。</p>
              </div>
              {selectionSpec ? <span>已选中区域</span> : <span>等待框选</span>}
            </div>
            {message ? <p className="chart-selection-message">{message}</p> : null}
            <textarea
              rows={3}
              value={question}
              disabled={!selectionSpec || compileLoading || answerLoading}
              placeholder="先点击上方“刷选提问”，在图表中框选数据区域；系统会把框选动作转换为可编辑追问。"
              onChange={(event) => setQuestion(event.target.value)}
            />
            <div className="chart-selection-actions">
              <button
                className="secondary-button"
                type="button"
                disabled={!selectionSpec || !question.trim() || compileLoading || answerLoading}
                onClick={submitSelectionQuestion}
              >
                {answerLoading ? "答案生成中" : "确认问题并生成答案"}
              </button>
            </div>
            {answer ? (
              <article className="chart-selection-answer">
                <strong>{answer.question}</strong>
                <p>{answer.answer}</p>
              </article>
            ) : null}
          </section>
        </div>
      </div>
    </div>
  );
}
