// The archive layer's calls to its API, and what its screens show besides drawing: the colour of a state, sizes, the
// retention, the order of items after a move up or down.
import { call } from "@pm/lib/api.js";

const M = "pm_archive.pm_archive.api.archive";

export const archive = {
  overview: (project) => call(`${M}.overview`, { project }),
  file: (name, start = 0) => call(`${M}.file_detail`, { name, start }),
  listing: (filters = {}, before = null) => call(`${M}.listing`, { filters, before }),
  storages: () => call(`${M}.storages`),
  checks: () => call(`${M}.checks`),
  compile: (project) => call(`${M}.compile_files`, { project }, { post: true }),
  requestFiling: (project) => call(`${M}.request_filing`, { project }, { post: true }),
  reorder: (file, order) => call(`${M}.reorder`, { file, order }, { post: true }),
  describe: (item, values) => call(`${M}.describe`, { item, values }, { post: true }),
  exclude: (item, excluded) => call(`${M}.exclude`, { item, excluded: excluded ? 1 : 0 }, { post: true }),
  move: (item, target) => call(`${M}.move`, { item, target }, { post: true }),
  upload: (file, upload, values = {}) => {
    const form = new FormData();
    form.append("file", file);
    form.append("file_content", upload, upload.name);
    for (const [key, value] of Object.entries(values)) if (value !== "" && value != null) form.append(key, value);
    return call(`${M}.upload`, form, { post: true });
  },
  setPaper: (file, storage, box, note) => call(`${M}.set_paper`, { file, storage, box, note }, { post: true }),
  fileRecords: (names) => call(`${M}.file_records`, { names }, { post: true }),
  startCheck: (file = null) => call(`${M}.start_check`, { file }, { post: true }),
  exportPackage: (file) => call(`${M}.export_package`, { file }, { post: true }),
  downloadUrl: (item, inline = false) => `/api/method/${M}.download?item=${encodeURIComponent(item)}${inline ? "&inline=1" : ""}`,
  packageUrl: (file) => `/api/method/${M}.download_package?file=${encodeURIComponent(file)}`,
};

export const DRAFT = "Đang lập";
export const WAITING = "Chờ nộp lưu";
export const FILED = "Đã nộp lưu";
export const RESTRICTED = "Hạn chế";
export const STATES = [DRAFT, WAITING, FILED];

const TONE = { [DRAFT]: "info", [WAITING]: "warning", [FILED]: "success", "Hoàn thành": "success", "Có lỗi": "danger", "Đang chạy": "info" };
export const stateClass = (state) => `badge badge-${TONE[state] || "muted"}`;

export function sizeText(bytes) {
  const size = Number(bytes) || 0;
  if (size >= 1024 ** 3) return `${(size / 1024 ** 3).toFixed(1).replace(".", ",")} GB`;
  if (size >= 1024 ** 2) return `${(size / 1024 ** 2).toFixed(1).replace(".", ",")} MB`;
  if (size >= 1024) return `${Math.round(size / 1024)} KB`;
  return `${size} B`;
}

export const retentionText = (value) => (!value ? "" : /^\d+$/.test(String(value)) ? `${value} năm` : value);

export function dayText(value) {
  if (!value) return "";
  const [year, month, day] = String(value).slice(0, 10).split("-");
  return `${day}/${month}/${year}`;
}

export function periodText(start, end) {
  const first = dayText(start);
  const last = dayText(end);
  return first === last ? first : [first, last].filter(Boolean).join(" – ");
}

/** The item names in their order after moving `name` one place up (-1) or down (+1). */
export function moved(names, name, step) {
  const order = [...names];
  const at = order.indexOf(name);
  const to = at + step;
  if (at < 0 || to < 0 || to >= order.length) return order;
  [order[at], order[to]] = [order[to], order[at]];
  return order;
}

/** "Kho A › Giá 1 › Hộp 3" for a storage place, from the flat list of places. */
export function placePath(storages, name) {
  const byName = new Map(storages.map((place) => [place.name, place]));
  const parts = [];
  let place = byName.get(name);
  while (place && parts.length < 10) {
    parts.unshift(place.title);
    place = byName.get(place.parent);
  }
  return parts.join(" › ");
}
