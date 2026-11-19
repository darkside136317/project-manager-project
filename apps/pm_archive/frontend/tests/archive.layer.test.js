// Tests of the archive layer's screens, run by the core's vitest (vite.config.js includes *.layer.test.js).
import { flushPromises, mount } from "@vue/test-utils";
import { computed, ref } from "vue";
import { describe, expect, it, vi } from "vitest";

vi.mock("@pm/lib/api.js", async (importOriginal) => {
  const real = await importOriginal();
  return { ...real, call: vi.fn() };
});

import { call } from "@pm/lib/api.js";
import module from "../pm-module.js";
import ArchiveTab from "../src/ArchiveTab.vue";
import { archive, moved, periodText, placePath, retentionText, sizeText, stateClass } from "../src/archive.js";

const provide = () => ({ project: { name: computed(() => "P-1"), overview: ref({ can: {} }), openTask: vi.fn(), version: ref(0), reload: vi.fn() } });
const stubs = { RouterLink: { props: ["to"], template: "<a><slot /></a>" } };

const overview = (can = {}, files = []) => ({
  project: { name: "P-1", project_name: "Nhà xưởng" }, files, missing: [{ code: "02.03", title: "Dữ liệu dự án" }],
  counts: { "Đang lập": 1, "Chờ nộp lưu": 0, "Đã nộp lưu": 0 },
  can: { manage: false, file: false, request: false, ...can },
});
const FILE = { name: "HSLT-00001", file_number: "XD01-01", title: "Hợp đồng — Nhà xưởng", category_label: "01.01 Hồ sơ pháp lý",
               status: "Chờ nộp lưu", access_mode: "Nội bộ dự án", item_count: 2, retention: "20",
               start_date: "2026-11-02", end_date: "2026-11-16" };

describe("archive module", () => {
  it("adds its tab after the documents and its pages", () => {
    expect(module.name).toBe("archive");
    expect(module.projectTabs.map((tab) => [tab.slug, tab.after])).toEqual([["ho-so-luu-tru", "tai-lieu"]]);
    expect(module.routes.map((route) => route.path)).toEqual(["/luu-tru", "/luu-tru/:name"]);
  });

  it("says what a file holds in words", () => {
    expect(retentionText("20")).toBe("20 năm");
    expect(retentionText("Vĩnh viễn")).toBe("Vĩnh viễn");
    expect(periodText("2026-11-02", "2026-11-16")).toBe("02/11/2026 – 16/11/2026");
    expect(periodText("2026-11-02", "2026-11-02")).toBe("02/11/2026");
    expect(sizeText(1536)).toBe("2 KB");
    expect(sizeText(5 * 1024 * 1024)).toBe("5,0 MB");
    expect(stateClass("Đã nộp lưu")).toBe("badge badge-success");
    expect(stateClass("Chờ nộp lưu")).toBe("badge badge-warning");
    expect(moved([1, 2, 3], 2, -1)).toEqual([2, 1, 3]);
    expect(moved([1, 2, 3], 3, 1)).toEqual([1, 2, 3]);
    const places = [{ name: "A", title: "Kho A" }, { name: "G1", title: "Giá 1", parent: "A" }, { name: "H3", title: "Hộp 3", parent: "G1" }];
    expect(placePath(places, "H3")).toBe("Kho A › Giá 1 › Hộp 3");
  });

  it("sends a scan as a form with its description", async () => {
    call.mockReset();
    call.mockResolvedValue({ file: "HSLT-00001" });
    const scan = new File(["%PDF"], "bien-ban.pdf", { type: "application/pdf" });
    await archive.upload("HSLT-00001", scan, { title: "Biên bản bàn giao", page_count: 3, author: "" });
    const [method, form, options] = call.mock.calls[0];
    expect(method).toMatch(/archive\.upload$/);
    expect(options).toEqual({ post: true });
    expect([form.get("file"), form.get("title"), form.get("page_count"), form.has("author")]).toEqual(["HSLT-00001", "Biên bản bàn giao", "3", false]);
    expect(form.get("file_content").name).toBe("bien-ban.pdf");
  });
});

describe("the project tab", () => {
  it("shows the files, what is missing, and the manager's buttons", async () => {
    call.mockReset();
    call.mockResolvedValue(overview({ manage: true, request: true }, [FILE]));
    const wrapper = mount(ArchiveTab, { global: { provide: provide(), stubs } });
    await flushPromises();
    expect(wrapper.findAll("[data-archive-file]")).toHaveLength(1);
    expect(wrapper.find("[data-archive-file]").text()).toContain("XD01-01");
    expect(wrapper.find("[data-missing]").text()).toContain("02.03 Dữ liệu dự án");
    expect(wrapper.find("[data-compile]").exists()).toBe(true);
    expect(wrapper.find("[data-file-all]").exists()).toBe(false);  // the archivist's
    call.mockResolvedValueOnce({ added: 3, files: [] }).mockResolvedValue(overview({ manage: true }, [FILE]));
    await wrapper.find("[data-compile]").trigger("click");
    await flushPromises();
    expect(call.mock.calls.some(([method, args]) => method.endsWith("compile_files") && args.project === "P-1")).toBe(true);
  });

  it("gives the archivist the filing of the waiting files", async () => {
    call.mockReset();
    call.mockResolvedValue(overview({ file: true }, [FILE]));
    const wrapper = mount(ArchiveTab, { global: { provide: provide(), stubs } });
    await flushPromises();
    call.mockResolvedValueOnce({ queued: ["HSLT-00001"], skipped: [] }).mockResolvedValue(overview({ file: true }, [FILE]));
    await wrapper.find("[data-file-all]").trigger("click");
    await flushPromises();
    expect(call.mock.calls.find(([method]) => method.endsWith("file_records"))[1]).toEqual({ names: ["HSLT-00001"] });
  });

  it("says so when the user may not see the archive", async () => {
    call.mockReset();
    call.mockRejectedValue(new Error("Bạn không xem được hồ sơ lưu trữ của dự án này"));
    const wrapper = mount(ArchiveTab, { global: { provide: provide(), stubs } });
    await flushPromises();
    expect(wrapper.find("[data-archive-error]").text()).toContain("không xem được");
  });
});
