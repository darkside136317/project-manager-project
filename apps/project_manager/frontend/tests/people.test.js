import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/lib/api.js", () => ({
  api: {
    people: { workload: vi.fn(), cell: vi.fn(), saveCapacity: vi.fn(), deleteCapacity: vi.fn(), performance: vi.fn(),
      person: vi.fn(), teams: vi.fn() },
    alerts: { portfolio: vi.fn() },
    linkSearch: vi.fn(async () => []),
  },
  call: vi.fn(),
}));

import { api } from "../src/lib/api.js";
import {
  OTHER, cellClass, columnText, days, extraColumns, mondayOf, percent, shares, shiftWeeks, sparkline, toneText, weekLabel,
} from "../src/lib/people.js";
import PerformancePage from "../src/pages/PerformancePage.vue";
import PortfolioPage from "../src/pages/PortfolioPage.vue";
import WorkloadPage from "../src/pages/WorkloadPage.vue";

describe("people helpers", () => {
  it("formats shares, days and weeks", () => {
    expect(percent(0.853)).toBe("85%");
    expect(percent(null)).toBe("—");
    expect(days(2.25)).toBe("2,3");
    expect(days(3)).toBe("3");
    expect(weekLabel("2030-01-07")).toBe("07/01");
    expect(mondayOf(new Date(2030, 0, 10))).toBe("2030-01-07");
    expect(mondayOf(new Date(2030, 0, 13))).toBe("2030-01-07");  // a Sunday
    expect(shiftWeeks("2030-01-07", -1)).toBe("2029-12-31");
    expect(cellClass("Quá tải")).toContain("text-danger");
  });

  it("puts the hidden projects last", () => {
    const list = shares({ [OTHER]: 4, A: 1, B: 3 }, { A: "Dự án A" });
    expect(list.map((s) => s.label)).toEqual(["B", "Dự án A", OTHER]);
    expect(list[2].hidden).toBe(true);
  });

  it("reads the layer columns of the portfolio", () => {
    const rows = [{ extra: { cost_ratio: { label: "Chi phí / giá trị", value: 1.2, format: "percent", tone: "bad" } } },
      { extra: { over_norm: { label: "Vượt định mức", value: 2, format: "number" } } }];
    expect(extraColumns(rows)).toEqual([{ key: "cost_ratio", label: "Chi phí / giá trị" }, { key: "over_norm", label: "Vượt định mức" }]);
    expect(columnText(rows[0].extra.cost_ratio)).toBe("120%");
    expect(columnText(rows[1].extra.over_norm)).toBe("2");
    expect(columnText(undefined)).toBe("—");
    expect(toneText("bad")).toBe("text-danger");
    expect(sparkline([0, 50, 100], 80, 20)).toBe("0,20 40,10 80,0");
    expect(sparkline([10])).toBe("");
  });
});

function router() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: "/:p(.*)*", component: { template: "<div />" } }] });
}

async function mountPage(component) {
  const r = router();
  r.push("/khoi-luong-cong-viec");
  await r.isReady();
  const wrapper = mount(component, { global: { plugins: [r] }, attachTo: document.body });
  await flushPromises();
  return wrapper;
}

const WEEK = { week: "2030-01-07", capacity: 5, demand: 7.5, utilization: 1.5, level: "Quá tải", projects: { P1: 5, [OTHER]: 2.5 } };

describe("WorkloadPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.people.teams.mockResolvedValue([{ name: "T1", team_name: "Tổ nề" }]);
    api.people.workload.mockResolvedValue({
      weeks: ["2030-01-07"], projects: { P1: "Nhà xưởng" }, thresholds: { busy: 0.8, overload: 1.2 }, can: { capacity: true },
      rows: [{ user: "a@x", full_name: "Kỹ sư A", weeks: [WEEK], peak: 1.5 },
        { user: "b@x", full_name: "Kỹ sư B", weeks: [{ ...WEEK, demand: 1, utilization: 0.2, level: "Vừa sức", projects: { P1: 1 } }], peak: 0.2 }],
      conflicts: [{ kind: "Người", subject: "Kỹ sư A", user: "a@x", week: "2030-01-07", utilization: 1.5, projects: WEEK.projects },
        { kind: "Máy", subject: "Máy đào", week: "2030-01-07", projects: { P1: 3, [OTHER]: 3 }, message: "Máy đào được hai dự án đặt" }],
    });
    api.people.cell.mockResolvedValue({ user: "a@x", week: "2030-01-07", capacity: 5, other: 2.5, periods: [],
      tasks: [{ task: "T-1", label: "1.1 Đổ bê tông", project: "P1", project_name: "Nhà xưởng", raci: "Thực hiện", days: 5, progress: 20 }] });
    api.people.saveCapacity.mockResolvedValue({ name: 1 });
  });

  it("shows the weeks, the conflicts and what I may not see", async () => {
    const wrapper = await mountPage(WorkloadPage);
    expect(wrapper.findAll("[data-workload-row]")).toHaveLength(2);
    expect(wrapper.find("[data-workload-cell]").text()).toContain("150%");
    expect(wrapper.find("[data-overloaded-count]").text()).toContain("1 người quá tải");
    const conflicts = wrapper.findAll("[data-conflict]");
    expect(conflicts).toHaveLength(2);
    expect(conflicts[0].text()).toContain("Nhà xưởng: 5");
    expect(conflicts[0].text()).toContain(`${OTHER}: 2,5`);
    await wrapper.find("input[type=checkbox]").setValue(true);
    expect(wrapper.findAll("[data-workload-row]")).toHaveLength(1);  // only the busy ones
    wrapper.unmount();
  });

  it("opens a week and records leave", async () => {
    const wrapper = await mountPage(WorkloadPage);
    await wrapper.find("[data-workload-cell]").trigger("click");
    await flushPromises();
    expect(api.people.cell).toHaveBeenCalledWith("a@x", "2030-01-07");
    const drawer = document.body.querySelector("[data-workload-drawer]");
    expect(drawer.textContent).toContain("1.1 Đổ bê tông");
    expect(drawer.textContent).toContain("Dự án khác: 2,5");
    drawer.querySelector("[data-capacity-form]").dispatchEvent(new Event("submit"));
    await flushPromises();
    expect(api.people.saveCapacity).toHaveBeenCalledWith(expect.objectContaining({ user: "a@x", capacity_pct: 0, reason: "Nghỉ phép" }));
    wrapper.unmount();
  });
});

