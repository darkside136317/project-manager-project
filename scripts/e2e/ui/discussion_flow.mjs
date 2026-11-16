// M5 end to end, in a real browser. On a phone: open a task, lose the connection, take a photo and write a comment,
// reload the app while still offline (it opens from the service worker, the comment still waits), get the connection
// back: the photo reaches the right task, once. A progress report written offline goes out the same way. On a
// computer: the project's discussion, search, the photo wall, and a document with two versions, approved.
//
//   cd scripts/e2e/ui && npm ci && node discussion_flow.mjs [base_url]
//
// Same conventions as forms_flow.mjs (reads docker/.env, never prints the password, pictures in out/). It creates a project
// named "Dự án thử trao đổi ...": run it on a scratch or development site. The exit code is the number of failed checks.
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out", "discussion");
const env = Object.fromEntries(readFileSync(join(HERE, "../../..", process.env.PM_ENV_FILE || "docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const STAMP = Date.now().toString(36).toUpperCase();
const WORD = `cotthep${STAMP.toLowerCase()}`;
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

let offlineNow = false;
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

async function build(page) {
  const { name: project } = await call(page, "projects.create", { values: { project_name: `Dự án thử trao đổi ${STAMP}` } });
  const add = async (subject) => (await call(page, "wbs.add", { project, subject })).name;
  return { project, formwork: await add("Cốp pha sàn tầng 3"), rebar: await add("Cốt thép sàn tầng 3") };
}

async function until(test, timeout = 15000, step = 400) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await test()) return true;
    await new Promise((resolve) => setTimeout(resolve, step));
  }
  return false;
}

