import { createRequire } from "node:module";
import { access, mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("../frontend/node_modules/playwright");

const root = resolve(".");
const outputDir = resolve(root, "product-design-options", "exports");
const htmlPath = resolve(root, "product-design-options", "index.html");
const targets = [
  ["option-a", "方案A-任务指挥中心.png"],
  ["option-b", "方案B-新手向导式工作台.png"],
  ["option-c", "方案C-数据产品实验室.png"]
];

await mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({
  headless: true,
  executablePath: await firstExistingPath([
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"
  ])
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1024 }, deviceScaleFactor: 1 });
await page.goto(`file:///${htmlPath.replace(/\\/g, "/")}`, { waitUntil: "networkidle" });

for (const [id, fileName] of targets) {
  const element = page.locator(`#${id}`);
  await element.screenshot({ path: resolve(outputDir, fileName) });
}

await browser.close();

async function firstExistingPath(paths) {
  for (const path of paths) {
    try {
      await access(path);
      return path;
    } catch {
      // Try the next installed browser.
    }
  }
  return undefined;
}
