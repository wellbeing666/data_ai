import type { AuthUser } from "./types";

export type WorkbenchPageKey =
  | "overview"
  | "data"
  | "workflow"
  | "agents"
  | "charts"
  | "dashboard"
  | "knowledge"
  | "prediction"
  | "reports"
  | "logs";

export type AppPageKey = WorkbenchPageKey | "account" | "admin";

export const workbenchPageKeys: WorkbenchPageKey[] = [
  "overview",
  "data",
  "workflow",
  "agents",
  "charts",
  "dashboard",
  "knowledge",
  "prediction",
  "reports",
  "logs"
];

export const pageTitles: Record<AppPageKey, string> = {
  overview: "总览",
  data: "数据资产",
  workflow: "AI 工作流",
  agents: "Agent 控制台",
  charts: "图表",
  dashboard: "Dashboard",
  knowledge: "知识库",
  prediction: "预测",
  reports: "报告",
  logs: "日志",
  account: "账号设置",
  admin: "用户管理"
};

export const menuSections: Array<{
  title: string;
  items: Array<{ key: AppPageKey; label: string; icon: string; adminOnly?: boolean }>;
}> = [
  {
    title: "总览",
    items: [{ key: "overview", label: "工作台总览", icon: "O" }]
  },
  {
    title: "数据准备",
    items: [
      { key: "data", label: "数据资产", icon: "D" },
      { key: "knowledge", label: "知识库", icon: "K" }
    ]
  },
  {
    title: "AI 执行",
    items: [
      { key: "workflow", label: "AI 工作流", icon: "W" },
      { key: "agents", label: "Agent 控制台", icon: "A" },
      { key: "prediction", label: "预测分析", icon: "P" },
      { key: "logs", label: "执行日志", icon: "L" }
    ]
  },
  {
    title: "结果交付",
    items: [
      { key: "charts", label: "图表管理", icon: "C" },
      { key: "dashboard", label: "Dashboard", icon: "B" },
      { key: "reports", label: "报告与 PPT", icon: "R" }
    ]
  },
  {
    title: "系统",
    items: [
      { key: "account", label: "账号设置", icon: "S" },
      { key: "admin", label: "用户管理", icon: "U", adminOnly: true }
    ]
  }
];

export function isWorkbenchPage(value: AppPageKey): value is WorkbenchPageKey {
  return workbenchPageKeys.includes(value as WorkbenchPageKey);
}

export function roleLabel(value: AuthUser["role"] | string): string {
  return value === "admin" ? "管理员" : "普通用户";
}

export function statusLabel(value: AuthUser["status"] | string): string {
  const labels: Record<string, string> = {
    pending: "待审核",
    active: "正常",
    frozen: "已冻结",
    rejected: "已驳回"
  };
  return labels[value] ?? value;
}
