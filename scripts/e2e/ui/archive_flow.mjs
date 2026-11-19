// M12 end to end, the project archive (pm_archive) on the demo data (bench execute pm_archive.pm_archive.setup.demo.up,
// after the core's and the construction layer's demos), in a real browser.
//
// On a computer:
// * the manager of the town house updates its files, describes an item, adds a scan and places the paper in a box;
// * the company archivist sees every project's files in /pm/luu-tru (not a member of any), files a waiting file of the
//   closed project DEMO-LT01, builds the archive package of its filed contract file and downloads it, downloads the
//   catalogue as Excel, runs the integrity check.
// On a phone: the site commander sees the factory's files without horizontal scrolling; an engineer is told he may not
// see the archive.
//
//   cd scripts/e2e/ui && npm ci && node archive_flow.mjs [base_url]
//
// Same conventions as the other flows (reads docker/.env or PM_ENV_FILE, never prints the password, pictures in out/).
// The demo users are reached by the administrator's "impersonate". It changes the demo: run
// `bench execute pm_archive.pm_archive.setup.demo.down` then `.up` to play it again.
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "archive");
const env = Object.fromEntries(readFileSync(join(HERE, "../../..", process.env.PM_ENV_FILE || "docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const A = "pm_archive.pm_archive.api.archive";
const MANAGER = "demo.quanly@pm.localhost";
const ARCHIVIST = "demo.luutru@pm.localhost";
const COMMANDER = "demo.chihuy@pm.localhost";
const ENGINEER = "demo.kysu1@pm.localhost";

let failures = 0;
const problems = [];

function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : ` — ${detail}`}`);
  if (!ok) failures += 1;
}

const shot = (page, name, fullPage = false) => page.screenshot({ path: join(OUT, `${name}.png`), fullPage });

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
    if (response.status() < 400 || response.status() === 417) return;
    if (expected.some((part) => response.url().includes(part))) return;
    problems.push(`${response.status()} ${response.url()}`);
  });
}

async function as(browser, user, viewport = { width: 1366, height: 860 }) {
  const phone = viewport.width < 768;
  const context = await browser.newContext({ viewport, locale: "vi-VN", ...(phone ? { isMobile: true, hasTouch: true } : {}) });
  const login = await context.request.post(`${BASE}/api/method/login`, { form: { usr: "Administrator", pwd: env.ADMIN_PASSWORD || "" } });
  check(`đăng nhập quản trị (${user})`, login.ok(), String(login.status()));
  const switched = await context.request.post(`${BASE}/api/method/frappe.core.doctype.user.user.impersonate`,
    { form: { user, reason: "Kiểm thử kịch bản lưu trữ M12" } });
  check(`vào vai ${user}`, switched.ok(), String(switched.status()));
  return context;
}

async function api(context, method, args = {}) {
  const response = await context.request.get(`${BASE}/api/method/${A}.${method}`, { params: args });
  return (await response.json()).message;
}

async function waitFor(fn, seconds = 90) {
  for (let i = 0; i < seconds; i += 2) {
    const value = await fn();
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  return null;
}

async function projectOf(context, code) {
  const response = await context.request.get(`${BASE}/api/method/project_manager.project_manager.api.projects.list_projects`,
    { params: { search: code } });
  const rows = (await response.json()).message?.rows || [];
  return rows.find((row) => row.pm_code === code)?.name;
}

async function manager(browser) {
  const context = await as(browser, MANAGER);
  const page = await context.newPage();
  watch(page);
  const project = await projectOf(context, "DEMO-NP01");
  check("có dự án mẫu nhà phố", Boolean(project), "DEMO-NP01");
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/ho-so-luu-tru`);
  await page.locator("[data-archive-tab]").waitFor();
  check("tab hồ sơ lưu trữ: có hồ sơ", (await page.locator("[data-archive-file]").count()) > 0);
  check("tab hồ sơ lưu trữ: báo danh mục còn thiếu", await page.locator("[data-missing]").isVisible());
  await page.locator("[data-compile]").click();
  await page.getByText(/tài liệu vào hồ sơ|Không có tài liệu mới/).first().waitFor();
  check("cập nhật hồ sơ", true);
  await shot(page, "01-tab-ho-so-luu-tru", true);

  await page.locator("[data-archive-file] a").first().click();
  await page.locator("[data-archive-file-page]").waitFor();
  await page.locator("[data-item-edit]").first().click();
  await page.locator("[data-item-form] input").nth(1).fill("12/2026/HĐ");
  await page.locator("[data-item-form] button[type=submit]").click();
  await page.getByText("12/2026/HĐ").first().waitFor();
  check("sửa số, ký hiệu của tài liệu", true);
  await page.locator("[data-scan-file]").setInputFiles({ name: "bien-ban-ban-giao-mat-bang.pdf", mimeType: "application/pdf",
                                                         buffer: Buffer.from("%PDF-1.4\n% bản scan thử\n") });
  await page.locator("[data-scan] input").nth(1).fill("Biên bản bàn giao mặt bằng (bản ký tay)");
  await page.locator("[data-scan] button[type=submit]").click();
  await page.getByText("Biên bản bàn giao mặt bằng (bản ký tay)").first().waitFor();
  check("thêm bản scan vào hồ sơ", true);
  await page.locator("[data-paper-storage]").selectOption({ label: "Kho A › Giá 1 › Hộp 2" });
  await page.locator("[data-paper-box]").fill("02");
  await page.locator("[data-paper] button[type=submit]").click();
  await page.getByText("Đã lưu chỗ để bản giấy").waitFor();
  check("ghi chỗ để bản giấy", true);
  check("quản lý dự án không có nút nộp lưu", (await page.locator("[data-file-it]").count()) === 0);
  await shot(page, "02-trang-ho-so", true);
  await context.close();
}

