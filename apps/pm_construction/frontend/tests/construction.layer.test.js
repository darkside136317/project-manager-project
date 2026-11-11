// Tests of the construction layer's screens, run by the core's vitest (vite.config.js includes *.layer.test.js).
import { describe, expect, it, vi } from "vitest";

vi.mock("@pm/lib/api.js", async (importOriginal) => {
  const real = await importOriginal();
  return { ...real, call: vi.fn(), api: { ...real.api, media: { ...real.api.media, upload: vi.fn() } } };
});

import { api, call } from "@pm/lib/api.js";
import { KINDS, SENDERS } from "@pm/lib/sync.js";
import module from "../pm-module.js";
import { boqRows, diaryRows, moneyText, percentText, qtyText, share, today } from "../src/construction.js";

describe("construction module", () => {
  it("adds its tabs and its kind of queued item", () => {
    expect(module.name).toBe("construction");
    expect(module.projectTabs.map((tab) => [tab.slug, tab.after])).toEqual([["boq", "cong-viec"], ["nhat-ky", "trao-doi"],
      ["vat-tu", "nhat-ky"], ["may", "vat-tu"], ["cham-cong", "may"], ["nghiem-thu", "tai-lieu"], ["chi-phi", "nghiem-thu"]]);
    expect(KINDS.diary.label).toBe("Nhật ký thi công");
    expect(KINDS.diary.summary({ payload: { rows: [{}, {}] }, photos: [{}] })).toBe("2 công tác · 1 ảnh");
  });

  it("sends a queued diary: save, its photos, then submit, all with the same id", async () => {
    call.mockReset();
    api.media.upload.mockReset();
    call.mockImplementation(async (method, args) => (method.endsWith("diary_save") ? { name: `${args.project}-ND-${args.day}` } : { status: "Đã nộp" }));
    api.media.upload.mockResolvedValue({ name: 1 });
    const item = {
      id: "d-1", kind: "diary", payload: { project: "P-1", day: "2026-11-09", values: { weather: "Nắng" }, rows: [{ task: "T-1", qty: 5 }] },
      photos: [{ uuid: "p-1", name: "a.jpg", type: "image/jpeg", data: new Uint8Array([1]).buffer, done: false }],
    };
    await expect(SENDERS.diary(item, async () => {})).resolves.toEqual({ status: "Đã nộp" });
    const [saveMethod, saveArgs] = call.mock.calls[0];
    expect(saveMethod).toMatch(/diary_save$/);
    expect(saveArgs).toMatchObject({ project: "P-1", day: "2026-11-09", client_uuid: "d-1", rows: [{ task: "T-1", qty: 5 }] });
    const form = api.media.upload.mock.calls[0][0];
    expect([form.get("reference_doctype"), form.get("reference_name"), form.get("client_uuid")]).toEqual(["PMC Site Diary", "P-1-ND-2026-11-09", "p-1"]);
    expect(call.mock.calls[1]).toEqual([expect.stringMatching(/diary_submit$/), { name: "P-1-ND-2026-11-09", media: ["p-1"], client_uuid: "d-1" }, { post: true }]);
  });
});

describe("construction figures", () => {
  it("writes money, quantities and shares the Vietnamese way", () => {
    expect(moneyText(1234567)).toBe("1.234.567 đ");
    expect(moneyText(758_900_000, { short: true })).toBe("758,9 triệu");
    expect(moneyText(758_989_000, { short: true })).toBe("759 triệu");
    expect(moneyText(1_250_000_000, { short: true })).toBe("1,25 tỷ");
    expect(qtyText(86.4, "m3")).toBe("86,4 m3");
    expect(percentText(33.333)).toBe("33,3%");
    expect(share(30, 40)).toBe(75);
    expect(share(50, 40)).toBe(100);
    expect(share(5, 0)).toBe(0);
    expect(today(new Date(2026, 10, 9))).toBe("2026-11-09");
  });

  it("totals each section of a BOQ, nested sections included", () => {
    const rows = boqRows([
      { line_no: 1, is_group: 1, parent_line: 0 },
      { line_no: 2, is_group: 0, parent_line: 1, amount: 100 },
      { line_no: 3, is_group: 1, parent_line: 1 },
      { line_no: 4, is_group: 0, parent_line: 3, amount: 50 },
    ]);
    expect(rows.map((row) => [row.line_no, row.total, row.works])).toEqual([[1, 150, 2], [2, 0, 0], [3, 50, 1], [4, 0, 0]]);
  });

  it("checks the quantities of a diary as they are typed", () => {
    const { rows, errors } = diaryRows([
      { task: "T-1", label: "Đào móng", qty: "12,5", note: " trục A " },
      { task: "", qty: "" },  // an empty line is dropped
      { task: "T-2", label: "Bê tông", qty: "0" },
      { task: "T-1", label: "Đào móng", qty: "3" },
      { task: "", qty: "4" },
    ]);
    expect(rows).toEqual([{ task: "T-1", qty: 12.5, note: "trục A" }]);
    expect(errors).toEqual(["Bê tông: khối lượng phải lớn hơn 0", "Đào móng được ghi hai lần", "Chọn công tác cho mỗi dòng có khối lượng"]);
  });
});
