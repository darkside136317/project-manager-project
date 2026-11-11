// Thin client for Frappe's /api/method/... : CSRF header, JSON, readable errors.
import { csrfToken, setCsrfToken } from "./boot.js";

export class ApiError extends Error {
  constructor(message, { status = 0, excType = "", messages = [] } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.excType = excType;
    this.messages = messages;
  }
}

/** Server messages are HTML snippets (links to the blocking records, <br>): reduce them to plain text. */
export function stripHtml(html) {
  return String(html ?? "")
    .replace(/<\s*br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|div)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function translateServerMessage(message) {
  const value = stripHtml(message);
  if (/is not a valid Email Address/i.test(value)) return "Địa chỉ email không hợp lệ.";
  if (/must be unique/i.test(value)) return "Giá trị này đã tồn tại. Vui lòng nhập giá trị khác.";
  if (/Cannot delete or cancel because|is linked with/i.test(value)) return "Không thể xóa vì bản ghi đang được sử dụng ở nơi khác.";
  if (/top-\d+ common password|password.*too common/i.test(value)) return "Mật khẩu quá phổ biến. Vui lòng chọn mật khẩu khác.";
  if (/^Incorrect password|^Invalid password/i.test(value)) return "Mật khẩu không đúng.";
  if (/^Missing mandatory fields|^This field is required/i.test(value)) return "Vui lòng điền đủ các trường bắt buộc.";
  if (/^Not permitted|^Insufficient Permission/i.test(value)) return "Bạn không có quyền thực hiện thao tác này.";
  return value;
}

/** `_server_messages` is a JSON list of JSON strings: [{"message": "...", "indicator": "red"}, ...]. */
export function serverMessages(payload) {
  const raw = payload && payload._server_messages;
  if (!raw) return [];
  try {
    return JSON.parse(raw)
      .map((entry) => {
        try {
          return translateServerMessage(JSON.parse(entry).message);
        } catch {
          return translateServerMessage(entry);
        }
      })
      .filter(Boolean);
  } catch {
    return [];
  }
}

export function errorMessage(payload, status) {
  const messages = serverMessages(payload);
  if (messages.length) return messages.join("\n");
  if (status === 403) return "Bạn không có quyền thực hiện thao tác này.";
  if (status === 404) return "Không tìm thấy dữ liệu yêu cầu.";
  if (status === 409 || payload?.exc_type === "TimestampMismatchError") {
    return "Bản ghi vừa được người khác thay đổi. Hãy tải lại rồi sửa tiếp.";
  }
  if (status >= 500) return "Máy chủ gặp lỗi. Vui lòng thử lại sau.";
  return "Không thực hiện được yêu cầu.";
}

function toQuery(args) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(args)) {
    if (value === undefined || value === null || value === "") continue;
    params.append(key, typeof value === "object" ? JSON.stringify(value) : String(value));
  }
  return params.toString();
}

export function redirectToLogin() {
  const here = window.location.pathname + window.location.search;
  window.location.assign(`/login?redirect-to=${encodeURIComponent(here)}`);
}

const isForm = (value) => typeof FormData !== "undefined" && value instanceof FormData;

/** Frappe answers a stale CSRF token with this exception. */
export const isCsrfError = (status, payload) => (status === 400 || status === 403) && payload?.exc_type === "CSRFTokenError";

/**
 * Call a whitelisted method. Reads use GET with the arguments in the query string; pass
 * `{ post: true }` for anything that changes data (Frappe requires POST + CSRF for those).
 * A FormData `args` is sent as multipart (files). A stale CSRF token is renewed once.
 */
export async function call(method, args = {}, options = {}) {
  try {
    return await send(method, args, options);
  } catch (error) {
    if (!(error instanceof ApiError) || error.excType !== "CSRFTokenError" || options.renewed) throw error;
    const token = await send(`${BASE}.boot.csrf_token`, {}, { fetcher: options.fetcher });
    setCsrfToken(token);
    return send(method, args, { ...options, renewed: true });
  }
}

