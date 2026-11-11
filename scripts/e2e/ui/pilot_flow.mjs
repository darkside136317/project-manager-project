// M7 end to end, the pilot scenario on the construction demo (DEMO-XD01, scripts: bootstrap --seed-demo, or
// `bench execute pm_construction.pm_construction.setup.demo.up`), in a real browser.
//
// On a computer, as the administrator: the portfolio shows the factory project in red with its open alerts; its
// overview shows the health, the phase PHẦN MÓNG waiting for one acceptance, the overdue alert that climbed to the site
// commander, the missing site diary; the alert rules are an administration screen.
// On a phone, as the site commander: the alerts page, "Đã biết" on one of them, the notification settings; then the
// commander approves the last acceptance of the foundation and the phase passes by itself to PHẦN THÂN.
//
//   cd scripts/e2e/ui && npm ci && node pilot_flow.mjs [base_url]
//
// Same conventions as forms_flow.mjs (reads docker/.env, never prints the password, pictures in out/). The site
// commander is reached by the administrator's "impersonate" (no password). It changes the demo: run
// `bench execute pm_construction.pm_construction.setup.demo.down` then `.up` to play it again.
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "pilot");
const env = Object.fromEntries(readFileSync(join(HERE, "../../../docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const API = "project_manager.project_manager.api";
const COMMANDER = "demo.chihuy@pm.localhost";
const PROJECT_NAME = "Nhà xưởng Tân Uyên – Bình Dương";

let failures = 0;
const problems = [];

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
    if (message.type() !== "error" || /Failed to load resource|WebSocket|net::/.test(text)) return;
    problems.push(`console: ${text}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && response.status() !== 417) problems.push(`${response.status()} ${response.url()}`);
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

async function signIn(context) {
  const login = await context.request.post(`${BASE}/api/method/login`, { form: { usr: "Administrator", pwd: env.ADMIN_PASSWORD || "" } });
  check("đăng nhập quản trị", login.ok(), String(login.status()));
}

async function asAdministrator(page) {
  await page.goto(`${BASE}/pm/danh-muc-du-an`);
  await page.getByRole("heading", { name: "Danh mục dự án" }).waitFor();
  const row = page.locator("[data-portfolio-row]", { hasText: PROJECT_NAME });
  await row.waitFor();
  const text = await row.innerText();
  check("danh mục: nhà xưởng có sức khỏe Đỏ", text.includes("Đỏ"), text.slice(0, 200));
  check("danh mục: giai đoạn hiện tại PHẦN MÓNG", text.includes("PHẦN MÓNG"), text.slice(0, 300));
  await shot(page, "01-danh-muc");

  const portfolio = await call(page, `${API}.alerts.portfolio`, {}, false);
  const project = portfolio.rows.find((r) => r.project_name === PROJECT_NAME);
  check("danh mục: có cảnh báo đang mở", project && project.alerts_open >= 3, JSON.stringify(project && project.alerts_open));
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project.name)}/tong-quan`);
  const card = page.locator("[data-health-card]");
  await card.waitFor();
  await card.locator("[data-project-alert]").first().waitFor();
  const overview = await card.innerText();
  check("tổng quan: sức khỏe dự án và lý do", /Đỏ/.test(overview) && /SPI/.test(overview), overview.slice(0, 300));
  check("tổng quan: phần móng chờ nghiệm thu một công tác", overview.includes("còn 1 công tác chưa nghiệm thu đủ khối lượng"), overview.slice(0, 400));
  check("tổng quan: cảnh báo quá hạn đã leo thang", /Leo thang bậc 1/.test(overview) && /Quá hạn/.test(overview), overview.slice(0, 600));
  check("tổng quan: thiếu nhật ký thi công", overview.includes("Chưa có nhật ký thi công"), overview.slice(0, 600));
  const modes = [await page.getByLabel("Chuyển giai đoạn PHẦN MÓNG").inputValue(), await page.getByLabel("Chuyển giai đoạn PHẦN THÂN").inputValue()];
  check("tổng quan: chế độ chuyển của từng giai đoạn", modes[0] === "Tự động" && modes[1] === "Cần duyệt", modes.join(", "));
  await shot(page, "02-tong-quan", true);

  await page.goto(`${BASE}/pm/quan-tri/quy-tac-canh-bao`);
  await page.getByText("Quá hạn", { exact: true }).first().waitFor();
  const rules = await page.locator("main").innerText();
  check("quản trị: danh sách quy tắc cảnh báo", ["Sắp đến hạn", "Chờ duyệt chuyển giai đoạn", "Thiếu nhật ký thi công"].every((r) => rules.includes(r)), rules.slice(0, 400));
  await shot(page, "03-quy-tac");
  await page.getByRole("row", { name: /^Quá hạn Quá hạn/ }).click();
  await page.getByText("Các bậc leo thang").waitFor();
  const steps = await page.getByRole("dialog").locator("table tbody tr").evaluateAll((rows) =>
    rows.map((row) => [...row.querySelectorAll("input, select")].map((field) => (field.type === "checkbox" ? field.checked : field.value))));
  check("quy tắc quá hạn: sau 2 ngày báo chỉ huy trưởng, sau 5 ngày báo quản lý",
    steps.length === 2 && String(steps[0][0]) === "2" && steps[0].includes("Chỉ huy trưởng") && String(steps[1][0]) === "5" && steps[1][1] === true,
    JSON.stringify(steps));
  await page.getByRole("dialog").getByText("Các bậc leo thang").scrollIntoViewIfNeeded();
  await shot(page, "03b-quy-tac-qua-han");
  await page.getByRole("dialog").getByRole("button", { name: "Hủy" }).click();
  return project.name;
}

async function asCommander(browser, project) {
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "vi-VN" });
  await signIn(phone);
  const switched = await phone.request.post(`${BASE}/api/method/frappe.core.doctype.user.user.impersonate`,
    { form: { user: COMMANDER, reason: "Kiểm thử kịch bản thí điểm M7" } });
  check("vào vai chỉ huy trưởng", switched.ok(), String(switched.status()));
  const page = await phone.newPage();
  watch(page);

  await page.goto(`${BASE}/pm/canh-bao`);
  await page.getByRole("heading", { name: "Cảnh báo" }).waitFor();
  await page.locator("[data-alert]").first().waitFor();
  const list = await page.locator("main").innerText();
  check("cảnh báo của chỉ huy trưởng: quá hạn bậc 1, thiếu nhật ký", /Leo thang bậc 1/.test(list) && list.includes("Chưa có nhật ký thi công"), list.slice(0, 500));
  await fits(page, "cảnh báo trên điện thoại");
  await shot(page, "04-canh-bao-dien-thoai", true);
  const diaryAlert = page.locator("[data-alert]", { hasText: "Chưa có nhật ký thi công" });
  await diaryAlert.getByRole("button", { name: "Đã biết, đang xử lý" }).click();
  await page.getByRole("dialog").getByLabel("Ghi chú (không bắt buộc)").fill("Sáng nay bổ sung nhật ký");
  await page.getByRole("dialog").getByRole("button", { name: "Xác nhận" }).click();
  await diaryAlert.getByText("Đã xác nhận", { exact: true }).waitFor();
  check("xác nhận cảnh báo: thôi leo thang", true);

  // notification settings
  await page.getByRole("button", { name: /^Tài khoản:/ }).click();
  await page.getByRole("menuitem", { name: "Tùy chọn thông báo" }).click();
  const drawer = page.getByRole("dialog", { name: "Tùy chọn thông báo" });
  await drawer.getByLabel("Từ").fill("22:00");
  await drawer.getByLabel("Sắp đến hạn").check();
  await shot(page, "05-tuy-chon");
  await drawer.getByRole("button", { name: "Lưu" }).click();
  await page.getByText("Đã lưu tùy chọn thông báo").waitFor();
  const pref = await call(page, `${API}.alerts.preference`, {}, false);
  check("tùy chọn đã lưu: giờ yên lặng, loại tắt", pref.quiet_start === "22:00" && pref.muted_types.includes("Sắp đến hạn"), JSON.stringify(pref));
  await call(page, `${API}.alerts.save_preference`, { values: { quiet_start: "", muted_types: "" } });  // as it was

  // the last acceptance of the foundation
  const waiting = await call(page, `${API}.forms.list_forms`, { project, state: "Đã nộp" }, false);
  const record = waiting.rows.find((row) => row.template_code === "NT-CONGVIEC");
  check("còn một biên bản nghiệm thu chờ duyệt", Boolean(record), JSON.stringify(waiting.rows.map((r) => r.title)));
  if (record) {
    await page.goto(`${BASE}/pm/bieu-mau/${record.name}`);
    await page.getByRole("button", { name: "Duyệt", exact: true }).click();
    await page.getByText("Đã duyệt biểu mẫu").waitFor();
    const state = await call(page, `${API}.alerts.phase_state`, { project }, false);
    check("duyệt xong: phần móng tự chuyển sang phần thân", state.current && state.current.label === "2 PHẦN THÂN" && state.done === 1, JSON.stringify(state));
    await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/tong-quan`);
    const card = page.locator("[data-gate]");
    await card.waitFor();
    const text = await card.innerText();
    check("tổng quan: giai đoạn 2/3 PHẦN THÂN, chuyển cần duyệt", text.includes("Giai đoạn 2/3") && text.includes("PHẦN THÂN") && text.includes("Cần duyệt"), text);
    await fits(page, "tổng quan trên điện thoại");
    await shot(page, "06-giai-doan-moi", true);
    const recent = await page.locator("main").innerText();
    check("lịch sử dự án ghi việc chuyển giai đoạn", recent.includes("Chuyển từ giai đoạn PHẦN MÓNG sang PHẦN THÂN"), recent.slice(-800));
  }
  await phone.close();
}

async function main() {
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
  try {
    const desktop = await browser.newContext({ viewport: { width: 1366, height: 860 }, locale: "vi-VN" });
    await signIn(desktop);
    const page = await desktop.newPage();
    watch(page);
    const project = await asAdministrator(page);
    await asCommander(browser, project);
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
