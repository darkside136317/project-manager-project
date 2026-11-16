// M9 end to end on the demos (core DEMO-NP01 and construction DEMO-XD01; run both demos first), in a real browser.
//
// The manager of both projects opens the workload: the crew leader working on both is overloaded, the crane is booked
// by both projects on the same days (conflicts); a week of the crew leader lists the tasks of both projects; the
// manager may not record leave, the administrator does and the leader's capacity drops. On a phone, the engineer sees
// only themselves (workload and performance), the crew leader their crew's productivity; the portfolio shows the v2
// columns (on time, overloaded members, trend, the cost against the work done for the manager).
//
//   cd scripts/e2e/ui && npm ci && node people_flow.mjs [base_url]
//
// Same conventions as pilot_flow.mjs (reads docker/.env, never prints the password, demo people reached through the
// administrator's "impersonate", pictures in out/). The leave it records is removed at the end.
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "people");
const env = Object.fromEntries(readFileSync(join(HERE, "../../..", process.env.PM_ENV_FILE || "docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const PEOPLE_API = "project_manager.project_manager.api.people";
const PEOPLE = { engineer: "demo.kysu1@pm.localhost", manager: "demo.quanly@pm.localhost", lead: "demo.totruong@pm.localhost" };
const CRANE = "Cần trục bánh hơi 16 tấn";

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

async function until(test, timeout = 15000, step = 300) {
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
      { form: { user: PEOPLE[who], reason: "Kiểm thử kịch bản hiệu suất M9" } });
    check(`vào vai ${who}`, switched.ok(), String(switched.status()));
  }
  const page = await context.newPage();
  watch(page);
  return { context, page };
}

const mondayOf = (date = new Date()) => {
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  day.setDate(day.getDate() - ((day.getDay() + 6) % 7));
  const pad = (n) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
};

async function managerWorkload(browser, projects) {
  const { context, page } = await as(browser, "manager");
  const started = Date.now();
  await page.goto(`${BASE}/pm/khoi-luong-cong-viec`);
  await page.locator("[data-workload-row]").first().waitFor();
  check("trang khối lượng công việc mở dưới 3 giây", Date.now() - started < 3000, `${Date.now() - started} ms`);
  const view = await call(page, `${PEOPLE_API}.workload_overview`, { start: mondayOf(), weeks: 6 }, false);
  const lead = view.rows.find((r) => r.user === PEOPLE.lead);
  check("quản lý thấy tổ trưởng làm ở hai dự án", Boolean(lead));
  const heavy = lead?.weeks.find((w) => w.level === "Quá tải");
  check("tổ trưởng quá tải ít nhất một tuần", Boolean(heavy), JSON.stringify(lead?.weeks.map((w) => w.utilization)));
  check("tuần quá tải có việc của cả hai dự án", heavy && projects.every((p) => p in heavy.projects), JSON.stringify(heavy?.projects));
  const crane = view.conflicts.find((c) => c.kind === "Máy" && c.subject === CRANE);
  check("cần trục được hai dự án đặt trùng ngày: xung đột", Boolean(crane) && projects.every((p) => p in crane.projects),
    JSON.stringify(view.conflicts.map((c) => [c.kind, c.subject])));
  check("xung đột về người: tổ trưởng", view.conflicts.some((c) => c.kind === "Người" && c.user === PEOPLE.lead));
  const shown = await page.locator("[data-conflict]").count();
  check("trang hiện các xung đột", shown === Math.min(10, view.conflicts.length), `${shown} vs ${view.conflicts.length}`);
  check("quản lý dự án không ghi được kỳ nghỉ", !view.can.capacity);
  await shot(page, "01-khoi-luong-quan-ly", true);
  const row = page.locator("[data-workload-row]", { hasText: "Võ Tổ Trưởng" });
  const index = lead.weeks.indexOf(heavy);
  await row.locator("[data-workload-cell]").nth(index).click();
  const drawer = page.locator("[data-workload-drawer]");
  await drawer.waitFor();
  await until(async () => (await drawer.locator("a").count()) > 0);
  const text = await drawer.innerText();
  check("tuần của tổ trưởng liệt kê việc của cả hai dự án", text.includes("Nhà xưởng") && text.includes("Nhà phố"), text.slice(0, 300));
  check("ngăn kỳ nghỉ không hiện cho quản lý", (await page.locator("[data-capacity-form]").count()) === 0);
  await shot(page, "02-tuan-cua-to-truong");
  await context.close();
  const engineerWeeks = view.rows.find((r) => r.user === PEOPLE.engineer)?.weeks.map((w) => w.utilization);
  return { heavy, engineerWeeks };
}

async function adminLeave(browser, heavy) {
  const { context, page } = await as(browser, "admin");
  await page.goto(`${BASE}/pm/khoi-luong-cong-viec`);
  await page.locator("[data-workload-row]").first().waitFor();
  const row = page.locator("[data-workload-row]", { hasText: "Võ Tổ Trưởng" });
  const before = (await call(page, `${PEOPLE_API}.workload_cell`, { user: PEOPLE.lead, week: heavy.week }, false)).capacity;
  const view = await call(page, `${PEOPLE_API}.workload_overview`, { start: mondayOf(), weeks: 6 }, false);
  const index = view.rows.find((r) => r.user === PEOPLE.lead).weeks.findIndex((w) => w.week === heavy.week);
  await row.locator("[data-workload-cell]").nth(index).click();
  const form = page.locator("[data-capacity-form]");
  await form.waitFor();
  await form.getByLabel("Từ ngày").fill(heavy.week);
  await form.getByLabel("Đến ngày").fill(heavy.week);
  await form.getByLabel("Ghi chú").fill("Kiểm thử M9");
  await form.getByRole("button", { name: "Ghi kỳ năng lực" }).click();
  await page.getByText("Đã ghi kỳ năng lực").waitFor();
  const cell = await call(page, `${PEOPLE_API}.workload_cell`, { user: PEOPLE.lead, week: heavy.week }, false);
  check("ghi nghỉ phép thứ Hai: năng lực của tuần giảm một ngày", Math.abs(before - cell.capacity - 1) < 1e-6, `${before} → ${cell.capacity}`);
  await shot(page, "03-ghi-nghi-phep");
  for (const period of cell.periods.filter((p) => p.note === "Kiểm thử M9")) await call(page, `${PEOPLE_API}.delete_capacity`, { name: period.name });
  const back = await call(page, `${PEOPLE_API}.workload_cell`, { user: PEOPLE.lead, week: heavy.week }, false);
  check("xóa kỳ nghỉ: năng lực trở lại", Math.abs(back.capacity - before) < 1e-6, `${back.capacity}`);
  await context.close();
}

async function engineerOnPhone(browser, seenByManager) {
  const { context, page } = await as(browser, "engineer", true);
  await page.goto(`${BASE}/pm/khoi-luong-cong-viec`);
  await page.locator("[data-workload-row]").first().waitFor();
  check("kỹ sư chỉ thấy chính mình (khối lượng)", (await page.locator("[data-workload-row]").count()) === 1);
  const own = (await call(page, `${PEOPLE_API}.workload_overview`, { start: mondayOf(), weeks: 6 }, false)).rows[0];
  check("khối lượng của kỹ sư như quản lý thấy (việc có người khác thực hiện không dồn cho kỹ sư)",
    JSON.stringify(own.weeks.map((w) => w.utilization)) === JSON.stringify(seenByManager),
    `${JSON.stringify(own.weeks.map((w) => w.utilization))} vs ${JSON.stringify(seenByManager)}`);
  await fits(page, "khối lượng công việc trên điện thoại");
  await shot(page, "04-khoi-luong-dien-thoai", true);
  await page.goto(`${BASE}/pm/hieu-suat`);
  await page.getByRole("heading", { name: "Hiệu suất" }).waitFor();
  await until(async () => (await page.locator("[data-performance-row]").count()) > 0);
  const view = await call(page, `${PEOPLE_API}.performance_overview`, { period: "4w" }, false);
  check("kỹ sư chỉ thấy hiệu suất của chính mình", view.people.length === 1 && view.people[0].user === PEOPLE.engineer,
    JSON.stringify(view.people.map((p) => p.user)));
  const refused = await context.request.get(`${BASE}/api/method/${PEOPLE_API}.performance_person?user=${encodeURIComponent(PEOPLE.manager)}`);
  check("kỹ sư không xem được hiệu suất người khác", refused.status() === 403, String(refused.status()));
  await fits(page, "hiệu suất trên điện thoại");
  await shot(page, "05-hieu-suat-dien-thoai", true);
  await context.close();
}

async function leadCrew(browser) {
  const { context, page } = await as(browser, "lead", true);
  await page.goto(`${BASE}/pm/hieu-suat`);
  await page.getByRole("heading", { name: "Hiệu suất" }).waitFor();
  const view = await call(page, `${PEOPLE_API}.performance_overview`, { period: "4w" }, false);
  check("tổ trưởng thấy năng suất tổ mình", view.crews.length > 0 && view.crews.every((c) => c.team_name.includes("Tổ nề")),
    JSON.stringify(view.crews.map((c) => c.team_name)));
  check("năng suất = khối lượng / công", view.crews.every((c) => !c.man_days || Math.abs(c.per_man_day - c.qty / c.man_days) < 0.01));
  await until(async () => (await page.locator("[data-crew-row]").count()) > 0);
  check("bảng năng suất tổ đội hiện trên điện thoại", (await page.locator("[data-crew-row]").count()) === view.crews.length);
  await fits(page, "năng suất tổ đội trên điện thoại");
  await shot(page, "06-nang-suat-to-doi", true);
  await context.close();
}

async function portfolio(browser, factory) {
  const { context, page } = await as(browser, "manager");
  const started = Date.now();
  await page.goto(`${BASE}/pm/danh-muc-du-an`);
  await page.locator("[data-portfolio-row]").first().waitFor();
  check("danh mục dự án mở dưới 2 giây", Date.now() - started < 2000, `${Date.now() - started} ms`);
  const view = await call(page, "project_manager.project_manager.api.alerts.portfolio", {}, false);
  const row = view.rows.find((r) => r.name === factory);
  check("danh mục v2: có người quá tải ở nhà xưởng", row?.overloaded > 0, JSON.stringify(row?.overloaded));
  check("danh mục v2: cột chi phí của lớp thi công (quản lý xem được)", Boolean(row?.extra?.cost_ratio), JSON.stringify(row?.extra));
  check("danh mục v2: có xu hướng tiến độ", Array.isArray(row?.trend));
  check("bảng hiện cột của lớp thi công", (await page.locator("[data-extra=cost_ratio]").count()) > 0);
  await shot(page, "07-danh-muc-v2", true);
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(factory)}/may`);
  await page.locator("[data-bookings]").waitFor();
  const clash = page.locator("[data-booking]", { hasText: CRANE }).locator("[data-booking-clash]");
  check("tab Máy: lượt đặt cần trục báo trùng lịch", (await clash.count()) === 1);
  await shot(page, "08-dat-may", true);
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
    const find = async (code) => (await call(admin.page, "project_manager.project_manager.api.projects.list_projects", { search: code }, false)).rows[0]?.name;
    const factory = await find("DEMO-XD01");
    const house = await find("DEMO-NP01");
    check("có dữ liệu mẫu của lõi và lớp thi công", Boolean(factory && house), "chạy hai demo trước");
    await admin.context.close();
    const { heavy, engineerWeeks } = await managerWorkload(browser, [factory, house]);
    if (heavy) await adminLeave(browser, heavy);
    await engineerOnPhone(browser, engineerWeeks);
    await leadCrew(browser);
    await portfolio(browser, factory);
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
