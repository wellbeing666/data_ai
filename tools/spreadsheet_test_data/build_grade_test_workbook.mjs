import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "../../outputs";
const outputPath = `${outputDir}/grade_class_stats_test.xlsx`;

const rows = [
  ["班级", "姓名", "学号", "语文成绩", "数学成绩", "英语成绩", "成绩", "性别", "备注"],
  ["一班", "张明", "S2026001", 86, 92, 88, 89, "男", "稳定"],
  ["一班", "李娜", "S2026002", 95, 96, 91, 94, "女", "优秀"],
  ["一班", "王强", "S2026003", 72, 68, 75, 72, "男", "需关注"],
  ["一班", "赵敏", "S2026004", 61, 59, 66, 62, "女", "临界"],
  ["一班", "刘洋", "S2026005", 88, 84, 90, 87, "男", "稳定"],
  ["一班", "陈晨", "S2026006", 54, 58, 62, 58, "女", "补考风险"],
  ["二班", "孙磊", "S2026007", 78, 81, 79, 79, "男", "稳定"],
  ["二班", "周悦", "S2026008", 92, 89, 94, 92, "女", "优秀"],
  ["二班", "吴迪", "S2026009", 66, 70, 64, 67, "男", "进步中"],
  ["二班", "郑雪", "S2026010", 83, 86, 80, 83, "女", "稳定"],
  ["二班", "何佳", "S2026011", 57, 63, 60, 60, "女", "临界"],
  ["二班", "马超", "S2026012", 49, 55, 52, 52, "男", "需帮扶"],
  ["三班", "胡斌", "S2026013", 91, 93, 89, 91, "男", "优秀"],
  ["三班", "郭婷", "S2026014", 74, 77, 72, 74, "女", "稳定"],
  ["三班", "罗浩", "S2026015", 63, 60, 58, 60, "男", "临界"],
  ["三班", "梁静", "S2026016", 85, 88, 86, 86, "女", "稳定"],
  ["三班", "宋宇", "S2026017", 96, 98, 95, 96, "男", "优秀"],
  ["三班", "唐欣", "S2026018", 52, 57, 55, 55, "女", "需帮扶"],
  ["四班", "许诺", "S2026019", 68, 72, 70, 70, "女", "稳定"],
  ["四班", "高峰", "S2026020", 82, 79, 84, 82, "男", "稳定"],
  ["四班", "蒋宁", "S2026021", 90, 91, 93, 91, "女", "优秀"],
  ["四班", "叶航", "S2026022", 58, 62, 57, 59, "男", "补考风险"],
  ["四班", "冯琪", "S2026023", 76, 74, 78, 76, "女", "稳定"],
  ["四班", "邓林", "S2026024", 80, 83, 81, null, "男", "成绩待录入"],
];

await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("成绩数据");
sheet.showGridLines = false;

sheet.getRange("A1:I25").values = rows;
sheet.freezePanes.freezeRows(1);

sheet.getRange("A1:I1").format = {
  fill: "#0F766E",
  font: { bold: true, color: "#FFFFFF" },
};
sheet.getRange("A1:I25").format = {
  font: { name: "Microsoft YaHei", size: 10 },
  verticalAlignment: "center",
};
sheet.getRange("A1:I25").format.borders = {
  top: { style: "continuous", color: "#CBD5E1" },
  bottom: { style: "continuous", color: "#CBD5E1" },
  left: { style: "continuous", color: "#CBD5E1" },
  right: { style: "continuous", color: "#CBD5E1" },
};
sheet.getRange("D2:G25").format.numberFormat = "0";
sheet.getRange("A:A").format.columnWidthPx = 90;
sheet.getRange("B:B").format.columnWidthPx = 90;
sheet.getRange("C:C").format.columnWidthPx = 110;
sheet.getRange("D:G").format.columnWidthPx = 92;
sheet.getRange("H:H").format.columnWidthPx = 70;
sheet.getRange("I:I").format.columnWidthPx = 120;

const table = sheet.tables.add("A1:I25", true, "GradeTestData");
table.style = "TableStyleMedium2";

const preview = await workbook.render({
  sheetName: "成绩数据",
  range: "A1:I25",
  scale: 1,
  format: "png",
});
await fs.writeFile(
  `${outputDir}/grade_class_stats_test_preview.png`,
  new Uint8Array(await preview.arrayBuffer()),
);

const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);

const inspect = await workbook.inspect({
  kind: "table",
  range: "成绩数据!A1:I8",
  include: "values",
  tableMaxRows: 8,
  tableMaxCols: 9,
});
console.log(inspect.ndjson);
console.log(outputPath);
