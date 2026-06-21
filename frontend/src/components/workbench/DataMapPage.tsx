import { useEffect, useMemo, useRef, useState } from "react";

import type { DatasetDataMap, DatasetDataMapEdge, DatasetDataMapNode, DatasetProfile } from "../../types";
import { EmptyState } from "../WorkbenchComponents";

type PositionedDataMapNode = DatasetDataMapNode & { x: number; y: number };
type NodePositionState = Record<string, { x: number; y: number }>;

type DragState = {
  id: string;
  pointerId: number;
  offsetX: number;
  offsetY: number;
  moved: boolean;
};

export function DataMapPage({
  dataMap,
  profile,
  loading,
  message,
  onRefresh,
  onUseQuestion
}: {
  dataMap: DatasetDataMap | null;
  profile: DatasetProfile | null;
  loading?: boolean;
  message?: string;
  onRefresh?: () => void;
  onUseQuestion?: (question: string) => void;
}) {
  const nodes = useMemo(() => normalizeDataMapNodes(dataMap), [dataMap]);
  const edges = dataMap?.graph?.edges ?? [];
  const [selectedNodeId, setSelectedNodeId] = useState<string>("");
  const [manualPositions, setManualPositions] = useState<NodePositionState>({});
  const [draggingNodeId, setDraggingNodeId] = useState<string>("");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragStateRef = useRef<DragState | null>(null);
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0] ?? null;
  const basePositionedNodes = useMemo(() => layoutDataMapNodes(nodes), [nodes]);
  const positionedNodes = useMemo(
    () => basePositionedNodes.map((node) => ({ ...node, ...(manualPositions[node.id] ?? {}) })),
    [basePositionedNodes, manualPositions]
  );
  const nodePosition = new Map<string, PositionedDataMapNode>(positionedNodes.map((node) => [node.id, node] as const));
  const questions = selectedNode ? questionsForDataMapNode(dataMap, selectedNode) : [];

  useEffect(() => {
    if (!nodes.length) {
      setSelectedNodeId("");
      setManualPositions({});
      return;
    }
    if (!nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(nodes[0].id);
    }
  }, [nodes, selectedNodeId]);

  useEffect(() => {
    setManualPositions((current) => {
      const next: NodePositionState = {};
      basePositionedNodes.forEach((node) => {
        next[node.id] = current[node.id] ?? { x: node.x, y: node.y };
      });
      return next;
    });
  }, [basePositionedNodes]);

  const readSvgPoint = (event: React.PointerEvent<SVGGElement>) => {
    const svg = svgRef.current;
    const matrix = svg?.getScreenCTM();
    if (!svg || !matrix) {
      return null;
    }
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(matrix.inverse());
  };

  const beginNodeDrag = (event: React.PointerEvent<SVGGElement>, node: PositionedDataMapNode) => {
    const point = readSvgPoint(event);
    if (!point) {
      setSelectedNodeId(node.id);
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragStateRef.current = {
      id: node.id,
      pointerId: event.pointerId,
      offsetX: point.x - node.x,
      offsetY: point.y - node.y,
      moved: false
    };
    setDraggingNodeId(node.id);
    setSelectedNodeId(node.id);
  };

  const moveNodeDrag = (event: React.PointerEvent<SVGGElement>) => {
    const dragState = dragStateRef.current;
    if (!dragState || dragState.pointerId !== event.pointerId) {
      return;
    }
    const point = readSvgPoint(event);
    const node = nodePosition.get(dragState.id);
    if (!point || !node) {
      return;
    }
    event.preventDefault();
    const radius = nodeRadius(node) + 8;
    const nextX = clamp(point.x - dragState.offsetX, radius, 720 - radius);
    const nextY = clamp(point.y - dragState.offsetY, radius, 460 - radius);
    const previous = manualPositions[dragState.id] ?? { x: node.x, y: node.y };
    if (Math.abs(previous.x - nextX) > 0.5 || Math.abs(previous.y - nextY) > 0.5) {
      dragState.moved = true;
    }
    setManualPositions((current) => ({ ...current, [dragState.id]: { x: nextX, y: nextY } }));
  };

  const endNodeDrag = (event: React.PointerEvent<SVGGElement>) => {
    const dragState = dragStateRef.current;
    if (dragState?.pointerId === event.pointerId) {
      event.currentTarget.releasePointerCapture(event.pointerId);
      dragStateRef.current = null;
      setDraggingNodeId("");
    }
  };

  return (
    <section className="page-section data-map-page">
      <div className="section-heading dashboard-heading">
        <div>
          <h2>数据地图</h2>
          <span>数据地图 Agent 将字段、实体、指标和可提问方向组织成可点击知识图谱。</span>
        </div>
        <button className="secondary-button agent-refresh-btn" type="button" disabled={!profile || loading} onClick={onRefresh}>
          {loading ? "生成中" : "刷新数据地图"}
        </button>
      </div>
      {message ? <p className="message success">{message}</p> : null}
      {!dataMap || !nodes.length ? (
        <EmptyState
          title="暂无数据地图"
          text="上传表格并生成数据画像后，系统会自动抽取实体、指标、维度和推荐问题。"
        />
      ) : (
        <div className="data-map-layout">
          <section className="data-map-canvas" aria-label="可拖拽数据知识图谱">
            <div className="data-map-interaction-tip"><span />拖拽节点整理视图，点击节点查看可追问方向</div>
            <svg ref={svgRef} viewBox="0 0 720 460" role="img" aria-label="数据地图关系图">
              <defs>
                <radialGradient id="data-map-glow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="rgba(20,184,166,0.28)" />
                  <stop offset="100%" stopColor="rgba(20,184,166,0)" />
                </radialGradient>
              </defs>
              <rect x="0" y="0" width="720" height="460" rx="24" className="data-map-svg-bg" />
              <circle cx="360" cy="230" r="172" fill="url(#data-map-glow)" />
              {edges.map((edge, index) => {
                const source = nodePosition.get(edge.source);
                const target = nodePosition.get(edge.target);
                if (!source || !target) {
                  return null;
                }
                const label = shouldShowEdgeRelationLabel(edge, index, edges) ? (edge.relation || "关联") : "";
                return (
                  <g key={`${edge.source}-${edge.target}-${index}`} className="data-map-edge">
                    <line x1={source.x} y1={source.y} x2={target.x} y2={target.y} />
                    {label ? (
                      <text x={(source.x + target.x) / 2} y={(source.y + target.y) / 2}>
                        {label}
                      </text>
                    ) : null}
                  </g>
                );
              })}
              {positionedNodes.map((node) => {
                const labelLines = nodeLabelLines(node);
                const lineGap = labelLineGap(labelLines.length);
                return (
                  <g
                    key={node.id}
                    className={`data-map-node node-${node.type} ${selectedNode?.id === node.id ? "selected" : ""} ${draggingNodeId === node.id ? "dragging" : ""}`}
                    transform={`translate(${node.x}, ${node.y})`}
                    onPointerDown={(event) => beginNodeDrag(event, node)}
                    onPointerMove={moveNodeDrag}
                    onPointerUp={endNodeDrag}
                    onPointerCancel={endNodeDrag}
                    tabIndex={0}
                    role="button"
                    aria-label={`${dataMapNodeTypeLabel(node.type)}：${node.label}`}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        setSelectedNodeId(node.id);
                      }
                    }}
                  >
                    <title>{node.label}</title>
                    <circle r={nodeRadius(node)} />
                    <text className="data-map-node-label" style={{ fontSize: labelFontSize(labelLines.length) }}>
                      {labelLines.map((line, index) => (
                        <tspan key={`${node.id}-${line}-${index}`} x={0} y={(index - (labelLines.length - 1) / 2) * lineGap}>
                          {line}
                        </tspan>
                      ))}
                    </text>
                  </g>
                );
              })}
            </svg>
          </section>
          <aside className="data-map-detail">
            <div className="data-map-summary-cards">
              <article><strong>{dataMap.row_count ?? profile?.row_count ?? 0}</strong><span>行</span></article>
              <article><strong>{dataMap.column_count ?? profile?.column_count ?? 0}</strong><span>列</span></article>
              <article><strong>{dataMap.data_map?.metrics?.length ?? 0}</strong><span>指标</span></article>
              <article><strong>{dataMap.data_map?.dimensions?.length ?? 0}</strong><span>维度</span></article>
            </div>
            {selectedNode ? (
              <article className={`data-map-node-card node-${selectedNode.type}`}>
                <span>{dataMapNodeTypeLabel(selectedNode.type)}</span>
                <h3>{selectedNode.label}</h3>
                <p>{selectedNode.description || "该节点来自数据地图 Agent 对字段和业务概念的自动识别。"}</p>
                {selectedNode.field ? <small>字段：{selectedNode.field}</small> : null}
              </article>
            ) : null}
            {questions.length ? (
              <div className="data-map-question-list">
                <strong>可以直接追问</strong>
                {questions.map((question) => (
                  <button key={question} type="button" onClick={() => onUseQuestion?.(question)}>
                    {question}
                  </button>
                ))}
              </div>
            ) : null}
            {dataMap.insights?.length ? (
              <div className="data-map-insights">
                <strong>AI 观察</strong>
                {dataMap.insights.slice(0, 4).map((item, index) => (
                  <p key={`${String(item.title)}-${index}`}>{String(item.description || item.title || "")}</p>
                ))}
              </div>
            ) : null}
          </aside>
        </div>
      )}
    </section>
  );
}