async function send(method, args = {}, { post = false, fetcher = fetch, loginOn401 = true } = {}) {
  const headers = { Accept: "application/json", "X-Frappe-CSRF-Token": csrfToken() };
  let url = `/api/method/${method}`;
  const init = { method: post ? "POST" : "GET", headers, credentials: "same-origin" };
  if (post && isForm(args)) {
    init.body = args;
  } else if (post) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(args);
  } else {
    const query = toQuery(args);
    if (query) url += `?${query}`;
  }

  let response;
  try {
    response = await fetcher(url, init);
  } catch {
    if (post) throw new ApiError("Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.");
    // A read can safely be retried once after a brief connection drop.
    await new Promise((resolve) => setTimeout(resolve, 400));
    try {
      response = await fetcher(url, init);
    } catch {
      throw new ApiError("Không kết nối được máy chủ. Kiểm tra mạng rồi thử lại.");
    }
  }
  const payload = await response.json().catch(() => ({}));
  // An expired session sends the user to the login page; a call that legitimately answers 401
  // (a wrong current password) opts out and shows its message instead.
  if (loginOn401 && (response.status === 401 || (response.status === 403 && payload?.exc_type === "AuthenticationError"))) {
    redirectToLogin();
  }
  if (!response.ok) {
    if (isCsrfError(response.status, payload)) {
      throw new ApiError("Phiên làm việc đã đổi: đang thử lại.", { status: response.status, excType: "CSRFTokenError" });
    }
    throw new ApiError(errorMessage(payload, response.status), {
      status: response.status,
      excType: payload?.exc_type || "",
      messages: serverMessages(payload),
    });
  }
  return payload.message;
}

