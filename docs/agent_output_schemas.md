# Agent 输出 JSON Schema 设计

本文档定义 AI 原生数据分析工作台中各类 Agent 的结构化输出格式。后续大模型必须严格按这些结构返回 JSON，不返回散文。

通用约定：

- 所有字段名使用 `snake_case`，便于 Python 后端直接处理。
- 时间建议使用 ISO 8601 字符串。
- 路径字段保存后端可访问的相对路径或绝对路径。
- Agent 输出必须是合法 JSON，不包含 Markdown 代码块。
- 当某个字段暂时无内容时，使用空数组、空对象或 `null`，不要省略关键字段。

## 1. DatasetUnderstandingResult

用途：数据理解 Agent 输出，用于描述数据集字段、质量问题和字段语义判断。

### 字段含义

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `dataset_id` | string | 数据集 ID |
| `file_type` | string | 文件类型，例如 `csv`、`xlsx` |
| `row_count` | integer | 行数 |
| `column_count` | integer | 列数 |
| `columns` | array | 字段列表，每个字段包含名称、类型、语义、质量信息 |
| `detected_entities` | object | 自动识别出的关键实体字段，例如班级、姓名、成绩、日期等 |
| `data_quality_issues` | array | 数据质量问题列表 |
| `suggested_cleaning_steps` | array | 建议清洗步骤 |
| `confidence` | number | 数据理解可信度，范围 0 到 1 |

### JSON 示例

```json
{
  "dataset_id": "322412d0836547809fcde7fd7d56a10a",
  "file_type": "xlsx",
  "row_count": 120,
  "column_count": 5,
  "columns": [
    {
      "name": "班级",
      "dtype": "object",
      "semantic_type": "class",
      "missing_count": 0,
      "missing_ratio": 0.0,
      "sample_values": ["一班", "二班", "三班"],
      "is_numeric": false
    },
    {
      "name": "姓名",
      "dtype": "object",
      "semantic_type": "person_name",
      "missing_count": 0,
      "missing_ratio": 0.0,
      "sample_values": ["张明", "李娜", "王强"],
      "is_numeric": false
    },
    {
      "name": "成绩",
      "dtype": "float64",
      "semantic_type": "score",
      "missing_count": 2,
      "missing_ratio": 0.0167,
      "sample_values": [89, 94, 72],
      "is_numeric": true
    }
  ],
  "detected_entities": {
    "class_column": "班级",
    "name_column": "姓名",
    "score_columns": ["成绩"]
  },
  "data_quality_issues": [
    {
      "type": "missing_values",
      "column": "成绩",
      "severity": "medium",
      "description": "成绩列存在少量缺失值"
    }
  ],
  "suggested_cleaning_steps": [
    {
      "step_id": "clean_001",
      "action": "drop_rows_with_missing_score",
      "description": "分析成绩统计时排除成绩为空的记录"
    }
  ],
  "confidence": 0.92
}
```

## 2. AnalysisPlan

用途：主控 Agent 或分析 Agent 输出，用于把用户目标拆成可执行分析计划。

必须重点保留以下结构：

```json
{
  "task_type": "grade_analysis",
  "steps": [],
  "required_columns": [],
  "analysis_methods": [],
  "charts": [],
  "expected_artifacts": []
}
```

### 字段含义

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `task_type` | string | 分析任务类型，例如 `grade_analysis`、`sales_analysis` |
| `user_goal` | string | 用户原始自然语言目标 |
| `steps` | array | 分析步骤，按执行顺序排列 |
| `required_columns` | array | 分析必需字段 |
| `optional_columns` | array | 可选字段 |
| `analysis_methods` | array | 统计或分析方法 |
| `charts` | array | 需要生成的图表 |
| `expected_artifacts` | array | 期望产物，例如 JSON、PNG、PPT |
| `assumptions` | array | 分析假设 |
| `risks` | array | 可能影响分析可信度的风险 |

### JSON 示例

