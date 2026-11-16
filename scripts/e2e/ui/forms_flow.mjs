// M3 end to end, in a real browser: design an acceptance form on a computer, then on a phone require it on a task, see the
// task refuse to close, fill the form in (photo, checklist, signature), submit, approve, get the PDF and the Excel, and
// close the task.
//
//   cd scripts/e2e/ui && npm ci && node forms_flow.mjs [base_url]
//
// The base URL defaults to http://localhost:<HTTP_PUBLISH_PORT from docker/.env>; the Administrator password is read from
// the same file and never printed. PW_CHANNEL picks the browser ("msedge" by default, "chrome"). Pictures of each step go
// to scripts/e2e/ui/out/. It creates a project and a form template (codes E2E-...): run it on a scratch or development
// site. The exit code is the number of failed checks.
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");
const env = Object.fromEntries(readFileSync(join(HERE, "../../..", process.env.PM_ENV_FILE || "docker/.env"), "utf8").split(/\r?\n/)
  .filter((line) => line.includes("=") && !line.trimStart().startsWith("#"))
  .map((line) => [line.slice(0, line.indexOf("=")).trim(), line.slice(line.indexOf("=") + 1)]));
const BASE = (process.argv[2] || `http://localhost:${env.HTTP_PUBLISH_PORT || 8890}`).replace(/\/$/, "");
const STAMP = Date.now().toString(36).toUpperCase();
const CODE = `E2E-${STAMP}`;
const TITLE = `Biên bản nghiệm thu thử ${STAMP}`;
const PROJECT = `Dự án thử biểu mẫu ${STAMP}`;
const TASK = `Đổ bê tông móng M${STAMP}`;
const PIXEL = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==", "base64");

let failures = 0;
const problems = [];

