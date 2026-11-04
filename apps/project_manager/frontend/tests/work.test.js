import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/lib/api.js", () => ({
  api: {
    tasks: { detail: vi.fn(), report: vi.fn(), respond: vi.fn(), review: vi.fn(), assign: vi.fn(), revoke: vi.fn() },
    projects: { members: vi.fn() },
    wbs: { update: vi.fn() },
  },
  call: vi.fn(),
}));

import { api } from "../src/lib/api.js";
import ProgressBar from "../src/components/ProgressBar.vue";
import SCurve from "../src/components/SCurve.vue";
import TaskDetail from "../src/components/TaskDetail.vue";
import WbsRow from "../src/pages/project/WbsRow.vue";
import { routes } from "../src/router.js";
import {
  clampProgress,
  deadlineText,
  deadlineTone,
  groupCards,
  needsDelayReason,
  statusBadge,
  statusLabel,
  variance,
} from "../src/lib/work.js";

beforeEach(() => vi.clearAllMocks());

const TODAY = new Date(2026, 10, 4);

describe("work helpers", () => {
  it("labels and colours statuses", () => {
    expect(statusLabel("Pending Review")).toBe("Chờ duyệt");
    expect(statusBadge("Completed")).toBe("badge badge-success");
    expect(statusBadge("whatever")).toBe("badge badge-muted");
  });

  it("says how far the deadline is", () => {
    expect(deadlineText({ exp_end_date: "2026-11-01 00:00:00", status: "Working" }, TODAY)).toBe("Trễ 3 ngày");
    expect(deadlineText({ exp_end_date: "2026-11-04", status: "Open" }, TODAY)).toBe("Hạn hôm nay");
    expect(deadlineText({ exp_end_date: "2026-11-06", status: "Open" }, TODAY)).toBe("Còn 2 ngày");
    expect(deadlineText({ exp_end_date: "2026-11-01", status: "Completed" }, TODAY)).toBe("");
    expect(deadlineText({ status: "Open" }, TODAY)).toBe("");
    expect(deadlineTone("Trễ 3 ngày")).toBe("text-danger");
    expect(deadlineTone("Còn 2 ngày")).toBe("text-ink-muted");
  });

  it("asks for a delay reason only for late, unexplained work", () => {
    const late = { exp_end_date: "2026-11-01", status: "Working", progress: 40 };
    expect(needsDelayReason(late, 60, TODAY)).toBe(true);
    expect(needsDelayReason({ ...late, pm_delay_reason: "Thiếu vật tư", pm_delay_source: "Cung ứng" }, 60, TODAY)).toBe(false);
    expect(needsDelayReason({ ...late, exp_end_date: "2026-11-10" }, 60, TODAY)).toBe(false);
    expect(needsDelayReason({ ...late, status: "Completed" }, 100, TODAY)).toBe(false);
  });

  it("groups cards by column and drops unknown statuses", () => {
    const columns = [{ status: "Open" }, { status: "Working" }];
    const grouped = groupCards(columns, [{ name: "a", status: "Open" }, { name: "b", status: "Working" }, { name: "c", status: "Cancelled" }]);
    expect(grouped.Open.map((c) => c.name)).toEqual(["a"]);
    expect(grouped.Working.map((c) => c.name)).toEqual(["b"]);
    expect(Object.keys(grouped)).toEqual(["Open", "Working"]);
  });

  it("clamps progress and measures the gap to plan", () => {
    expect(clampProgress("120")).toBe(100);
    expect(clampProgress(-3)).toBe(0);
    expect(clampProgress("abc")).toBe(0);
    expect(variance(40, 55.4)).toBe(-15);
  });
});

describe("charts", () => {
  it("marks a project behind plan in red", () => {
    const behind = mount(ProgressBar, { props: { value: 20, planned: 50 } });
    expect(behind.find(".bg-danger").exists()).toBe(true);
    const fine = mount(ProgressBar, { props: { value: 48, planned: 50 } });
    expect(fine.find(".bg-danger").exists()).toBe(false);
  });

  it("draws both series of the S-curve and offers the numbers as a table", async () => {
    const points = [
      { snapshot_date: "2026-11-01", progress: 5, planned_progress: 10 },
      { snapshot_date: "2026-11-02", progress: 12, planned_progress: 20 },
    ];
    const wrapper = mount(SCurve, { props: { points } });
    expect(wrapper.findAll("path")).toHaveLength(2);
    expect(wrapper.find("svg[role=img]").attributes("aria-label")).toContain("thực tế 12%");
    await wrapper.find("button").trigger("click");
    expect(wrapper.findAll("tbody tr")).toHaveLength(2);
  });

  it("explains an empty S-curve", () => {
    expect(mount(SCurve, { props: { points: [] } }).text()).toContain("Chưa có số liệu");
  });
});