function normalizeDataMapNodes(dataMap: DatasetDataMap | null): DatasetDataMapNode[] {
  const explicitNodes = dataMap?.graph?.nodes;
  if (explicitNodes?.length) {
    return explicitNodes;
  }
  const entities = dataMap?.data_map?.entities ?? [];
  const metrics = dataMap?.data_map?.metrics ?? [];
  const dimensions = dataMap?.data_map?.dimensions ?? [];
  const timeDimensions = dataMap?.data_map?.time_dimensions ?? [];
  const identifiers = dataMap?.data_map?.identifiers ?? [];
  return [
    ...entities.map((label, index) => ({ id: `entity-${index}`, label, type: "entity" })),
    ...metrics.map((label, index) => ({ id: `metric-${index}`, label, type: "metric" })),
    ...dimensions.map((label, index) => ({ id: `dimension-${index}`, label, type: "dimension" })),
    ...timeDimensions.map((label, index) => ({ id: `time-${index}`, label, type: "time" })),
    ...identifiers.map((label, index) => ({ id: `identifier-${index}`, label, type: "identifier" }))
  ];
}

function layoutDataMapNodes(nodes: DatasetDataMapNode[]): PositionedDataMapNode[] {
  const centerX = 360;
  const centerY = 230;
  if (!nodes.length) {
    return [];
  }
  const entityNodes = nodes.filter((node) => node.type === "entity");
  const otherNodes = nodes.filter((node) => node.type !== "entity");
  const positioned: PositionedDataMapNode[] = [];
  const entitySpacing = entityNodes.length > 1 ? Math.min(140, 600 / Math.max(1, entityNodes.length - 1)) : 0;
  entityNodes.forEach((node, index) => {
    const startX = centerX - ((entityNodes.length - 1) * entitySpacing) / 2;
    positioned.push({ ...node, x: startX + index * entitySpacing, y: centerY });
  });
  const radiusByType: Record<string, number> = { metric: 150, dimension: 170, time: 190, identifier: 135 };
  otherNodes.forEach((node, index) => {
    const angle = (-Math.PI / 2) + (index / Math.max(1, otherNodes.length)) * Math.PI * 2;
    const radius = radiusByType[node.type] ?? 170;
    positioned.push({ ...node, x: centerX + Math.cos(angle) * radius, y: centerY + Math.sin(angle) * radius });
  });
  return positioned;
}

