// The construction layer's calls to its API, and the parts of its screens that are not drawing: amounts in đồng,
// quantities, a BOQ as rows with their sections, a diary's quantities as they are written.
import { call } from "@pm/lib/api.js";

const M = "pm_construction.pm_construction.api.construction";

export const construction = {
  boqVersions: (project) => call(`${M}.boq_versions`, { project }),
  boqDetail: (name) => call(`${M}.boq_detail`, { name }),
  boqPreview: (project, content) => call(`${M}.boq_preview`, { project, content }, { post: true }),
  boqUpload: (project, content, values = {}) => call(`${M}.boq_upload`, { project, content, ...values }, { post: true }),
  boqApprove: (name) => call(`${M}.boq_approve`, { name }, { post: true }),
  boqTemplateUrl: () => `/api/method/${M}.boq_template`,
  diaries: (project, params = {}) => call(`${M}.diaries`, { project, ...params }),
  diaryDay: (project, day) => call(`${M}.diary_day`, { project, day }),
  diaryWorks: (project, search = "") => call(`${M}.diary_works`, { project, search }),
  diarySave: (project, day, values, rows, clientUuid = null) =>
    call(`${M}.diary_save`, { project, day, values, rows, client_uuid: clientUuid }, { post: true }),
  diarySubmit: (name, media = [], clientUuid = null) => call(`${M}.diary_submit`, { name, media, client_uuid: clientUuid }, { post: true }),
  diaryConfirm: (name, note = "") => call(`${M}.diary_confirm`, { name, note }, { post: true }),
  diarySendBack: (name, note) => call(`${M}.diary_send_back`, { name, note }, { post: true }),
  acceptance: (project) => call(`${M}.acceptance_overview`, { project }),
};

const money = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });
const quantity = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 });

/** 1234567 -> "1.234.567 đ"; large amounts shortened: "1,23 tỷ", "456,7 triệu". */
export function moneyText(value, { short = false } = {}) {
  const amount = Number(value) || 0;
  if (short && Math.abs(amount) >= 1e9) return `${(amount / 1e9).toFixed(2).replace(".", ",").replace(/,?0+$/, "")} tỷ`;
  if (short && Math.abs(amount) >= 1e6) return `${(amount / 1e6).toFixed(1).replace(".", ",").replace(/,0$/, "")} triệu`;
  return `${money.format(amount)} đ`;
}

export const qtyText = (value, uom = "") => `${quantity.format(Number(value) || 0)}${uom ? ` ${uom}` : ""}`;

export const percentText = (value) => `${Math.round((Number(value) || 0) * 10) / 10}%`.replace(".", ",");

/** Share of `part` in `whole`, 0-100. */
export function share(part, whole) {
  const total = Number(whole) || 0;
  return total > 0 ? Math.min(100, Math.max(0, ((Number(part) || 0) / total) * 100)) : 0;
}

/** BOQ lines with what each section holds (its total and number of work items), in sheet order. */
export function boqRows(items) {
  const byLine = new Map(items.map((item) => [item.line_no, { ...item, total: 0, works: 0 }]));
  for (const item of byLine.values()) {
    if (item.is_group) continue;
    let parent = byLine.get(item.parent_line);
    while (parent) {
      parent.total += Number(item.amount) || 0;
      parent.works += 1;
      parent = byLine.get(parent.parent_line);
    }
  }
  return [...byLine.values()];
}

/** Rows of a diary as typed: drop empty lines, merge nothing, check quantities. Returns { rows, errors }. */
export function diaryRows(lines) {
  const rows = [];
  const errors = [];
  const seen = new Set();
  for (const line of lines) {
    if (!line.task && !line.qty) continue;
    const qty = Number(String(line.qty ?? "").replace(",", "."));
    if (!line.task) errors.push("Chọn công tác cho mỗi dòng có khối lượng");
    else if (!(qty > 0)) errors.push(`${line.label || "Công tác"}: khối lượng phải lớn hơn 0`);
    else if (seen.has(line.task)) errors.push(`${line.label || "Công tác"} được ghi hai lần`);
    else {
      seen.add(line.task);
      rows.push({ task: line.task, qty, note: (line.note || "").trim() });
    }
  }
  return { rows, errors: [...new Set(errors)] };
}

export const DIARY_TONE = { "Nháp": "badge-muted", "Đã nộp": "badge-warning", "Đã xác nhận": "badge-success" };
export const BOQ_TONE = { "Nháp": "badge-warning", "Đã duyệt": "badge-success", "Thay thế": "badge-muted" };

/** Today's date as the server reads it (local time). */
export function today(date = new Date()) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
