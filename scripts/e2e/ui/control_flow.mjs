// M10 end to end on the demos (core DEMO-NP01 and construction DEMO-XD01; run both demos first), in a real browser.
//
// The manager of the town house reads the budget and its earned value, records a risk that then happens (it becomes
// an issue), approves the change request the engineer sent (its cost goes into the budget in use). The engineer, on a
// phone, sends a change request and cannot see the budget. The manager runs the reports (on screen, Excel, PDF) and
// sees the weekly report scheduled for them; exports the plan to MS Project XML and imports it into a scratch project,
// builds that project's dossier (ZIP with its manifest), closes and reopens it.
//
//   cd scripts/e2e/ui && npm ci && node control_flow.mjs [base_url]
//
// Same conventions as pilot_flow.mjs (reads docker/.env, never prints the password, demo people reached through the
// administrator's "impersonate", pictures in out/). It changes the demo (a risk, a decided change request) and leaves
// a closed scratch project "E2E MS Project …": rebuild the demos to play it again from the start.
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "control");
const env = Object.fromEntries(readFileSync(join(HERE, "../../..", process.env.PM_ENV_FILE || "docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const API = "project_manager.project_manager.api";
const PEOPLE = { engineer: "demo.kysu1@pm.localhost", manager: "demo.quanly@pm.localhost" };
const STAMP = Date.now().toString(36);

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

function watch(page, expected = []) {
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    const text = message.text();
    if (message.type() !== "error" || /Failed to load resource|WebSocket|net::/.test(text)) return;
    problems.push(`console: ${text}`);
  });
  page.on("response", (response) => {
    const allowed = response.status() === 403 && expected.some((part) => response.url().includes(part));
    if (response.status() >= 400 && response.status() !== 417 && !allowed) problems.push(`${response.status()} ${response.url()}`);
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

async function until(test, timeout = 20000, step = 500) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await test()) return true;
    await new Promise((resolve) => setTimeout(resolve, step));
  }
  return false;
}

async function as(browser, who, phone = false, expected = []) {
  const context = await browser.newContext(phone
    ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "vi-VN", acceptDownloads: true }
    : { viewport: { width: 1366, height: 860 }, locale: "vi-VN", acceptDownloads: true });
  const login = await context.request.post(`${BASE}/api/method/login`, { form: { usr: "Administrator", pwd: env.ADMIN_PASSWORD || "" } });
  check(`đăng nhập (${who})`, login.ok(), String(login.status()));
  if (who !== "admin") {
    const switched = await context.request.post(`${BASE}/api/method/frappe.core.doctype.user.user.impersonate`,
      { form: { user: PEOPLE[who], reason: "Kiểm thử kịch bản kiểm soát dự án M10" } });
    check(`vào vai ${who}`, switched.ok(), String(switched.status()));
  }
  const page = await context.newPage();
  watch(page, expected);
  return { context, page };
}

const tab = (project, slug) => `${BASE}/pm/du-an/${encodeURIComponent(project)}/${slug}`;

async function engineerRequests(browser, house) {
  const { context, page } = await as(browser, "engineer", true, ["budget_overview"]);
  await page.goto(tab(house, "phat-sinh"));
  await page.locator("[data-changes]").waitFor();
  const before = await page.locator("[data-change]").count();
  await page.getByRole("button", { name: "Lập phát sinh" }).click();
  const drawer = page.getByRole("dialog", { name: "Lập phát sinh" });
  await drawer.getByLabel("Nội dung phát sinh").fill(`Thêm ổ cắm phòng khách ${STAMP}`);
  await drawer.getByLabel("Chi phí phát sinh").fill("3500000");
  await drawer.getByRole("button", { name: "Lưu và gửi duyệt" }).click();
  await page.getByText("Đã gửi duyệt phát sinh").waitFor();
  check("kỹ sư lập và gửi duyệt phát sinh trên điện thoại", await until(async () => (await page.locator("[data-change]").count()) === before + 1));
  const mine = page.locator("[data-change]", { hasText: STAMP });
  await mine.getByText("Chờ duyệt", { exact: true }).waitFor();
  check("kỹ sư không có nút duyệt phát sinh của mình", (await mine.getByRole("button", { name: "Duyệt", exact: true }).count()) === 0);
  await fits(page, "phát sinh trên điện thoại");
  await shot(page, "01-ky-su-phat-sinh", true);
  await page.goto(tab(house, "ngan-sach"));
  await page.getByText("Không xem được ngân sách", { exact: true }).waitFor();
  check("kỹ sư không xem được ngân sách", true);
  await context.close();
}

