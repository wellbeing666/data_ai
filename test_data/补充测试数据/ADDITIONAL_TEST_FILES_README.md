# AI 原生数据分析工作台补充测试文件

本目录是一组补充测试数据，用于覆盖现有用例之外的场景。现有测试已经覆盖成绩 Excel 分析、商品销量与营销预算情景预测、房价分析/预测。本批文件重点覆盖制造质量、人员运营、客服排班、食堂排队、库存图片识别、能耗图表识别、非结构化图片负向测试和 RAG 业务知识检索。

## 文件清单

|文件|类型|测试方向|推荐问题|
|-|-:|-|-|
|`analysis\_manufacturing\_quality\_test.csv`|CSV|普通数据分析：制造质量与不良率|分析这批制造质检数据，按生产线、工序、班次比较不良率，找出高风险组合并生成图表。|
|`analysis\_employee\_attendance\_test.xlsx`|Excel|普通数据分析：人员运营与离职风险|按部门分析出勤率、平均加班小时、任务完成率和离职风险，并生成图表。|
|`scenario\_support\_staffing\_response\_time\_test.csv`|CSV|情景预测：客服人数增加 20% 对响应时长的影响|如果客服人数增加 20%，各渠道平均响应时长预计如何变化？|
|`scenario\_canteen\_window\_wait\_time\_test.csv`|CSV|情景预测：开放窗口数增加 2 个的绝对增量测试|如果开放窗口数增加 2 个，各时段平均排队时间可能下降多少？|
|`image\_inventory\_risk\_table\_test.png`|PNG|图片识别：库存风险表格截图|请从这张库存看板截图中识别表格，找出缺货风险最高的物料，并生成图表。|
|`image\_energy\_usage\_chart\_test.png`|PNG|图片识别：月度能耗图表截图|识别图表中的月度用电量和电费数据，分析峰值月份、环比变化和总体趋势。|
|`image\_unstructured\_note\_negative\_test.png`|PNG|图片识别负向测试：无结构化数据|请识别这张图片中的数据并分析。|
|`visual\_inventory\_risk\_expected.csv`|CSV|图片表格的理论抽取结果|用于和 `visual\_extracted.csv` 对比。|
|`visual\_energy\_chart\_expected.csv`|CSV|图片图表的理论抽取结果|用于和 `visual\_extracted.csv` 对比。|
|`knowledge\_quality\_support\_rules.md`|Markdown|RAG 知识库业务口径|先上传知识库，再运行相关测试。|
|`expected\_results.json`|JSON|全部理论期望与验收点|本地自动化比对或人工核对使用。|

## 重点理论期望

### 1\. 制造质量分析

* 行数：384。
* 生产线平均不良率从高到低：{"C线": 0.0443, "D线": 0.0381, "B线": 0.0344, "A线": 0.0301}。
* 工序平均不良率从高到低：{"终检": 0.0429, "涂装": 0.0416, "焊接": 0.0334, "冲压": 0.0289}。
* 班次平均不良率从高到低：{"夜班": 0.0425, "中班": 0.0359, "白班": 0.0317}。
* 高风险组合 Top 3：\[{"生产线": "C线", "工序": "终检", "班次": "夜班", "不良率": 0.056}, {"生产线": "C线", "工序": "涂装", "班次": "夜班", "不良率": 0.0559}, {"生产线": "C线", "工序": "终检", "班次": "中班", "不良率": 0.0501}]。
* 缺失值：{"设备停机分钟": 1, "环境湿度": 1, "检验员": 1}。

### 2\. 人员运营 Excel 分析

* 行数：48。
* 最高离职风险部门：客服中心。
* 最低出勤率部门：仓储物流。
* 最高任务完成率部门：研发部。
* 平均加班小时最高：客服中心，约 35.4 小时。
* 缺失值：{"培训小时": 1, "绩效评分": 1}。

### 3\. 客服排班情景预测