const BASE = "project_manager.project_manager.api";
export const api = {
  boot: () => call(`${BASE}.boot.get_boot`),
  describe: (doctype) => call(`${BASE}.meta.get_doctype_ui`, { doctype }),
  list: (doctype, params = {}) => call(`${BASE}.crud.get_list`, { doctype, ...params }),
  get: (doctype, name) => call(`${BASE}.crud.get`, { doctype, name }),
  save: (doctype, values, name = null) => call(`${BASE}.crud.save`, { doctype, values, name }, { post: true }),
  remove: (doctype, name) => call(`${BASE}.crud.delete`, { doctype, name }, { post: true }),
  linkSearch: (doctype, txt = "", filters = null) => call(`${BASE}.crud.link_search`, { doctype, txt, filters }),
  treeChildren: (doctype, parent = null, filters = null) =>
    call(`${BASE}.crud.tree_children`, { doctype, parent, filters }),
  users: {
    roles: () => call(`${BASE}.users.roles_info`),
    list: (params = {}) => call(`${BASE}.users.list_users`, params),
    get: (name) => call(`${BASE}.users.get_user`, { name }),
    save: (values, name = null) => call(`${BASE}.users.save_user`, { values, name }, { post: true }),
    setEnabled: (name, enabled) => call(`${BASE}.users.set_enabled`, { name, enabled: enabled ? 1 : 0 }, { post: true }),
    link: (name) => call(`${BASE}.users.issue_password_link`, { name }, { post: true }),
    remove: (name) => call(`${BASE}.users.delete_user`, { name }, { post: true }),
    matrix: () => call(`${BASE}.users.role_matrix`),
  },
  permissions: {
    list: () => call(`${BASE}.permissions.list_groups`),
    get: (role) => call(`${BASE}.permissions.get_group`, { role }),
    save: (role, values) => call(`${BASE}.permissions.save_group`, { role, values }, { post: true }),
    create: (values) => call(`${BASE}.permissions.create_group`, values, { post: true }),
    remove: (role) => call(`${BASE}.permissions.delete_group`, { role }, { post: true }),
    reset: (role) => call(`${BASE}.permissions.reset_group`, { role }, { post: true }),
  },
  logs: {
    options: () => call(`${BASE}.logs.filter_options`),
    list: (params = {}) => call(`${BASE}.logs.list_logs`, params),
    get: (name) => call(`${BASE}.logs.get_log`, { name }),
    previewPurge: (before, types) => call(`${BASE}.logs.preview_purge`, { before, activity_types: types }),
    purge: (before, confirmCount, types) => call(`${BASE}.logs.purge`, { before, confirm_count: confirmCount, activity_types: types }, { post: true }),
  },
  monitor: () => call(`${BASE}.admin.monitor`),
  alerts: {
    mine: (state = "open", limit = 100) => call(`${BASE}.alerts.mine`, { state, limit }),
    ofProject: (project, state = "open") => call(`${BASE}.alerts.of_project`, { project, state }),
    acknowledge: (name, note = "") => call(`${BASE}.alerts.acknowledge`, { name, note }, { post: true }),
    preference: () => call(`${BASE}.alerts.preference`),
    savePreference: (values) => call(`${BASE}.alerts.save_preference`, { values }, { post: true }),
    portfolio: (params = {}) => call(`${BASE}.alerts.portfolio`, params),
    phaseState: (project) => call(`${BASE}.alerts.phase_state`, { project }),
    passPhase: (phase, note = "") => call(`${BASE}.alerts.pass_phase`, { phase, note }, { post: true }),
  },
  people: {
    workload: (params = {}) => call(`${BASE}.people.workload_overview`, params),
    cell: (user, week) => call(`${BASE}.people.workload_cell`, { user, week }),
    saveCapacity: (values) => call(`${BASE}.people.save_capacity`, values, { post: true }),
    deleteCapacity: (name) => call(`${BASE}.people.delete_capacity`, { name }, { post: true }),
    performance: (params = {}) => call(`${BASE}.people.performance_overview`, params),
    person: (user, params = {}) => call(`${BASE}.people.performance_person`, { user, ...params }),
    teams: () => call(`${BASE}.people.teams`),
  },
  projects: {
    list: (params = {}) => call(`${BASE}.projects.list_projects`, params),
    overview: (project) => call(`${BASE}.projects.overview`, { project }),
    create: (values, template = null) => call(`${BASE}.projects.create`, { values, template }, { post: true }),
    update: (project, values) => call(`${BASE}.projects.update`, { project, values }, { post: true }),
    members: (project) => call(`${BASE}.projects.members`, { project }),
    addMember: (project, values) => call(`${BASE}.projects.add_member`, { project, ...values }, { post: true }),
    setMember: (name, values) => call(`${BASE}.projects.set_member`, { name, values }, { post: true }),
    candidates: (project, txt = "") => call(`${BASE}.projects.member_candidates`, { project, txt }),
  },
  wbs: {
    children: (project, parent = null, start = 0) => call(`${BASE}.wbs.children`, { project, parent, start }),
    add: (project, values) => call(`${BASE}.wbs.add`, { project, ...values }, { post: true }),
    update: (task, values, reason = "") => call(`${BASE}.wbs.update`, { task, values, reason }, { post: true }),
    setGateMode: (task, mode) => call(`${BASE}.wbs.update`, { task, values: { pm_gate_mode: mode } }, { post: true }),
    move: (task, parent, index = null, reason = "") => call(`${BASE}.wbs.move`, { task, parent, index, reason }, { post: true }),
    cancel: (task, reason) => call(`${BASE}.wbs.cancel`, { task, reason }, { post: true }),
    remove: (task) => call(`${BASE}.wbs.delete`, { task }, { post: true }),
    importPreview: (project, content) => call(`${BASE}.wbs.import_preview`, { project, content }, { post: true }),
    importRun: (project, content, parent = null) => call(`${BASE}.wbs.import_run`, { project, content, parent }, { post: true }),
    importTemplateUrl: () => `/api/method/${BASE}.wbs.import_template`,
  },
  schedule: {
    gantt: (project, baseline = null) => call(`${BASE}.schedule.gantt`, { project, baseline }),
    calendar: (project, first, last) => call(`${BASE}.schedule.calendar`, { project, first, last }),
    dependencies: (task) => call(`${BASE}.schedule.dependencies`, { task }),
    searchTasks: (project, txt = "", exclude = null) => call(`${BASE}.schedule.search_tasks`, { project, txt, exclude }),
    addDependency: (predecessor, successor, kind = "FS", lag = 0) => call(`${BASE}.schedule.add_dependency`, { predecessor, successor, kind, lag }, { post: true }),
    updateDependency: (name, kind, lag = 0) => call(`${BASE}.schedule.update_dependency`, { name, kind, lag }, { post: true }),
    removeDependency: (name) => call(`${BASE}.schedule.remove_dependency`, { name }, { post: true }),
    previewMove: (task, start = null, end = null) => call(`${BASE}.schedule.preview_move`, { task, start, end }, { post: true }),
    applyMove: (task, start = null, end = null, reason = "") => call(`${BASE}.schedule.apply_move`, { task, start, end, reason }, { post: true }),
    previewConflicts: (project) => call(`${BASE}.schedule.preview_conflicts`, { project }),
    applyConflicts: (project, reason = "") => call(`${BASE}.schedule.apply_conflicts`, { project, reason }, { post: true }),
    listBaselines: (project) => call(`${BASE}.schedule.list_baselines`, { project }),
    captureBaseline: (project, title = "", note = "") => call(`${BASE}.schedule.capture_baseline`, { project, title, note }, { post: true }),
    setPrimaryBaseline: (name) => call(`${BASE}.schedule.set_primary_baseline`, { name }, { post: true }),
    removeBaseline: (name) => call(`${BASE}.schedule.remove_baseline`, { name }, { post: true }),
    compareBaseline: (name, lateOnly = 0) => call(`${BASE}.schedule.compare_baseline`, { name, late_only: lateOnly }),
  },
  forms: {
    templates: () => call(`${BASE}.forms.templates_overview`),
    inUse: () => call(`${BASE}.forms.templates_in_use`),
    template: (name) => call(`${BASE}.forms.template`, { name }),
    templateCreate: (code, values, rows = null) => call(`${BASE}.forms.template_create`, { code, values, rows }, { post: true }),
    templateSave: (name, values, rows = null) => call(`${BASE}.forms.template_save`, { name, values, rows }, { post: true }),
    templateActivate: (name) => call(`${BASE}.forms.template_activate`, { name }, { post: true }),
    templateRetire: (name) => call(`${BASE}.forms.template_retire`, { name }, { post: true }),
    templateNewVersion: (name) => call(`${BASE}.forms.template_new_version`, { name }, { post: true }),
    templateRemove: (name) => call(`${BASE}.forms.template_remove`, { name }, { post: true }),
    start: (templateCode, project = null, task = null) => call(`${BASE}.forms.start`, { template_code: templateCode, project, task }, { post: true }),
    detail: (name) => call(`${BASE}.forms.detail`, { name }),
    save: (name, data) => call(`${BASE}.forms.save`, { name, data }, { post: true }),
    submit: (name, data = null) => call(`${BASE}.forms.submit`, { name, data }, { post: true }),
    approve: (name, note = "") => call(`${BASE}.forms.approve`, { name, note }, { post: true }),
    sendBack: (name, note) => call(`${BASE}.forms.send_back`, { name, note }, { post: true }),
    discard: (name) => call(`${BASE}.forms.discard`, { name }, { post: true }),
    attach: (name, content, filename = "") => call(`${BASE}.forms.attach`, { name, content, filename }, { post: true }),
    list: (params = {}) => call(`${BASE}.forms.list_forms`, params),
    waiting: (limit = 20) => call(`${BASE}.forms.waiting_for_me`, { limit }),
    forTask: (task) => call(`${BASE}.forms.for_task`, { task }),
    gateAdd: (task, formCode, note = "") => call(`${BASE}.forms.gate_add`, { task, form_code: formCode, note }, { post: true }),
    gateRemove: (name) => call(`${BASE}.forms.gate_remove`, { name }, { post: true }),
    pdfUrl: (name) => `/api/method/${BASE}.forms.pdf?name=${encodeURIComponent(name)}`,
    exportUrl: (project, code) => `/api/method/${BASE}.forms.export?project=${encodeURIComponent(project)}&template_code=${encodeURIComponent(code)}`,
  },
  tasks: {
    mine: (params = {}) => call(`${BASE}.tasks.my_tasks`, params),
    kanban: (project, params = {}) => call(`${BASE}.tasks.kanban`, { project, ...params }),
    whoDoesWhat: (project) => call(`${BASE}.tasks.who_does_what`, { project }),
    detail: (task) => call(`${BASE}.tasks.detail`, { task }),
    assign: (task, values) => call(`${BASE}.tasks.assign`, { task, ...values }, { post: true }),
    respond: (assignment, accept, reason = "") => call(`${BASE}.tasks.respond`, { assignment, accept: accept ? 1 : 0, reason }, { post: true }),
    revoke: (assignment, reason) => call(`${BASE}.tasks.revoke`, { assignment, reason }, { post: true }),
    report: (task, values) => call(`${BASE}.tasks.report`, { task, ...values }, { post: true }),
    review: (task, approve, note = "") => call(`${BASE}.tasks.review`, { task, approve: approve ? 1 : 0, note }, { post: true }),
    move: (task, status, values = {}) => call(`${BASE}.tasks.move`, { task, status, ...values }, { post: true }),
  },
  activity: {
    feed: (doctype, name, params = {}) => call(`${BASE}.activity.feed`, { reference_doctype: doctype, reference_name: name, ...params }),
    entry: (name) => call(`${BASE}.activity.entry`, { name }),
    people: (doctype, name, search = "") => call(`${BASE}.activity.people`, { reference_doctype: doctype, reference_name: name, search }),
    post: (doctype, name, values) => call(`${BASE}.activity.post`, { reference_doctype: doctype, reference_name: name, ...values }, { post: true }),
    hide: (name) => call(`${BASE}.activity.hide`, { name }, { post: true }),
    follow: (doctype, name, watching) => call(`${BASE}.activity.follow`, { reference_doctype: doctype, reference_name: name, watching: watching ? 1 : 0 }, { post: true }),
    markRead: (doctype, name, upto) => call(`${BASE}.activity.mark_read`, { reference_doctype: doctype, reference_name: name, upto }, { post: true }),
    search: (query, params = {}) => call(`${BASE}.activity.search`, { query, ...params }),
  },
  media: {
    upload: (form) => call(`${BASE}.media.upload`, form, { post: true }),
    gallery: (project, params = {}) => call(`${BASE}.media.gallery`, { project, ...params }),
    url: (name, size = "thumb") => `/api/method/${BASE}.media.file?name=${encodeURIComponent(name)}&size=${size}`,
  },
  documents: {
    list: (project, params = {}) => call(`${BASE}.documents.listing`, { project, ...params }),
    detail: (name) => call(`${BASE}.documents.detail`, { name }),
    create: (form) => call(`${BASE}.documents.create`, form, { post: true }),
    addVersion: (form) => call(`${BASE}.documents.add_version`, form, { post: true }),
    approve: (name, versionNo) => call(`${BASE}.documents.approve`, { name, version_no: versionNo }, { post: true }),
    url: (name, version = null, inline = false) =>
      `/api/method/${BASE}.documents.download?name=${encodeURIComponent(name)}${version ? `&version=${version}` : ""}${inline ? "&inline=1" : ""}`,
  },
  notifications: {
    list: (params = {}) => call(`${BASE}.account.get_notifications`, params),
    markRead: (names = []) => call(`${BASE}.account.mark_notifications_read`, { names }, { post: true }),
  },
  // Own endpoint: a wrong current password must not end the session (Frappe's update_password would).
  changePassword: (oldPassword, newPassword) =>
    call(`${BASE}.account.change_password`, { old_password: oldPassword, new_password: newPassword }, { post: true, loginOn401: false }),
};
