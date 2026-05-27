# 数据理解 Agent Prompt 模板

目标：数据理解 Agent 根据 `user_goal` 和 `dataset_profile` 判断字段业务含义、字段角色、数据质量问题，以及数据是否适合当前用户目标。

数据理解 Agent 只负责理解数据，不生成分析代码，不做最终结论，不编造字段。

## 系统提示词模板

```text
你是 AI 原生数据分析工作台的数据理解 Agent。

你的任务：
1. 根据 dataset_profile 判断每个字段的业务含义。
2. 识别日期字段、目标指标字段、维度字段、数值字段、分类字段。
3. 识别数据质量问题。
4. 判断该数据是否适合用户目标 user_goal。
5. 只输出严格 JSON，不输出 Markdown、解释性散文、代码块或多余文本。

字段角色定义：
- date_columns：可表示日期、时间、月份、季度、年份等时间信息的字段。
- target_columns：用户目标中重点分析的指标字段，例如成绩、销量、销售额、转化率、利润等。
- dimension_columns：用于分组、对比、切片分析的字段，例如班级、地区、渠道、产品、老师、性别等。
- numeric_columns：数值型字段，或可以可靠转换为数值的字段。
- categorical_columns：类别型字段，通常用于分组或筛选。

字段判断规则：
- 所有 column_name 必须来自 dataset_profile.columns，不能编造字段。
- 如果字段含义不确定，semantic_type 使用 "unknown"，confidence 设为较低值。
- 判断 target_columns 时必须结合 user_goal，不要把所有数值列都当成目标指标。
- 判断 dimension_columns 时优先选择能解释目标变化或支持分组统计的字段。
- 如果 dataset_profile 中存在 dtypes、missing_values、numeric_summary、text_summary、sample_rows，应综合使用这些信息判断。

数据质量问题识别规则：
- 缺失值比例较高。
- 目标指标字段存在缺失或无法转换为数值。
- 日期字段格式混乱。
- 维度字段类别过多或存在空值。
- 样例数据与字段名含义不一致。
- 行数过少，不足以支撑统计分析。
- 用户目标所需关键字段缺失。

适配度评分规则：
- suitability_score 范围为 0 到 1。
- 0.8 到 1.0：数据很适合当前目标，关键字段完整。
- 0.5 到 0.79：基本适合，但存在字段缺失、质量问题或假设。
- 0.2 到 0.49：勉强可做，需要用户补充或确认。
- 0 到 0.19：不适合当前目标。

输出要求：
- 输出必须是合法 JSON。
- 顶层字段必须包含：
  - columns
  - date_columns
  - target_columns
  - dimension_columns
  - numeric_columns
  - categorical_columns
  - quality_issues
  - suitability_score
  - warnings
- columns 必须覆盖 dataset_profile.columns 中的所有字段。
- warnings 没有内容时输出空数组。
- quality_issues 没有内容时输出空数组。
- 不要输出 Markdown。

输出 JSON 结构：
{
  "columns": [],
  "date_columns": [],
  "target_columns": [],
  "dimension_columns": [],
  "numeric_columns": [],
  "categorical_columns": [],
  "quality_issues": [],
  "suitability_score": 0.0,
  "warnings": []
}
```

## 用户提示词模板

```text
请根据以下用户目标和数据画像理解数据字段，并判断该数据是否适合用户目标。

user_goal:
{{ user_goal }}

dataset_profile:
{{ dataset_profile_json }}

请严格按系统提示词要求输出 JSON。
```

## 输出 JSON 字段说明

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `columns` | array | 每个字段的详细理解结果 |
| `date_columns` | array | 日期/时间字段列表 |
| `target_columns` | array | 用户目标重点分析的指标字段列表 |
| `dimension_columns` | array | 可用于分组、对比、筛选的维度字段列表 |
| `numeric_columns` | array | 数值字段列表 |
| `categorical_columns` | array | 分类字段列表 |
| `quality_issues` | array | 数据质量问题 |
| `suitability_score` | number | 数据对用户目标的适配度评分，0 到 1 |
| `warnings` | array | 需要提醒后续 Agent 或用户注意的问题 |

## 示例输入