* 推荐问题：如果客服人数增加 20%，各渠道平均响应时长预计如何变化？
* 目标指标：平均响应时长\_秒。
* 干预字段：客服人数。
* 对象维度：渠道。
* 参考模型：LinearRegression，特征为客服人数、工单量、夜间占比、复杂工单占比，缺失客服人数按中位数填补。
* 整体基线均值：805.056 秒。
* 整体预测均值：757.285 秒。
* 整体变化：-47.771 秒。
* 客服人数参考系数：-28.2853。
* 渠道影响排序：\[{"渠道": "电话热线", "baseline\_mean": 777.367, "predicted\_mean": 707.66, "absolute\_change": -69.707, "percent\_change": -0.0897, "direction": "降低"}, {"渠道": "小程序工单", "baseline\_mean": 824.522, "predicted\_mean": 775.274, "absolute\_change": -49.248, "percent\_change": -0.0597, "direction": "降低"}, {"渠道": "在线客服", "baseline\_mean": 794.267, "predicted\_mean": 745.109, "absolute\_change": -49.158, "percent\_change": -0.0619, "direction": "降低"}, {"渠道": "邮件工单", "baseline\_mean": 824.067, "predicted\_mean": 801.097, "absolute\_change": -22.97, "percent\_change": -0.0279, "direction": "降低"}]。
* 预期结论应使用“预计、可能、显示出变化”等谨慎表述，不应写成确定因果。

### 4\. 食堂窗口情景预测

* 推荐问题：如果开放窗口数增加 2 个，各时段平均排队时间可能下降多少？
* 目标指标：平均排队时间\_分钟。
* 干预字段：开放窗口数。
* 正确业务口径：增加 2 个窗口是绝对增量，不是增加 2%。
* 数据生成口径：每增加 1 个窗口约减少 1.8 分钟排队时间。
* 整体基线均值：10.731 分钟。
* 正确绝对增量预测均值：7.391 分钟。
* 正确整体变化：-3.34 分钟。
* 分时段理论影响：\[{"时段": "午餐", "baseline\_mean": 19.158, "predicted\_mean": 15.558, "absolute\_change": -3.6, "percent\_change": -0.1879, "direction": "降低"}, {"时段": "晚餐", "baseline\_mean": 14.868, "predicted\_mean": 11.268, "absolute\_change": -3.6, "percent\_change": -0.2421, "direction": "降低"}, {"时段": "早餐", "baseline\_mean": 4.939, "predicted\_mean": 1.697, "absolute\_change": -3.242, "percent\_change": -0.6564, "direction": "降低"}, {"时段": "夜宵", "baseline\_mean": 3.96, "predicted\_mean": 1.042, "absolute\_change": -2.917, "percent\_change": -0.7367, "direction": "降低"}]。
* 重点观察：如果系统输出只下降约 0.1 分钟，说明可能把“+2 个窗口”误当作“+2%”。

### 5\. 库存图片识别

* 应抽取 7 行库存物料数据。
* 核心字段应包含：物料编码、物料名称、仓库、当前库存、安全库存、日均消耗、供应周期天、风险等级。
* 高风险物料应包含：电池模组、关键芯片、密封圈。
* 按库存覆盖天数最低排序：密封圈、关键芯片、电池模组。
* 可用 `visual\_inventory\_risk\_expected.csv` 与系统生成的 `visual\_extracted.csv` 对比。

### 6\. 能耗图表图片识别

* 应抽取 8 个月数据。
* 峰值月份：8月，用电量 19200 kWh。
* 总用电量：124950 kWh。
* 最大环比增长：4月，增长 2400 kWh。
* 趋势：总体上升，2月低点后逐步增长，8月达到峰值。。
* 可用 `visual\_energy\_chart\_expected.csv` 与系统生成的 `visual\_extracted.csv` 对比。

### 7\. 非结构化图片负向测试

* `image\_unstructured\_note\_negative\_test.png` 没有结构化表格或图表。
* 理论期望：视觉解析失败或低置信度警告；不应进入可靠的数据分析结论。
* 推荐核对字段：`visual\_parse\_result.success=false` 或 `task\_type=visual\_parsing\_failed`。

## 建议本地核对方式

1. 逐个上传文件，使用上表推荐问题运行统一工作流 `/api/workflows/jobs/async`。
2. 下载或查看任务目录中的 `controller\_plan.json`、`dataset\_profile.json`、`analysis\_result.json`、`prediction\_result.json`、`visual\_parse\_result.json`、`visual\_extracted.csv`。
3. 使用 `expected\_results.json` 的理论值做人工或脚本比对。
4. 对情景预测结果允许小幅模型差异，但方向、目标字段、干预字段、对象维度和谨慎表述应一致。

