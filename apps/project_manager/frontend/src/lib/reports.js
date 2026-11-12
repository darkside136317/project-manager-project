// Helpers of the report screens: filters as form fields, cells as text, and the links to a report's output.
// Copied from document_manager (frontend/src/lib/reports.js, see docs/NGUON_GOC.md); money cells added.
import { formatDate, formatDateTime, formatNumber } from "./format.js";

/** A filter the server declares, as the field the generic form input draws. */
export function filterField(spec) {
  const field = { fieldname: spec.fieldname, label: spec.label, fieldtype: spec.fieldtype, reqd: 0, read_only: false };
  if (spec.fieldtype === "Select") {
    field.options = `${spec.default ? "" : "\n"}${(spec.options || []).join("\n")}`;
  } else if (spec.options) {
    field.options = spec.options;
  }
  return field;
}

/** The starting values of a filter form: the declared defaults, or what the address already says. */
export function initialFilters(specs, query = {}) {
  const values = {};
  for (const spec of specs) {
    const fromQuery = query[spec.fieldname];
    if (fromQuery !== undefined && fromQuery !== "") values[spec.fieldname] = spec.fieldtype === "Int" || spec.fieldtype === "Check" ? Number(fromQuery) : String(fromQuery);
    else values[spec.fieldname] = spec.default ?? (spec.fieldtype === "Check" ? 0 : "");
  }
  return values;
}

/** Only the filters that say something (what is sent to the server and kept in the address). */
export function cleanFilters(values) {
  const out = {};
  for (const [name, value] of Object.entries(values || {})) {
    if (value === "" || value === null || value === undefined || value === 0 || value === false) continue;
    out[name] = value;
  }
  return out;
}

/** The names of the filters that hang on `name`: they restart when it changes. */
export function dependents(specs, name) {
  return specs.filter((spec) => spec.depends === name).map((spec) => spec.fieldname);
}

/** Filter for the search of a Link filter: the records under the value of the filter it depends on. */
export function linkFilter(spec, values) {
  return spec.depends && values[spec.depends] ? { [spec.depends]: values[spec.depends] } : null;
}

/** Change one value of a filter form and clear the filters that depend on it (a new object, never the old one). */
export function withFilter(specs, values, name, value) {
  const next = { ...values, [name]: value };
  for (const child of dependents(specs, name)) {
    next[child] = specs.find((s) => s.fieldname === child)?.default ?? "";
    Object.assign(next, ...dependents(specs, child).map((grand) => ({ [grand]: "" })));
  }
  return next;
}

/** What a report cell shows. */
export function formatCell(column, value) {
  if (value === null || value === undefined || value === "") return "";
  switch (column.fieldtype) {
    case "Int":
      return formatNumber(value);
    case "Float":
      return new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0);
    case "Percent":
      return `${new Intl.NumberFormat("vi-VN", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Number(value) || 0)}%`;
    case "Currency":
      return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(Math.round(Number(value) || 0));
    case "Date":
      return formatDate(value);
    case "Datetime":
      return formatDateTime(value);
    default:
      return String(value);
  }
}

/** The route a cell links to ("/du-an/{project}" filled from the row), or "" when the column has no link. */
export function routeOf(column, row) {
  if (!column.link) return "";
  if (column.link === "{route}") return typeof row.route === "string" && row.route.startsWith("/") && !row.route.includes("//") ? row.route : "";
  const route = column.link.replace(/\{(\w+)\}/g, (_, key) => encodeURIComponent(row[key] ?? ""));
  return /\{|\/$/.test(route) || route.includes("//") ? "" : route;
}

const BASE = "/api/method/project_manager.project_manager.api.reports";

function outputUrl(method, slug, filters, extra) {
  const params = new URLSearchParams({ slug, ...extra });
  const clean = cleanFilters(filters);
  if (Object.keys(clean).length) params.set("filters", JSON.stringify(clean));
  return `${BASE}.${method}?${params}`;
}

export const downloadUrl = (slug, filters, format = "xlsx") => outputUrl("download_report", slug, filters, { format });
export const printUrl = (slug, filters, format = "html") => outputUrl("print_report", slug, filters, { format });

export const WEEKDAYS = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"];
export const FREQUENCIES = ["Hằng ngày", "Hằng tuần", "Hằng tháng"];

/** "Hằng tuần, Thứ Hai lúc 7 giờ" of a subscription. */
export function scheduleText(row) {
  const hour = `lúc ${Number(row.hour ?? 7)} giờ`;
  if (row.frequency === "Hằng tuần") return `Hằng tuần, ${row.weekday || WEEKDAYS[0]} ${hour}`;
  if (row.frequency === "Hằng tháng") return `Ngày ${Number(row.day_of_month || 1)} hằng tháng ${hour}`;
  return `Hằng ngày ${hour}`;
}
