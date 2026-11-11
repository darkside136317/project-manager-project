// M8 end to end on the factory demo (DEMO-XD01; run the core and construction demos first), in a real browser.
//
// On a phone, as the engineer, without a connection: ask for cement for the columns; when the connection is back the
// request is sent. On a computer, as the store keeper: issue what was asked; the table "định mức so với thực tế" shows
// the columns' cement used against the norm of the work done, over the norm now. Also: a machine shift written on the
// phone, the site commander confirming a crew's day, the costs for the manager and not for the engineer.
//
//   cd scripts/e2e/ui && npm ci && node site_flow.mjs [base_url]
//
// Same conventions as pilot_flow.mjs (reads docker/.env, never prints the password, demo people reached through the
// administrator's "impersonate", pictures in out/). It changes the demo: rebuild it (construction demo down, up) to
// play it again.
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "site");
const env = Object.fromEntries(readFileSync(join(HERE, "../../../docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const SITE = "pm_construction.pm_construction.api.site";
const PEOPLE = { engineer: "demo.kysu1@pm.localhost", keeper: "demo.thukho@pm.localhost", commander: "demo.chihuy@pm.localhost",
  manager: "demo.quanly@pm.localhost" };
const COLUMNS = "Bê tông cột đá 1x2";
const CEMENT = "VT-XM40";
const ASKED = 600;

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
    const expected = response.status() === 403 && response.url().includes("cost_summary");  // the engineer is refused the costs
    if (response.status() >= 400 && response.status() !== 417 && !offlineNow && !expected) problems.push(`${response.status()} ${response.url()}`);
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

async function until(test, timeout = 20000, step = 400) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await test()) return true;
    await new Promise((resolve) => setTimeout(resolve, step));
  }
  return false;
}

async function as(browser, who, phone = false) {
  const context = await browser.newContext(phone
    ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "vi-VN" }
    : { viewport: { width: 1366, height: 860 }, locale: "vi-VN" });
  const login = await context.request.post(`${BASE}/api/method/login`, { form: { usr: "Administrator", pwd: env.ADMIN_PASSWORD || "" } });
  check(`đăng nhập (${who})`, login.ok(), String(login.status()));
  if (who !== "admin") {
    const switched = await context.request.post(`${BASE}/api/method/frappe.core.doctype.user.user.impersonate`,
      { form: { user: PEOPLE[who], reason: "Kiểm thử kịch bản vật tư M8" } });
    check(`vào vai ${who}`, switched.ok(), String(switched.status()));
  }
  const page = await context.newPage();
  watch(page);
  return { context, page };
}

async function columnsRow(page, project) {
  const view = await call(page, `${SITE}.materials_overview`, { project }, false);
  return view.rows.find((row) => row.task_label.includes(COLUMNS) && row.item === CEMENT);
}

async function engineerAsks(browser, project) {
  const { context, page } = await as(browser, "engineer", true);
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/vat-tu`);
  await page.locator("[data-materials]").waitFor();
  await page.evaluate(async () => navigator.serviceWorker.ready);
  await fits(page, "vật tư trên điện thoại");
  await shot(page, "01-vat-tu-dien-thoai", true);
  const before = await columnsRow(page, project);
  await page.getByRole("button", { name: "Đề xuất vật tư" }).click();
  const drawer = page.getByRole("dialog", { name: "Đề xuất vật tư" });
  await drawer.getByLabel("Vật tư").selectOption(CEMENT);
  const task = await drawer.getByLabel("Công tác").locator("option", { hasText: COLUMNS }).getAttribute("value");
  await drawer.getByLabel("Công tác").selectOption(task);
  await drawer.getByLabel(/Số lượng/).fill(String(ASKED));
  await drawer.getByLabel("Ghi chú").fill("Đổ cột trục 5–8");
  offlineNow = true;
  await context.setOffline(true);
  await drawer.getByRole("button", { name: "Gửi đề xuất" }).click();
  await page.getByText("Đề xuất đang chờ có mạng để gửi").waitFor();
  check("đề xuất viết khi mất mạng được giữ lại", true);
  await shot(page, "02-de-xuat-cho-mang");
  offlineNow = false;
  await context.setOffline(false);
  const sent = await until(async () => (await page.getByText("Đề xuất đang chờ có mạng để gửi").count()) === 0
    && (await page.getByText("Đang gửi đề xuất").count()) === 0, 25000);
  check("có mạng lại: đề xuất tự gửi", sent);
  const requests = (await call(page, `${SITE}.materials_overview`, { project }, false)).requests;
  const mine = requests.find((r) => r.open && r.lines.some((l) => l.item_code === CEMENT && l.pmc_task === task && l.left === ASKED));
  check("đề xuất đến kho, gắn đúng công tác", Boolean(mine), JSON.stringify(requests.map((r) => r.name)));
  await shot(page, "03-de-xuat-da-gui", true);

  // a machine shift from the phone
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/may`);
  await page.locator("[data-machines]").waitFor();
  const shiftsBefore = await page.locator("[data-shift]").count();
  await page.getByRole("button", { name: "Ghi ca máy" }).first().click();
  const shiftDrawer = page.getByRole("dialog", { name: "Ghi ca máy" });
  await shiftDrawer.getByLabel("Máy").selectOption("MT-01");
  await shiftDrawer.getByLabel("Công tác").selectOption(task);
  await shiftDrawer.getByLabel("Nhiên liệu (lít)").fill("0");
  await shiftDrawer.getByRole("button", { name: "Ghi ca máy" }).click();
  check("ghi ca máy trên điện thoại", await until(async () => (await page.locator("[data-shift]").count()) > shiftsBefore));
  await fits(page, "máy trên điện thoại");
  await shot(page, "04-ca-may", true);
  await context.close();
  return { task, request: mine?.name, before };
}

