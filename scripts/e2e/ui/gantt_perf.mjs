// How long the Gantt of a large project takes, in a real browser: from navigation to the first complete drawing, and the
// frames while scrolling. On a computer, then on a phone with the CPU slowed down 4x (about a mid-range Android phone).
//
//   docker compose exec ... scripts/perf/gantt_seed.py seed     prints PROJECT=...
//   cd scripts/e2e/ui && node gantt_perf.mjs PROJECT [base_url]
//
// The target of the plan: 2 000 tasks, API and drawing, under 2 s.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const env = Object.fromEntries(readFileSync(join(HERE, "../../..", process.env.PM_ENV_FILE || "docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const PROJECT = process.argv[2];
const BASE = (process.argv[3] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const PROFILES = [
  { name: "máy tính", viewport: { width: 1366, height: 800 }, cpu: 1 },
  { name: "điện thoại (CPU x4)", viewport: { width: 390, height: 844 }, cpu: 4, isMobile: true, hasTouch: true },
];
const RUNS = 3;

if (!PROJECT) {
  console.log("Thiếu tên dự án");
  process.exit(1);
}

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
let worst = 0;
for (const profile of PROFILES) {
  const context = await browser.newContext({ viewport: profile.viewport, isMobile: profile.isMobile, hasTouch: profile.hasTouch });
  await context.request.post(`${BASE}/api/method/login`, { form: { usr: "Administrator", pwd: env.ADMIN_PASSWORD || "" } });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: profile.cpu });
  const results = [];
  for (let run = 0; run < RUNS; run += 1) {
    await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(PROJECT)}/gantt`);
    await page.locator(".gantt-scroller[data-ready]").waitFor({ timeout: 60000 });
    results.push(await page.evaluate(() => {
      const mark = performance.getEntriesByName("pm-gantt-drawn")[0];
      const call = performance.getEntriesByType("resource").find((entry) => entry.name.includes("schedule.gantt"));
      return { drawn: mark?.startTime, api: call?.duration, bytes: call?.encodedBodySize, rows: document.querySelectorAll(".gantt-row").length };
    }));
  }
  const frames = await page.evaluate(async () => {
    const scroller = document.querySelector(".gantt-scroller");
    const times = [];
    let last = performance.now();
    for (let step = 0; step < 90; step += 1) {
      scroller.scrollTop += 90;
      scroller.scrollLeft += 12;
      await new Promise((resolve) => requestAnimationFrame(resolve));
      const now = performance.now();
      times.push(now - last);
      last = now;
    }
    times.sort((a, b) => a - b);
    return { median: times[Math.floor(times.length / 2)], p95: times[Math.floor(times.length * 0.95)] };
  });
  const best = results.reduce((a, b) => (a.drawn < b.drawn ? a : b));
  worst = Math.max(worst, ...results.map((result) => result.drawn));
  console.log(`${profile.name}: vẽ xong ${results.map((r) => Math.round(r.drawn)).join(" / ")} ms (API ${Math.round(best.api)} ms, ${Math.round((best.bytes || 0) / 1024)} KB nén); cuộn: trung vị ${frames.median.toFixed(1)} ms/khung, p95 ${frames.p95.toFixed(1)} ms`);
  await context.close();
}
await browser.close();
console.log(worst < 2000 ? "Đạt mục tiêu dưới 2 s" : `Chậm hơn mục tiêu 2 s: ${Math.round(worst)} ms`);
process.exit(worst < 2000 ? 0 : 1);
