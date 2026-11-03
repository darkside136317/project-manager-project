// Data the Frappe host page (www/pm.py) embeds at start-up, with safe defaults for tests and for a page rendered
// without it.
const empty = {
  csrf_token: "",
  user: { name: "", full_name: "", roles: [], capabilities: [], is_admin: false, all_projects: false },
  company: "",
  version: "",
  home: "/pm",
  lang: "vi",
  nav: [],
  masters: [],
  admin: [],
};

export function readBoot(source = typeof window !== "undefined" ? window.__PM_BOOT__ : undefined) {
  const data = source && typeof source === "object" ? source : {};
  return { ...empty, ...data, user: { ...empty.user, ...(data.user || {}) } };
}

export const boot = readBoot();

export const csrfToken = () => boot.csrf_token;

export const hasCapability = (code) => (boot.user.capabilities || []).includes(code);

export function masterBySlug(slug, source = "masters") {
  return (boot[source] || []).find((m) => m.slug === slug) || null;
}

export function initials(name) {
  const parts = String(name || "?").trim().split(/\s+/);
  return ((parts[0]?.[0] || "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}
