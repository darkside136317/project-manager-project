// Boot data written by www/pm.py into window.__PM_BOOT__, with safe defaults for tests and
// for a page rendered without it.
const DEFAULTS = {
  user: "Guest",
  full_name: "",
  company: "",
  lang: "vi",
  version: "",
  csrf_token: "",
};

export function readBoot(source = globalThis.window?.__PM_BOOT__) {
  return { ...DEFAULTS, ...(source && typeof source === "object" ? source : {}) };
}

export const boot = readBoot();