function questionsForDataMapNode(dataMap: DatasetDataMap | null, node: DatasetDataMapNode): string[] {
  const questions = dataMap?.data_map?.possible_questions ?? {};
  return questions[node.label] ?? questions[node.type === "metric" ? "指标" : ""] ?? [];
}

function nodeRadius(node: DatasetDataMapNode): number {
  const base = node.type === "entity" ? 38 : node.type === "metric" ? 31 : 27;
  const labelLength = weightedLabelLength(node.label);
  const extra = Math.min(10, Math.max(0, labelLength - 7) * 0.7);
  return Math.min(48, (base + extra) * Number(node.size || 1));
}

function nodeLabelLines(node: DatasetDataMapNode): string[] {
  const label = String(node.label || "").trim();
  if (!label) {
    return [""];
  }
  const isCjk = /[\u3400-\u9fff]/.test(label);
  const maxChars = isCjk ? (node.type === "entity" ? 5 : 4) : (node.type === "entity" ? 10 : 8);
  const tokens = isCjk ? splitFixedLength(label, maxChars) : splitLatinLabel(label, maxChars);
  const lines: string[] = [];

  tokens.forEach((token) => {
    const current = lines[lines.length - 1];
    const separator = isCjk ? "" : " ";
    if (!current) {
      lines.push(token);
      return;
    }
    const merged = `${current}${separator}${token}`.trim();
    if (weightedLabelLength(merged) <= maxChars) {
      lines[lines.length - 1] = merged;
      return;
    }
    lines.push(token);
  });

  if (lines.length <= 3) {
    return lines;
  }
  const visible = lines.slice(0, 3);
  visible[2] = truncateLabel(visible[2], Math.max(4, maxChars - 1));
  return visible;
}