async function managerControls(browser, house) {
  const { context, page } = await as(browser, "manager");
  await page.goto(tab(house, "ngan-sach"));
  await page.locator("[data-budget]").waitFor();
  const before = await call(page, `${API}.control.budget_overview`, { project: house }, false);
  check("ngân sách: có BAC, CPI, SPI", (await page.locator("[data-evm]").count()) === 8);
  check("ngân sách theo khoản mục", (await page.locator("[data-category-row]").count()) >= 4);
  await shot(page, "02-ngan-sach", true);

  await page.goto(tab(house, "rui-ro"));
  await page.locator("[data-control]").waitFor();
  const risks = await page.locator("[data-risk]").count();
  check("sổ rủi ro của dữ liệu mẫu", risks >= 3, String(risks));
  check("vấn đề quá hạn được đánh dấu", (await page.locator("[data-issue] [data-overdue]").count()) >= 1);
  await page.getByRole("button", { name: "Ghi rủi ro" }).click();
  const drawer = page.getByRole("dialog", { name: "Ghi rủi ro" });
  await drawer.getByLabel("Rủi ro", { exact: true }).fill(`Nhà bên cạnh khiếu nại tiếng ồn ${STAMP}`);
  await drawer.getByLabel("Khả năng (1–5)").selectOption("4");
  await drawer.getByLabel("Ảnh hưởng (1–5)").selectOption("4");
  check("điểm rủi ro tính ngay khi chọn", (await drawer.getByText("Điểm 16").count()) === 1);
  await drawer.getByRole("button", { name: "Lưu" }).click();
  await page.getByText("Đã ghi rủi ro").waitFor();
  const row = page.locator("[data-risk]", { hasText: STAMP });
  check("rủi ro mới mức cao", await until(async () => (await row.getByText("Cao · 16").count()) === 1));
  await row.getByRole("button", { name: "Đã xảy ra" }).click();
  await page.getByRole("dialog", { name: "Rủi ro đã xảy ra" }).getByRole("button", { name: "Chuyển thành vấn đề" }).click();
  await page.getByText("Đã chuyển rủi ro thành vấn đề cần xử lý").waitFor();
  check("rủi ro đã xảy ra thành vấn đề cần xử lý", await until(async () => (await page.locator("[data-issue]", { hasText: STAMP }).count()) === 1));
  await shot(page, "03-rui-ro-van-de", true);

  await page.goto(tab(house, "phat-sinh"));
  await page.locator("[data-changes]").waitFor();
  const card = page.locator("[data-change]", { hasText: STAMP });
  await card.getByRole("button", { name: "Duyệt", exact: true }).click();
  await page.getByRole("dialog", { name: "Duyệt phát sinh" }).getByRole("button", { name: "Duyệt", exact: true }).click();
  await page.getByText("Đã duyệt, cộng vào ngân sách").waitFor();
  const after = await call(page, `${API}.control.budget_overview`, { project: house }, false);
  check("phát sinh được duyệt cộng vào ngân sách đang dùng", Math.round(after.evm.bac - before.evm.bac) === 3500000,
    `${before?.evm.bac} → ${after.evm.bac}`);
  await shot(page, "04-duyet-phat-sinh", true);
  await context.close();
}

async function managerReports(browser) {
  const { context, page } = await as(browser, "manager");
  await page.goto(`${BASE}/pm/bao-cao`);
  await page.locator("[data-report-card]").first().waitFor();
  check("danh mục báo cáo có lịch gửi của tôi", (await page.locator("[data-scheduled]").count()) >= 1);
  await shot(page, "05-bao-cao", true);
  const started = Date.now();
  await page.goto(`${BASE}/pm/bao-cao/ngan-sach-evm`);
  await page.locator("[data-report-row]").first().waitFor();
  check("báo cáo EVM mở dưới 3 giây", Date.now() - started < 3000, `${Date.now() - started} ms`);
  check("báo cáo EVM: hai dự án mẫu", (await page.locator("[data-report-row]").count()) === 2);
  const xlsx = await context.request.get(await page.locator("[data-export=xlsx]").getAttribute("href").then((h) => `${BASE}${h}`));
  check("xuất Excel", xlsx.ok() && (await xlsx.body()).subarray(0, 2).toString() === "PK", String(xlsx.status()));
  const pdf = await context.request.get(await page.locator("[data-export=pdf]").getAttribute("href").then((h) => `${BASE}${h}`));
  check("xuất PDF", pdf.ok() && (await pdf.body()).subarray(0, 4).toString() === "%PDF", String(pdf.status()));
  await shot(page, "06-bao-cao-evm", true);
  await page.goto(`${BASE}/pm/bao-cao/tien-do-du-an`);
  await page.locator("[data-report-row]").first().waitFor();
  await page.getByRole("button", { name: "Gửi theo lịch" }).click();
  await page.locator("[data-schedule-row]").first().waitFor();
  await page.locator("[data-schedule-row]").first().getByRole("button", { name: "Gửi thử ngay" }).click();
  await page.getByText(/^Đã gửi cho 2 người/).waitFor();
  check("gửi thử báo cáo theo lịch: hai người nhận", true);
  await shot(page, "07-gui-theo-lich");
  await context.close();
}