```json
{
  "task_type": "grade_analysis",
  "user_goal": "把这批 Excel 成绩按班级统计并生成图表",
  "steps": [
    {
      "step_id": "step_001",
      "name": "字段识别",
      "description": "识别班级、姓名和成绩字段"
    },
    {
      "step_id": "step_002",
      "name": "数据清洗",
      "description": "排除成绩为空或无法转换为数值的记录"
    },
    {
      "step_id": "step_003",
      "name": "班级聚合统计",
      "description": "按班级计算人数、平均分、最高分、最低分、及格率和优秀率"
    },
    {
      "step_id": "step_004",
      "name": "生成图表",
      "description": "生成班级平均分和及格率柱状图"
    }
  ],
  "required_columns": [
    {
      "semantic_name": "class",
      "matched_column": "班级",
      "required": true
    },
    {
      "semantic_name": "score",
      "matched_column": "成绩",
      "required": true
    }
  ],
  "optional_columns": [
    {
      "semantic_name": "name",
      "matched_column": "姓名",
      "required": false
    }
  ],
  "analysis_methods": [
    {
      "method": "groupby_aggregation",
      "description": "按班级分组聚合成绩指标"
    },
    {
      "method": "rate_calculation",
      "description": "计算及格率和优秀率"
    }
  ],
  "charts": [
    {
      "chart_id": "chart_001",
      "chart_type": "bar",
      "title": "班级平均分",
      "x": "班级",
      "y": "平均分"
    },
    {
      "chart_id": "chart_002",
      "chart_type": "bar",
      "title": "班级及格率",
      "x": "班级",
      "y": "及格率"
    }
  ],
  "expected_artifacts": [
    {
      "artifact_type": "json",
      "name": "analysis_result.json"
    },
    {
      "artifact_type": "image",
      "name": "class_average_score.png"
    },
    {
      "artifact_type": "image",
      "name": "class_pass_rate.png"
    }
  ],
  "assumptions": [
    "成绩满分按 100 分处理",
    "及格线为 60 分",
    "优秀线为 90 分"
  ],
  "risks": [
    {
      "risk_type": "missing_score",
      "description": "部分成绩为空，可能影响统计结果"
    }
  ]
}
```

## 3. CodeGenerationRequest

用途：代码 Agent 的输入结构，由主控 Agent 或分析 Agent 生成，用于要求代码 Agent 生成可执行 Python 脚本。

### 字段含义

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `job_id` | string | 分析任务 ID |
| `dataset_id` | string | 数据集 ID |
| `task_type` | string | 任务类型 |
| `input_file_path` | string | 数据文件路径 |
| `output_dir` | string | 输出目录 |
| `analysis_plan` | object | 分析计划 |
| `runtime` | object | 运行环境限制 |
| `allowed_libraries` | array | 允许使用的 Python 库 |
| `required_outputs` | array | 必须生成的输出 |
| `code_constraints` | array | 代码约束 |

### JSON 示例

```json
{
  "job_id": "job_20260515_001",
  "dataset_id": "322412d0836547809fcde7fd7d56a10a",
  "task_type": "grade_analysis",
  "input_file_path": "storage/uploads/322412d0836547809fcde7fd7d56a10a/grade_class_stats_test.xlsx",
  "output_dir": "storage/jobs/job_20260515_001",
  "analysis_plan": {
    "task_type": "grade_analysis",
    "steps": [],
    "required_columns": [],
    "analysis_methods": [],
    "charts": [],
    "expected_artifacts": []
  },
  "runtime": {
    "python_version": "3.10",
    "timeout_seconds": 60,
    "memory_limit_mb": 1024,
    "network_allowed": false
  },
  "allowed_libraries": ["pandas", "duckdb", "matplotlib", "seaborn", "json", "pathlib"],
  "required_outputs": [
    "analysis_result.json",
    "charts/class_average_score.png",
    "charts/class_pass_rate.png"
  ],
  "code_constraints": [
    "不得访问 output_dir 之外的目录",
    "不得联网",
    "所有输出文件必须写入 output_dir"
  ]
}
```

## 4. CodeExecutionResult

用途：沙箱执行模块输出，用于描述代码运行是否成功、产物路径和日志。