function splitLatinLabel(label: string, maxChars: number): string[] {
  const normalized = label
    .replace(/[_.:/\\-]+/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Za-z])([0-9])/g, "$1 $2")
    .replace(/([0-9])([A-Za-z])/g, "$1 $2");
  return normalized
    .split(/\s+/)
    .filter(Boolean)
    .flatMap((token) => splitFixedLength(token, Math.max(4, maxChars)));
}

function splitFixedLength(value: string, maxChars: number): string[] {
  const chars = Array.from(value);
  const result: string[] = [];
  for (let index = 0; index < chars.length; index += maxChars) {
    result.push(chars.slice(index, index + maxChars).join(""));
  }
  return result;
}

function truncateLabel(label: string, maxChars: number): string {
  const chars = Array.from(label);
  if (chars.length <= maxChars) {
    return label;
  }
  return `${chars.slice(0, Math.max(1, maxChars - 1)).join("")}…`;
}

function weightedLabelLength(label: unknown): number {
  return Array.from(String(label || "")).reduce((total, char) => total + (/[^\x00-\xff]/.test(char) ? 2 : 1), 0);
}

function labelFontSize(lineCount: number): number {
  if (lineCount >= 3) {
    return 9.5;
  }
  if (lineCount === 2) {
    return 10.5;
  }
  return 11.5;
}

function labelLineGap(lineCount: number): number {
  return lineCount >= 3 ? 10.5 : 12;
}

function dataMapNodeTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    entity: "业务实体",
    metric: "度量指标",
    dimension: "分析维度",
    time: "时间维度",
    identifier: "标识字段"
  };
  return labels[type] ?? type;
}

function shouldShowEdgeRelationLabel(edge: DatasetDataMapEdge, index: number, edges: DatasetDataMapEdge[]): boolean {
  const relation = String(edge.relation || "").trim();
  if (!relation || edges.length > 36) {
    return false;
  }
  const firstSameRelation = edges.findIndex((item) => String(item.relation || "").trim() === relation);
  if (firstSameRelation !== index) {
    return false;
  }
  return edges.slice(0, index).filter((item) => String(item.relation || "").trim()).length < 6;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}