async function keeperIssues(browser, project, asked) {
  const { context, page } = await as(browser, "keeper");
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/vat-tu`);
  await page.locator("[data-materials]").waitFor();
  const card = page.locator("[data-request]", { hasText: asked.request });
  await card.getByRole("button", { name: "Cấp phát" }).click();
  const drawer = page.getByRole("dialog", { name: "Cấp phát" });
  check("phiếu cấp phát điền sẵn từ đề xuất", (await drawer.getByLabel(/Số lượng/).inputValue()) === String(ASKED));
  await shot(page, "05-cap-phat");
  await drawer.getByRole("button", { name: "Cấp phát" }).click();
  await page.getByText(/^Cấp phát: /).waitFor();
  const after = await columnsRow(page, project);
  check("cấp phát: đã cấp thêm đúng số lượng", after.issued === asked.before.issued + ASKED, `${asked.before.issued} → ${after.issued}`);
  const expectedNorm = Math.round(after.unit_qty * after.done_qty * 1000) / 1000;
  check("định mức của khối lượng đã làm = hao phí × khối lượng đã làm", Math.abs(after.norm_done - expectedNorm) < 0.01,
    `${after.norm_done} vs ${expectedNorm}`);
  check("đã dùng = đã cấp − trả lại; chênh lệch = đã dùng − định mức",
    Math.abs(after.used - (after.issued - after.returned)) < 1e-6 && Math.abs(after.gap - (after.used - after.norm_done)) < 1e-6,
    JSON.stringify(after));
  const beyondDone = after.used > after.norm_done * 1.05;
  const beyondPlan = after.used > after.planned * 1.05;
  check("vượt định mức: quá cả thiết kế, hoặc công tác xong mà quá khối lượng đã làm",
    after.over_norm === (beyondPlan || (after.finished && beyondDone)), JSON.stringify(after));
  check("chưa xong mà cấp quá khối lượng đã làm: cấp trước khối lượng", after.ahead === (beyondDone && !after.over_norm),
    JSON.stringify(after));
  const requests = (await call(page, `${SITE}.materials_overview`, { project }, false)).requests;
  check("đề xuất đã cấp xong", requests.find((r) => r.name === asked.request)?.status === "Issued");
  await page.reload();
  await page.locator("[data-materials]").waitFor();
  const work = page.locator("[data-work]", { hasText: COLUMNS });
  const text = await work.innerText();
  const shown = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 }).format(after.used);
  check("bảng định mức so với thực tế hiện đúng số đã dùng", text.includes(shown), text.slice(0, 400));
  check("nhãn của công tác cột khớp số liệu", text.includes("Vượt định mức") === after.over_norm
    && text.includes("Cấp trước khối lượng") === after.ahead, text.slice(0, 200));
  await work.scrollIntoViewIfNeeded();
  await shot(page, "06-dinh-muc-thuc-te", true);
  await context.close();
}

async function commanderConfirms(browser, project) {
  const { context, page } = await as(browser, "commander", true);
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/cham-cong`);
  await page.locator("[data-labour]").waitFor();
  const waiting = page.locator("aside li button", { hasText: "Đã nộp" }).first();
  await waiting.click();
  await page.getByRole("button", { name: "Xác nhận", exact: true }).click();
  await page.getByText("Đã xác nhận chấm công").waitFor();
  check("chỉ huy trưởng xác nhận chấm công trên điện thoại", true);
  await fits(page, "chấm công trên điện thoại");
  await shot(page, "07-cham-cong", true);
  await context.close();
}

async function costs(browser, project) {
  const boss = await as(browser, "manager");
  await boss.page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/chi-phi`);
  await boss.page.locator("[data-costs]").waitFor();
  const summary = await call(boss.page, `${SITE}.cost_summary`, { project }, false);
  const parts = summary.total.material + summary.total.machine + summary.total.labour;
  check("chi phí thực tế = vật tư + máy + nhân công", Math.abs(summary.total.actual - parts) < 1, JSON.stringify(summary.total));
  check("bảng chi phí có các hạng mục", (await boss.page.locator("[data-cost-row]").count()) > 3);
  await shot(boss.page, "08-chi-phi", true);
  await boss.context.close();
  const engineer = await as(browser, "engineer", true);
  await engineer.page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/chi-phi`);
  await engineer.page.getByText("không xem được chi phí").waitFor();
  check("kỹ sư không xem được chi phí", true);
  await engineer.context.close();
}

async function main() {
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
  try {
    const admin = await as(browser, "admin");
    await admin.page.goto(`${BASE}/pm/du-an`);
    await admin.page.getByRole("heading", { name: "Dự án", exact: true }).waitFor();
    const listed = await call(admin.page, "project_manager.project_manager.api.projects.list_projects", { search: "DEMO-XD01" }, false);
    const project = listed.rows[0]?.name;
    check("có dữ liệu mẫu nhà xưởng", Boolean(project), "chạy demo của lớp thi công trước");
    await admin.context.close();
    const asked = await engineerAsks(browser, project);
    await keeperIssues(browser, project, asked);
    await commanderConfirms(browser, project);
    await costs(browser, project);
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