/** The phone: the task, offline photo and comment, offline reload, back online. */
async function onPhone(context, page, project, task, photo) {
  offlineNow = false;
  await page.goto(`${BASE}/pm/cong-viec/${task}`);
  await page.getByRole("heading", { name: /Cốp pha sàn tầng 3/ }).waitFor();
  const controlled = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return Boolean(registration.active);
  });
  check("ứng dụng cài được: service worker đã chạy", controlled);
  await page.reload();  // this load goes through the worker, which keeps the page and the task for offline use
  await page.getByRole("heading", { name: /Cốp pha sàn tầng 3/ }).waitFor();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller));
  await page.waitForTimeout(800);
  await fits(page, "công việc trên điện thoại");

  offlineNow = true;
  await context.setOffline(true);
  await page.getByRole("status").filter({ hasText: "Mất mạng" }).waitFor({ timeout: 5000 }).catch(() => {});
  check("biết là mất mạng", await page.getByText("Mất mạng").first().isVisible());
  await page.locator('input[type="file"][capture]').setInputFiles({ name: "hien-truong.jpg", mimeType: "image/jpeg", buffer: photo });
  await page.getByRole("list", { name: "Ảnh sẽ gửi" }).getByRole("listitem").first().waitFor();
  const text = `Cốp pha trục 4 đã ghép xong, chờ nghiệm thu ${WORD}`;
  await page.getByLabel("Nội dung trao đổi").fill(text);
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  const waiting = page.getByRole("list", { name: "Đang chờ gửi" });
  await waiting.getByText("Chờ có mạng").waitFor();
  check("trao đổi viết khi mất mạng vẫn hiện ngay, ghi rõ chờ mạng", true);
  check("thanh trên báo 1 mục chờ gửi", await page.getByRole("link", { name: /1 mục đang chờ gửi/ }).isVisible());
  await shot(page, "01-offline-queued");

  await page.reload();  // still offline: the worker answers with the kept page, the queue lives in IndexedDB
  await page.getByRole("heading", { name: /Cốp pha sàn tầng 3/ }).waitFor({ timeout: 15000 });
  check("mở lại ứng dụng khi mất mạng vẫn được", true);
  await page.getByRole("list", { name: "Đang chờ gửi" }).getByText("Chờ có mạng").waitFor();
  check("mục chờ gửi vẫn còn sau khi mở lại", true);
  await shot(page, "02-offline-reloaded");

  // a progress report without a connection
  const slider = page.getByLabel("Phần trăm");
  if (await slider.count()) {
    await slider.fill("30");
    await page.getByLabel("Ghi chú").fill("Đã ghép 30% cốp pha");
    await page.getByRole("button", { name: "Gửi cập nhật" }).click();
    await page.getByText("Chưa có mạng: đã lưu báo cáo").waitFor();
    check("báo cáo tiến độ khi mất mạng được giữ lại", true);
  }

  offlineNow = false;
  await context.setOffline(false);
  const sent = await until(async () => (await page.getByRole("list", { name: "Đang chờ gửi" }).count()) === 0, 20000);
  check("có mạng lại: tự gửi, hết mục chờ", sent);
  const entry = page.locator("[data-entry]").filter({ hasText: WORD });
  await entry.first().waitFor({ timeout: 10000 });
  check("trao đổi lên đúng công việc, kèm 1 ảnh", (await entry.first().getByRole("button", { name: /Xem ảnh/ }).count()) === 1);
  await shot(page, "03-online-sent");

  const feed = await call(page, "activity.feed", { reference_doctype: "Task", reference_name: task, kind: "comment" }, false);
  const mine = feed.entries.filter((row) => row.content.includes(WORD));
  check("máy chủ có đúng 1 trao đổi và 1 ảnh (không trùng)", mine.length === 1 && mine[0].photos.length === 1,
    JSON.stringify(mine.map((row) => [row.name, row.photos.length])));
  const photoRow = mine[0]?.photos?.[0];
  check("ảnh đã thu nhỏ trước khi gửi (≤ 1600 px)", photoRow && Math.max(photoRow.width, photoRow.height) <= 1600, JSON.stringify(photoRow));
  const reported = await until(async () => (await call(page, "tasks.detail", { task }, false)).task.progress >= 30, 15000);
  check("báo cáo tiến độ viết khi mất mạng đã tới máy chủ", reported);

  await page.goto(`${BASE}/pm/hang-doi`);
  await page.getByRole("heading", { name: "Hàng đợi gửi" }).waitFor();
  check("hàng đợi trống", await page.getByText("Không có gì đang chờ").isVisible());
  await fits(page, "hàng đợi");
  await page.goto(`${BASE}/pm/du-an/${project}/trao-doi`);
  await page.locator("[data-entry]").first().waitFor();
  await fits(page, "trao đổi dự án trên điện thoại");
  await page.goto(`${BASE}/pm/du-an/${project}/tai-lieu`);
  await page.getByText(/Bản vẽ mặt bằng|Chưa có tài liệu/).first().waitFor();
  await fits(page, "tài liệu trên điện thoại");
  await shot(page, "04-phone-documents");
}