describe("WorkloadPage with many conflicts", () => {
  it("shows ten, then all on request", async () => {
    api.people.teams.mockResolvedValue([]);
    api.people.workload.mockResolvedValue({ weeks: ["2030-01-07"], projects: {}, thresholds: { busy: 0.8, overload: 1.2 }, can: {},
      rows: [{ user: "a@x", full_name: "A", weeks: [WEEK], peak: 1.5 }],
      conflicts: Array.from({ length: 12 }, (_, i) => ({ kind: "Người", subject: `Người ${i}`, week: "2030-01-07", projects: { P1: 1, P2: 1 } })) });
    const wrapper = await mountPage(WorkloadPage);
    expect(wrapper.findAll("[data-conflict]")).toHaveLength(10);
    await wrapper.findAll("button").find((b) => b.text().includes("Xem tất cả 12")).trigger("click");
    expect(wrapper.findAll("[data-conflict]")).toHaveLength(12);
    wrapper.unmount();
  });
});

describe("PerformancePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.people.teams.mockResolvedValue([]);
    api.people.performance.mockResolvedValue({
      first: "2030-01-01", last: "2030-01-28", scope: { all: false, projects: ["P1"], teams: [] },
      total: { done: 3, on_time_rate: 0.667, open_late: 1, avg_delay: 2 },
      people: [{ user: "a@x", full_name: "Kỹ sư A", done: 3, on_time: 2, late_done: 1, open_late: 1, avg_delay: 2, on_time_rate: 0.667, reports: 4 }],
      projects: [{ project: "P1", project_name: "Nhà xưởng", done: 3, on_time_rate: 0.667, open_late: 1, avg_delay: 2 }],
      crews: [{ team: "T1", team_name: "Tổ nề", uom: "m3", qty: 6, man_days: 3, per_man_day: 2, works: 1 }],
    });
    api.people.person.mockResolvedValue({ user: "a@x", full_name: "Kỹ sư A", total: { done: 3, on_time_rate: 0.667, open_late: 1 },
      projects: [{ project: "P1", project_name: "Nhà xưởng", done: 3, on_time_rate: 0.667, open_late: 1 }],
      tasks: [{ name: "T-1", subject: "Cột", pm_wbs_code: "1.2", project_name: "Nhà xưởng", status: "Completed", late: true, exp_end_date: "2030-01-09", act_end_date: "2030-01-11" }],
      trend: [{ week: "2029-12-31", done: 1, open_late: 0 }, { week: "2030-01-07", done: 2, open_late: 1 }] });
  });

  it("shows people, projects and crews within my scope", async () => {
    const wrapper = await mountPage(PerformancePage);
    expect(wrapper.text()).toContain("mọi người trong 1 dự án");
    expect(wrapper.find("[data-total-done]").text()).toBe("3");
    expect(wrapper.find("[data-performance-row]").text()).toContain("67%");
    expect(wrapper.find("[data-crew-row]").text()).toContain("Tổ nề");
    await wrapper.findAll("button").find((b) => b.text() === "13 tuần").trigger("click");
    await flushPromises();
    expect(api.people.performance).toHaveBeenLastCalledWith(expect.objectContaining({ period: "quarter" }));
    await wrapper.find("[data-performance-row] button").trigger("click");
    await flushPromises();
    const drawer = document.body.querySelector("[data-person-drawer]");
    expect(drawer.textContent).toContain("1.2 Cột");
    expect(drawer.textContent).toContain("Trễ");
    wrapper.unmount();
  });
});

describe("PortfolioPage v2", () => {
  it("shows on time, overloaded members, the trend and the layer columns", async () => {
    api.alerts.portfolio.mockResolvedValue({ totals: { Đỏ: 1 }, alerts_open: 0, rows: [{
      name: "P1", project_name: "Nhà xưởng", pm_health: "Đỏ", percent_complete: 40, planned_progress: 50, late: 2, alerts_open: 0,
      on_time_rate: 0.5, overloaded: 2, trend: [10, 25, 40],
      extra: { cost_ratio: { label: "Chi phí / giá trị làm được", value: 1.2, format: "percent", tone: "bad" } } }] });
    const wrapper = await mountPage(PortfolioPage);
    expect(wrapper.find("[data-on-time]").text()).toBe("50%");
    expect(wrapper.find("[data-overloaded] a").text()).toBe("2");
    expect(wrapper.find("polyline").exists()).toBe(true);
    expect(wrapper.find("[data-extra=cost_ratio]").text()).toBe("120%");
    expect(wrapper.find("[data-extra=cost_ratio]").classes()).toContain("text-danger");
    expect(wrapper.text()).toContain("Chi phí / giá trị làm được");
    wrapper.unmount();
  });
});
