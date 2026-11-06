import { flushPromises, mount } from "@vue/test-utils";
import { computed, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/lib/api.js", () => ({
  api: {
    schedule: {
      gantt: vi.fn(), previewMove: vi.fn(), applyMove: vi.fn(), previewConflicts: vi.fn(), applyConflicts: vi.fn(), addDependency: vi.fn(),
      dependencies: vi.fn(), searchTasks: vi.fn(), removeDependency: vi.fn(), calendar: vi.fn(), listBaselines: vi.fn(),
      compareBaseline: vi.fn(), captureBaseline: vi.fn(), setPrimaryBaseline: vi.fn(), removeBaseline: vi.fn(),
    },
    forms: {},
    tasks: {},
    projects: {},
    wbs: {},
  },
  call: vi.fn(),
}));

import { api } from "../src/lib/api.js";
import GanttChart from "../src/components/gantt/GanttChart.vue";
import MovePreview from "../src/components/gantt/MovePreview.vue";
import TaskLinks from "../src/components/gantt/TaskLinks.vue";
import SCurve from "../src/components/SCurve.vue";
import {
  HEADER,
  ROW,
  agenda,
  axisTicks,
  collapsedBeyond,
  criticalOnly,
  dayNumber,
  dayRange,
  fromSideIsEnd,
  hitZone,
  isOn,
  isoOf,
  linkPath,
  monthWeeks,
  movedDates,
  slipText,
  tasksFrom,
  toSideIsStart,
  visibleRows,
} from "../src/lib/gantt.js";
import BaselineTab from "../src/pages/project/BaselineTab.vue";
import CalendarTab from "../src/pages/project/CalendarTab.vue";
import GanttTab from "../src/pages/project/GanttTab.vue";
import { routes } from "../src/router.js";

beforeEach(() => vi.clearAllMocks());

const COLUMNS = ["name", "subject", "code", "level", "group", "parent", "start", "end", "progress", "status", "critical", "float", "milestone", "forecast", "conflict", "who", "late", "base_start", "base_end"];
const row = (name, extra = {}) => {
  const values = { name, subject: name, code: "1", level: 1, group: 0, parent: null, start: "2026-11-02", end: "2026-11-05", progress: 0, status: "Open", critical: 0, float: 3, milestone: 0, forecast: null, conflict: 0, who: null, late: 0, base_start: null, base_end: null, ...extra };
  return COLUMNS.map((column) => values[column]);
};
const payload = (rows, extra = {}) => ({
  columns: COLUMNS, rows, links: [], days_off: [], today: "2026-11-06", baselines: [], baseline: null, more: false, flat: false,
  can: { plan: true, dates: true }, summary: { plan_end: "2026-11-30", forecast_end: "2026-12-02", forecast_slip: 2, critical: 1, conflicts: 0, links: 1 }, ...extra,
});

describe("days", () => {
  it("counts days without a time zone getting in the way", () => {
    expect(dayNumber("2026-11-06 00:00:00") - dayNumber("2026-11-05")).toBe(1);
    expect(isoOf(dayNumber("2026-03-01"))).toBe("2026-03-01");  // across the end of February
    expect(dayNumber(null)).toBeNull();
  });

  it("gives the chart room around everything it shows", () => {
    const tasks = tasksFrom(payload([row("a", { base_end: "2026-12-01", forecast: "2026-12-20" })]));
    const { first, last } = dayRange(tasks, "2026-10-01");
    expect(first).toBe(dayNumber("2026-10-01") - 14);
    expect(last).toBe(dayNumber("2026-12-20") + 30);
  });

  it("labels the scale by zoom", () => {
    const from = dayNumber("2026-10-30");
    const to = dayNumber("2026-11-03");
    expect(axisTicks(from, to, "day").major.map((t) => t.label)).toEqual(["11/2026"]);
    expect(axisTicks(from, to, "day").minor.map((t) => t.label)).toEqual(["30", "31", "1", "2", "3"]);
    expect(axisTicks(from, to, "week").minor.map((t) => t.label)).toEqual(["2/11"]);  // Mondays
    expect(axisTicks(dayNumber("2026-12-20"), dayNumber("2027-02-10"), "month").minor.map((t) => t.label)).toEqual(["1", "2"]);
    expect(axisTicks(dayNumber("2026-12-20"), dayNumber("2027-02-10"), "month").major.map((t) => t.label)).toEqual(["2027"]);
  });
});

