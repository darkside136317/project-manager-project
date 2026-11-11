// Workload and performance of people as the screens show them (services/workload.py, performance.py).

export const OTHER = "Dự án khác";  // the load of projects the viewer may not name (workload.OTHER)
export const LEVELS = ["Quá tải", "Bận", "Vừa sức", "Rảnh"];
// Whole class names: Tailwind keeps only what it sees.
const CELL = { "Quá tải": "bg-danger-soft text-danger", Bận: "bg-warning-soft text-warning", "Vừa sức": "bg-success-soft text-success", Rảnh: "text-ink-muted" };
const BADGE = { "Quá tải": "danger", Bận: "warning", "Vừa sức": "success", Rảnh: "muted" };
export const cellClass = (level) => CELL[level] || "text-ink-muted";
export const levelBadge = (level) => `badge badge-${BADGE[level] || "muted"}`;

export const CAPACITY_REASONS = ["Nghỉ phép", "Bán thời gian", "Điều động việc khác", "Khác"];
export const PERIODS = [
  { key: "week", label: "Tuần trước" },
  { key: "4w", label: "4 tuần" },
  { key: "quarter", label: "13 tuần" },
];

/** 0.853 → "85%"; empty → "—". */
export function percent(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value) * 100)}%`;
}

/** Days with at most one decimal: 2 → "2", 2.25 → "2,3". */
export function days(value) {
  const number = Math.round((Number(value) || 0) * 10) / 10;
  return String(number).replace(".", ",");
}

/** "2030-01-07" → "07/01". */
export function weekLabel(iso) {
  if (!iso) return "";
  const [, month, day] = String(iso).slice(0, 10).split("-");
  return `${day}/${month}`;
}

/** Monday of the week of `date` (local), as "YYYY-MM-DD". */
export function mondayOf(date = new Date()) {
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  day.setDate(day.getDate() - ((day.getDay() + 6) % 7));
  const pad = (n) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/** Move a Monday ("YYYY-MM-DD") by whole weeks. */
export function shiftWeeks(iso, weeks) {
  const [year, month, day] = iso.split("-").map(Number);
  return mondayOf(new Date(year, month - 1, day + 7 * weeks));
}

/** The projects behind one week of one person, the largest first, the hidden ones last. */
export function shares(projects, labels = {}) {
  return Object.entries(projects || {})
    .map(([key, value]) => ({ key, label: key === OTHER ? OTHER : labels[key] || key, days: Number(value) || 0, hidden: key === OTHER }))
    .sort((a, b) => Number(a.hidden) - Number(b.hidden) || b.days - a.days);
}

/** A column a layer added to the portfolio ({label, value, format, tone}) as text. */
export function columnText(column) {
  if (!column || column.value === null || column.value === undefined) return "—";
  if (column.format === "percent") return percent(column.value);
  if (column.format === "currency") return new Intl.NumberFormat("vi-VN").format(Math.round(Number(column.value)));
  return String(column.value);
}

const TONE_TEXT = { good: "text-success", warn: "text-warning", bad: "text-danger" };
export const toneText = (tone) => TONE_TEXT[tone] || "";

/** The labels of every layer column of the portfolio rows, in the order they first appear. */
export function extraColumns(rows) {
  const out = new Map();
  for (const row of rows || []) {
    for (const [key, column] of Object.entries(row.extra || {})) {
      if (!out.has(key)) out.set(key, column.label || key);
    }
  }
  return [...out.entries()].map(([key, label]) => ({ key, label }));
}

/** Points of a small line (SVG polyline) for a series of 0–100 values. */
export function sparkline(values, width = 80, height = 22) {
  const list = (values || []).map((v) => Number(v) || 0);
  if (list.length < 2) return "";
  const step = width / (list.length - 1);
  return list.map((v, i) => `${Math.round(i * step * 10) / 10},${Math.round((height - (Math.min(100, Math.max(0, v)) / 100) * height) * 10) / 10}`).join(" ");
}
