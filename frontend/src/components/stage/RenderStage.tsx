import { useEffect, useMemo, useState } from "react";

import type { AgentCardView } from "../../utils/workbenchUtils";
import { fullBodyPortraitPath } from "./stageAssets";

function sourceForAgent(agent: AgentCardView): string {
  const isSandbox = agent.key === "sandbox";
  const input = isSandbox ? "generated_script.py" : "analysis_plan.json";
  const output = isSandbox ? "analysis_result.json" : "generated_script_attempt.py";
  return [
    "import json",
    "from pathlib import Path",
    "import pandas as pd",
    "import matplotlib.pyplot as plt",
    "",
    `INPUT = Path(\"${input}\")`,
    `OUTPUT = Path(\"${output}\")`,
    "",
    "df = pd.read_csv(runtime.dataset_path)",
    "profile = runtime.load_profile()",
    `# ${agent.action}`,
    "metrics = runtime.select_metrics(profile)",
    "fig, ax = plt.subplots(figsize=(10, 6))",
    "df[metrics].mean().plot(kind=\"bar\", ax=ax)",
    "ax.set_title(\"AI 数据分析结果\")",
    "runtime.save_chart(fig, \"charts/agent_result.png\")",
    "runtime.write_json(OUTPUT, {\"success\": True})"
  ].join("\n");
}

export function RenderStage({ agent }: { agent: AgentCardView }) {
  const source = useMemo(() => sourceForAgent(agent), [agent]);
  const [typedLength, setTypedLength] = useState(0);

  useEffect(() => {
    setTypedLength(0);
    const timer = window.setInterval(() => {
      setTypedLength((current) => {
        if (current >= source.length) {
          window.clearInterval(timer);
          return current;
        }
        return Math.min(source.length, current + 3);
      });
    }, 28);
    return () => window.clearInterval(timer);
  }, [source]);

  const complete = typedLength >= source.length;
  const displayedSource = source.slice(0, typedLength);

  return (
    <div className={`render-stage ${complete ? "complete" : "typing"}`}>
      <section className="render-terminal" aria-label="代码生成推演">
        <header>
          <span />
          <span />
          <span />
          <strong>{agent.key === "sandbox" ? "sandbox_executor.py" : "agent_code_generator.py"}</strong>
        </header>
        <pre>{displayedSource}<i aria-hidden="true" /></pre>
        <footer>{complete ? "代码编译与产物渲染完成" : "正在生成可执行分析脚本"}</footer>
      </section>

      <section className="render-output" aria-label="图表渲染推演">
        <div className="render-agent-figure" aria-hidden="true">
          <img src={fullBodyPortraitPath(agent.key)} alt="" />
        </div>
        <div className="render-scan" aria-hidden="true" />
        <div className="render-skeleton" aria-hidden={complete}>
          <span style={{ height: "36%" }} />
          <span style={{ height: "68%" }} />
          <span style={{ height: "52%" }} />
          <span style={{ height: "82%" }} />
          <span style={{ height: "61%" }} />
        </div>
        <img className="render-chart-image" src="/stage-assets/render-chart-result.svg" alt="渲染完成的数据图表" />
        <div className="render-output-badge">{complete ? "图表与 JSON 产物已生成" : "正在装配图表骨架"}</div>
      </section>
    </div>
  );
}

