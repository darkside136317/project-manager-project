// M4 end to end, in a real browser: a project with dependencies; take a baseline; drag a critical task on the Gantt; the
// preview shows what follows; after confirming, the Gantt shows the gap to the baseline and the forecast has moved. Then
// the same screens on a phone, where the Gantt only reads.
//
//   cd scripts/e2e/ui && npm ci && node schedule_flow.mjs [base_url]
//
// Same conventions as forms_flow.mjs (reads docker/.env, never prints the password, pictures in out/). It creates a project
// named "Dự án thử lịch trình ...": run it on a scratch or development site. The exit code is the number of failed checks.
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";
import { ROW, ZOOMS, dayNumber, dayRange, isoOf, tasksFrom } from "../../../apps/project_manager/frontend/src/lib/gantt.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "schedule");
const env = Object.fromEntries(readFileSync(join(HERE, "../../..", process.env.PM_ENV_FILE || "docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const STAMP = Date.now().toString(36).toUpperCase();
const METHOD = "project_manager.project_manager.api";

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
  await page.waitForTimeout(150);
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  check(`${where}: không cuộn ngang`, scroll <= client, `${scroll} > ${client}`);
}

function watch(page) {
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error" && !/Failed to load resource/.test(message.text())) problems.push(`console: ${message.text()}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && response.status() !== 417) problems.push(`${response.status()} ${response.url()}`);
  });
}

/** A call to the app from inside the page, with its session and CSRF token. */
const call = (page, method, args = {}, post = true) => page.evaluate(async ({ url, args, post }) => {
  const options = { method: post ? "POST" : "GET", headers: { "X-Frappe-CSRF-Token": window.__PM_BOOT__.csrf_token, "Content-Type": "application/json", Accept: "application/json" } };
  if (post) options.body = JSON.stringify(args);
  const query = post ? "" : `?${new URLSearchParams(args)}`;
  const response = await fetch(url + query, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload._server_messages || payload.exception || response.status);
  return payload.message;
}, { url: `/api/method/${METHOD}.${method}`, args, post });

/** The next Monday at least a week away: all the dates of the plan are in the future, so nothing is late. */
function monday() {
  const today = dayNumber(new Date().toISOString());
  let day = today + 7;
  while ((new Date(day * 86400000).getUTCDay()) !== 1) day += 1;
  return day;
}

async function build(page) {
  const start = monday();
  const when = (offset, length = 1) => ({ start: isoOf(start + offset), end: isoOf(start + offset + length - 1) });
  const { name: project } = await call(page, "projects.create", { values: { project_name: `Dự án thử lịch trình ${STAMP}`, expected_start_date: isoOf(start), expected_end_date: isoOf(start + 60) } });
  const add = async (subject, extra) => (await call(page, "wbs.add", { project, subject, ...extra })).name;
  const phase1 = await add("Phần móng", { is_group: 1 });
  const phase2 = await add("Phần thân", { is_group: 1 });
  const tasks = {
    dig: await add("Đào móng", { parent: phase1, ...when(0, 3) }),
    pour: await add("Đổ móng", { parent: phase1, ...when(3, 3) }),
    frame: await add("Dựng khung", { parent: phase2, ...when(7, 3) }),
    wall: await add("Xây tường", { parent: phase2, ...when(7, 2) }),
    handover: await add("Bàn giao", { parent: phase2, ...when(10, 1) }),
  };
  const link = (predecessor, successor) => call(page, "schedule.add_dependency", { predecessor, successor });
  await link(tasks.dig, tasks.pour);
  await link(tasks.pour, tasks.frame);
  await link(tasks.frame, tasks.handover);
  await link(tasks.wall, tasks.handover);
  return { project, tasks };
}