describe("rows", () => {
  const tasks = tasksFrom(payload([
    row("p", { group: 1, critical: 1 }),
    row("q", { group: 1, parent: "p", level: 2 }),
    row("a", { parent: "q", level: 3, critical: 1 }),
    row("b", { parent: "q", level: 3 }),
    row("r", { group: 1 }),
    row("c", { parent: "r", level: 2 }),
  ]));

  it("hides what is under a closed group", () => {
    expect(visibleRows(tasks, new Set()).map((t) => t.name)).toEqual(["p", "q", "a", "b", "r", "c"]);
    expect(visibleRows(tasks, new Set(["q"])).map((t) => t.name)).toEqual(["p", "q", "r", "c"]);
    expect(visibleRows(tasks, new Set(["p"])).map((t) => t.name)).toEqual(["p", "r", "c"]);
  });

  it("closes the groups beyond a depth (three levels on a phone)", () => {
    expect([...collapsedBeyond(tasks, 2)]).toEqual(["q"]);
    expect(collapsedBeyond(tasks, 1)).toEqual(new Set(["p", "q", "r"]));
  });

  it("keeps the way to critical tasks", () => {
    expect(criticalOnly(tasks).map((t) => t.name)).toEqual(["p", "q", "a"]);
  });

  it("knows which groups have children", () => {
    expect(tasks.find((t) => t.name === "q").hasChildren).toBe(true);
    expect(tasks.find((t) => t.name === "a").hasChildren).toBe(false);
  });
});

describe("dragging", () => {
  const task = { startDay: 100, endDay: 104 };

  it("tells a move from a resize", () => {
    expect(hitZone(10, 10, 100)).toBe("start");
    expect(hitZone(98, 10, 100)).toBe("end");
    expect(hitZone(50, 10, 100)).toBe("move");
    expect(hitZone(200, 10, 100)).toBeNull();
    expect(hitZone(10, 10, 100, true)).toBe("move");  // a milestone only moves
    expect(hitZone(10, 10, 100, false, false)).toBe("move");  // a group too
    expect(hitZone(12, 10, 18)).toBe("move");  // too short to have ends
  });

  it("moves the dates", () => {
    expect(movedDates(task, "move", 2)).toMatchObject({ startDay: 102, endDay: 106 });
    expect(movedDates(task, "end", 3)).toMatchObject({ startDay: 100, endDay: 107 });
    expect(movedDates(task, "start", -2)).toMatchObject({ startDay: 98, endDay: 104 });
    expect(movedDates(task, "start", 10)).toMatchObject({ startDay: 104, endDay: 104 });  // never inside out
    expect(movedDates(task, "end", -10)).toMatchObject({ startDay: 100, endDay: 100 });
    expect(movedDates(task, "move", 0)).toBeNull();
    expect(movedDates({ startDay: 100, endDay: 100 }, "start", 5)).toBeNull();
    expect(movedDates(task, "move", 2).start).toBe(isoOf(102));
  });
});

describe("arrows", () => {
  it("run straight when there is room", () => {
    expect(linkPath({ x: 10, y: 15 }, { x: 60, y: 45 }, true, true)).toEqual([[10, 15], [18, 15], [18, 45], [60, 45]]);
  });

  it("go round when the target lies behind", () => {
    const points = linkPath({ x: 100, y: 15 }, { x: 60, y: 75 }, true, true);
    expect(points[0]).toEqual([100, 15]);
    expect(points.at(-1)).toEqual([60, 75]);
    expect(points[2]).toEqual([108, 15 + ROW / 2]);  // along the gap between the rows
    expect(points).toHaveLength(6);
  });

  it("leave and enter by the side their kind says", () => {
    expect(["FS", "SS", "FF", "SF"].map(fromSideIsEnd)).toEqual([true, false, true, false]);
    expect(["FS", "SS", "FF", "SF"].map(toSideIsStart)).toEqual([true, true, false, false]);
  });
});