async function archivist(browser) {
  const context = await as(browser, ARCHIVIST);
  const page = await context.newPage();
  watch(page);
  await page.goto(`${BASE}/pm/luu-tru`);
  await page.locator("[data-register-row]").first().waitFor();
  const text = await page.locator("main").innerText();
  check("lưu trữ: thấy hồ sơ của các dự án (không là thành viên)", text.includes("DEMO-LT01") && text.includes("DEMO-XD01"), text.slice(0, 300));
  check("lưu trữ: số hồ sơ chờ nộp lưu", await page.locator("[data-waiting]").isVisible());
  check("thanh bên có mục Lưu trữ hồ sơ", await page.getByRole("link", { name: /Lưu trữ hồ sơ/ }).first().isVisible());
  await shot(page, "03-luu-tru", true);

  await page.locator("[data-waiting]").click();
  await page.waitForTimeout(500);
  const waiting = page.locator("[data-register-row]", { hasText: "DEMO-LT01" }).first();
  const number = (await waiting.locator("a").first().innerText()).trim();
  await waiting.locator("a").first().click();
  await page.locator("[data-file-it]").click();
  const filed = await waitFor(async () => {
    await page.reload();
    await page.locator("[data-file-status]").waitFor();
    return (await page.locator("[data-file-status]").innerText()).includes("Đã nộp lưu");
  });
  check(`nộp lưu hồ sơ ${number}`, Boolean(filed));
  check("hồ sơ đã nộp lưu có SHA-256", (await page.locator("[data-manifest]").innerText()).length === 64);
  check("hồ sơ đã nộp lưu không còn sửa được", (await page.locator("[data-item-edit]").count()) === 0);
  await shot(page, "04-da-nop-luu", true);

  await page.locator("[data-package]").click();
  const ready = await waitFor(async () => {
    await page.reload();
    await page.locator("[data-archive-file-page]").waitFor();
    return page.locator("[data-package-download]").count();
  });
  check("lập gói nộp lưu", Boolean(ready));
  const name = page.url().split("/").pop();
  const pack = await context.request.get(`${BASE}/api/method/${A}.download_package`, { params: { file: decodeURIComponent(name) } });
  const body = await pack.body();
  check("tải gói nộp lưu (ZIP)", pack.ok() && body.subarray(0, 2).toString() === "PK", `${pack.status()} ${body.length}`);
  const excel = await context.request.get(`${BASE}/api/method/project_manager.project_manager.api.reports.download_report`,
    { params: { slug: "muc-luc-van-ban", filters: JSON.stringify({ archive_file: decodeURIComponent(name) }), format: "xlsx" } });
  check("mục lục văn bản ra Excel", excel.ok() && (await excel.body()).subarray(0, 2).toString() === "PK", String(excel.status()));

  await page.goto(`${BASE}/pm/luu-tru`);
  await page.locator("[data-check]").click();
  const checked = await waitFor(async () => {
    const result = await api(context, "listing", { filters: JSON.stringify({}) });
    return result?.last_check && result.last_check.status !== "Đang chạy" ? result.last_check : null;
  });
  check("kiểm tra toàn vẹn: không lỗi", checked && checked.status === "Hoàn thành" && checked.checked > 0, JSON.stringify(checked));
  await context.close();
}

async function phone(browser) {
  const context = await as(browser, COMMANDER, { width: 390, height: 844 });
  const page = await context.newPage();
  watch(page);
  const project = await projectOf(context, "DEMO-XD01");
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/ho-so-luu-tru`);
  await page.locator("[data-archive-tab]").waitFor();
  check("điện thoại, chỉ huy trưởng: thấy hồ sơ của nhà xưởng", (await page.locator("[data-archive-file]").count()) > 0);
  check("chỉ huy trưởng không cập nhật hồ sơ", (await page.locator("[data-compile]").count()) === 0);
  await fits(page, "tab hồ sơ trên điện thoại");
  await shot(page, "05-dien-thoai", true);
  await context.close();

  const other = await as(browser, ENGINEER, { width: 390, height: 844 });
  const denied = await other.newPage();
  watch(denied, [`${A}.overview`]);
  await denied.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/ho-so-luu-tru`);
  await denied.locator("[data-archive-error]").waitFor();
  check("kỹ sư được báo không xem được hồ sơ lưu trữ", (await denied.locator("[data-archive-error]").innerText()).includes("không"));
  await other.close();
}

async function main() {
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
  try {
    await manager(browser);
    await archivist(browser);
    await phone(browser);
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