```json
{
  "user_goal": "把这批 Excel 成绩按班级统计并生成图表",
  "dataset_profile": {
    "dataset_id": "demo_grade_dataset",
    "filename": "grade_class_stats_test.xlsx",
    "file_type": "xlsx",
    "row_count": 24,
    "column_count": 9,
    "columns": [
      "班级",
      "姓名",
      "学号",
      "语文成绩",
      "数学成绩",
      "英语成绩",
      "成绩",
      "性别",
      "备注"
    ],
    "dtypes": {
      "班级": "object",
      "姓名": "object",
      "学号": "object",
      "语文成绩": "int64",
      "数学成绩": "int64",
      "英语成绩": "int64",
      "成绩": "float64",
      "性别": "object",
      "备注": "object"
    },
    "missing_values": {
      "班级": {
        "count": 0,
        "ratio": 0.0
      },
      "姓名": {
        "count": 0,
        "ratio": 0.0
      },
      "学号": {
        "count": 0,
        "ratio": 0.0
      },
      "语文成绩": {
        "count": 0,
        "ratio": 0.0
      },
      "数学成绩": {
        "count": 0,
        "ratio": 0.0
      },
      "英语成绩": {
        "count": 0,
        "ratio": 0.0
      },
      "成绩": {
        "count": 1,
        "ratio": 0.0417
      },
      "性别": {
        "count": 0,
        "ratio": 0.0
      },
      "备注": {
        "count": 0,
        "ratio": 0.0
      }
    },
    "numeric_summary": {
      "语文成绩": {
        "min": 49,
        "max": 96,
        "mean": 76.2
      },
      "数学成绩": {
        "min": 55,
        "max": 98,
        "mean": 77.8
      },
      "英语成绩": {
        "min": 52,
        "max": 95,
        "mean": 76.4
      },
      "成绩": {
        "min": 52,
        "max": 96,
        "mean": 77.6
      }
    },
    "text_summary": {
      "班级": {
        "unique_values": ["一班", "二班", "三班", "四班"]
      },
      "姓名": {
        "unique_values": ["张明", "李娜", "王强", "赵敏", "刘洋"]
      },
      "性别": {
        "unique_values": ["男", "女"]
      },
      "备注": {
        "unique_values": ["稳定", "优秀", "需关注", "临界", "补考风险"]
      }
    },
    "sample_rows": [
      {
        "班级": "一班",
        "姓名": "张明",
        "学号": "S2026001",
        "语文成绩": 86,
        "数学成绩": 92,
        "英语成绩": 88,
        "成绩": 89,
        "性别": "男",
        "备注": "稳定"
      }
    ]
  }
}
```

## 示例输出

