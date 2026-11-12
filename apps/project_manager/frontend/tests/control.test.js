import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/lib/api.js", () => ({
  api: {
    control: { budget: vi.fn(), saveBudget: vi.fn(), reviseBudget: vi.fn(), approveBudget: vi.fn(), discardBudget: vi.fn(),
      register: vi.fn(), saveRisk: vi.fn(), riskHappened: vi.fn(), saveIssue: vi.fn(), saveChange: vi.fn(), submitChange: vi.fn(),
      decideChange: vi.fn(), cancelChange: vi.fn() },
    reports: { get: vi.fn(), run: vi.fn(), list: vi.fn(), subscriptions: vi.fn(), saveSubscription: vi.fn(), recipients: vi.fn(),
      sendNow: vi.fn(), deleteSubscription: vi.fn() },
    projects: { members: vi.fn() },
    schedule: { searchTasks: vi.fn(async () => []) },
    linkSearch: vi.fn(async () => []),
  },
  call: vi.fn(),
}));

import { api } from "../src/lib/api.js";
import { budgetLines, indexTone, matrix, money, moneyShort, ratio, riskScore, total, usage } from "../src/lib/control.js";
import { formatCell, routeOf, scheduleText } from "../src/lib/reports.js";
import BudgetTab from "../src/pages/project/BudgetTab.vue";
import ChangesTab from "../src/pages/project/ChangesTab.vue";
import ControlTab from "../src/pages/project/ControlTab.vue";
import ReportPage from "../src/pages/ReportPage.vue";

const provide = () => ({ project: { name: computed(() => "P-1"), overview: ref({ can: {} }), openTask: vi.fn(), version: ref(0), reload: vi.fn() } });
const mountTab = async (component) => {
  const wrapper = mount(component, { global: { provide: provide(), stubs: { teleport: true } } });
  await flushPromises();
  return wrapper;
};

describe("control helpers", () => {
  it("formats money and indexes", () => {
    expect(money(1234567.4)).toBe("1.234.567");
    expect(money(null)).toBe("—");
    expect(moneyShort(1955500000)).toBe("1,96 tỷ");
    expect(moneyShort(760890000)).toBe("760,89 tr");
    expect(ratio(0.873)).toBe("0,87");
    expect(indexTone(0.85)).toBe("text-danger");
    expect(indexTone(0.97)).toBe("text-warning");
    expect(indexTone(1.1)).toBe("text-success");
    expect(usage(100, 130)).toEqual({ width: 100, over: true, pct: 130 });
    expect(usage(0, 10).pct).toBe(null);
  });

  it("scores risks like the server and lays out the matrix", () => {
    expect(riskScore(4, 3)).toEqual({ score: 12, level: "Cao" });
    expect(riskScore(2, 2)).toEqual({ score: 4, level: "Thấp" });
    const grid = matrix([{ probability: 4, impact: 3, status: "Mở" }, { probability: 4, impact: 3, status: "Đã đóng" }]);
    expect(grid[0].impact).toBe(5);
    expect(grid[2].cells[3].risks).toHaveLength(1);  // impact 3, probability 4, only the open one
  });

  it("reads the lines of a budget form", () => {
    const lines = [{ category: "Vật tư", amount: "1.500.000" }, { category: "Khác", amount: "", description: "" }, { amount: "200" }];
    expect(budgetLines(lines)).toEqual([{ category: "Vật tư", task: null, description: "", amount: 1500000 },
      { category: "Khác", task: null, description: "", amount: 200 }]);
    expect(total(lines)).toBe(1500200);
  });

  it("shows report cells and schedules", () => {
    expect(formatCell({ fieldtype: "Currency" }, 1234567.6)).toBe("1.234.568");
    expect(routeOf({ link: "/du-an/{project}/ngan-sach" }, { project: "P 1" })).toBe("/du-an/P%201/ngan-sach");
    expect(scheduleText({ frequency: "Hằng tuần", weekday: "Thứ Hai", hour: 7 })).toBe("Hằng tuần, Thứ Hai lúc 7 giờ");
    expect(scheduleText({ frequency: "Hằng tháng", day_of_month: 5, hour: 8 })).toBe("Ngày 5 hằng tháng lúc 8 giờ");
  });
});

const EVM = { bac: 1000, pv: 500, ev: 400, ac: 500, cpi: 0.8, spi: 0.8, eac: 1250, vac: -250, planned_pct: 50, progress_pct: 40 };