describe("words", () => {
  it("says how a date compares", () => {
    expect(slipText(0)).toBe("đúng kế hoạch");
    expect(slipText(3)).toBe("trễ 3 ngày");
    expect(slipText(-2)).toBe("sớm 2 ngày");
    expect(slipText(null)).toBe("");
  });
});

describe("the calendar", () => {
  it("lays a month out in weeks, Monday first", () => {
    const weeks = monthWeeks(2026, 10);  // November 2026 starts on a Sunday
    expect(weeks[0][0]).toBe("2026-10-26");
    expect(weeks[0][6]).toBe("2026-11-01");
    expect(weeks.at(-1).at(-1) >= "2026-11-30").toBe(true);
    expect(weeks.every((week) => week.length === 7)).toBe(true);
  });

  it("knows what runs on a day", () => {
    const task = { start: "2026-11-02", end: "2026-11-04" };
    expect(["2026-11-01", "2026-11-02", "2026-11-04", "2026-11-05"].map((day) => isOn(task, day))).toEqual([false, true, true, false]);
    expect(isOn({ start: null, end: "2026-11-04" }, "2026-11-04")).toBe(true);
  });

  it("lists what starts and what is due", () => {
    const days = agenda([{ name: "a", start: "2026-11-02", end: "2026-11-04" }, { name: "m", start: "2026-11-04", end: "2026-11-04", milestone: 1 },
      { name: "o", start: "2026-10-01", end: "2026-10-05" }], "2026-11-01", "2026-11-30");
    expect(days.map((entry) => entry.day)).toEqual(["2026-11-02", "2026-11-04"]);
    expect(days[1].items.map((item) => item.kind)).toEqual(["Hạn", "Mốc"]);
  });
});

function chartProps(extra = {}) {
  const tasks = tasksFrom(payload([row("a", { critical: 1 }), row("b", { code: "2" })]));
  return { rows: tasks, span: dayRange(tasks, "2026-11-06"), today: "2026-11-06", collapsed: new Set(), label: "Biểu đồ", ...extra };
}

describe("GanttChart", () => {
  it("lists the rows beside the canvas, and opens a task from its name", async () => {
    const wrapper = mount(GanttChart, { props: chartProps() });
    await flushPromises();
    expect(wrapper.find("canvas").attributes("aria-label")).toBe("Biểu đồ");
    const names = wrapper.findAll(".gantt-name");
    expect(names.map((button) => button.text())).toEqual(["1 a", "2 b"]);
    await names[1].trigger("click");
    expect(wrapper.emitted("open")[0]).toEqual(["b"]);
  });

  it("opens and closes a group", async () => {
    const tasks = tasksFrom(payload([row("p", { group: 1 }), row("c", { parent: "p", level: 2 })]));
    const wrapper = mount(GanttChart, { props: chartProps({ rows: tasks }) });
    await flushPromises();
    await wrapper.find(".gantt-toggle").trigger("click");
    expect(wrapper.emitted("toggle")[0]).toEqual(["p"]);
  });

  it("reserves the height of every row, so the page scrolls over them all", async () => {
    const tasks = tasksFrom(payload(Array.from({ length: 2000 }, (_unused, index) => row(`t${index}`))));
    const wrapper = mount(GanttChart, { props: chartProps({ rows: tasks }) });
    await flushPromises();
    expect(wrapper.find(".gantt-scroller > div").attributes("style")).toContain(`height: ${HEADER + 2000 * ROW + 8}px`);
    expect(wrapper.findAll(".gantt-row").length).toBeLessThan(100);  // and draws only those on screen
  });
});