### 字段含义

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `job_id` | string | 分析任务 ID |
| `success` | boolean | 脚本是否执行成功 |
| `exit_code` | integer | 进程退出码 |
| `started_at` | string | 开始时间 |
| `finished_at` | string | 结束时间 |
| `duration_ms` | integer | 执行耗时 |
| `stdout` | string | 标准输出 |
| `stderr` | string | 标准错误 |
| `artifacts` | array | 生成的文件产物 |
| `error` | object/null | 错误信息 |

### JSON 示例

```json
{
  "job_id": "job_20260515_001",
  "success": true,
  "exit_code": 0,
  "started_at": "2026-05-15T15:30:00+08:00",
  "finished_at": "2026-05-15T15:30:03+08:00",
  "duration_ms": 3120,
  "stdout": "analysis completed",
  "stderr": "",
  "artifacts": [
    {
      "artifact_type": "json",
      "path": "storage/jobs/job_20260515_001/analysis_result.json",
      "exists": true,
      "size_bytes": 2048
    },
    {
      "artifact_type": "image",
      "path": "storage/jobs/job_20260515_001/charts/class_average_score.png",
      "exists": true,
      "size_bytes": 53210
    }
  ],
  "error": null
}
```

## 5. ValidationResult

用途：验证 Agent 输出，用于判断代码执行结果、统计结果和图表是否可信。

### 字段含义

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `job_id` | string | 分析任务 ID |
| `is_valid` | boolean | 是否通过验证 |
| `score` | number | 验证评分，范围 0 到 1 |
| `checks` | array | 验证检查项 |
| `issues` | array | 发现的问题 |
| `suggested_fixes` | array | 建议修复方案 |
| `approved_artifacts` | array | 通过验证的产物路径 |

### JSON 示例

```json
{
  "job_id": "job_20260515_001",
  "is_valid": true,
  "score": 0.95,
  "checks": [
    {
      "check_name": "required_artifacts_exist",
      "passed": true,
      "message": "analysis_result.json 和两张图表均已生成"
    },
    {
      "check_name": "summary_fields_complete",
      "passed": true,
      "message": "班级统计字段完整"
    },
    {
      "check_name": "rate_range_check",
      "passed": true,
      "message": "及格率和优秀率均在 0 到 1 之间"
    }
  ],
  "issues": [],
  "suggested_fixes": [],
  "approved_artifacts": [
    "storage/jobs/job_20260515_001/analysis_result.json",
    "storage/jobs/job_20260515_001/charts/class_average_score.png",
    "storage/jobs/job_20260515_001/charts/class_pass_rate.png"
  ]
}
```

## 6. ExplanationResult

用途：解释 Agent 输出，用于生成自然语言结论、图表解读和报告内容。

### 字段含义

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `job_id` | string | 分析任务 ID |
| `title` | string | 报告标题 |
| `summary` | string | 一句话总结 |
| `key_findings` | array | 关键发现 |
| `chart_explanations` | array | 图表解读 |
| `recommendations` | array | 建议 |
| `limitations` | array | 局限性说明 |
| `report_sections` | array | 报告章节 |

### JSON 示例

```json
{
  "job_id": "job_20260515_001",
  "title": "成绩按班级统计分析报告",
  "summary": "本次分析显示，一班和三班整体成绩较高，四班存在部分低分学生需要关注。",
  "key_findings": [
    {
      "finding_id": "finding_001",
      "title": "三班平均分最高",
      "description": "三班平均分达到 86.5，高于其他班级。",
      "evidence": "analysis_result.json 中 class_name=三班 的 average_score 最高"
    },
    {
      "finding_id": "finding_002",
      "title": "四班及格率偏低",
      "description": "四班及格率低于其他班级，需要关注临界学生。",
      "evidence": "class_pass_rate.png 显示四班及格率最低"
    }
  ],
  "chart_explanations": [
    {
      "chart_path": "storage/jobs/job_20260515_001/charts/class_average_score.png",
      "title": "班级平均分柱状图",
      "insight": "该图用于比较不同班级的整体成绩水平。"
    },
    {
      "chart_path": "storage/jobs/job_20260515_001/charts/class_pass_rate.png",
      "title": "班级及格率柱状图",
      "insight": "该图用于识别及格率较低、需要重点辅导的班级。"
    }
  ],
  "recommendations": [
    "对及格率较低的班级开展错题回顾和分层辅导",
    "对接近 60 分的学生建立重点跟踪名单"
  ],
  "limitations": [
    "当前只基于单次成绩表分析，未纳入历史趋势",
    "未考虑不同科目难度差异"
  ],
  "report_sections": [
    {
      "heading": "一、数据概况",
      "content": "本次数据包含多个班级的学生成绩记录。"
    },
    {
      "heading": "二、班级对比",
      "content": "从平均分和及格率两个角度比较班级表现。"
    }
  ]
}
```