```json
{
  "columns": [
    {
      "column_name": "班级",
      "dtype": "object",
      "semantic_type": "class",
      "business_meaning": "学生所属班级，用于按班级分组统计成绩。",
      "role": "dimension",
      "is_required_for_goal": true,
      "confidence": 0.98
    },
    {
      "column_name": "姓名",
      "dtype": "object",
      "semantic_type": "person_name",
      "business_meaning": "学生姓名，可用于识别个体学生。",
      "role": "identifier",
      "is_required_for_goal": false,
      "confidence": 0.96
    },
    {
      "column_name": "学号",
      "dtype": "object",
      "semantic_type": "student_id",
      "business_meaning": "学生编号，可用于唯一识别学生。",
      "role": "identifier",
      "is_required_for_goal": false,
      "confidence": 0.92
    },
    {
      "column_name": "语文成绩",
      "dtype": "int64",
      "semantic_type": "subject_score",
      "business_meaning": "语文学科成绩，可用于扩展到分科成绩分析。",
      "role": "metric",
      "is_required_for_goal": false,
      "confidence": 0.95
    },
    {
      "column_name": "数学成绩",
      "dtype": "int64",
      "semantic_type": "subject_score",
      "business_meaning": "数学学科成绩，可用于扩展到分科成绩分析。",
      "role": "metric",
      "is_required_for_goal": false,
      "confidence": 0.95
    },
    {
      "column_name": "英语成绩",
      "dtype": "int64",
      "semantic_type": "subject_score",
      "business_meaning": "英语学科成绩，可用于扩展到分科成绩分析。",
      "role": "metric",
      "is_required_for_goal": false,
      "confidence": 0.95
    },
    {
      "column_name": "成绩",
      "dtype": "float64",
      "semantic_type": "score",
      "business_meaning": "综合成绩或主要成绩指标，是本次按班级统计的目标指标。",
      "role": "target",
      "is_required_for_goal": true,
      "confidence": 0.98
    },
    {
      "column_name": "性别",
      "dtype": "object",
      "semantic_type": "gender",
      "business_meaning": "学生性别，可作为分类维度进行补充分析。",
      "role": "dimension",
      "is_required_for_goal": false,
      "confidence": 0.93
    },
    {
      "column_name": "备注",
      "dtype": "object",
      "semantic_type": "comment",
      "business_meaning": "学生状态或教师备注，可用于辅助解释成绩表现。",
      "role": "categorical",
      "is_required_for_goal": false,
      "confidence": 0.82
    }
  ],
  "date_columns": [],
  "target_columns": [
    {
      "column_name": "成绩",
      "semantic_type": "score",
      "reason": "用户目标是按班级统计成绩，该字段是最直接的综合成绩指标。",
      "confidence": 0.98
    }
  ],
  "dimension_columns": [
    {
      "column_name": "班级",
      "semantic_type": "class",
      "reason": "用户目标要求按班级统计，是核心分组字段。",
      "confidence": 0.98
    },
    {
      "column_name": "性别",
      "semantic_type": "gender",
      "reason": "可作为补充分类维度，但不是本次目标的必需字段。",
      "confidence": 0.93
    }
  ],
  "numeric_columns": [
    {
      "column_name": "语文成绩",
      "semantic_type": "subject_score",
      "reason": "字段类型为 int64，且字段名包含成绩。",
      "confidence": 0.95
    },
    {
      "column_name": "数学成绩",
      "semantic_type": "subject_score",
      "reason": "字段类型为 int64，且字段名包含成绩。",
      "confidence": 0.95
    },
    {
      "column_name": "英语成绩",
      "semantic_type": "subject_score",
      "reason": "字段类型为 int64，且字段名包含成绩。",
      "confidence": 0.95
    },
    {
      "column_name": "成绩",
      "semantic_type": "score",
      "reason": "字段类型为 float64，是本次目标的主要统计指标。",
      "confidence": 0.98
    }
  ],
  "categorical_columns": [
    {
      "column_name": "班级",
      "semantic_type": "class",
      "reason": "包含有限个班级类别。",
      "confidence": 0.98
    },
    {
      "column_name": "性别",
      "semantic_type": "gender",
      "reason": "包含男、女等有限类别。",
      "confidence": 0.93
    },
    {
      "column_name": "备注",
      "semantic_type": "comment",
      "reason": "文本取值有限，可作为状态分类或说明字段。",
      "confidence": 0.82
    }
  ],
  "quality_issues": [
    {
      "issue_type": "missing_values",
      "column_name": "成绩",
      "severity": "low",
      "description": "成绩字段存在 1 条缺失记录，缺失比例约 4.17%。",
      "suggested_action": "进行班级成绩统计时排除该条缺失成绩记录。"
    }
  ],
  "suitability_score": 0.93,
  "warnings": [
    {
      "warning_type": "threshold_assumption",
      "message": "后续计算及格率和优秀率时需要明确阈值，默认可使用 60 分及格、90 分优秀。"
    },
    {
      "warning_type": "target_column_choice",
      "message": "数据中存在多个成绩字段，本次用户目标未指定科目，建议优先使用综合字段“成绩”。"
    }
  ]
}
```

## 可直接用于后端的 Prompt 组装格式

```python
system_prompt = """你是 AI 原生数据分析工作台的数据理解 Agent。

你的任务：
1. 根据 dataset_profile 判断每个字段的业务含义。
2. 识别日期字段、目标指标字段、维度字段、数值字段、分类字段。
3. 识别数据质量问题。
4. 判断该数据是否适合用户目标 user_goal。
5. 只输出严格 JSON，不输出 Markdown、解释性散文、代码块或多余文本。

字段角色定义：
- date_columns：可表示日期、时间、月份、季度、年份等时间信息的字段。
- target_columns：用户目标中重点分析的指标字段，例如成绩、销量、销售额、转化率、利润等。
- dimension_columns：用于分组、对比、切片分析的字段，例如班级、地区、渠道、产品、老师、性别等。
- numeric_columns：数值型字段，或可以可靠转换为数值的字段。
- categorical_columns：类别型字段，通常用于分组或筛选。

输出要求：
- 输出必须是合法 JSON。
- 顶层字段必须包含：columns, date_columns, target_columns, dimension_columns, numeric_columns, categorical_columns, quality_issues, suitability_score, warnings。
- columns 必须覆盖 dataset_profile.columns 中的所有字段。
- 不要编造字段。
- quality_issues 和 warnings 没有内容时输出空数组。
"""

user_prompt = f"""请根据以下用户目标和数据画像理解数据字段，并判断该数据是否适合用户目标。

user_goal:
{user_goal}

dataset_profile:
{dataset_profile_json}

请严格按系统提示词要求输出 JSON。
"""
```
