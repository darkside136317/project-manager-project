import { flushPromises, mount } from "@vue/test-utils";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/lib/api.js", () => ({
  api: {
    alerts: { mine: vi.fn(), acknowledge: vi.fn(), portfolio: vi.fn(), preference: vi.fn(), savePreference: vi.fn(),
      ofProject: vi.fn(), passPhase: vi.fn() },
    wbs: { setGateMode: vi.fn() },
  },
  call: vi.fn(),
}));

import { api } from "../src/lib/api.js";
import HealthBadge from "../src/components/HealthBadge.vue";
import NotificationPrefsDialog from "../src/components/NotificationPrefsDialog.vue";
import AlertsPage from "../src/pages/AlertsPage.vue";
import OverviewTab from "../src/pages/project/OverviewTab.vue";
import PortfolioPage from "../src/pages/PortfolioPage.vue";
import { routes } from "../src/router.js";
import {
  canPassPhase,
  gateSummary,
  healthBadge,
  healthColour,
  healthText,
  levelText,
  spaPath,
} from "../src/lib/health.js";

beforeEach(() => vi.clearAllMocks());

const router = () => createRouter({ history: createMemoryHistory(), routes });

describe("health helpers", () => {
  it("colours and names the levels", () => {
    expect(healthBadge("Đỏ")).toBe("badge badge-danger");
    expect(healthBadge("Vàng")).toBe("badge badge-warning");
    expect(healthBadge("Xanh")).toBe("badge badge-success");
    expect(healthBadge("")).toBe("badge badge-muted");
    expect(healthColour("Đỏ")).toBe("text-danger");
    expect(healthText("Đỏ")).toBe("Đỏ · Nguy cơ trễ");
    expect(healthText("")).toBe("Chưa đánh giá");
  });

  it("speaks of escalation and server links", () => {
    expect(levelText(0)).toBe("");
    expect(levelText(2)).toBe("Leo thang bậc 2");
    expect(spaPath("/pm/cong-viec/TASK-1")).toBe("/cong-viec/TASK-1");
    expect(spaPath("/pm")).toBe("/");
    expect(spaPath("")).toBe("/");
  });

  it("says what the current phase waits for and who may pass it", () => {
    expect(gateSummary(null)).toBe("Đã qua mọi giai đoạn");
    expect(gateSummary({ missing: ["còn 2 việc chưa xong"] })).toBe("Chưa đủ điều kiện: còn 2 việc chưa xong");
    expect(gateSummary({ missing: [], state: "Chờ duyệt" })).toMatch(/chờ quản lý dự án duyệt/);
    expect(gateSummary({ missing: [], mode: "Thủ công" })).toMatch(/chuyển khi sẵn sàng/);
    expect(canPassPhase({ can_pass: true, mode: "Cần duyệt" })).toBe(true);
    expect(canPassPhase({ can_pass: true, mode: "Tự động" })).toBe(false);  // it passes by itself
    expect(canPassPhase({ can_pass: false, mode: "Thủ công" })).toBe(false);
    expect(canPassPhase(null)).toBe(false);
  });

  it("routes the new screens", () => {
    const r = router();
    expect(r.resolve("/canh-bao").name).toBe("alerts");
    expect(r.resolve("/danh-muc-du-an").name).toBe("portfolio");
  });
});

describe("health badge", () => {
  it("shows the level, the reason on hover and below when detailed", () => {
    const wrapper = mount(HealthBadge, { props: { level: "Vàng", reason: "SPI 0.90", detailed: true } });
    expect(wrapper.text()).toContain("Vàng · Cần chú ý");
    expect(wrapper.text()).toContain("SPI 0.90");
    expect(wrapper.find("[data-health]").attributes("title")).toBe("SPI 0.90");
    expect(mount(HealthBadge, { props: { level: "Đỏ", short: true } }).text()).toBe("Đỏ");
  });
});

