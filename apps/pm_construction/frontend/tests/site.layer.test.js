// M8 screens of the construction layer: materials, machines, labour, costs; M9: machine bookings.
import { flushPromises, mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";

vi.mock("@pm/lib/api.js", async (importOriginal) => {
  const real = await importOriginal();
  return { ...real, call: vi.fn() };
});

import { call } from "@pm/lib/api.js";
import { KINDS, SENDERS } from "@pm/lib/sync.js";
import "../pm-module.js";
import { attendanceLines, byWork, clashText, materialRows } from "../src/construction.js";
import CostTab from "../src/CostTab.vue";
import MachinesTab from "../src/MachinesTab.vue";
import MaterialsTab from "../src/MaterialsTab.vue";

const provide = () => ({ project: { name: computed(() => "P-1"), overview: ref({ can: {} }), openTask: vi.fn(), version: ref(0), reload: vi.fn() } });

describe("site helpers", () => {
  it("reads the lines of a stock form", () => {
    const { rows, errors } = materialRows([
      { item: "XM", item_name: "Xi măng", qty: "1.200,5".replace(".", ""), task: "T-1" },
      { item: "", qty: "" },
      { item: "CAT", item_name: "Cát", qty: "0", task: "T-1" },
      { item: "DA", item_name: "Đá", qty: "3", task: "" },
    ], { task: true });
    expect(rows).toEqual([{ item: "XM", qty: 1200.5, task: "T-1" }]);
    expect(errors).toEqual(["Cát: số lượng phải lớn hơn 0", "Đá: chọn công tác"]);
    expect(materialRows([{ item: "XM", qty: "10" }], { rate: true }).errors).toEqual(["XM: nhập đơn giá"]);
    expect(materialRows([{ item: "XM", qty: "10", rate: "1850", material_request_item: "mri-1" }], { rate: true }).rows)
      .toEqual([{ item: "XM", qty: 10, task: null, rate: 1850, material_request_item: "mri-1" }]);
  });

  it("groups usage by work item and marks the ones over the norm", () => {
    const groups = byWork([
      { task: "T-1", task_label: "1.1 Móng", item: "XM", over_norm: false },
      { task: "T-1", task_label: "1.1 Móng", item: "CAT", over_norm: true },
      { task: "T-2", task_label: "1.2 Lót", item: "XM", over_norm: false, ahead: true },
    ]);
    expect(groups.map((g) => [g.task, g.rows.length, g.over, g.ahead])).toEqual([["T-1", 2, true, false], ["T-2", 1, false, true]]);
  });

  it("reads an attendance sheet", () => {
    const { lines, errors, total } = attendanceLines([
      { worker: "W1", worker_name: "A", task: "T-1", man_days: "1", overtime_hours: "2" },
      { worker: "W2", worker_name: "B", task: "", man_days: "0,5" },
      { worker: "W3", worker_name: "C", man_days: "0" },
      { worker: "W4", worker_name: "D", man_days: "3" },
    ]);
    expect(lines).toEqual([{ worker: "W1", task: "T-1", man_days: 1, overtime_hours: 2, note: "" },
      { worker: "W2", task: null, man_days: 0.5, overtime_hours: 0, note: "" }]);
    expect(total).toBe(1.5);
    expect(errors).toEqual(["D: số công tối đa 2"]);
  });
});

describe("queued items of the site", () => {
  it("sends each with its id as the client uuid", async () => {
    call.mockReset();
    call.mockResolvedValue({ name: "X" });
    expect(KINDS["material-request"].summary({ payload: { rows: [{}, {}] } })).toBe("2 dòng vật tư");
    await SENDERS["material-request"]({ id: "m-1", payload: { project: "P-1", rows: [{ task: "T-1", item: "XM", qty: 5 }], note: "gấp", needed_by: "2026-11-12" } });
    expect(call.mock.calls[0]).toEqual([expect.stringMatching(/material_request$/), {
      project: "P-1", rows: [{ task: "T-1", item: "XM", qty: 5 }], note: "gấp", needed_by: "2026-11-12", client_uuid: "m-1" }, { post: true }]);
    await SENDERS["machine-shift"]({ id: "s-1", payload: { project: "P-1", machine: "MX-01", shifts: 1 } });
    expect(call.mock.calls[1][1]).toMatchObject({ machine: "MX-01", client_uuid: "s-1" });
    await SENDERS.attendance({ id: "a-1", payload: { project: "P-1", team: "TEAM", day: "2026-11-11", lines: [{ worker: "W1" }], note: "" } });
    expect(call.mock.calls[2]).toEqual([expect.stringMatching(/attendance_record$/), {
      project: "P-1", team: "TEAM", day: "2026-11-11", lines: [{ worker: "W1" }], note: "", client_uuid: "a-1" }, { post: true }]);
  });
});

const OVERVIEW = {
  store: "Kho P-1", over_norm: 1, can: { request: true, manage: true, plan: false, finance: false },
  rows: [{ task: "T-1", task_label: "1.5 Bê tông móng", path: "1.5", item: "XM", item_name: "Xi măng", uom: "Kg", planned: 13609.75,
    requested: 0, issued: 14600, returned: 150, used: 14450, norm_done: 13609.75, gap: 840.25, over_norm: true }],
  stock: [{ item: "XM", item_name: "Xi măng", uom: "Kg", qty: 4190 }],
  requests: [{ name: "MR-1", status: "Pending", requester: "Kỹ sư", schedule_date: "2026-11-12", open: true,
    lines: [{ name: "mri-1", item_code: "THEP", item_name: "Thép D10", uom: "Kg", left: 1200, pmc_task: "T-2", task_label: "2.1.2 Cốt thép cột" }] }],
  entries: [], items: [{ name: "XM", item_name: "Xi măng", stock_uom: "Kg" }, { name: "THEP", item_name: "Thép D10", stock_uom: "Kg" }],
};

describe("materials tab", () => {
  it("shows the norm against what was used and issues a request", async () => {
    call.mockReset();
    call.mockImplementation(async (method) => {
      if (method.endsWith("materials_overview")) return OVERVIEW;
      if (method.endsWith("diary_works")) return [{ name: "T-2", subject: "Cốt thép cột", pm_wbs_code: "2.1.2" }];
      if (method.endsWith("stock_issue")) return { name: "SE-1" };
      return {};
    });
    const wrapper = mount(MaterialsTab, { global: { provide: provide(), stubs: { teleport: true } } });
    await flushPromises();
    expect(wrapper.text()).toContain("Kho công trường: Kho P-1");
    expect(wrapper.text()).toContain("1 dòng vượt định mức");
    expect(wrapper.find("[data-work]").text()).toContain("Vượt định mức");
    expect(wrapper.text()).not.toContain("Giá trị");  // no finance.view
    await wrapper.find("[data-request]").findAll("button").find((b) => b.text().includes("Cấp phát")).trigger("click");
    await flushPromises();
    const lines = wrapper.findAll("[data-line]");
    expect(lines).toHaveLength(1);
    expect(lines[0].find("input").element.value).toBe("1200");
    await wrapper.find("#stock-form").trigger("submit");
    await flushPromises();
    const sent = call.mock.calls.find(([method]) => method.endsWith("stock_issue"));
    expect(sent[1]).toMatchObject({ project: "P-1", rows: [{ item: "THEP", qty: 1200, task: "T-2", material_request_item: "mri-1" }] });
  });
});

describe("cost tab", () => {
  it("shows the totals and says why when costs are not for this user", async () => {
    call.mockReset();
    call.mockResolvedValue({ total: { estimate: 1e9, earned: 4e8, actual: 3e8, variance: 1e8, material: 2e8, machine: 5e7, labour: 5e7 },
      rows: [{ name: "G", label: "1 PHẦN MÓNG", level: 1, is_group: 1, estimate: 5e8, earned: 4e8, material: 2e8, machine: 5e7, labour: 5e7, actual: 3e8, variance: 1e8 }] });
    const wrapper = mount(CostTab, { global: { provide: provide() } });
    await flushPromises();
    expect(wrapper.text()).toContain("1 tỷ");
    expect(wrapper.findAll("[data-cost-row]")).toHaveLength(1);
    call.mockRejectedValue(new Error("Vai trò của bạn trong dự án không xem được chi phí"));
    const denied = mount(CostTab, { global: { provide: provide() } });
    await flushPromises();
    expect(denied.text()).toContain("không xem được chi phí");
  });
});

describe("machine bookings (M9)", () => {
  it("names the other projects' bookings of the same days", () => {
    expect(clashText([{ project: "P-2", project_name: "Nhà phố", from_date: "2030-01-08", to_date: "2030-01-10" },
      { project: null, project_name: "Dự án khác", from_date: "2030-01-09", to_date: "2030-01-09" }]))
      .toBe("Nhà phố 08/01–10/01; Dự án khác 09/01–09/01");
  });

  it("lists the bookings with their clashes and books a machine", async () => {
    call.mockReset();
    call.mockImplementation(async (method) => {
      if (method.endsWith("machines_overview")) {
        return { machines: [], free: [], shifts: [], transfers: [], can: { move: true, book: true, record: false },
          bookable: [{ name: "CT-01", machine_name: "Cần trục", machine_type: "Cần trục" }],
          bookings: [{ name: 7, machine: "CT-01", machine_name: "Cần trục", from_date: "2030-01-08", to_date: "2030-01-14",
            clashes: [{ project: null, project_name: "Dự án khác", from_date: "2030-01-12", to_date: "2030-01-16" }] }] };
      }
      if (method.endsWith("diary_works")) return [];
      if (method.endsWith("machine_book")) return { name: 8, clashes: [] };
      return {};
    });
    const wrapper = mount(MachinesTab, { global: { provide: provide(), stubs: { teleport: true } } });
    await flushPromises();
    expect(wrapper.find("[data-booking-clash]").text()).toContain("Dự án khác 12/01–16/01");
    await wrapper.findAll("button").find((b) => b.text().includes("Đặt máy")).trigger("click");
    await wrapper.find("#booking-machine").setValue("CT-01");
    await wrapper.find("#booking-from").setValue("2030-01-20");
    await wrapper.find("#booking-to").setValue("2030-01-22");
    await wrapper.find("#booking-form").trigger("submit");
    await flushPromises();
    const sent = call.mock.calls.find(([method]) => method.endsWith("machine_book"));
    expect(sent[1]).toMatchObject({ project: "P-1", machine: "CT-01", from_date: "2030-01-20", to_date: "2030-01-22" });
    await wrapper.find("[data-booking] button").trigger("click");
    await flushPromises();
    expect(call.mock.calls.some(([method, args]) => method.endsWith("machine_booking_cancel") && args.name === 7)).toBe(true);
  });
});