function detail(overrides = {}) {
  return {
    task: { name: "TASK-1", subject: "Đổ bê tông", status: "Working", progress: 40, exp_end_date: "2026-01-01 00:00:00",
      project: "PROJ-1", project_name: "Nhà A", pm_wbs_code: "1.2", is_group: 0, ...overrides.task },
    ancestors: [{ name: "TASK-0", subject: "Móng", pm_wbs_code: "1" }],
    assignments: overrides.assignments || [],
    reports: [], timeline: [], children: 0,
    can: { update: true, plan: false, assign: false, dates: false, review: false, ...overrides.can },
    mine: true, delay_reasons: ["Thiếu vật tư"], delay_sources: ["Cung ứng"], raci_roles: ["Thực hiện"],
  };
}

async function mountDetail(data) {
  api.tasks.detail.mockResolvedValue(data);
  const router = createRouter({ history: createMemoryHistory(), routes });
  const wrapper = mount(TaskDetail, { props: { name: "TASK-1" }, global: { plugins: [router] } });
  await flushPromises();
  return wrapper;
}

describe("TaskDetail", () => {
  it("asks late work for its reason and sends the report once", async () => {
    const wrapper = await mountDetail(detail());
    expect(wrapper.text()).toContain("Công việc đã quá hạn");
    await wrapper.find("#delay-reason").setValue("Thiếu vật tư");
    await wrapper.find("#delay-source").setValue("Cung ứng");
    api.tasks.report.mockResolvedValue({});
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    const [task, values] = api.tasks.report.mock.calls[0];
    expect(task).toBe("TASK-1");
    expect(values).toMatchObject({ progress_value: 40, delay_reason: "Thiếu vật tư", delay_source: "Cung ứng" });
    expect(values.client_uuid).toBeTruthy();
  });

  it("lets the assignee accept or decline", async () => {
    const wrapper = await mountDetail(detail({
      assignments: [{ name: 7, raci: "Thực hiện", who: "An", state: "Chờ nhận", is_active: 1, can_respond: true, can_revoke: false }],
    }));
    expect(wrapper.text()).toContain("Bạn được giao vai trò");
    api.tasks.respond.mockResolvedValue({});
    await wrapper.findAll("button").find((b) => b.text().includes("Nhận việc")).trigger("click");
    await flushPromises();
    expect(api.tasks.respond).toHaveBeenCalledWith(7, true);
  });

  it("hides the report form from people who may not update", async () => {
    const wrapper = await mountDetail(detail({ can: { update: false } }));
    expect(wrapper.find("#task-progress").exists()).toBe(false);
    expect(wrapper.text()).toContain("Nhà A");
  });

  it("shows the approval buttons to the reviewer", async () => {
    const wrapper = await mountDetail(detail({ task: { status: "Pending Review" }, can: { review: true } }));
    expect(wrapper.find("#task-progress").exists()).toBe(false);
    expect(wrapper.text()).toContain("chờ bạn duyệt");
  });
});

describe("routes", () => {
  it("serve the project, task and my-tasks screens", () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    expect(router.resolve("/du-an/PROJ-1/kanban").name).toBe("project");
    expect(router.resolve("/du-an/PROJ-1").name).toBe("project");
    expect(router.resolve("/cong-viec/TASK-2026-00001").name).toBe("task");
    expect(router.resolve("/viec-cua-toi").name).toBe("my-tasks");
  });
});

describe("WbsRow", () => {
  const node = { name: "T-1", subject: "Cốt thép", pm_wbs_code: "2.3", is_group: 0, status: "Working", progress: 42, children: 0 };
  const tree = { expanded: {}, children: {}, loading: {}, more: {}, toggle: vi.fn(), load: vi.fn() };

  it("closes its menu after an action and passes the action up", async () => {
    const wrapper = mount(WbsRow, { props: { node, tree, index: 1, siblings: 3, canPlan: true } });
    wrapper.find("details").element.setAttribute("open", "");
    await wrapper.findAll("button").find((b) => b.text() === "Xuống dưới").trigger("click");
    expect(wrapper.find("details").attributes("open")).toBeUndefined();
    expect(wrapper.emitted("action")[0][0]).toMatchObject({ kind: "down", index: 1 });
  });

  it("shows the progress on a phone too", () => {
    const wrapper = mount(WbsRow, { props: { node, tree } });
    expect(wrapper.findAll("span").filter((s) => s.text() === "42%")).toHaveLength(2);  // the wide column and the phone one
  });
});