const ALERTS = [
  { name: 2, state: "Đang mở", level: 1, rule_type: "Quá hạn", message: "Quá hạn: cột", project: "P1", project_name: "Nhà xưởng",
    link: "/pm/cong-viec/T1", opened_on: "2026-11-08 06:00:00" },
  { name: 1, state: "Đang mở", level: 0, rule_type: "Thiếu nhật ký thi công", message: "Chưa có nhật ký", project: "P2",
    project_name: "Nhà phố", link: "/pm/du-an/P2/tong-quan", opened_on: "2026-11-11 06:00:00" },
];

describe("alerts page", () => {
  it("groups by project, shows the escalation and acknowledges", async () => {
    api.alerts.mine.mockResolvedValue({ alerts: ALERTS, open: 2 });
    api.alerts.acknowledge.mockResolvedValue({ ...ALERTS[0], state: "Đã xác nhận", acknowledged_by: "a@b" });
    const wrapper = mount(AlertsPage, { global: { plugins: [router()] }, attachTo: document.body });
    await flushPromises();
    expect(api.alerts.mine).toHaveBeenCalledWith("open");
    expect(wrapper.findAll("[data-alert]")).toHaveLength(2);
    expect(wrapper.text()).toContain("Nhà xưởng");
    expect(wrapper.text()).toContain("Leo thang bậc 1");
    expect(wrapper.text()).toContain("2 cảnh báo đang mở");
    expect(wrapper.find("[data-alert] a").attributes("href")).toBe("/cong-viec/T1");
    await wrapper.findAll("button").find((b) => b.text().includes("Đã biết")).trigger("click");
    const note = document.querySelector("textarea");
    note.value = "đang xử lý";
    note.dispatchEvent(new Event("input"));
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Xác nhận").click();
    await flushPromises();
    expect(api.alerts.acknowledge).toHaveBeenCalledWith(2, "đang xử lý");
    expect(wrapper.text()).toContain("Đã xác nhận");
    expect(wrapper.text()).toContain("1 cảnh báo đang mở");
    wrapper.unmount();
  });

  it("explains an empty list", async () => {
    api.alerts.mine.mockResolvedValue({ alerts: [], open: 0 });
    const wrapper = mount(AlertsPage, { global: { plugins: [router()] } });
    await flushPromises();
    expect(wrapper.text()).toContain("Không có cảnh báo đang mở");
  });
});

describe("portfolio", () => {
  it("lists the projects and filters by health", async () => {
    api.alerts.portfolio.mockResolvedValue({
      rows: [
        { name: "P1", project_name: "Nhà xưởng", pm_health: "Đỏ", pm_health_reason: "SPI 0.79", percent_complete: 33,
          planned_progress: 38, pm_spi: 0.79, forecast_slip: 0, phase: "1 PHẦN MÓNG", alerts_open: 4, late: 1 },
        { name: "P2", project_name: "Văn phòng", pm_health: "Xanh", percent_complete: 50, planned_progress: 50, pm_spi: 1,
          forecast_slip: -2, phase: "2 Thân", phase_waiting: true, alerts_open: 0, late: 0 },
      ],
      totals: { Đỏ: 1, Vàng: 0, Xanh: 1 }, alerts_open: 4,
    });
    const wrapper = mount(PortfolioPage, { global: { plugins: [router()] } });
    await flushPromises();
    const rows = wrapper.findAll("[data-portfolio-row]");
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain("SPI 0.79");
    expect(rows[1].text()).toContain("Chờ duyệt");
    expect(rows[1].text()).toContain("sớm 2 ngày");
    await wrapper.findAll("button").find((b) => b.text().includes("Sức khỏe Đỏ")).trigger("click");
    expect(wrapper.findAll("[data-portfolio-row]")).toHaveLength(1);
  });
});