function check(name, ok, detail = "") {
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : ` — ${detail}`}`);
  if (!ok) failures += 1;
}

async function shot(page, name) {
  await page.screenshot({ path: join(OUT, `${name}.png`), fullPage: true });
}

async function fitsTheScreen(page, where) {
  await page.waitForTimeout(150);
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  check(`${where}: không cuộn ngang`, scroll <= client, `${scroll} > ${client}`);
}

function watch(page) {
  page.on("pageerror", (error) => problems.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    // A failed request is reported below, with its address; 417 is the server refusing by a rule, provoked on purpose.
    if (message.type() === "error" && !/Failed to load resource/.test(message.text())) problems.push(`console: ${message.text()}`);
  });
  page.on("response", (response) => {
    if (response.status() >= 400 && response.status() !== 417) problems.push(`${response.status()} ${response.url()}`);
  });
}

const button = (page, name) => page.getByRole("button", { name, exact: true });

async function addField(page, index, label, kind, { required, options, preset } = {}) {
  await page.getByRole("button", { name: "Thêm trường" }).click();
  await page.getByLabel("Nhãn trường").nth(index).fill(label);
  await page.getByLabel("Kiểu trường").nth(index).selectOption(kind);
  const row = page.locator("ol[aria-label='Các trường'] > li").nth(index);
  if (required) await row.getByLabel("Bắt buộc").check();
  if (options) await row.locator("textarea").nth(0).fill(options);
  if (preset) await row.locator("textarea").nth(1).fill(preset);
}

async function design(context) {
  const page = await context.newPage();
  watch(page);
  await page.goto(`${BASE}/pm/bieu-mau-mau`);
  await page.getByRole("button", { name: "Tạo mẫu" }).click();
  await page.locator("#t-title").fill(TITLE);
  await page.locator("#t-code").fill(CODE);
  await page.locator("#t-category").fill("Nghiệm thu");
  await button(page, "Tạo").click();
  await page.waitForURL(`**/bieu-mau-mau/${CODE}-v01`);
  await addField(page, 0, "Thông tin nghiệm thu", "Tiêu đề mục");
  await addField(page, 1, "Ngày nghiệm thu", "Ngày", { required: true });
  await addField(page, 2, "Khối lượng", "Số");
  await addField(page, 3, "Kết luận", "Chọn", { required: true, options: "Đạt\nKhông đạt" });
  await addField(page, 4, "Danh mục kiểm tra", "Bảng", { required: true, options: "Nội dung\nKết quả | Chọn: Đạt, Không đạt", preset: "Đúng bản vẽ\nĐủ hồ sơ chất lượng" });
  await addField(page, 5, "Ảnh hiện trường", "Ảnh");
  await addField(page, 6, "Người nghiệm thu ký", "Chữ ký", { required: true });
  await button(page, "Lưu").click();
  await page.getByText("Đã lưu bản nháp").waitFor();
  check("thiết kế: xem trước theo bản đã lưu", await page.getByText("Danh mục kiểm tra").count() > 0);
  await shot(page, "01-thiet-ke-mau");
  await page.getByRole("button", { name: "Đưa vào dùng" }).click();
  await page.getByText("Đã đưa mẫu vào dùng").waitFor();
  check("mẫu đã dùng thì không sửa được", await page.getByLabel("Nhãn trường").count() === 0 && await page.getByRole("button", { name: "Tạo phiên bản mới" }).count() === 1);

  await page.goto(`${BASE}/pm/du-an`);
  await page.getByRole("button", { name: "Tạo dự án" }).click();
  await page.locator("#p-name").fill(PROJECT);
  await button(page, "Tạo").click();
  await page.waitForURL("**/du-an/*/tong-quan");
  const project = decodeURIComponent(page.url().split("/du-an/")[1].split("/")[0]);
  check("tạo dự án", Boolean(project));
  await page.close();
  return project;
}

async function onPhone(context, project) {
  const page = await context.newPage();
  watch(page);
  const end = new Date(Date.now() + 10 * 86400000).toISOString().slice(0, 10);

  // the task, and what it requires
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/cong-viec`);
  await page.getByRole("button", { name: "Thêm hạng mục" }).click();
  await page.getByLabel("Tên công việc").fill(TASK);
  await page.getByLabel("Ngày kết thúc").fill(end);
  await button(page, "Thêm").click();
  await page.getByRole("button", { name: TASK }).click();
  await page.getByLabel("Chọn biểu mẫu bắt buộc").selectOption(CODE);
  await page.getByRole("button", { name: "Thêm điều kiện" }).click();
  await page.getByText(`Bắt buộc: ${TITLE}`).waitFor();
  await fitsTheScreen(page, "bảng công việc");
  await shot(page, "02-dieu-kien-dong-viec");

  // it refuses to close
  await page.getByLabel("Phần trăm").fill("100");
  await page.getByRole("button", { name: "Gửi cập nhật" }).click();
  await page.getByText(/cần biểu mẫu đã duyệt/).first().waitFor();
  check("chưa có biểu mẫu thì không đóng được việc", true);
  await shot(page, "03-chua-dong-duoc");

  // fill the form in
  await page.locator("[aria-label='Biểu mẫu bắt buộc để đóng việc']").getByRole("button", { name: "Điền", exact: true }).click();
  await page.waitForURL("**/bieu-mau/*");
  const formUrl = page.url();
  await page.getByRole("button", { name: "Nộp", exact: true }).click();
  await page.getByText(/mục bắt buộc chưa điền/).waitFor();
  check("thiếu mục bắt buộc thì không nộp được", await page.getByText("Cần điền mục này").count() > 0);
  await page.locator("#f-ngay_nghiem_thu").fill(new Date().toISOString().slice(0, 10));
  await page.locator("#f-khoi_luong").fill("12.5");
  await page.getByRole("radio", { name: "Đạt", exact: true }).click();
  for (const select of await page.getByLabel("Kết quả").all()) await select.selectOption("Đạt");
  await page.locator("input[type=file]").setInputFiles({ name: "hien-truong.png", mimeType: "image/png", buffer: PIXEL });
  await page.locator("img[alt='hien-truong.png']").waitFor();
  check("ảnh được thu nhỏ và gửi lên", true);
  const canvas = page.locator("canvas");
  await canvas.scrollIntoViewIfNeeded();
  const box = await canvas.boundingBox();
  await page.mouse.move(box.x + 20, box.y + 30);
  await page.mouse.down();
  await page.mouse.move(box.x + 120, box.y + 80, { steps: 6 });
  await page.mouse.move(box.x + 200, box.y + 40, { steps: 6 });
  await page.mouse.up();
  await page.getByRole("button", { name: "Dùng chữ ký này" }).click();
  await page.locator("img[alt='Người nghiệm thu ký']").waitFor();
  check("ký bằng tay", true);
  await page.getByText(/Đã lưu lúc/).waitFor({ timeout: 8000 });
  await fitsTheScreen(page, "điền biểu mẫu");
  await shot(page, "04-dien-bieu-mau");

  // nothing typed is lost
  await page.reload();
  await page.locator("img[alt='Người nghiệm thu ký']").waitFor();
  check("tự lưu: tải lại vẫn còn nội dung", await page.locator("#f-khoi_luong").inputValue() === "12.5");

  // submit and approve
  await page.getByRole("button", { name: "Nộp", exact: true }).click();
  await page.getByText("Đã nộp biểu mẫu").waitFor();
  check("nộp xong thì chỉ còn đọc", await page.locator("#f-khoi_luong").count() === 0);
  await page.getByRole("button", { name: "Duyệt", exact: true }).click();
  await page.getByText("Đã duyệt biểu mẫu").waitFor();
  await shot(page, "05-da-duyet");

  const pdf = await context.request.get(await page.getByRole("link", { name: "Tải PDF" }).evaluate((a) => a.href));
  const bytes = await pdf.body();
  check("PDF đã duyệt", pdf.ok() && bytes.subarray(0, 4).toString() === "%PDF", String(pdf.status()));
  writeFileSync(join(OUT, "bieu-mau.pdf"), bytes);
  const again = await context.request.get(await page.getByRole("link", { name: "Tải PDF" }).evaluate((a) => a.href));
  check("PDF giữ nguyên qua các lần tải", Buffer.compare(bytes, await again.body()) === 0);

  // the Excel of the project
  await page.goto(`${BASE}/pm/du-an/${encodeURIComponent(project)}/bieu-mau`);
  await page.getByLabel("Loại biểu mẫu").selectOption(CODE);
  await page.getByRole("link", { name: "Xuất Excel" }).waitFor();
  await fitsTheScreen(page, "tab biểu mẫu");
  await shot(page, "06-tab-bieu-mau");
  const excel = await context.request.get(await page.getByRole("link", { name: "Xuất Excel" }).evaluate((a) => a.href));
  check("xuất Excel", excel.ok() && (await excel.body()).subarray(0, 2).toString() === "PK", String(excel.status()));

  // now the task closes
  await page.goto(formUrl);
  await page.getByRole("link", { name: TASK }).click();
  await page.waitForURL("**/cong-viec/*");
  await page.getByLabel("Phần trăm").fill("100");
  await page.getByRole("button", { name: "Gửi cập nhật" }).click();
  await page.getByText("Đã cập nhật tiến độ").waitFor();
  await page.locator("article header").getByText("Xong", { exact: true }).waitFor();
  check("biểu mẫu đã duyệt thì đóng được việc", true);
  await fitsTheScreen(page, "chi tiết công việc");
  await shot(page, "07-da-dong-viec");
  await page.close();
}

async function main() {
  if (existsSync(OUT)) rmSync(OUT, { recursive: true });
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || "msedge" });
  try {
    const desktop = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "vi-VN" });
    const login = await desktop.request.post(`${BASE}/api/method/login`, { form: { usr: "Administrator", pwd: env.ADMIN_PASSWORD || "" } });
    check("đăng nhập", login.ok(), String(login.status()));
    const project = await design(desktop);
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, locale: "vi-VN",
      storageState: await desktop.storageState() });
    await onPhone(phone, project);
    check("không có lỗi JavaScript", problems.length === 0, problems.join(" | ").slice(0, 600));
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
