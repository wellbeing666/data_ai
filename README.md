# AI 原生数据分析工作台

这是一个基于 FastAPI + React 的 AI 原生数据分析工作台。系统支持上传 CSV / Excel，输入自然语言分析目标，并通过多 Agent 完成任务规划、字段理解、分析计划、代码生成、安全检查、沙箱执行、结果验证、解释总结和报告生成。

当前后端技术栈：

- FastAPI + Python
- pandas / duckdb / matplotlib / seaborn
- python-pptx
- DeepSeek OpenAI-compatible API
- 本地沙箱执行与静态安全检查

当前前端技术栈：

- React + TypeScript + Vite

## DeepSeek API 配置

### 1. 申请 API Key

1. 访问 DeepSeek 开放平台：https://platform.deepseek.com/
2. 注册或登录账号。
3. 进入 API Keys / 账户设置页面。
4. 创建新的 API Key。
5. 复制 API Key，并只保存在本地 `.env` 或系统环境变量中。

不要把真实 API Key 提交到 Git，也不要写死在代码里。

### 2. 创建 `.env`

项目根目录已提供 [.env.example](./.env.example)。你可以复制一份：

```bash
copy .env.example .env
```

Windows PowerShell 也可以使用：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`：

```env
DEEPSEEK_API_KEY=你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

`.env` 已加入 `.gitignore`，不会被提交。

### 3. fallback 模式

如果没有配置 `DEEPSEEK_API_KEY`，系统不会崩溃，会自动进入规则版 fallback 模式。

此时：

- 后端 `/health` 会返回 `llm_mode = mock/fallback`。
- 前端会显示“当前使用规则分析模式”。
- Controller / Data Understanding / Analysis / Code / Explanation 等 Agent 会优先尝试 DeepSeek；DeepSeek 不可用时自动回退到规则版逻辑。

## 启动后端

建议使用项目对应的 Python 环境，然后安装依赖：

```bash
pip install -r requirements.txt
```

启动 FastAPI：

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

健康检查：

```text
GET http://127.0.0.1:8001/health
```

示例返回：

```json
{
  "status": "ok",
  "llm_mode": "mock/fallback",
  "deepseek_configured": false,
  "message": "DEEPSEEK_API_KEY is not configured; using mock/fallback mode."
}
```

## 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认访问：

```text
http://127.0.0.1:5173
```

## RAG 向量知识库配置

第一版 RAG 使用全局业务知识库，知识文档会保存到 `storage/knowledge/raw/{doc_id}/`，向量库保存到 `storage/knowledge/chroma/`。

`.env` 可配置：

```env
RAG_ENABLED=true
RAG_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
RAG_TOP_K=5
RAG_CHUNK_SIZE=800
RAG_CHUNK_OVERLAP=120
```

前端“知识库”页面支持上传 `.txt` / `.md` 文档、查看文档列表、测试检索结果。分析任务会在生成数据画像后检索知识库，并把命中的业务片段传给 Controller、Data Understanding、Analysis 和 Explanation Agent。

如果 `chromadb`、`sentence-transformers` 或本地 embedding 模型不可用，系统会记录 RAG fallback 信息并继续常规 DeepSeek / 规则版分析流程。

开发环境下，Vite 会把 `/api` 请求代理到：

```text
http://127.0.0.1:8001
```

## 完整演示流程

### 演示 1：成绩 Excel 分析

1. 启动后端和前端。
2. 打开前端页面：`http://127.0.0.1:5173`
3. 上传成绩 Excel，例如 `test_data/grade_class_stats_test.xlsx`。
4. 在分析目标中输入：

```text
把这批 Excel 成绩按班级统计并生成图表
```

5. 点击开始分析。
6. 在页面中查看 DeepSeek Agent 工作过程：
   - 主控 Agent 正在规划
   - 数据理解 Agent 正在识别字段
   - 分析 Agent 正在选择方法
   - 代码 Agent 正在生成脚本
   - 沙箱正在执行
   - 验证 Agent 正在检查结果
   - 解释 Agent 正在生成结论