describe("notification settings", () => {
  it("loads, changes and saves one's own choices", async () => {
    api.alerts.preference.mockResolvedValue({ email: 1, quiet_start: "21:00", quiet_end: "07:00", digest_daily: 1,
      digest_weekly: 1, muted_types: [], types: ["Quá hạn", "Sắp đến hạn"], email_ready: false });
    api.alerts.savePreference.mockResolvedValue({});
    const wrapper = mount(NotificationPrefsDialog, { props: { open: false }, attachTo: document.body });
    await wrapper.setProps({ open: true });
    await flushPromises();
    expect(document.body.textContent).toContain("chưa có tài khoản email gửi đi");
    const muted = [...document.querySelectorAll("label")].find((l) => l.textContent.includes("Sắp đến hạn")).querySelector("input");
    muted.click();
    const start = document.querySelector("#quiet-start");
    start.value = "22:30";
    start.dispatchEvent(new Event("input"));
    document.querySelector("#notification-prefs").dispatchEvent(new Event("submit"));
    await flushPromises();
    expect(api.alerts.savePreference).toHaveBeenCalledWith(expect.objectContaining({ quiet_start: "22:30", muted_types: "Sắp đến hạn",
      email: 1, digest_daily: 1 }));
    expect(wrapper.emitted("close")).toBeTruthy();
    wrapper.unmount();
  });
});

const OVERVIEW = {
  project: { name: "P1", project_name: "Nhà xưởng", percent_complete: 33, pm_rollup_method: "Theo giá trị dự toán" },
  planned_progress: 38, schedule: { spi: 0.79 }, curve: [], delays: [], recent: [], pending_acceptance: 0, forms_waiting: 0,
  tasks: { total: 12, done: 5, working: 2, review: 0, late: 1, soon: 1 }, sees_all_tasks: true,
  health: { level: "Đỏ", reason: "SPI 0.79" }, alerts_open: 1,
  can: { "plan.edit": true, "task.approve": true },
  gate: { phases: 3, done: 0, current: { name: "T1", label: "1 PHẦN MÓNG", mode: "Cần duyệt", state: "Chờ duyệt", missing: [],
    next: "2 PHẦN THÂN", can_pass: true } },
  phases: [{ name: "T1", subject: "PHẦN MÓNG", pm_wbs_code: "1", status: "Completed", progress: 100, planned_progress: 100,
    is_group: 1, pm_gate_mode: "Cần duyệt", pm_gate_state: "Chờ duyệt" }],
};

describe("overview: health, phase gate, alerts", () => {
  it("shows them, passes the phase and sets its mode", async () => {
    api.alerts.ofProject.mockResolvedValue([{ name: 7, state: "Đang mở", level: 1, rule_type: "Quá hạn", message: "Quá hạn: cột",
      link: "/pm/cong-viec/T5" }]);
    api.alerts.passPhase.mockResolvedValue({});
    api.wbs.setGateMode.mockResolvedValue({});
    const project = { name: computed(() => "P1"), overview: ref(OVERVIEW), openTask: vi.fn(), version: ref(0), reload: vi.fn() };
    const r = createRouter({ history: createMemoryHistory(), routes });
    const wrapper = mount(OverviewTab, { global: { plugins: [r], provide: { project } }, attachTo: document.body });
    await flushPromises();
    const card = wrapper.find("[data-health-card]");
    expect(card.text()).toContain("Đỏ · Nguy cơ trễ");
    expect(card.text()).toContain("Giai đoạn 1/3: 1 PHẦN MÓNG");
    expect(card.text()).toContain("chờ quản lý dự án duyệt");
    expect(wrapper.findAll("[data-project-alert]")).toHaveLength(1);
    expect(wrapper.text()).toContain("Leo thang bậc 1");
    expect(wrapper.text()).toContain("Chờ duyệt chuyển");
    await card.findAll("button").find((b) => b.text().includes("Duyệt chuyển giai đoạn")).trigger("click");
    [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Chuyển giai đoạn").click();
    await flushPromises();
    expect(api.alerts.passPhase).toHaveBeenCalledWith("T1", "");
    expect(project.reload).toHaveBeenCalled();
    const select = wrapper.find('select[aria-label="Chuyển giai đoạn PHẦN MÓNG"]');
    expect(select.element.value).toBe("Cần duyệt");
    await select.setValue("Tự động");
    await flushPromises();
    expect(api.wbs.setGateMode).toHaveBeenCalledWith("T1", "Tự động");
    wrapper.unmount();
  });
});