describe("BudgetTab", () => {
  beforeEach(() => vi.clearAllMocks());

  it("shows the earned value, the categories and approves a draft", async () => {
    api.control.budget.mockResolvedValue({ evm: EVM, can: { manage: true },
      by_category: [{ category: "Vật tư", budget: 600, actual: 700 }], by_section: [],
      budgets: [{ name: "NS-2", title: "Điều chỉnh", version: 2, status: "Nháp", total: 1100 }, { name: "NS-1", title: "Gốc", version: 1, status: "Đã duyệt", total: 1000 }],
      in_use: { name: "NS-1", title: "Gốc", lines: [{ name: "l1", category: "Vật tư", amount: 600 }] },
      draft: { name: "NS-2", title: "Điều chỉnh", total: 1100, lines: [] } });
    api.control.approveBudget.mockResolvedValue({});
    const wrapper = await mountTab(BudgetTab);
    expect(wrapper.find("[data-evm=cpi]").text()).toContain("0,80");
    expect(wrapper.find("[data-evm=cpi] .text-danger").exists()).toBe(true);
    expect(wrapper.find("[data-category-row]").text()).toContain("117%");
    await wrapper.find("[data-budget-draft]").findAll("button").find((b) => b.text().includes("Duyệt")).trigger("click");
    await flushPromises();
    expect(api.control.approveBudget).toHaveBeenCalledWith("NS-2");
  });

  it("says why when the budget is not for this user", async () => {
    api.control.budget.mockRejectedValue(new Error("Vai trò của bạn trong dự án không xem được ngân sách"));
    const wrapper = await mountTab(BudgetTab);
    expect(wrapper.text()).toContain("không xem được ngân sách");
  });

  it("prepares a budget and sends its lines", async () => {
    api.control.budget.mockResolvedValue({ evm: EVM, can: { manage: true }, by_category: [], by_section: [], budgets: [], in_use: null, draft: null });
    api.control.saveBudget.mockResolvedValue({ name: "NS-1" });
    const wrapper = await mountTab(BudgetTab);
    await wrapper.findAll("button").find((b) => b.text().includes("Lập ngân sách")).trigger("click");
    const line = wrapper.find("[data-budget-line]");
    await line.findAll("input").at(-1).setValue("2500000");
    expect(wrapper.find("[data-budget-total]").text()).toBe("2.500.000");
    await wrapper.find("[data-budget-form] form").trigger("submit");
    await flushPromises();
    expect(api.control.saveBudget).toHaveBeenCalledWith("P-1", "Ngân sách dự án", [{ category: "Vật tư", task: null, description: "", amount: 2500000 }], "", null);
  });
});

const REGISTER = {
  summary: { risks_open: 1, risks_high: 1, issues_open: 1, issues_overdue: 1, changes_waiting: 1, changes_approved_cost: 0 },
  can: { risk: true, request: true, approve: true }, finance: true,
  risks: [{ name: "RR-1", title: "Mưa", probability: 4, impact: 3, score: 12, level: "Cao", status: "Mở", response: "Giảm thiểu" }],
  issues: [{ name: "VD-1", title: "Bản vẽ", priority: "Cao", status: "Mở", due_date: "2026-01-01", overdue: true }],
  changes: [{ name: "PS-1", title: "Mái che", reason: "Chủ đầu tư yêu cầu", cost_impact: 45000000, days_impact: 3, status: "Chờ duyệt",
    tasks: [], requested_by: "a@x", can: { edit: false, decide: true, cancel: true } }],
};

describe("ControlTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.control.register.mockResolvedValue(REGISTER);
    api.projects.members.mockResolvedValue({ rows: [{ user: "a@x", full_name: "Kỹ sư A", current: true }] });
  });

  it("shows the matrix, the register and records a risk", async () => {
    api.control.saveRisk.mockResolvedValue({ name: "RR-2" });
    const wrapper = await mountTab(ControlTab);
    expect(wrapper.find("[data-risk-matrix]").text()).toContain("1");
    expect(wrapper.find("[data-risk]").text()).toContain("Cao · 12");
    expect(wrapper.find("[data-issue] [data-overdue]").exists()).toBe(true);
    await wrapper.findAll("button").find((b) => b.text().includes("Ghi rủi ro")).trigger("click");
    await wrapper.find("#risk-title").setValue("Thép về chậm");
    await wrapper.find("#risk-p").setValue(5);
    await wrapper.find("#risk-i").setValue(4);
    expect(wrapper.text()).toContain("Điểm 20");
    await wrapper.find("#risk-form").trigger("submit");
    await flushPromises();
    expect(api.control.saveRisk).toHaveBeenCalledWith("P-1", expect.objectContaining({ title: "Thép về chậm", probability: 5, impact: 4, owner_user: null }), null);
  });
});