describe("MovePreview", () => {
  const plan = (extra = {}) => ({
    total: 2, clamped: false, over_contract: false, reason_required: false, plan_end_before: "2026-11-15", plan_end_after: "2026-11-18", contract_end: "2026-11-30",
    changes: [{ name: "a", label: "1 A", direct: true, from_start: "2026-11-02", from_end: "2026-11-04", to_start: "2026-11-03", to_end: "2026-11-05" },
      { name: "b", label: "2 B", direct: false, from_start: "2026-11-05", from_end: "2026-11-06", to_start: "2026-11-06", to_end: "2026-11-07" }], ...extra,
  });
  const open = (props) => mount(MovePreview, { props, global: { stubs: { teleport: true } } });

  it("says what moves and what it does to the end", () => {
    const text = open({ plan: plan() }).text();
    expect(text).toContain("1 việc bị đẩy theo phụ thuộc");
    expect(text).toContain("2 B");
    expect(text).toContain("18/11/2026");
  });

  it("asks for a reason once work is given", async () => {
    const wrapper = open({ plan: plan({ reason_required: true }) });
    const button = wrapper.findAll("button").find((b) => b.text().includes("Dời lịch"));
    await button.trigger("click");
    expect(wrapper.emitted("confirm")).toBeUndefined();
    expect(wrapper.text()).toContain("cần ghi lý do");
    await wrapper.find("textarea").setValue("Chờ thép");
    await button.trigger("click");
    expect(wrapper.emitted("confirm")[0]).toEqual(["Chờ thép"]);
  });

  it("warns when the plan goes past the deadline", () => {
    expect(open({ plan: plan({ over_contract: true }) }).text()).toContain("vượt hạn");
  });

  it("explains when nothing changes", () => {
    const wrapper = open({ plan: plan({ total: 0, changes: [], clamped: true }) });
    expect(wrapper.text()).toContain("không thể sớm hơn");
    expect(wrapper.findAll("button").some((b) => b.text().includes("Dời lịch"))).toBe(false);
  });
});

describe("TaskLinks", () => {
  const view = (extra = {}) => ({ predecessors: [{ name: 1, task: "x", label: "1 X", dep_type: "FS", lag_days: 2 }], successors: [], can_edit: true, total_float: 0, critical: 1, conflict_days: 0, forecast_end: "2026-11-20", ...extra });

  it("shows where the task stands", async () => {
    api.schedule.dependencies.mockResolvedValue(view({ conflict_days: 3 }));
    const wrapper = mount(TaskLinks, { props: { task: "t", project: "p" } });
    await flushPromises();
    expect(wrapper.text()).toContain("Trên đường găng");
    expect(wrapper.text()).toContain("1 X");
    expect(wrapper.text()).toContain("FS +2 ngày");
    expect(wrapper.text()).toContain("sớm hơn phụ thuộc cho phép 3 ngày");
  });

  it("removes a link", async () => {
    api.schedule.dependencies.mockResolvedValue(view());
    api.schedule.removeDependency.mockResolvedValue({});
    const wrapper = mount(TaskLinks, { props: { task: "t", project: "p" } });
    await flushPromises();
    await wrapper.find("button[aria-label='Bỏ phụ thuộc']").trigger("click");
    await flushPromises();
    expect(api.schedule.removeDependency).toHaveBeenCalledWith(1);
    expect(wrapper.emitted("changed")).toHaveLength(1);
  });

  it("offers nothing to those who may not edit", async () => {
    api.schedule.dependencies.mockResolvedValue(view({ can_edit: false, critical: 0, total_float: 4 }));
    const wrapper = mount(TaskLinks, { props: { task: "t", project: "p" } });
    await flushPromises();
    expect(wrapper.text()).toContain("Dự trữ 4 ngày");
    expect(wrapper.text()).not.toContain("Thêm phụ thuộc");
    expect(wrapper.find("button[aria-label='Bỏ phụ thuộc']").exists()).toBe(false);
  });
});

