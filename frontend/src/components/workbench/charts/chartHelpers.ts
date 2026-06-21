import { toStorageUrl } from "../../../api";
import type { AnalysisResult, PredictionResult, WorkflowJobResponse } from "../../../types";
import type { AnyRecord } from "../../../utils/workbenchUtils";

export function toVersionedStorageUrl(path: string, token: number): string {
  const url = toStorageUrl(path);
  if (!token) {
    return url;
  }
  return `${url}${url.includes("?") ? "&" : "?"}v=${token}`;
}

export function buildChartRefineSuggestions(
  chartPath: string,
  isPredictionWorkflow: boolean,
  analysisResult?: AnalysisResult | null,
  predictionResult?: PredictionResult | null,
  job?: WorkflowJobResponse | null
): string[] {
  const chartType = inferChartType(chartPath);
  const field = friendlyFieldName(extractChartField(chartPath));
  const target = friendlyFieldName(inferTargetMetric(analysisResult, predictionResult));
  const goal = (job?.user_goal || "当前分析目标").slice(0, 24);

  if (isPredictionWorkflow) {
    return [
      `改为${target}的基准值与预测值并列柱状图，并按预测变化绝对值从高到低排序。`,
      `只展示${target}变化最大的前 5 个对象，并在柱尾标注变化量和变化率。`,
      "把预测提升和预测下降分开表达，并在标题中写清当前情景假设。",
      "增加模型限制说明到图表副标题，提示预测结果不是确定因果。"
    ];
  }

  if (chartType === "line") {
    return [
      `增加月度峰谷标注，突出${target}下降最快的区间。`,
      `按地区拆分为多条趋势线，展示${field || target}在不同区域的变化差异。`,
      "改成同比/环比变化率折线图，突出下降阶段和反弹阶段。",
      "在图中标出最低点和最高点，并显示每个点的数值标签。"
    ];
  }
  if (chartType === "bar" || chartType === "barh") {
    return [
      `只保留${field || target}最高和最低的前 5 组，并按数值排序。`,
      "转换为横向柱状图，显示数值标签，便于长分类名称阅读。",
      "增加对比基准线，例如整体平均值或上期值，突出高低差异。",
      `按“${goal}”重新命名标题，并在副标题写清筛选口径。`
    ];
  }
  if (chartType === "scatter") {
    return [
      "增加趋势线和相关系数说明，但避免写成确定因果。",
      "按核心维度上色，并只标注离群点或 Top 10 对象。",
      "把散点透明度调高并缩小点大小，减少重叠遮挡。",
      "增加异常点说明框，突出偏离整体趋势的数据点。"
    ];
  }
  if (chartType === "heatmap") {
    return [
      "将热力图色阶固定为 -1 到 1，并放大字段标签，便于比较强弱关系。",
      "只保留与目标指标相关性最高的前 8 个字段。",
      "在每个格子中显示两位小数相关系数。",
      "把标题改为字段相关性复核，并补充“相关不等于因果”的注释。"
    ];
  }
  return [
    "改为更适合对比的柱状图，并显示数值标签。",
    "增加排序、筛选和标题说明，使图表直接对应当前分析目标。",
    "只保留最关键的前 10 个对象，避免图表过密。",
    "补充数据口径说明和限制提示。"
  ];
}

function inferChartType(chartPath: string): "heatmap" | "scatter" | "line" | "bar" | "barh" | "chart" {
  const name = chartPath.toLowerCase();
  if (name.includes("heatmap") || name.includes("corr")) {
    return "heatmap";
  }
  if (name.includes("scatter")) {
    return "scatter";
  }
  if (name.includes("trend") || name.includes("line") || name.includes("monthly")) {
    return "line";
  }
  if (name.includes("barh") || name.includes("top")) {
    return "barh";
  }
  if (name.includes("bar") || name.includes("group") || name.includes("category") || name.includes("channel")) {
    return "bar";
  }
  return "chart";
}

function extractChartField(chartPath: string): string {
  const filename = chartPath.split(/[\\/]/).pop() || chartPath;
  const stem = filename.replace(/\.[^.]+$/, "");
  const tokens = stem.split(/[_\-]+/).filter(Boolean);
  const ignored = new Set(["chart", "plot", "trend", "bar", "line", "scatter", "heatmap", "top", "monthly", "by", "group", "comparison"]);
  const fieldTokens = tokens.filter((token) => !ignored.has(token.toLowerCase()));
  return fieldTokens.slice(0, 3).join(" ") || stem;
}

function inferTargetMetric(analysisResult?: AnalysisResult | null, predictionResult?: PredictionResult | null): string {
  const predictionTarget = String(predictionResult?.target_metric || "").trim();
  if (predictionTarget) {
    return predictionTarget;
  }
  const result = analysisResult as AnyRecord | null | undefined;
  const direct = String(result?.target_metric || result?.metric || "").trim();
  if (direct) {
    return direct;
  }
  const summary = result?.analysis_summary;
  if (summary && typeof summary === "object") {
    const summaryText = JSON.stringify(summary);
    for (const value of ["SalePrice", "销量", "销售额", "成绩", "不良率", "响应时长", "排队时间"]) {
      if (summaryText.includes(value)) {
        return value;
      }
    }
  }
  const text = JSON.stringify(analysisResult || {});
  if (text.includes("SalePrice")) {
    return "SalePrice";
  }
  if (text.includes("销量")) {
    return "销量";
  }
  if (text.includes("销售额")) {
    return "销售额";
  }
  if (text.includes("成绩")) {
    return "成绩";
  }
  return "目标指标";
}

function friendlyFieldName(value: string): string {
  const text = (value || "").trim();
  const normalized = text.toLowerCase().replace(/[^0-9a-z\u4e00-\u9fff]/g, "");
  const labels: Record<string, string> = {
    saleprice: "房价（SalePrice）",
    overallqual: "整体质量（OverallQual）",
    grlivarea: "地上居住面积（GrLivArea）",
    totalbsmtsf: "地下室总面积（TotalBsmtSF）",
    "1stflrsf": "一层面积（1stFlrSF）",
    garagecars: "车库容量（GarageCars）",
    garagearea: "车库面积（GarageArea）",
    neighborhood: "社区/区域（Neighborhood）",
    mszoning: "住宅分区（MSZoning）",
    yearbuilt: "建造年份（YearBuilt）",
    fullbath: "全卫数量（FullBath）",
    totrmsabvgrd: "地上房间数（TotRmsAbvGrd）"
  };
  return labels[normalized] || text || "目标指标";
}