## 7. PPTSpec

用途：解释 Agent 或 PPT Agent 输出，用于指导 `python-pptx` 生成演示文稿。

### 字段含义

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `job_id` | string | 分析任务 ID |
| `title` | string | PPT 标题 |
| `theme` | object | 主题配置 |
| `slides` | array | 幻灯片列表 |
| `assets` | array | 需要插入的图片、图表等资源 |
| `output_path` | string | PPT 输出路径 |

### JSON 示例

```json
{
  "job_id": "job_20260515_001",
  "title": "成绩按班级统计分析",
  "theme": {
    "style": "clean_academic",
    "primary_color": "#0F766E",
    "font_family": "Microsoft YaHei",
    "page_size": "16:9"
  },
  "slides": [
    {
      "slide_id": "slide_001",
      "layout": "title",
      "title": "成绩按班级统计分析",
      "subtitle": "基于上传 Excel 成绩表自动生成",
      "speaker_notes": "介绍本次分析目标和数据来源。"
    },
    {
      "slide_id": "slide_002",
      "layout": "summary",
      "title": "核心结论",
      "bullets": [
        "三班平均分最高",
        "四班及格率偏低",
        "建议关注临界分数学生"
      ],
      "speaker_notes": "先讲结论，再展开图表。"
    },
    {
      "slide_id": "slide_003",
      "layout": "chart",
      "title": "班级平均分对比",
      "chart_path": "storage/jobs/job_20260515_001/charts/class_average_score.png",
      "caption": "不同班级平均成绩对比",
      "speaker_notes": "说明平均分最高和最低的班级。"
    },
    {
      "slide_id": "slide_004",
      "layout": "chart",
      "title": "班级及格率对比",
      "chart_path": "storage/jobs/job_20260515_001/charts/class_pass_rate.png",
      "caption": "不同班级及格率对比",
      "speaker_notes": "说明需要重点关注的班级。"
    },
    {
      "slide_id": "slide_005",
      "layout": "recommendations",
      "title": "教学建议",
      "bullets": [
        "对低于 60 分学生建立辅导清单",
        "对 60 到 70 分学生进行临界提升训练",
        "复盘优秀班级的学习策略"
      ],
      "speaker_notes": "给出可执行的教学改进建议。"
    }
  ],
  "assets": [
    {
      "asset_id": "asset_001",
      "asset_type": "image",
      "path": "storage/jobs/job_20260515_001/charts/class_average_score.png"
    },
    {
      "asset_id": "asset_002",
      "asset_type": "image",
      "path": "storage/jobs/job_20260515_001/charts/class_pass_rate.png"
    }
  ],
  "output_path": "storage/jobs/job_20260515_001/report.pptx"
}
```

## 后续大模型输出要求

后续接入大模型时，系统提示词应明确要求：

1. 只输出 JSON。
2. JSON 顶层结构必须匹配对应 schema。
3. 不允许输出 Markdown、解释性散文或代码块包裹。
4. 不确定的字段使用 `null`、空数组或低 `confidence` 表达。
5. 所有文件路径、字段名、图表 ID 必须与后端已有上下文一致。
6. `AnalysisPlan` 必须保留 `task_type`、`steps`、`required_columns`、`analysis_methods`、`charts`、`expected_artifacts`。