describe("SCurve with a baseline", () => {
  const points = [
    { snapshot_date: "2026-11-01", progress: 0, planned_progress: 0 },
    { snapshot_date: "2026-11-06", progress: 20, planned_progress: 30 },
    { snapshot_date: "2026-11-30", progress: null, planned_progress: 100 },
  ];

  it("stops the actual line at today and runs the plan to the end", () => {
    const wrapper = mount(SCurve, { props: { points } });
    const [plan, actual] = wrapper.findAll("path").map((path) => path.attributes("d"));
    expect(plan.match(/[ML]/g)).toHaveLength(3);
    expect(actual.match(/[ML]/g)).toHaveLength(2);
    expect(wrapper.find("svg[role=img]").attributes("aria-label")).toContain("thực tế 20%");
  });

  it("spaces points by their dates", () => {
    const wrapper = mount(SCurve, { props: { points } });
    const coordinates = wrapper.findAll("path")[0].attributes("d").match(/[ML]([\d.]+)/g).map((part) => Number(part.slice(1)));
    expect(coordinates[1] - coordinates[0]).toBeLessThan((coordinates[2] - coordinates[1]) / 2);
  });

  it("shows the future as empty in the table", async () => {
    const wrapper = mount(SCurve, { props: { points } });
    await wrapper.find("button").trigger("click");
    expect(wrapper.findAll("tbody tr")[2].text()).toContain("—");
  });
});

function provideProject(extra = {}) {
  return { name: computed(() => "P-1"), overview: ref({ can: {} }), openTask: vi.fn(), version: ref(0), reload: vi.fn(), ...extra };
}

async function mountTab(component, project = provideProject()) {
  const router = createRouter({ history: createMemoryHistory(), routes });
  const wrapper = mount(component, { global: { plugins: [router], provide: { project }, stubs: { teleport: true } } });
  await flushPromises();
  return { wrapper, project };
}

describe("GanttTab", () => {
  it("shows how the plan stands", async () => {
    api.schedule.gantt.mockResolvedValue(payload([row("a")]));
    const { wrapper } = await mountTab(GanttTab);
    expect(wrapper.text()).toContain("02/12/2026");
    expect(wrapper.text()).toContain("trễ 2 ngày");
    expect(wrapper.text()).toContain("1 việc");
  });

  it("offers to fix conflicts, previews them, and applies with the reason", async () => {
    api.schedule.gantt.mockResolvedValue(payload([row("a")], { summary: { conflicts: 2, links: 1 } }));
    api.schedule.previewConflicts.mockResolvedValue({ total: 1, changes: [{ name: "a", label: "1 A", direct: false }], reason_required: false, plan_end_before: "2026-11-05", plan_end_after: "2026-11-05" });
    api.schedule.applyConflicts.mockResolvedValue({ total: 1 });
    const { wrapper, project } = await mountTab(GanttTab);
    await wrapper.findAll("button").find((b) => b.text().includes("Sửa 2 xung đột")).trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("1 A");
    expect(api.schedule.applyConflicts).not.toHaveBeenCalled();
    await wrapper.findAll("button").find((b) => b.text().includes("Dời lịch")).trigger("click");
    await flushPromises();
    expect(api.schedule.applyConflicts).toHaveBeenCalledWith("P-1", "");
    expect(project.reload).toHaveBeenCalled();
  });

  it("says when there is nothing to show", async () => {
    api.schedule.gantt.mockResolvedValue(payload([]));
    const { wrapper } = await mountTab(GanttTab);
    expect(wrapper.text()).toContain("Chưa có công việc nào");
  });

  it("tells someone who only sees their own tasks", async () => {
    api.schedule.gantt.mockResolvedValue(payload([row("a")], { flat: true }));
    const { wrapper } = await mountTab(GanttTab);
    expect(wrapper.text()).toContain("chỉ thấy các việc được giao");
  });
});

