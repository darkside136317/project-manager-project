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

// --- materials, machines, labour, costs (M8) --------------------------------------------------------------------------
const S = "pm_construction.pm_construction.api.site";

// What the store keeper does, the method of each and what its rows need.
export const STOCK_ACTIONS = {
  receive: { label: "Nhập kho", method: "stock_receive", task: false, rate: true, icon: "download" },
  issue: { label: "Cấp phát", method: "stock_issue", task: true, icon: "send" },
  return: { label: "Hoàn trả", method: "stock_return", task: true, icon: "undo" },
  write_off: { label: "Hao hụt", method: "stock_write_off", task: false, note: true, icon: "trash-2" },
  transfer: { label: "Điều chuyển", method: "stock_transfer", task: false, target: true, icon: "arrow-left-right" },
};

export const site = {
  materials: (project) => call(`${S}.materials_overview`, { project }),
  createStore: (project) => call(`${S}.create_store`, { project }, { post: true }),
  recomputePlan: (project) => call(`${S}.recompute_plan`, { project }, { post: true }),
  request: (project, rows, note = "", neededBy = null, clientUuid = null) =>
    call(`${S}.material_request`, { project, rows, note, needed_by: neededBy, client_uuid: clientUuid }, { post: true }),
  stopRequest: (name, note = "") => call(`${S}.stop_request`, { name, note }, { post: true }),
  stock: (action, project, rows, values = {}) =>
    call(`${S}.${STOCK_ACTIONS[action].method}`, { project, rows, ...values }, { post: true }),
  machines: (project) => call(`${S}.machines_overview`, { project }),
  moveMachine: (machine, toProject = null, transferDate = null, note = "") =>
    call(`${S}.machine_transfer`, { machine, to_project: toProject, transfer_date: transferDate, note }, { post: true }),
  shift: (values, clientUuid = null) => call(`${S}.machine_shift`, { ...values, client_uuid: clientUuid }, { post: true }),
  deleteShift: (name) => call(`${S}.delete_shift`, { name }, { post: true }),
  labour: (project) => call(`${S}.labour_overview`, { project }),
  sheet: (project, team, day) => call(`${S}.attendance_sheet`, { project, team, day }),
  attendanceSave: (project, team, day, lines, note = "") => call(`${S}.attendance_save`, { project, team, day, lines, note }, { post: true }),
  attendanceRecord: (project, team, day, lines, note = "", clientUuid = null) =>
    call(`${S}.attendance_record`, { project, team, day, lines, note, client_uuid: clientUuid }, { post: true }),
  attendanceConfirm: (name) => call(`${S}.attendance_confirm`, { name }, { post: true }),
  attendanceSendBack: (name, note) => call(`${S}.attendance_send_back`, { name, note }, { post: true }),
  costs: (project) => call(`${S}.cost_summary`, { project }),
};

const number = (value) => Number(String(value ?? "").replace(",", "."));

/** Rows of a stock or request form as typed: empty lines dropped, numbers read with a decimal comma. */
export function materialRows(lines, { task = false, rate = false } = {}) {
  const rows = [];
  const errors = [];
  for (const line of lines) {
    if (!line.item && !line.qty) continue;
    const qty = number(line.qty);
    if (!line.item) errors.push("Chọn vật tư cho mỗi dòng có số lượng");
    else if (!(qty > 0)) errors.push(`${line.item_name || line.item}: số lượng phải lớn hơn 0`);
    else if (task && !line.task) errors.push(`${line.item_name || line.item}: chọn công tác`);
    else if (rate && !(number(line.rate) > 0)) errors.push(`${line.item_name || line.item}: nhập đơn giá`);
    else {
      const row = { item: line.item, qty, task: line.task || null };
      if (rate) row.rate = number(line.rate);
      if (line.material_request_item) row.material_request_item = line.material_request_item;
      rows.push(row);
    }
  }
  return { rows, errors: [...new Set(errors)] };
}

/** Usage rows grouped by work item, in tree order; a work item is over the norm when one of its materials is. */
export function byWork(rows) {
  const groups = new Map();
  for (const row of rows) {
    if (!groups.has(row.task)) groups.set(row.task, { task: row.task, label: row.task_label, path: row.path, rows: [], over: false, ahead: false });
    const group = groups.get(row.task);
    group.rows.push(row);
    group.over = group.over || row.over_norm;
    group.ahead = group.ahead || Boolean(row.ahead);
  }
  return [...groups.values()];
}

/** Lines of an attendance sheet as typed: workers with no man-days dropped. Returns { lines, errors, total }. */
export function attendanceLines(lines) {
  const out = [];
  const errors = [];
  for (const line of lines) {
    const days = number(line.man_days);
    if (!(days > 0)) continue;
    if (days > 2) errors.push(`${line.worker_name}: số công tối đa 2`);
    else out.push({ worker: line.worker, task: line.task || null, man_days: days, overtime_hours: number(line.overtime_hours) || 0, note: (line.note || "").trim() });
  }
  return { lines: out, errors, total: out.reduce((sum, line) => sum + line.man_days, 0) };
}

export const SHEET_TONE = { "Nháp": "badge-muted", "Đã nộp": "badge-warning", "Đã xác nhận": "badge-success" };
export const REQUEST_STATUS = { Pending: "Chờ cấp", "Partially Ordered": "Cấp một phần", Issued: "Đã cấp", Stopped: "Đã dừng", Ordered: "Đã cấp" };
