// Helpers of the project and task screens: status colours, Kanban columns, dates, files. No Vue, no network.

export const STATUS = { OPEN: "Open", WORKING: "Working", REVIEW: "Pending Review", COMPLETED: "Completed", CANCELLED: "Cancelled" };
export const STATUS_LABELS = {
  Open: "Chưa làm",
  Working: "Đang làm",
  "Pending Review": "Chờ duyệt",
  Completed: "Xong",
  Cancelled: "Hủy",
};
const STATUS_TONES = { Open: "muted", Working: "info", "Pending Review": "warning", Completed: "success", Cancelled: "muted" };
const STATE_TONES = { "Chờ nhận": "warning", "Đã nhận": "info", "Từ chối": "danger", "Thu hồi": "muted", "Hoàn thành": "success" };

export const statusLabel = (status) => STATUS_LABELS[status] || status || "";
export const statusBadge = (status) => `badge badge-${STATUS_TONES[status] || "muted"}`;
export const stateBadge = (state) => `badge badge-${STATE_TONES[state] || "muted"}`;

export const RACI = {
  ACCOUNTABLE: "Chịu trách nhiệm chính",
  RESPONSIBLE: "Thực hiện",
  CONSULTED: "Tham vấn",
  INFORMED: "Được báo",
  REVIEWER: "Duyệt",
};
/** Roles that must go to one person, never to a team. */
export const PERSON_ONLY = new Set([RACI.ACCOUNTABLE, RACI.REVIEWER]);

/** Cards grouped by the board's columns, in the server's order. Unknown statuses are left out. */
export function groupCards(columns, cards) {
  const out = Object.fromEntries(columns.map((column) => [column.status, []]));
  for (const card of cards) if (out[card.status]) out[card.status].push(card);
  return out;
}

/** "Trễ 3 ngày", "Hạn hôm nay", "Còn 2 ngày" (or "" without a deadline, or when the task is closed). */
export function deadlineText(task, today = new Date()) {
  if (!task?.exp_end_date || task.status === STATUS.COMPLETED || task.status === STATUS.CANCELLED) return "";
  const end = new Date(`${String(task.exp_end_date).slice(0, 10)}T00:00:00`);
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const diff = Math.round((end - day) / 86400000);
  if (diff < 0) return `Trễ ${-diff} ngày`;
  if (diff === 0) return "Hạn hôm nay";
  return `Còn ${diff} ngày`;
}

export const deadlineTone = (text) => (text.startsWith("Trễ") ? "text-danger" : text === "Hạn hôm nay" ? "text-warning" : "text-ink-muted");

/** Planned against actual, in percentage points: positive = ahead. */
export const variance = (actual, planned) => Math.round((Number(actual) || 0) - (Number(planned) || 0));

export function clampProgress(value) {
  const number = Math.round(Number(value));
  if (Number.isNaN(number)) return 0;
  return Math.min(100, Math.max(0, number));
}

/** A task is late for the report form: past its end and not finished (the server checks it again). */
export function needsDelayReason(task, progress, today = new Date()) {
  if (!task?.exp_end_date || [STATUS.COMPLETED, STATUS.CANCELLED].includes(task.status)) return false;
  if (task.pm_delay_reason && task.pm_delay_source) return false;
  const end = new Date(`${String(task.exp_end_date).slice(0, 10)}T00:00:00`);
  const day = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  return day > end && (Number(progress) >= 100 || Number(task.progress) < 100);
}

/** Read a picked file as base64 (without the data: prefix), for the import endpoints. */
export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1] || "");
    reader.onerror = () => reject(new Error("Không đọc được tệp"));
    reader.readAsDataURL(file);
  });
}

/** A unique id for one report, so that sending it twice records it once. */
export function clientUuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export const PROJECT_TABS = [
  { slug: "tong-quan", label: "Tổng quan", icon: "layout-dashboard" },
  { slug: "cong-viec", label: "Công việc", icon: "list-tree" },
  { slug: "trao-doi", label: "Trao đổi", icon: "message-square" },
  { slug: "gantt", label: "Gantt", icon: "chart-bar" },
  { slug: "kanban", label: "Kanban", icon: "kanban" },
  { slug: "lich", label: "Lịch", icon: "calendar-clock" },
  { slug: "ai-lam-gi", label: "Ai làm gì", icon: "user-check" },
  { slug: "tai-lieu", label: "Tài liệu", icon: "folder-open" },
  { slug: "bieu-mau", label: "Biểu mẫu", icon: "clipboard-list" },
  { slug: "baseline", label: "Baseline", icon: "history" },
  { slug: "thanh-vien", label: "Thành viên", icon: "users" },
];
