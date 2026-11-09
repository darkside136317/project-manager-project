// M6 end to end, in a real browser. On a computer: import the sample BOQ from Excel, look at the preview, keep it as
// version 1 and approve it: the WBS gets its sections and work items. On a phone, without a connection: write the
// site diary of the day with a quantity and a photo; when the connection is back it is submitted and the work item's
// progress follows the quantity. Back on the computer: confirm the diary, see the value done, start an acceptance.
//
//   cd scripts/e2e/ui && npm ci && node construction_flow.mjs [base_url]
//
// Same conventions as forms_flow.mjs (reads docker/.env, never prints the password, pictures in out/). It creates a project
// named "Dự án thử thi công ...": run it on a scratch or development site. The exit code is the number of failed checks.
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "construction");
const env = Object.fromEntries(readFileSync(join(HERE, "../../../docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const STAMP = Date.now().toString(36).toUpperCase();
const LAYER = "pm_construction.pm_construction.api.construction";
const DIG = "Đào móng băng bằng thủ công, đất cấp II";

let failures = 0;
const problems = [];
let offlineNow = false;

function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : ` — ${detail}`}`);
  if (!ok) failures += 1;
}

async function shot(page, name, fullPage = false) {
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage });
}

async function fits(page, where) {
  await page.waitForTimeout(200);
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  check(`${where}: không cuộn ngang`, scroll <= client, `${scroll} > ${client}`);
}

function watch(page) {
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() !== "error" || /Failed to load resource|WebSocket|ERR_INTERNET_DISCONNECTED|net::/.test(text)) return;
    problems.push(`console: ${text}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && response.status() !== 417 && !offlineNow) problems.push(`${response.status()} ${response.url()}`);
  });
}

const call = (page, method, args = {}, post = true) => page.evaluate(async ({ url, args, post }) => {
  const options = { method: post ? "POST" : "GET", headers: { "X-Frappe-CSRF-Token": window.__PM_BOOT__.csrf_token, "Content-Type": "application/json", Accept: "application/json" } };
  if (post) options.body = JSON.stringify(args);
  const query = post ? "" : `?${new URLSearchParams(args)}`;
  const response = await fetch(url + query, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload._server_messages || payload.exception || response.status);
  return payload.message;
}, { url: `/api/method/${method}`, args, post });

async function until(test, timeout = 15000, step = 400) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await test()) return true;
    await new Promise((resolve) => setTimeout(resolve, step));
  }
  return false;
}

