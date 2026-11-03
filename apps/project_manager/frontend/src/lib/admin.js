// Helpers of the administration screens (module 8): users, the permission matrix, the system log and the monitor.
import { formatNumber } from "./format.js";

/** A server path (a set-password link) as a full address to hand over. */
export function absoluteLink(path, origin = typeof window !== "undefined" ? window.location.origin : "") {
  return /^https?:\/\//i.test(path) ? path : `${origin}${path}`;
}

export const ROLE_ORDER = ["PM Admin", "PM Director", "PM Staff"];

// The project scope of a user beyond the projects they are a member of (PM Access; constants.py has the same texts).
export const READ_MEMBER = "Chỉ dự án tham gia";
export const READ_ALL = "Tất cả dự án";
export const READ_CHOSEN = "Dự án tham gia và dự án được chọn";
export const WRITE_MEMBER = "Theo vai trò trong dự án";
export const WRITE_SAME = "Như phạm vi xem";
export const WRITE_CHOSEN = "Theo vai trò và dự án được chọn";

/** The scope of a user who has none of their own: only the projects they are a member of. */
export function blankAccess() {
  return { read_scope: READ_MEMBER, write_scope: WRITE_MEMBER, read_projects: [], write_projects: [] };
}

function accessToForm(access) {
  const a = access || blankAccess();
  return { read_scope: a.read_scope || READ_MEMBER, write_scope: a.write_scope || WRITE_MEMBER,
    read_projects: [...(a.read_projects || [])], write_projects: [...(a.write_projects || [])] };
}

/** Initial values of the user form; the permission groups it may give come from the server. */
export function blankUser() {
  return { email: "", first_name: "", last_name: "", phone: "", enabled: 1, roles: [], groups: [], access: blankAccess() };
}

export function userToForm(user) {
  return { email: user.name, first_name: user.first_name, last_name: user.last_name, phone: user.phone, enabled: user.enabled, roles: [...user.roles],
    groups: [...user.groups], access: accessToForm(user.access) };
}

/** The scope as the server stores it (only what decides it: project codes, not their names). */
export function accessKey(access) {
  const a = accessToForm(access);
  return JSON.stringify([a.read_scope, a.write_scope,
    a.read_scope === READ_CHOSEN ? a.read_projects.map((r) => r.project).sort() : [],
    a.write_scope === WRITE_CHOSEN ? a.write_projects.map((r) => r.project).sort() : []]);
}

/** Why a scope cannot be saved yet ("" when it can). */
export function accessProblem(access) {
  const a = accessToForm(access);
  if (a.read_scope === READ_CHOSEN && !a.read_projects.length) return "Chọn ít nhất một dự án được xem thêm";
  if (a.write_scope === WRITE_CHOSEN && !a.write_projects.length) return "Chọn ít nhất một dự án được sửa thêm";
  if (a.read_scope === READ_CHOSEN && a.write_scope === WRITE_CHOSEN) {
    const readable = new Set(a.read_projects.map((r) => r.project));
    const outside = a.write_projects.filter((r) => !readable.has(r.project)).map((r) => r.project_name || r.project);
    if (outside.length) return `Dự án được sửa phải nằm trong các dự án được xem: ${outside.join(", ")}`;
  }
  return "";
}

/** Roles in the order the screen shows them, whatever order the user holds them in. */
export const sortRoles = (roles) => [...roles].sort((a, b) => rank(a) - rank(b) || String(a).localeCompare(String(b), "vi"));
// the built-in groups first, in their usual order; groups made by the administrators after them
const rank = (role) => (ROLE_ORDER.includes(role) ? ROLE_ORDER.indexOf(role) : ROLE_ORDER.length);

export function toggleValue(list, value) {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

/** Only what changed, so an edit never resends (and never overwrites) what the form did not touch. */
export function changedValues(original, form) {
  const out = {};
  for (const key of ["first_name", "last_name", "phone", "enabled"]) if (form[key] !== original[key]) out[key] = form[key];
  for (const key of ["roles", "groups"]) {
    if (JSON.stringify(sortRoles(form[key])) !== JSON.stringify(sortRoles(original[key]))) out[key] = form[key];
  }
  if (form.access && accessKey(form.access) !== accessKey(original.access)) out.access = form.access;
  return out;
}

/** Why a user form cannot be sent yet ("" when it can). */
export function userProblem(form, creating) {
  if (creating && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(form.email).trim())) return "Nhập địa chỉ email hợp lệ";
  if (!String(form.first_name).trim()) return "Nhập tên";
  return form.access ? accessProblem(form.access) : "";
}

/** Can the current user change this account in the screen at all? (the server enforces the same rules) */
export function canEditUser(user, me) {
  if (!user) return false;
  if (user.protected) return me.roles.includes("System Manager") || me.name === "Administrator";
  return true;
}

export const permissionIcons = [["read", "Xem"], ["create", "Thêm"], ["write", "Sửa"], ["delete", "Xóa"]];