7. 查看班级平均分、及格率、优秀率等图表。
8. 查看解释结论和建议。
9. 点击“下载报告”获取 Markdown 报告。

### 演示 2：销售 CSV 下降分析

1. 上传销售 CSV。
2. 在分析目标中输入：

```text
找出影响销量下降的原因
```

3. 系统会执行多 Agent 流程。
4. 数据理解 Agent 会识别日期、销量、销售额、品类、区域、渠道等字段。
5. 分析 Agent 会选择趋势分析、分组对比、指标拆解等方法。
6. 代码 Agent 会生成 Python 分析脚本。
7. 沙箱执行后，验证 Agent 会检查 JSON、图表和结论支撑。
8. 解释 Agent 会生成谨慎表述的结论。

注意：销量下降分析只会输出“可能原因”“显示出相关性”“可能有关”等表述，不会把相关性写成确定因果。

前端会展示：

- AI 分析过程
- 每个 Agent 的关键输出摘要
- 最终图表
- 解释结论
- 建议动作
- 报告下载
- PPT 大纲

## API 使用示例

### 上传数据

```bash
curl -X POST "http://127.0.0.1:8000/api/datasets/upload" \
  -F "file=@example.xlsx"
```

支持：

- `.csv`
- `.xlsx`
- `.xls`

上传后文件保存到：

```text
storage/uploads/{dataset_id}/
```

### 查看数据画像

```bash
curl "http://127.0.0.1:8000/api/datasets/{dataset_id}/profile"
```

画像保存到：

```text
storage/uploads/{dataset_id}/profile.json
```

### 创建多 Agent 自动分析任务

```bash
curl -X POST "http://127.0.0.1:8000/api/analysis/auto-repair-jobs" \
  -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"{dataset_id}\",\"user_goal\":\"把这批 Excel 成绩按班级统计并生成图表\",\"max_retries\":3,\"timeout_seconds\":60}"
```

完整流程：

```text
controller_agent
-> data_understanding_agent
-> analysis_agent
-> code_agent
-> code_safety
-> sandbox_executor
-> validation_agent
-> explanation_agent
```

如果执行失败，系统会把 `stderr`、`validation_result`、`repair_suggestions` 交给 Code Agent 重新生成脚本。最多重试 3 次。

### 查看执行日志

```bash
curl "http://127.0.0.1:8000/api/analysis/jobs/{job_id}/logs"
```

日志保存到：

```text
storage/jobs/{job_id}/execution_log.json
```

## Job 目录产物

每个任务会保存到：

```text
storage/jobs/{job_id}/
```

常见产物：

```text
controller_plan.json
dataset_profile.json
data_understanding.json
analysis_plan.json
generated_script_attempt_1.py
code_safety_result_attempt_1.json
execution_result_attempt_1.json
validation_result_attempt_1.json
analysis_result.json
report_data.json
explanation.json
report.md
charts/
task_status.json
execution_log.json
```

## 代码安全检查

DeepSeek 生成的 Python 脚本在执行前会进行静态安全检查。

禁止内容包括：

- `import socket`
- `import requests`
- `import subprocess`
- `import shutil`
- `os.system`
- `eval`
- `exec`
- `open('/'...)`
- `open('C:\\'...)`
- `pathlib.Path.home()`

脚本只允许访问：

- 当前上传的 `input_file`
- 当前任务的 `output_dir`

如果检查失败，任务会记录失败原因，并把安全问题交给 Code Agent 作为下一轮修复上下文。

## 生成报告

```bash
curl -X POST "http://127.0.0.1:8000/api/reports/generate" \
  -H "Content-Type: application/json" \
  -d "{\"analysis_result_path\":\"storage/jobs/{job_id}/analysis_result.json\"}"
```

报告保存为：

```text
storage/jobs/{job_id}/report.md
```

## 前端构建

```bash
cd frontend
npm run build
```

## Playwright 验证

前端项目已安装 Playwright。当前机器可通过系统 Chrome 运行：

```ts
chromium.launch({ channel: "chrome", headless: true })
```

如需安装 Playwright 自带浏览器：

```bash
npx playwright install chromium
```