async function importBoq(page, project) {
  await page.goto(`${BASE}/pm/du-an/${project}/boq`);
  await page.getByText("Chưa có BOQ").waitFor();
  const tabs = await page.getByRole("navigation", { name: "Các mục của dự án" }).innerText();
  check("dự án có tab BOQ, Nhật ký, Nghiệm thu", ["BOQ", "Nhật ký", "Nghiệm thu"].every((label) => tabs.includes(label)), tabs);
  const template = await page.request.get(`${BASE}/api/method/${LAYER}.boq_template`);
  check("tải được tệp BOQ mẫu", template.ok(), String(template.status()));
  await page.getByRole("button", { name: "Nhập BOQ từ Excel" }).click();
  await page.getByLabel("Tệp BOQ").setInputFiles({ name: "du-toan.xlsx", mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", buffer: await template.body() });
  await page.getByText("công tác, tổng").waitFor();
  const summary = await page.getByText("công tác, tổng").innerText();
  check("xem trước: 5 hạng mục, 12 công tác", /5\s*hạng mục, 12\s*công tác/.test(summary), summary);
  await shot(page, "01-boq-preview");
  await page.getByRole("button", { name: "Nhập bản 1" }).click();
  await page.getByRole("button", { name: "Duyệt bản này" }).waitFor();
  check("bản 1 được giữ ở trạng thái nháp", await page.getByText("Bản nháp: chưa ảnh hưởng tới công việc").isVisible());
  await page.getByRole("button", { name: "Duyệt bản này" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Duyệt" }).click();
  await page.getByRole("columnheader", { name: "Đã làm" }).waitFor();
  check("duyệt BOQ: bảng có cột đã làm", true);
  const tree = await call(page, "project_manager.project_manager.api.wbs.children", { project }, false);
  const names = (tree.rows || tree).map((row) => row.subject);
  check("WBS có các hạng mục của BOQ", ["PHẦN MÓNG", "PHẦN THÂN", "PHẦN HOÀN THIỆN"].every((name) => names.includes(name)), names.join(", "));
  await shot(page, "02-boq-approved");
}

async function diaryOffline(context, page, project, photo) {
  offlineNow = false;
  await page.goto(`${BASE}/pm/du-an/${project}/nhat-ky`);
  await page.getByRole("heading", { name: "Khối lượng đã làm" }).waitFor();
  await page.evaluate(async () => navigator.serviceWorker.ready);
  await page.reload();
  await page.getByRole("heading", { name: "Khối lượng đã làm" }).waitFor();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  await page.waitForTimeout(800);
  await fits(page, "nhật ký trên điện thoại");

  offlineNow = true;
  await context.setOffline(true);
  await page.getByRole("button", { name: "Nắng" }).click();
  await page.getByLabel("Nhân công trên công trường").fill("18");
  await page.getByLabel("Công tác", { exact: true }).first().fill("Đào móng");
  await page.getByRole("button", { name: /Đào móng băng/ }).click();
  await page.getByLabel("Khối lượng", { exact: true }).first().fill("43,2");
  await page.getByLabel("Công việc đã làm").fill(`Đào móng trục A–C ${STAMP}`);
  await page.locator('input[type="file"][capture]').setInputFiles({ name: "mong.jpg", mimeType: "image/jpeg", buffer: photo });
  await page.getByRole("list", { name: "Ảnh sẽ gửi" }).getByRole("listitem").first().waitFor();
  await page.getByRole("button", { name: "Nộp nhật ký" }).click();
  await page.getByText("Nhật ký đang chờ có mạng để gửi").waitFor();
  check("nhật ký viết khi mất mạng được giữ lại", true);
  await shot(page, "03-diary-offline");

  offlineNow = false;
  await context.setOffline(false);
  const sent = await until(async () => (await page.getByText("Đã nộp", { exact: true }).count()) > 0, 25000);
  check("có mạng lại: nhật ký tự nộp", sent);
  const tasks = await call(page, `${LAYER}.diary_works`, { project }, false);
  const dig = tasks.find((row) => row.subject === DIG);
  check("khối lượng đào móng đã cộng: 43,2 / 86,4, tiến độ 50%", dig && dig.pmc_done_qty === 43.2 && Math.round(dig.progress) === 50, JSON.stringify(dig));
  const listing = await call(page, `${LAYER}.diaries`, { project }, false);
  check("một nhật ký, có 1 ảnh (không trùng)", listing.diaries.length === 1 && listing.diaries[0].photos === 1,
    JSON.stringify(listing.diaries.map((d) => [d.name, d.photos])));
  await shot(page, "04-diary-sent");
  await page.goto(`${BASE}/pm/du-an/${project}/boq`);
  await page.getByRole("columnheader", { name: "Đã làm" }).waitFor();
  await fits(page, "BOQ trên điện thoại");
  await page.goto(`${BASE}/pm/du-an/${project}/nghiem-thu`);
  await page.getByRole("heading", { name: "Khối lượng theo công tác" }).waitFor();
  await fits(page, "nghiệm thu trên điện thoại");
}

async function confirmAndAccept(page, project) {
  await page.goto(`${BASE}/pm/du-an/${project}/nhat-ky`);
  await page.getByRole("button", { name: "Xác nhận" }).click();
  await page.getByText("Đã xác nhận", { exact: true }).first().waitFor();
  check("chỉ huy xác nhận nhật ký", true);
  await page.goto(`${BASE}/pm/du-an/${project}/boq`);
  await page.getByText("Đã thi công").waitFor();
  const done = await page.locator("section[aria-label='Giá trị theo BOQ'] .card").nth(1).innerText();
  check("BOQ cho thấy phần giá trị đã thi công: 1,6%", /1,6%/.test(done), done.replace(/\s+/g, " "));
  const overview = await call(page, "project_manager.project_manager.api.projects.overview", { project }, false);
  const expected = (43.2 * 285000) / 758989000 * 100;
  check("tiến độ dự án tính theo giá trị dự toán", Math.abs((overview.project.percent_complete || 0) - expected) < 0.05,
    `${overview.project.percent_complete} ≠ ${expected.toFixed(2)}`);
  await page.goto(`${BASE}/pm/du-an/${project}/nghiem-thu`);
  const row = page.getByRole("row").filter({ hasText: "Đào móng băng" });
  await row.getByRole("button", { name: "Lập biên bản" }).click();
  await page.waitForURL(/\/pm\/bieu-mau\//);
  await page.getByText("Biên bản nghiệm thu công việc xây dựng").first().waitFor();
  check("lập biên bản nghiệm thu từ công tác chờ nghiệm thu", true);
  await shot(page, "05-acceptance-form");
}

async function bigPhoto(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
  const page = await context.newPage();
  await page.setContent(`<body style="margin:0;background:linear-gradient(135deg,#78716c,#0a1f35)"><h1 style="color:#fff;font:700 40px sans-serif;padding:40px">Móng ${STAMP}</h1></body>`);
  const buffer = await page.screenshot({ type: "jpeg", quality: 85 });
  await context.close();
  return buffer;
}

async function main() {
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
  try {
    const desktop = await browser.newContext({ viewport: { width: 1366, height: 860 }, locale: "vi-VN" });
    const login = await desktop.request.post(`${BASE}/api/method/login`, { form: { usr: "Administrator", pwd: env.ADMIN_PASSWORD || "" } });
    check("đăng nhập", login.ok(), String(login.status()));
    const page = await desktop.newPage();
    watch(page);
    await page.goto(`${BASE}/pm/du-an`);
    await page.getByRole("heading", { name: "Dự án", exact: true }).waitFor();
    const { name: project } = await call(page, "project_manager.project_manager.api.projects.create", { values: { project_name: `Dự án thử thi công ${STAMP}` } });
    check("tạo dự án thử", Boolean(project));
    await importBoq(page, project);
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "vi-VN",
      storageState: await desktop.storageState() });
    const small = await phone.newPage();
    watch(small);
    await diaryOffline(phone, small, project, await bigPhoto(browser));
    await confirmAndAccept(page, project);
    check("không có lỗi JavaScript", problems.length === 0, problems.join(" | ").slice(0, 700));
  } catch (error) {
    check("kịch bản chạy hết", false, String(error.message || error).slice(0, 900));
    if (problems.length) console.log(problems.join("\n").slice(0, 900));
  } finally {
    await browser.close();
  }
  console.log(`${failures} failure(s)`);
  process.exit(failures);
}

main();
