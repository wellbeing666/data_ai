import { useEffect, useMemo, useState } from "react";

import type { DatasetDataMap, DatasetDataMapEdge, DatasetDataMapNode, DatasetProfile } from "../../types";
import { EmptyState } from "../WorkbenchComponents";

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
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0] ?? null;
  const positionedNodes = useMemo(() => layoutDataMapNodes(nodes), [nodes]);
  const nodePosition = new Map<string, DatasetDataMapNode & { x: number; y: number }>(
    positionedNodes.map((node) => [node.id, node] as const)
  );
  const questions = selectedNode ? questionsForDataMapNode(dataMap, selectedNode) : [];

  useEffect(() => {
    if (!nodes.length) {
      setSelectedNodeId("");
      return;
    }
    if (!nodes.some((node) => node.id === selectedNodeId)) {
      setSelectedNodeId(nodes[0].id);
    }
  }, [nodes, selectedNodeId]);

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
          <section className="data-map-canvas" aria-label="可点击数据知识图谱">
            <svg viewBox="0 0 720 460" role="img" aria-label="数据地图关系图">
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
              {positionedNodes.map((node) => (
                <g
                  key={node.id}
                  className={`data-map-node node-${node.type} ${selectedNode?.id === node.id ? "selected" : ""}`}
                  transform={`translate(${node.x}, ${node.y})`}
                  onClick={() => setSelectedNodeId(node.id)}
                  tabIndex={0}
                  role="button"
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      setSelectedNodeId(node.id);
                    }
                  }}
                >
                  <circle r={nodeRadius(node)} />
                  <text>{node.label}</text>
                </g>
              ))}
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

function layoutDataMapNodes(nodes: DatasetDataMapNode[]): Array<DatasetDataMapNode & { x: number; y: number }> {
  const centerX = 360;
  const centerY = 230;
  if (!nodes.length) {
    return [];
  }
  const entityNodes = nodes.filter((node) => node.type === "entity");
  const otherNodes = nodes.filter((node) => node.type !== "entity");
  const positioned: Array<DatasetDataMapNode & { x: number; y: number }> = [];
  const entitySpacing = entityNodes.length > 1 ? 140 : 0;
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
  return base * Number(node.size || 1);
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
