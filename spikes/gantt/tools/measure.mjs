// Measures every candidate with a real browser (Edge through Playwright), headless:
//   node measure.mjs [baseUrl] [counts]      e.g. node measure.mjs http://localhost:4173 2000,5000
// Desktop 1366x768, then a phone (390x844, touch) with the CPU slowed down 4x through the DevTools protocol — about a
// mid-range Android phone. Prints one JSON line per run and a table at the end.
import { chromium } from "playwright-core";

const base = process.argv[2] || "http://localhost:4173";
const counts = (process.argv[3] || "2000,5000").split(",").map(Number);
const libs = ["canvas", "svar", "dhtmlx", "frappe"];
const profiles = [
  { name: "máy tính", viewport: { width: 1366, height: 768 }, cpu: 1 },
  { name: "điện thoại (CPU x4)", viewport: { width: 390, height: 844 }, cpu: 4, isMobile: true, hasTouch: true },
];

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
const rows = [];
for (const profile of profiles) {
  for (const count of counts) {
    for (const lib of libs) {
      const context = await browser.newContext({ viewport: profile.viewport, isMobile: profile.isMobile, hasTouch: profile.hasTouch });
      const page = await context.newPage();
      const cdp = await context.newCDPSession(page);
      await cdp.send("Emulation.setCPUThrottlingRate", { rate: profile.cpu });
      const started = Date.now();
      let result = null;
      try {
        await page.goto(`${base}/?lib=${lib}&n=${count}`);
        await page.waitForFunction(() => window.__spike, null, { timeout: 120000 });
        result = await page.evaluate(() => window.__spike);
      } catch (error) {
        result = { lib, count, error: String(error.message || error).slice(0, 120) };
      }
      const row = { profile: profile.name, ...result, wall: Date.now() - started };
      console.log(JSON.stringify(row));
      rows.push(row);
      await context.close();
    }
  }
}
await browser.close();
console.log("\n| Cấu hình | Thư viện | Công việc | Vẽ lần đầu (ms) | Cuộn TB (ms/khung) | Cuộn p95 | Nút DOM |");
console.log("|---|---|---|---|---|---|---|");
for (const r of rows) {
  console.log(`| ${r.profile} | ${r.lib} | ${r.count ?? "—"} | ${r.render ?? r.error} | ${r.scrollAvg ?? "—"} | ${r.scrollP95 ?? "—"} | ${r.domNodes ?? "—"} |`);
}