async function openGantt(page, project, zoom = "Ngày") {
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/gantt`);
  await page.locator(".gantt-scroller[data-ready]").waitFor();
  if (zoom) {
    await page.getByRole("button", { name: zoom, exact: true }).click();
    await page.waitForTimeout(250);
  }
}

/** Scroll the chart so that this task's bar shows. */
async function reveal(page, project, subject) {
  const payload = await call(page, "schedule.gantt", { project }, false);
  const tasks = tasksFrom(payload);
  const { first } = dayRange(tasks, payload.today);
  const target = (tasks.find((row) => row.subject === subject).startDay - first) * ZOOMS.day.px - 80;
  await page.locator(".gantt-scroller").evaluate((element, left) => { element.scrollLeft = left; }, target);
  await page.waitForTimeout(150);
}

/** Where a task's bar is on the screen, from the same data and the same arithmetic the chart uses. */
async function barOf(page, project, subject) {
  const payload = await call(page, "schedule.gantt", { project }, false);
  const tasks = tasksFrom(payload);
  const task = tasks.find((row) => row.subject === subject);
  const { first } = dayRange(tasks, payload.today);
  const px = ZOOMS.day.px;
  const canvas = await page.locator(".gantt-canvas").boundingBox();
  const scrolled = await page.locator(".gantt-scroller").evaluate((element) => element.scrollLeft);
  const row = await page.locator(".gantt-row", { hasText: subject }).boundingBox();
  const left = canvas.x + (task.startDay - first) * px - scrolled;
  const right = canvas.x + (task.endDay + 1 - first) * px - scrolled;
  return { left, right, middle: (left + right) / 2, y: row.y + ROW / 2 - 1, task, payload };
}

async function dragBy(page, fromX, y, days) {
  await page.mouse.move(fromX, y);
  await page.mouse.down();
  await page.mouse.move(fromX + (days * ZOOMS.day.px) / 2, y, { steps: 4 });
  await page.mouse.move(fromX + days * ZOOMS.day.px, y, { steps: 4 });
  await page.mouse.up();
}

async function onComputer(page, project, tasks) {
  await openGantt(page, project);
  await shot(page, "01-gantt-truoc-khi-doi");
  let view = await call(page, "schedule.gantt", { project }, false);
  const before = view.summary;
  check("có đường găng", before.critical >= 3, JSON.stringify(before));
  check("chưa có baseline", !before.baseline);
  const critical = tasksFrom(view).find((row) => row.subject === "Đổ móng");
  check("việc trên chuỗi dài nhất là việc găng", critical.critical === 1, JSON.stringify(critical));
  check("việc ngắn song song có dự trữ", tasksFrom(view).find((row) => row.subject === "Xây tường").float > 0);

  // take the baseline on its screen
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/baseline`);
  await page.getByRole("button", { name: "Chụp baseline" }).click();
  await page.locator("#bl-title").fill("Kế hoạch được duyệt");
  await page.getByRole("button", { name: "Chụp", exact: true }).click();
  await page.getByText("Đã chụp baseline").waitFor();
  await page.getByRole("cell", { name: /Đổ móng/ }).waitFor();
  check("chụp baseline", true);

  // drag the critical task three days later
  await openGantt(page, project);
  await reveal(page, project, "Đào móng");
  const bar = await barOf(page, project, "Đổ móng");
  await dragBy(page, bar.middle, bar.y, 3);
  await page.getByRole("dialog", { name: /Dời lịch/ }).waitFor();
  const dialog = page.getByRole("dialog", { name: /Dời lịch/ });
  check("kéo thanh: xem trước các việc bị đẩy theo", await dialog.getByText("việc bị đẩy theo phụ thuộc").count() > 0);
  check("xem trước chưa đổi gì", (await call(page, "schedule.gantt", { project }, false)).summary.plan_end === before.plan_end);
  await shot(page, "02-xem-truoc-doi-lich");
  await dialog.getByRole("button", { name: "Dời lịch" }).click();
  await page.getByText(/Đã dời \d+ việc/).waitFor();
  await page.waitForTimeout(500);
  await shot(page, "03-gantt-sau-khi-doi");

  view = await call(page, "schedule.gantt", { project }, false);
  const after = view.summary;
  const moved = tasksFrom(view).find((row) => row.subject === "Đổ móng");
  const next = tasksFrom(view).find((row) => row.subject === "Dựng khung");
  check("việc găng đã dời, có chênh lệch với baseline", moved.endDay > moved.baseEndDay, JSON.stringify(moved));
  check("kéo cả thanh qua Chủ nhật vẫn giữ số ngày làm việc", moved.endDay - moved.startDay === 2, `${moved.start} → ${moved.end}`);
  check("việc sau bị đẩy theo", next.startDay > next.baseStartDay, JSON.stringify(next));
  check("ngày kết thúc kế hoạch đổi", after.plan_end > before.plan_end, `${before.plan_end} → ${after.plan_end}`);
  check("dự báo đổi theo", after.forecast_end > before.forecast_end && after.forecast_slip > 0, JSON.stringify(after));
  check("Gantt ghi rõ trễ", await page.getByText(/trễ \d+ ngày/).count() > 0);

  // cancelling a preview changes nothing
  await reveal(page, project, "Xây tường");
  const wall = await barOf(page, project, "Xây tường");
  await dragBy(page, wall.right - 2, wall.y, 2);
  await page.getByRole("dialog", { name: /Dời lịch/ }).waitFor();
  await page.getByRole("dialog", { name: /Dời lịch/ }).getByRole("button", { name: "Hủy" }).click();
  const unchanged = tasksFrom(await call(page, "schedule.gantt", { project }, false)).find((row) => row.subject === "Xây tường");
  check("hủy xem trước: không đổi gì", unchanged.endDay === wall.task.endDay, JSON.stringify(unchanged));

  // a dependency by dragging from the dot after a bar
  const links = view.links.length;
  await reveal(page, project, "Đào móng");
  const from = await barOf(page, project, "Đào móng");
  const to = await barOf(page, project, "Xây tường");
  await page.mouse.move(from.middle, from.y);
  await page.waitForTimeout(100);
  await page.mouse.move(from.right + 11, from.y);
  await page.mouse.down();
  await page.mouse.move(to.middle, to.y, { steps: 6 });
  await page.mouse.up();
  await page.getByText("Đã thêm phụ thuộc").waitFor();
  check("kéo từ chấm tròn để nối hai việc", (await call(page, "schedule.gantt", { project }, false)).links.length === links + 1);

  // a click opens the task, with where it stands
  await page.waitForTimeout(500);
  await reveal(page, project, "Dựng khung");
  const open = await barOf(page, project, "Dựng khung");
  await page.mouse.click(open.middle, open.y);
  const panel = page.getByRole("dialog", { name: "Chi tiết công việc" });
  await panel.getByText("Trên đường găng").waitFor();
  check("bấm vào thanh mở chi tiết công việc", await panel.getByText("Chờ các việc").count() > 0);
  await shot(page, "04-chi-tiet-cong-viec");
  await panel.getByRole("button", { name: "Đóng" }).click();

  // the other screens
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/baseline`);
  await page.getByText(/trễ \d+ ngày/).first().waitFor();
  check("bảng so với baseline, trễ nhất lên đầu", (await page.locator("tbody tr").first().textContent()).includes("trễ"));
  await shot(page, "05-so-voi-baseline");
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/tong-quan`);
  await page.getByText("Dự báo xong").first().waitFor();
  await shot(page, "06-tong-quan", true);
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/lich`);
  await page.getByRole("heading", { name: /^Tháng/ }).waitFor();
  await page.waitForTimeout(400);
  await shot(page, "07-lich-may-tinh");
  for (let step = 0; step < 2 && await page.getByText("Đổ móng").count() === 0; step += 1) {
    await page.getByRole("button", { name: "Tháng sau" }).click();
    await page.waitForTimeout(400);
  }
  check("lịch thi công có công việc", await page.getByText("Đổ móng").count() > 0);
  return tasks;
}

async function onPhone(page, project) {
  await openGantt(page, project, null);
  await fits(page, "Gantt");
  await shot(page, "08-gantt-dien-thoai");
  const before = await call(page, "schedule.gantt", { project }, false);
  const canvas = await page.locator(".gantt-canvas").boundingBox();
  const row = await page.locator(".gantt-row", { hasText: "Đổ móng" }).boundingBox().catch(() => null);
  if (row) {
    await page.mouse.move(canvas.x + canvas.width / 2, row.y + 10);
    await page.mouse.down();
    await page.mouse.move(canvas.x + canvas.width / 2 + 60, row.y + 10, { steps: 3 });
    await page.mouse.up();
  }
  check("trên điện thoại Gantt chỉ để xem", await page.getByRole("dialog", { name: /Dời lịch/ }).count() === 0);
  check("không đổi gì", JSON.stringify((await call(page, "schedule.gantt", { project }, false)).rows) === JSON.stringify(before.rows));
  for (const [tab, name] of [["lich", "lịch"], ["baseline", "baseline"], ["tong-quan", "tổng quan"], ["cong-viec", "công việc"]]) {
    await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/${tab}`);
    await page.waitForTimeout(900);
    await fits(page, name);
    await shot(page, `09-${tab}-dien-thoai`);
  }
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
    const { project, tasks } = await build(page);
    check("tạo dự án có phụ thuộc", Boolean(project));
    await onComputer(page, project, tasks);
    await page.close();
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "vi-VN",
      storageState: await desktop.storageState() });
    const small = await phone.newPage();
    watch(small);
    await onPhone(small, project);
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