/** Compact text of what a role may do on a DocType: "Xem, Thêm, Sửa". */
export function permissionText(perms) {
  const given = permissionIcons.filter(([key]) => perms?.[key]).map(([, label]) => label);
  return given.length ? given.join(", ") : "Không";
}

// --- permission groups (the editable matrix) ---------------------------------------------------------------------------

export const MATRIX_COLUMNS = ["read", "create", "write", "delete", "submit", "cancel", "print", "export", "own_only", "sensitive"];

/** A matrix cell after ticking or unticking `key`: any right brings reading; unticking reading takes everything away. */
export function toggleCell(cell, key, value) {
  const next = { ...cell, [key]: value };
  if (key === "read" && !value) return Object.fromEntries(Object.keys(next).map((k) => [k, false]));
  if (value && key !== "read") next.read = true;
  if (key === "cancel" && value) next.submit = true;
  if (key === "submit" && !value) next.cancel = false;
  return next;
}

/** {doctype: cell} of a group, to edit without touching what the server sent. */
export function editableMatrix(group) {
  const out = {};
  for (const section of group?.matrix || []) for (const row of section.rows) out[row.doctype] = { ...row.cell };
  return out;
}

export const checkedCapabilities = (group) =>
  (group?.capabilities || []).flatMap((m) => m.items.filter((i) => i.checked).map((i) => i.code));

const sameCell = (a, b) => MATRIX_COLUMNS.every((k) => Boolean(a?.[k]) === Boolean(b?.[k]));

/** Only the rows that changed: what `save_group` needs. */
export function changedMatrix(original, edited) {
  const out = {};
  for (const [doctype, cell] of Object.entries(edited)) if (!sameCell(original[doctype], cell)) out[doctype] = cell;
  return out;
}

/** What a save would change, in words, for the confirmation: ["Hồ sơ lưu trữ: thêm Xóa; bỏ In", "Thêm chức năng: …"]. */
export function describeChanges(group, edited, capabilities, columnLabels = {}) {
  const lines = [];
  const original = editableMatrix(group);
  const labels = {};
  for (const section of group?.matrix || []) for (const row of section.rows) labels[row.doctype] = row.label;
  for (const [doctype, cell] of Object.entries(changedMatrix(original, edited))) {
    const added = MATRIX_COLUMNS.filter((k) => cell[k] && !original[doctype]?.[k]).map((k) => columnLabels[k] || k);
    const removed = MATRIX_COLUMNS.filter((k) => !cell[k] && original[doctype]?.[k]).map((k) => columnLabels[k] || k);
    const parts = [added.length && `thêm ${added.join(", ")}`, removed.length && `bỏ ${removed.join(", ")}`].filter(Boolean);
    lines.push(`${labels[doctype] || doctype}: ${parts.join("; ")}`);
  }
  const before = new Set(checkedCapabilities(group));
  const after = new Set(capabilities);
  const names = Object.fromEntries((group?.capabilities || []).flatMap((m) => m.items.map((i) => [i.code, i.label])));
  const plus = [...after].filter((c) => !before.has(c)).map((c) => names[c] || c);
  const minus = [...before].filter((c) => !after.has(c)).map((c) => names[c] || c);
  if (plus.length) lines.push(`Thêm chức năng: ${plus.join(", ")}`);
  if (minus.length) lines.push(`Bỏ chức năng: ${minus.join(", ")}`);
  return lines;
}

// --- the system log -------------------------------------------------------------------------------------------------

export const LOG_FILTERS = ["activity_type", "user", "reference_doctype", "reference_name", "search", "date_from", "date_to"];

export function cleanLogFilters(values) {
  const out = {};
  for (const key of LOG_FILTERS) if (values[key]) out[key] = String(values[key]).trim();
  return out;
}

export function logDownloadUrl(filters) {
  const params = new URLSearchParams(cleanLogFilters(filters));
  return `/api/method/project_manager.project_manager.api.logs.download_logs?${params}`;
}

/** The newest date a clean-up may reach: the server never cleans the last `keepDays` days. */
export function latestPurgeDate(keepDays = 7, today = new Date()) {
  const date = new Date(today.getFullYear(), today.getMonth(), today.getDate() - keepDays);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** The count must be typed back exactly before a clean-up is offered. */
export const purgeConfirmed = (typed, total) => total > 0 && String(typed).replace(/\D/g, "") === String(total);

export function prettyJson(text) {
  if (!text) return "";
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return String(text);
  }
}

// --- the monitor ----------------------------------------------------------------------------------------------------

export function serviceTone(service) {
  return service?.disabled ? "muted" : service?.ok ? "success" : "danger";
}

export function diskTone(disk) {
  if (!disk) return "muted";
  return disk.used_percent >= 90 ? "danger" : disk.used_percent >= 75 ? "warning" : "success";
}

export const SERVICE_LABELS = { meilisearch: "Tìm kiếm (Meilisearch)", overdue_job: "Job Overdue của ERPNext" };

export const queueText = (queues) => (queues || []).map((q) => `${q.name}: ${formatNumber(q.jobs)}`).join(" · ") || "—";