describe("ChangesTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.control.register.mockResolvedValue(REGISTER);
  });

  it("decides a waiting change request", async () => {
    api.control.decideChange.mockResolvedValue({ moved: ["T-1"], budget: "NS-1" });
    const wrapper = await mountTab(ChangesTab);
    expect(wrapper.find("[data-change]").text()).toContain("45.000.000");
    await wrapper.find("[data-change]").findAll("button").find((b) => b.text() === "Duyệt").trigger("click");
    const dialog = wrapper.findAll("button").find((b) => b.text() === "Duyệt" && b.element.closest("[role=dialog]"));
    await dialog.trigger("click");
    await flushPromises();
    expect(api.control.decideChange).toHaveBeenCalledWith("PS-1", true, "");
  });

  it("prepares and sends a change request", async () => {
    api.control.saveChange.mockResolvedValue({ name: "PS-2" });
    api.control.submitChange.mockResolvedValue({});
    const wrapper = await mountTab(ChangesTab);
    await wrapper.findAll("button").find((b) => b.text().includes("Lập phát sinh")).trigger("click");
    await wrapper.find("#change-title").setValue("Thêm cửa");
    await wrapper.find("#change-cost").setValue("1500000");
    await wrapper.findAll("button").find((b) => b.text() === "Lưu và gửi duyệt").trigger("click");
    await flushPromises();
    expect(api.control.saveChange).toHaveBeenCalledWith("P-1", expect.objectContaining({ title: "Thêm cửa", cost_impact: 1500000 }), [], null);
    expect(api.control.submitChange).toHaveBeenCalledWith("PS-2");
  });
});

describe("ReportPage", () => {
  it("waits for a required filter, then runs, exports and schedules", async () => {
    api.reports.get.mockResolvedValue({ slug: "vat-tu-dinh-muc", title: "Vật tư so với định mức", group: "Thi công", description: "",
      filters: [{ fieldname: "project", label: "Dự án", fieldtype: "Link", options: "Project", reqd: 1 }],
      columns: [{ fieldname: "item_name", label: "Vật tư", fieldtype: "Data" }, { fieldname: "used", label: "Đã dùng", fieldtype: "Float", align: "right" }] });
    api.reports.run.mockResolvedValue({ rows: [{ item_name: "Xi măng", used: 12.5 }], total: 1, page: 1, page_size: 50, paged: true,
      columns: null, info: [], summary: null });
    api.reports.subscriptions.mockResolvedValue([]);
    api.reports.saveSubscription.mockResolvedValue({ name: 1 });
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
    router.push("/bao-cao/vat-tu-dinh-muc");
    await router.isReady();
    const empty = mount(ReportPage, { props: { slug: "vat-tu-dinh-muc" }, global: { plugins: [router], stubs: { teleport: true } } });
    await flushPromises();
    expect(api.reports.run).not.toHaveBeenCalled();
    expect(empty.text()).toContain("Chọn dự án");
    empty.unmount();
    await router.replace({ query: { project: "P-1" } });  // a shared address with its filters
    const wrapper = mount(ReportPage, { props: { slug: "vat-tu-dinh-muc" }, global: { plugins: [router], stubs: { teleport: true } } });
    await flushPromises();
    expect(api.reports.run).toHaveBeenCalledWith("vat-tu-dinh-muc", { project: "P-1" }, 1, 50);
    expect(wrapper.find("[data-report-row]").text()).toContain("12,50");
    expect(wrapper.find("[data-export=xlsx]").attributes("href")).toContain("download_report");
    await wrapper.findAll("button").find((b) => b.text().includes("Gửi theo lịch")).trigger("click");
    await flushPromises();
    await wrapper.find("[data-schedule-form]").trigger("submit");
    await flushPromises();
    expect(api.reports.saveSubscription).toHaveBeenCalledWith("vat-tu-dinh-muc", expect.objectContaining({ frequency: "Hằng tuần", hour: 7 }),
      [""], { project: "P-1" }, null);
  });
});