async function msProjectAndDossier(browser, house) {
  const admin = await as(browser, "admin");
  await admin.page.goto(`${BASE}/pm/du-an`);
  await admin.page.getByRole("heading", { name: "Dự án", exact: true }).waitFor();
  const scratch = (await call(admin.page, `${API}.projects.create`, { values: { project_name: `E2E MS Project ${STAMP}`,
    pm_code: `E2E-MSP-${STAMP}`, pm_state: "Đang thực hiện" } })).name;
  await call(admin.page, `${API}.projects.add_member`, { project: scratch, user: PEOPLE.manager, project_role: "Quản lý dự án" });
  await admin.context.close();

  const { context, page } = await as(browser, "manager");
  await page.goto(tab(house, "cong-viec"));
  await page.locator("[data-msproject-export]").waitFor();
  const xml = await context.request.get(`${BASE}${await page.locator("[data-msproject-export]").getAttribute("href")}`);
  const body = await xml.text();
  check("xuất MS Project XML", xml.ok() && body.includes("<Project") && body.includes("<PredecessorLink>"), String(xml.status()));
  const file = join(OUT, "ke-hoach.xml");
  writeFileSync(file, body);
  await page.goto(tab(scratch, "cong-viec"));
  await page.getByRole("button", { name: "Nhập MS Project" }).click();
  const drawer = page.getByRole("dialog", { name: "Nhập kế hoạch từ MS Project" });
  await drawer.locator("input[type=file]").setInputFiles(file);
  await drawer.locator("[data-import-summary]").waitFor();
  const summary = await drawer.locator("[data-import-summary]").innerText();
  check("xem trước tệp MS Project: không có lỗi", summary.includes("không có lỗi") && /\d+ phụ thuộc/.test(summary), summary);
  await shot(page, "08-nhap-ms-project");
  await drawer.getByRole("button", { name: /^Nhập \d+ công việc/ }).click();
  await page.getByText(/^Đã nhập \d+ công việc, \d+ phụ thuộc/).waitFor();
  const imported = await call(page, `${API}.schedule.gantt`, { project: scratch }, false);
  check("nhập MS Project: có công việc và phụ thuộc", imported.rows.length > 10 && imported.links.length > 5,
    `${imported.rows.length} việc, ${imported.links.length} phụ thuộc`);

  await page.goto(tab(scratch, "tong-quan"));
  await page.locator("[data-closing]").waitFor();
  await page.getByRole("button", { name: "Xuất hồ sơ dự án (ZIP)" }).click();
  await page.getByText(/^Đang lập hồ sơ dự án/).waitFor();
  const ready = await until(async () => (await call(page, `${API}.control.closing_check`, { project: scratch }, false)).dossiers.length > 0, 90000, 1500);
  check("hồ sơ dự án được lập ở hàng đợi", ready);
  if (ready) {
    const [dossier] = (await call(page, `${API}.control.closing_check`, { project: scratch }, false)).dossiers;
    const zip = await context.request.get(`${BASE}${dossier.file_url}`);
    check("tải hồ sơ ZIP", zip.ok() && (await zip.body()).subarray(0, 2).toString() === "PK", String(zip.status()));
  }
  await page.getByRole("button", { name: "Đóng dự án" }).click();
  const dialog = page.getByRole("dialog", { name: "Đóng dự án" });
  await dialog.getByRole("textbox").fill("Kiểm thử đóng dự án");
  await dialog.getByRole("button", { name: "Đóng dự án" }).click();
  await page.getByText("Đã đóng dự án").waitFor();
  check("đóng dự án", (await call(page, `${API}.control.closing_check`, { project: scratch }, false)).state === "Đóng");
  await page.getByRole("button", { name: "Mở lại dự án" }).click();
  const again = page.getByRole("dialog", { name: "Mở lại dự án" });
  await again.getByRole("textbox").fill("Kiểm thử mở lại");
  await again.getByRole("button", { name: "Mở lại" }).click();
  await page.getByText("Đã mở lại dự án").waitFor();
  check("mở lại dự án", (await call(page, `${API}.control.closing_check`, { project: scratch }, false)).state === "Đang thực hiện");
  await shot(page, "09-ket-thuc-du-an", true);
  await call(page, `${API}.control.close_project`, { project: scratch, note: "Dự án tạm của kịch bản kiểm thử" });  // out of the live lists
  await context.close();
}

async function main() {
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
  try {
    const admin = await as(browser, "admin");
    await admin.page.goto(`${BASE}/pm/du-an`);
    await admin.page.getByRole("heading", { name: "Dự án", exact: true }).waitFor();
    const house = (await call(admin.page, `${API}.projects.list_projects`, { search: "DEMO-NP01" }, false)).rows[0]?.name;
    check("có dữ liệu mẫu nhà phố", Boolean(house), "chạy demo của lõi trước");
    await admin.context.close();
    await engineerRequests(browser, house);
    await managerControls(browser, house);
    await managerReports(browser);
    await msProjectAndDossier(browser, house);
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
