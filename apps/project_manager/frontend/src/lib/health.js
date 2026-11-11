// Health (Xanh / Vàng / Đỏ), alerts and phase gates as the screens show them (services/risk.py, alerts.py, phases.py).

export const HEALTH = ["Đỏ", "Vàng", "Xanh"];
const HEALTH_TONES = { Xanh: "success", Vàng: "warning", Đỏ: "danger" };
const HEALTH_TEXT = { Xanh: "Đúng tiến độ", Vàng: "Cần chú ý", Đỏ: "Nguy cơ trễ" };

export const healthTone = (level) => HEALTH_TONES[level] || "muted";
export const healthBadge = (level) => `badge badge-${healthTone(level)}`;
const HEALTH_COLOURS = { Xanh: "text-success", Vàng: "text-warning", Đỏ: "text-danger" };  // whole names: Tailwind sees them
export const healthColour = (level) => HEALTH_COLOURS[level] || "text-ink-muted";
export const healthText = (level) => (level ? `${level} · ${HEALTH_TEXT[level] || ""}`.replace(/ · $/, "") : "Chưa đánh giá");

export const ALERT_OPEN = "Đang mở";
export const ALERT_ACKED = "Đã xác nhận";
export const ALERT_OVER = "Đã hết";
const ALERT_TONES = { [ALERT_OPEN]: "danger", [ALERT_ACKED]: "info", [ALERT_OVER]: "muted" };
export const alertBadge = (state) => `badge badge-${ALERT_TONES[state] || "muted"}`;
export const levelText = (level) => (Number(level) > 0 ? `Leo thang bậc ${level}` : "");

// A link of the server ("/pm/cong-viec/X") is a route of the SPA ("/cong-viec/X").
export const spaPath = (link) => (link || "/").replace(/^\/pm(?=\/|$)/, "") || "/";

export const GATE_AUTO = "Tự động";
export const GATE_APPROVAL = "Cần duyệt";
export const GATE_MANUAL = "Thủ công";
export const GATE_MODES = [GATE_MANUAL, GATE_APPROVAL, GATE_AUTO];
export const GATE_WAITING = "Chờ duyệt";
export const GATE_PASSED = "Đã chuyển";

// What the current phase waits for, in a sentence.
export function gateSummary(current) {
  if (!current) return "Đã qua mọi giai đoạn";
  if (current.missing?.length) return `Chưa đủ điều kiện: ${current.missing.join("; ")}`;
  if (current.state === GATE_WAITING) return "Đủ điều kiện, chờ quản lý dự án duyệt chuyển giai đoạn";
  if (current.mode === GATE_MANUAL) return "Đủ điều kiện, quản lý dự án chuyển khi sẵn sàng";
  return "Đủ điều kiện";
}

// The manager may pass it by hand once nothing is missing (an automatic phase passes by itself).
export const canPassPhase = (current) => Boolean(current?.can_pass && current.mode !== GATE_AUTO);

export const QUIET_DEFAULT = { start: "21:00", end: "07:00" };
