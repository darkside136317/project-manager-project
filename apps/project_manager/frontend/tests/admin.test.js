import { describe, expect, it } from "vitest";
import {
  READ_CHOSEN, WRITE_CHOSEN, absoluteLink, accessKey, accessProblem, blankUser, canEditUser, changedValues, cleanLogFilters,
  diskTone, latestPurgeDate, logDownloadUrl, permissionText, prettyJson, purgeConfirmed, queueText, serviceTone, sortRoles,
  toggleValue, userProblem, userToForm,
} from "../src/lib/admin.js";

describe("administration helpers", () => {
  const original = { name: "an@x.vn", first_name: "An", last_name: "Nguyen", phone: "", enabled: 1, roles: ["PM Staff", "PM Admin"], groups: ["Nhóm A"], protected: false };

  it("starts a user form blank and fills it from an account", () => {
    expect(blankUser()).toEqual({ email: "", first_name: "", last_name: "", phone: "", enabled: 1, roles: [], groups: [],
      access: { read_scope: "Chỉ dự án tham gia", write_scope: "Theo vai trò trong dự án", read_projects: [], write_projects: [] } });
    expect(userToForm(original)).toMatchObject({ email: "an@x.vn", first_name: "An", roles: ["PM Staff", "PM Admin"] });
  });

  it("sends the scope only when it changed, and checks it before sending", () => {
    const form = userToForm(original);
    expect(changedValues(original, form)).toEqual({});
    const chosen = { ...form.access, read_scope: READ_CHOSEN, read_projects: [{ project: "PROJ-0001", project_name: "Nhà A" }] };
    expect(changedValues(original, { ...form, access: chosen })).toEqual({ access: chosen });
    // the names of the projects are not part of the scope: only their codes are compared
    const renamed = { ...chosen, read_projects: [{ project: "PROJ-0001", project_name: "Tên khác" }] };
    expect(accessKey(renamed)).toBe(accessKey(chosen));
    expect(accessProblem({ ...form.access, read_scope: READ_CHOSEN })).toContain("ít nhất một dự án");
    expect(accessProblem({ ...chosen, write_scope: WRITE_CHOSEN, write_projects: [{ project: "PROJ-0002", project_name: "Cầu B" }] })).toContain("Cầu B");
    expect(accessProblem(chosen)).toBe("");
    expect(userProblem({ ...form, access: { ...form.access, read_scope: READ_CHOSEN } }, false)).toContain("dự án");
  });

  it("turns a set-password path into a full address", () => {
    expect(absoluteLink("/update-password?key=x", "http://pm.vn")).toBe("http://pm.vn/update-password?key=x");
    expect(absoluteLink("https://a.vn/x", "http://pm.vn")).toBe("https://a.vn/x");
  });

  it("sends only what changed, whatever order roles and groups are in", () => {
    const form = userToForm(original);
    expect(changedValues(original, form)).toEqual({});
    expect(changedValues(original, { ...form, roles: ["PM Admin", "PM Staff"] })).toEqual({});
    expect(changedValues(original, { ...form, phone: "0912", enabled: 0 })).toEqual({ phone: "0912", enabled: 0 });
    expect(changedValues(original, { ...form, roles: ["PM Staff"], groups: [] })).toEqual({ roles: ["PM Staff"], groups: [] });
  });

  it("orders roles and toggles values without touching the old list", () => {
    expect(sortRoles(["PM Staff", "PM Admin", "PM Director"])).toEqual(["PM Admin", "PM Director", "PM Staff"]);
    const list = ["a"];
    expect(toggleValue(list, "b")).toEqual(["a", "b"]);
    expect(toggleValue(["a", "b"], "a")).toEqual(["b"]);
    expect(list).toEqual(["a"]);
  });

  it("explains why a user form cannot be sent", () => {
    expect(userProblem({ email: "bad", first_name: "x" }, true)).toBe("Nhập địa chỉ email hợp lệ");
    expect(userProblem({ email: "a@b.vn", first_name: " " }, true)).toBe("Nhập tên");
    expect(userProblem({ email: "", first_name: "x" }, false)).toBe("");
  });

  it("lets only a System Manager change an account that holds that role", () => {
    const me = { name: "admin@x.vn", roles: ["PM Admin"] };
    expect(canEditUser(original, me)).toBe(true);
    expect(canEditUser({ ...original, protected: true }, me)).toBe(false);
    expect(canEditUser({ ...original, protected: true }, { ...me, roles: ["System Manager"] })).toBe(true);
    expect(canEditUser(null, me)).toBe(false);
  });

  it("says what a role may do in words", () => {
    expect(permissionText({ read: 1, write: 1, create: 0, delete: 0 })).toBe("Xem, Sửa");
    expect(permissionText({ read: 1, create: 1, write: 1, delete: 1 })).toBe("Xem, Thêm, Sửa, Xóa");
    expect(permissionText({})).toBe("Không");
    expect(permissionText(undefined)).toBe("Không");
  });

  it("builds the log filters and the download link from the filled fields only", () => {
    expect(cleanLogFilters({ activity_type: "Xem", user: "", search: " abc ", date_from: "2026-01-01", extra: "x" })).toEqual({ activity_type: "Xem", search: "abc", date_from: "2026-01-01" });
    const url = new URL(logDownloadUrl({ user: "a@x.vn", search: "" }), "http://x");
    expect(url.pathname).toContain("logs.download_logs");
    expect(url.searchParams.get("user")).toBe("a@x.vn");
    expect(url.searchParams.has("search")).toBe(false);
  });

  it("keeps the last week out of a clean-up and wants the count typed back", () => {
    expect(latestPurgeDate(7, new Date(2026, 9, 8))).toBe("2026-10-01");
    expect(latestPurgeDate(7, new Date(2026, 0, 3))).toBe("2025-12-27");
    expect(purgeConfirmed("1.234", 1234)).toBe(true);
    expect(purgeConfirmed("1233", 1234)).toBe(false);
    expect(purgeConfirmed("", 0)).toBe(false);
  });

  it("pretty-prints log data and tolerates text that is not JSON", () => {
    expect(prettyJson('{"a":1}')).toBe('{\n  "a": 1\n}');
    expect(prettyJson("not json")).toBe("not json");
    expect(prettyJson("")).toBe("");
  });

  it("colours the monitor figures", () => {
    expect(serviceTone({ ok: true })).toBe("success");
    expect(serviceTone({ ok: false })).toBe("danger");
    expect(serviceTone({ ok: true, disabled: true })).toBe("muted");
    expect(diskTone({ used_percent: 95 })).toBe("danger");
    expect(diskTone({ used_percent: 80 })).toBe("warning");
    expect(diskTone({ used_percent: 20 })).toBe("success");
    expect(diskTone(null)).toBe("muted");
    expect(queueText([{ name: "long", jobs: 1500 }, { name: "short", jobs: 0 }])).toBe("long: 1.500 · short: 0");
    expect(queueText(null)).toBe("—");
  });
});