/** The computer: project discussion, search, photos, a document with versions. */
async function onComputer(page, project, task) {
  await page.goto(`${BASE}/pm/du-an/${project}/trao-doi`);
  await page.getByRole("heading", { name: "Trao đổi chung và theo công việc" }).waitFor();
  const note = `Họp giao ban 7h sáng mai tại công trường ${STAMP}`;
  await page.getByLabel("Nội dung trao đổi").fill(note);
  await page.getByRole("button", { name: "Gửi", exact: true }).click();
  await page.locator("[data-entry]").filter({ hasText: note }).waitFor();
  check("trao đổi chung của dự án", true);
  check("dòng thời gian dự án có trao đổi của công việc", await page.locator("[data-entry]").filter({ hasText: WORD }).count() === 1);

  const found = await until(async () => {
    await page.getByLabel("Tìm trong trao đổi và tài liệu").fill(WORD);
    await page.getByLabel("Tìm trong trao đổi và tài liệu").press("Enter");
    await page.waitForTimeout(600);
    return (await page.getByRole("region", { name: "Kết quả tìm kiếm" }).locator("mark").count()) > 0;
  }, 20000, 1500);
  check("tìm thấy trao đổi, chữ tìm được tô đậm", found);
  await shot(page, "05-search");
  await page.getByRole("button", { name: "Đóng", exact: true }).click();

  await page.getByRole("button", { name: /Ảnh hiện trường/ }).click();
  await page.getByRole("button", { name: "Xem ảnh 1" }).waitFor();
  await page.getByRole("button", { name: "Xem ảnh 1" }).click();
  await page.getByRole("dialog", { name: "Xem ảnh" }).waitFor();
  check("tường ảnh mở được ảnh lớn", true);
  await shot(page, "06-photo");
  await page.keyboard.press("Escape");

  await page.goto(`${BASE}/pm/du-an/${project}/tai-lieu`);
  await page.getByRole("button", { name: "Tải lên tài liệu" }).click();
  await page.getByLabel("Tệp (tối đa 100 MB)").setInputFiles({ name: "mat-bang-tang-3.pdf", mimeType: "application/pdf", buffer: Buffer.from(`%PDF-1.4\n% ${STAMP} v1\n`) });
  await page.getByLabel("Tên tài liệu").fill("Bản vẽ mặt bằng tầng 3");
  await page.getByRole("button", { name: "Tải lên", exact: true }).click();
  await page.getByRole("heading", { name: "Các bản" }).waitFor();
  await page.getByLabel("Tệp của bản mới").setInputFiles({ name: "mat-bang-tang-3-sua.pdf", mimeType: "application/pdf", buffer: Buffer.from(`%PDF-1.4\n% ${STAMP} v2\n`) });
  await page.getByLabel("Ghi chú bản mới").fill("Sửa vị trí lỗ mở kỹ thuật");
  await page.getByRole("button", { name: "Tải lên bản mới" }).click();
  await page.getByText("Bản 2", { exact: true }).waitFor();
  await page.getByRole("button", { name: "Duyệt bản này" }).first().click();
  await page.getByText("Đã duyệt · bản 2").first().waitFor();
  check("tài liệu hai bản, bản mới được duyệt", true);
  const href = await page.getByRole("link", { name: "Tải về" }).first().getAttribute("href");
  const download = await page.request.get(`${BASE}${href}`);
  check("tải về đúng tệp của bản mới", download.ok() && (await download.text()).includes(`${STAMP} v2`), String(download.status()));
  await shot(page, "07-document");
  await page.getByRole("button", { name: "Đóng" }).first().click().catch(() => {});

  // live: a comment written elsewhere appears on an open task without reloading it
  await page.goto(`${BASE}/pm/cong-viec/${task}`);
  await page.locator("[data-entry]").filter({ hasText: WORD }).waitFor();
  await page.waitForTimeout(1500);  // the socket joins the task's room
  const other = await page.context().newPage();
  await other.goto(`${BASE}/pm/du-an`);
  const live = `Đã kiểm tra lại cốp pha trục 5 ${STAMP}`;
  await call(other, "activity.post", { reference_doctype: "Task", reference_name: task, content: live, client_uuid: `live-${STAMP}` });
  await other.close();
  const arrived = await page.locator("[data-entry]").filter({ hasText: live }).waitFor({ timeout: 8000 }).then(() => true, () => false);
  check("trao đổi mới hiện ngay trên màn đang mở (realtime)", arrived);
}

/** A big JPEG (a phone screen at 3x), so the app has to shrink it. */
async function bigPhoto(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 3 });
  const page = await context.newPage();
  await page.setContent(`<body style="margin:0;background:linear-gradient(135deg,#c2410c,#0a1f35)"><h1 style="color:#fff;font:700 40px sans-serif;padding:40px">Cốp pha ${STAMP}</h1></body>`);
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
    const { project, formwork } = await build(page);
    check("tạo dự án thử", Boolean(project));
    const photo = await bigPhoto(browser);

    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "vi-VN",
      storageState: await desktop.storageState() });
    const small = await phone.newPage();
    watch(small);
    await onPhone(phone, small, project, formwork, photo);
    await onComputer(page, project, formwork);
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
