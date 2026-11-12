// Budgets and earned value, risks, issues, change requests as the screens show them (services/budget.py, control.py).

export const BUDGET_CATEGORIES = ["Vật tư", "Nhân công", "Máy thi công", "Thầu phụ", "Chi phí chung", "Dự phòng", "Phát sinh", "Khác"];
export const RISK_CATEGORIES = ["Kỹ thuật", "Tiến độ", "Chi phí", "An toàn", "Pháp lý", "Cung ứng", "Thời tiết", "Khác"];
export const RESPONSES = ["Giảm thiểu", "Tránh", "Chuyển giao", "Chấp nhận"];
export const RISK_STATES = ["Mở", "Đang xử lý", "Đã xảy ra", "Đã đóng"];
export const ISSUE_STATES = ["Mở", "Đang xử lý", "Đã giải quyết", "Đã đóng"];
export const PRIORITIES = ["Khẩn", "Cao", "Trung bình", "Thấp"];
export const CHANGE_REASONS = ["Chủ đầu tư yêu cầu", "Thay đổi thiết kế", "Điều kiện hiện trường", "Sai sót, thiếu sót", "Khác"];

/** 1234567.4 → "1.234.567"; empty → "—". */
export function money(value) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(Math.round(Number(value) || 0));
}

/** Short money for the tiles: 1,25 tỷ / 340 tr / 12.000. */
export function moneyShort(value) {
  const n = Number(value) || 0;
  const abs = Math.abs(n);
  const fmt = (x) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 2 }).format(x);
  if (abs >= 1e9) return `${fmt(n / 1e9)} tỷ`;
  if (abs >= 1e6) return `${fmt(n / 1e6)} tr`;
  return money(n);
}

/** 0.873 → "0,87"; empty → "—". */
export function ratio(value) {
  if (value === null || value === undefined || value === "") return "—";
  return new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value));
}

/** Colour of an index (CPI, SPI): under 0.9 red, under 1 amber, else green. */
export function indexTone(value) {
  if (value === null || value === undefined) return "text-ink-muted";
  return value < 0.9 ? "text-danger" : value < 1 ? "text-warning" : "text-success";
}

/** Colour of a money difference (CV, VAC): negative is red. */
export const varianceTone = (value) => (value === null || value === undefined ? "text-ink-muted" : Number(value) < 0 ? "text-danger" : "text-success");

/** What actual cost is of the budget, as a bar width (0–100) and whether it is over. */
export function usage(budget, actual) {
  const b = Number(budget) || 0;
  const a = Number(actual) || 0;
  if (!b) return { width: a ? 100 : 0, over: a > 0, pct: null };
  return { width: Math.min(100, Math.round((a / b) * 100)), over: a > b, pct: Math.round((a / b) * 100) };
}

const LEVEL = { Cao: "danger", "Trung bình": "warning", Thấp: "success" };
export const levelBadge = (level) => `badge badge-${LEVEL[level] || "muted"}`;
const STATE = { Mở: "info", "Đang xử lý": "warning", "Đã xảy ra": "danger", "Đã đóng": "muted", "Đã giải quyết": "success",
  Nháp: "muted", "Chờ duyệt": "warning", "Đã duyệt": "success", "Từ chối": "danger", "Đã hủy": "muted",
  "Thay thế": "muted" };
export const stateBadge = (state) => `badge badge-${STATE[state] || "muted"}`;
const PRIORITY = { Khẩn: "danger", Cao: "warning", "Trung bình": "info", Thấp: "muted" };
export const priorityBadge = (priority) => `badge badge-${PRIORITY[priority] || "muted"}`;

/** Score and level of a risk as the server computes them (5 × 5). */
export function riskScore(probability, impact) {
  const score = (Number(probability) || 0) * (Number(impact) || 0);
  return { score, level: score >= 12 ? "Cao" : score >= 5 ? "Trung bình" : "Thấp" };
}

/** The 5 × 5 matrix: rows impact 5→1, columns probability 1→5, each cell with its risks. */
export function matrix(risks) {
  const open = (risks || []).filter((r) => r.status === "Mở" || r.status === "Đang xử lý");
  return [5, 4, 3, 2, 1].map((impact) => ({
    impact,
    cells: [1, 2, 3, 4, 5].map((probability) => ({
      probability,
      level: riskScore(probability, impact).level,
      risks: open.filter((r) => Number(r.probability) === probability && Number(r.impact) === impact),
    })),
  }));
}

const CELL = { Cao: "bg-danger-soft", "Trung bình": "bg-warning-soft", Thấp: "bg-success-soft" };
export const cellTone = (level) => CELL[level] || "";

/** Sum of the lines of a budget form. */
export const total = (lines) => (lines || []).reduce((sum, line) => sum + (Number(String(line.amount ?? "").replace(/\./g, "").replace(",", ".")) || 0), 0);

/** Lines of a budget form as the server takes them (amounts as numbers, empty lines left out). */
export function budgetLines(lines) {
  return (lines || [])
    .map((line) => ({ category: line.category || "Khác", task: line.task || null, description: (line.description || "").trim(),
      amount: Number(String(line.amount ?? "").replace(/\./g, "").replace(",", ".")) || 0 }))
    .filter((line) => line.amount || line.description);
}