describe("CalendarTab", () => {
  it("asks for the whole visible month and shows its tasks", async () => {
    api.schedule.calendar.mockResolvedValue({ today: "2026-11-06", days_off: [], tasks: [{ name: "a", subject: "Đổ móng", pm_wbs_code: "1", start: new Date().toISOString().slice(0, 10), end: new Date().toISOString().slice(0, 10), status: "Open" }] });
    const { wrapper, project } = await mountTab(CalendarTab);
    const [, first, last] = api.schedule.calendar.mock.calls[0];
    expect(first < last).toBe(true);
    expect(wrapper.text()).toContain("Đổ móng");
    await wrapper.findAll("button").find((b) => b.text().includes("Đổ móng")).trigger("click");
    expect(project.openTask).toHaveBeenCalledWith("a");
  });

  it("moves between months", async () => {
    api.schedule.calendar.mockResolvedValue({ today: "2026-11-06", days_off: [], tasks: [] });
    const { wrapper } = await mountTab(CalendarTab);
    expect(api.schedule.calendar).toHaveBeenCalledTimes(1);
    await wrapper.find("button[aria-label='Tháng sau']").trigger("click");
    await flushPromises();
    expect(api.schedule.calendar).toHaveBeenCalledTimes(2);
  });
});

describe("BaselineTab", () => {
  const list = (extra = {}) => ({ can_edit: true, rows: [{ name: "BL1", title: "Gốc", is_primary: 1, taken_on: "2026-11-01 08:00:00" }, { name: "BL2", title: "Sửa đổi", is_primary: 0 }], ...extra });
  const compare = { title: "Gốc", end_date: "2026-11-15", taken_on: "2026-11-01 08:00:00", later: 1, earlier: 0, added: 2, total: 1, summary: { plan_end: "2026-11-18" },
    rows: [{ task: "a", label: "1 A", status: "Working", base_end: "2026-11-05", end: "2026-11-07", plan_slip: 2, forecast: "2026-11-07", forecast_slip: 2, critical: 1 }] };

  it("opens on the main baseline and shows the gap", async () => {
    api.schedule.listBaselines.mockResolvedValue(list());
    api.schedule.compareBaseline.mockResolvedValue(compare);
    const { wrapper } = await mountTab(BaselineTab);
    expect(api.schedule.compareBaseline).toHaveBeenCalledWith("BL1", 0);
    expect(wrapper.text()).toContain("trễ 2 ngày");
    expect(wrapper.text()).toContain("1 việc lùi");
    expect(wrapper.text()).toContain("2 việc mới");
    expect(wrapper.findAll("button").some((b) => b.text().includes("Dùng làm baseline chính"))).toBe(false);
  });

  it("captures a new one", async () => {
    api.schedule.listBaselines.mockResolvedValue(list());
    api.schedule.compareBaseline.mockResolvedValue(compare);
    api.schedule.captureBaseline.mockResolvedValue({ name: "BL3" });
    const { wrapper } = await mountTab(BaselineTab);
    await wrapper.findAll("button").find((b) => b.text().includes("Chụp baseline")).trigger("click");
    await wrapper.find("#bl-title").setValue("Đợt 3");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(api.schedule.captureBaseline).toHaveBeenCalledWith("P-1", "Đợt 3", "");
  });

  it("invites the first baseline, and only to those who may", async () => {
    api.schedule.listBaselines.mockResolvedValue(list({ rows: [], can_edit: false }));
    const { wrapper } = await mountTab(BaselineTab);
    expect(wrapper.text()).toContain("Chưa có baseline nào");
    expect(wrapper.findAll("button").some((b) => b.text().includes("Chụp baseline"))).toBe(false);
  });
});

describe("routes", () => {
  it("serve the new tabs", () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    for (const tab of ["gantt", "lich", "baseline"]) expect(router.resolve(`/du-an/P-1/${tab}`).name).toBe("project");
  });
});
