import { flushPromises, mount } from "@vue/test-utils";
import { computed, ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/lib/api.js", () => ({
  api: {
    activity: { feed: vi.fn(), entry: vi.fn(), people: vi.fn(), post: vi.fn(), hide: vi.fn(), follow: vi.fn(), markRead: vi.fn(), search: vi.fn() },
    media: { upload: vi.fn(), gallery: vi.fn(), url: (name, size) => `/photo/${name}/${size}` },
    documents: { list: vi.fn(), detail: vi.fn(), create: vi.fn(), addVersion: vi.fn(), approve: vi.fn(), url: (name, v) => `/doc/${name}/${v}` },
    schedule: { searchTasks: vi.fn() },
    tasks: { report: vi.fn() },
  },
  call: vi.fn(),
}));

vi.mock("../src/lib/sync.js", async () => {
  const { reactive } = await import("vue");
  const network = reactive({ online: true, items: [], sending: false });
  return {
    network,
    onSent: vi.fn(() => () => {}),
    queueComment: vi.fn(async () => ({ id: "q1" })),
    preparePhotos: vi.fn(async () => []),
    queuedFor: (doctype, name) => network.items.filter((item) => item.reference?.doctype === doctype && item.reference?.name === name),
    removeQueued: vi.fn(),
    retryQueued: vi.fn(),
    sendNow: vi.fn(),
    KINDS: { comment: { label: "Trao đổi" }, progress: { label: "Báo cáo tiến độ" } },
  };
});

import { api } from "../src/lib/api.js";
import { network, queueComment } from "../src/lib/sync.js";
import Composer from "../src/components/timeline/Composer.vue";
import Timeline from "../src/components/timeline/Timeline.vue";
import OutboxPage from "../src/pages/OutboxPage.vue";
import DocumentsTab from "../src/pages/project/DocumentsTab.vue";

const today = new Date().toISOString().slice(0, 10);
const comment = { name: 12, type: "Bình luận", actor: "an@x.vn", actor_name: "Lê An", content: "Nhờ @[Bình](binh@x.vn) xem cốp pha", creation: `${today} 08:30:00`,
  task: "T-1", photos: [{ name: 5, width: 800, height: 600, thumb: true }], mentions: ["binh@x.vn"], mine: true };
const change = { name: 11, type: "Tiến độ", actor: "an@x.vn", actor_name: "Lê An", content: "Tiến độ 0% → 30%", creation: `${today} 08:00:00`, task: "T-1", photos: [], mentions: [], mine: true };

function router() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: "/:any(.*)*", component: { template: "<div />" } }] });
}

beforeEach(() => {
  vi.clearAllMocks();
  network.items = [];
  network.online = true;
  api.activity.feed.mockResolvedValue({ entries: [comment, change], more: false, next: null, following: false, last_read: 0, unread: 1 });
  api.activity.markRead.mockResolvedValue({});
});

describe("Timeline", () => {
  it("shows comments with their mentions and photos, and the history, by day", async () => {
    const wrapper = mount(Timeline, { props: { doctype: "Task", name: "T-1" }, global: { stubs: { teleport: true } } });
    await flushPromises();
    expect(wrapper.text()).toContain("Hôm nay");
    expect(wrapper.text()).toContain("@Bình");
    expect(wrapper.find("[title='binh@x.vn']").exists()).toBe(true);
    expect(wrapper.find("button[aria-label='Xem ảnh 1']").exists()).toBe(true);
    expect(wrapper.text()).toContain("Tiến độ 0% → 30%");
    expect(api.activity.markRead).toHaveBeenCalledWith("Task", "T-1", 12);
  });

  it("starts following on request", async () => {
    api.activity.follow.mockResolvedValue({ following: true });
    const wrapper = mount(Timeline, { props: { doctype: "Task", name: "T-1" }, global: { stubs: { teleport: true } } });
    await flushPromises();
    await wrapper.findAll("button").find((b) => b.text() === "Theo dõi").trigger("click");
    await flushPromises();
    expect(api.activity.follow).toHaveBeenCalledWith("Task", "T-1", true);
    expect(wrapper.text()).toContain("Đang theo dõi");
  });

  it("shows what waits to be sent, and says when there is no connection", async () => {
    network.online = false;
    network.items = [{ id: "q1", kind: "comment", user: "", reference: { doctype: "Task", name: "T-1" }, payload: { content: "Viết lúc mất mạng" }, photos: [], state: "waiting", tries: 0, error: "" }];
    const wrapper = mount(Timeline, { props: { doctype: "Task", name: "T-1" }, global: { stubs: { teleport: true } } });
    await flushPromises();
    const waiting = wrapper.find("[aria-label='Đang chờ gửi']");
    expect(waiting.text()).toContain("Viết lúc mất mạng");
    expect(waiting.text()).toContain("Chờ có mạng");
  });
});

describe("Composer", () => {
  it("queues the comment and empties itself", async () => {
    const wrapper = mount(Composer, { props: { doctype: "Task", name: "T-1", label: "1 Cốp pha" } });
    const send = wrapper.find("button[type='submit']");
    expect(send.attributes("disabled")).toBeDefined();
    await wrapper.find("textarea").setValue("Đã ghép xong");
    await wrapper.find("form").trigger("submit");
    await flushPromises();
    expect(queueComment).toHaveBeenCalledWith({ doctype: "Task", name: "T-1" }, "Đã ghép xong", [], "1 Cốp pha");
    expect(wrapper.find("textarea").element.value).toBe("");
  });

  it("refuses a text that is too long", async () => {
    const wrapper = mount(Composer, { props: { doctype: "Task", name: "T-1" } });
    await wrapper.find("textarea").setValue("x".repeat(5001));
    expect(wrapper.text()).toContain("Dài quá 5000 ký tự");
    expect(wrapper.find("button[type='submit']").attributes("disabled")).toBeDefined();
  });

  it("suggests people after @", async () => {
    api.activity.people.mockResolvedValue([{ user: "binh@x.vn", full_name: "Trần Bình" }, { user: "chi@x.vn", full_name: "Ngô Chi" }]);
    const wrapper = mount(Composer, { props: { doctype: "Task", name: "T-1" } });
    const box = wrapper.find("textarea");
    box.element.value = "Nhờ @bì";
    box.element.setSelectionRange(7, 7);
    await box.trigger("input");
    await flushPromises();
    const options = wrapper.findAll("[role='option']");
    expect(options).toHaveLength(1);
    await options[0].find("button").trigger("mousedown");
    expect(box.element.value).toBe("Nhờ @[Trần Bình](binh@x.vn) ");
  });
});

describe("DocumentsTab", () => {
  const project = { name: computed(() => "P-1"), overview: ref({ can: {} }), openTask: vi.fn(), version: ref(0), reload: vi.fn() };
  const doc = { name: "PMD-1", title: "Mặt bằng tầng 3", category: "Bản vẽ", status: "Nháp", current_version: 2, approved_version: 1,
    file_name: "mb.pdf", content_type: "application/pdf", size_bytes: 2048, updated_on: `${today} 09:00:00` };

  it("lists documents with the version in force", async () => {
    api.documents.list.mockResolvedValue({ documents: [doc], more: false, categories: ["Bản vẽ", "Khác"], can: { upload: true, approve: true } });
    const wrapper = mount(DocumentsTab, { global: { plugins: [router()], provide: { project }, stubs: { teleport: true } } });
    await flushPromises();
    expect(wrapper.text()).toContain("Mặt bằng tầng 3");
    expect(wrapper.text()).toContain("Bản 2 chờ duyệt · đang dùng bản 1");
    expect(wrapper.text()).toContain("Tải lên tài liệu");
  });

  it("approves a draft newer than the one in force", async () => {
    api.documents.list.mockResolvedValue({ documents: [doc], more: false, categories: ["Bản vẽ"], can: { upload: true, approve: true } });
    const versions = [
      { version_no: 2, status: "Nháp", file_name: "mb2.pdf", content_type: "application/pdf", size_bytes: 2048, uploaded_by_name: "An", uploaded_on: `${today} 09:00:00` },
      { version_no: 1, status: "Đã duyệt", file_name: "mb.pdf", content_type: "application/pdf", size_bytes: 1024, uploaded_by_name: "An", uploaded_on: `${today} 08:00:00`, approved_by: "x", approved_by_name: "Bình", approved_on: `${today} 08:30:00` },
    ];
    api.documents.detail.mockResolvedValue({ ...doc, versions, can: { upload: true, approve: true } });
    api.documents.approve.mockResolvedValue({ ...doc, status: "Đã duyệt", approved_version: 2, versions, can: { upload: true, approve: true } });
    const wrapper = mount(DocumentsTab, { global: { plugins: [router()], provide: { project }, stubs: { teleport: true } } });
    await flushPromises();
    await wrapper.find("ul button").trigger("click");
    await flushPromises();
    const approve = wrapper.findAll("button").filter((b) => b.text().includes("Duyệt bản này"));
    expect(approve).toHaveLength(1);  // the approved version 1 cannot be approved again
    await approve[0].trigger("click");
    await flushPromises();
    expect(api.documents.approve).toHaveBeenCalledWith("PMD-1", 2);
  });
});

describe("OutboxPage", () => {
  it("lists what waits, oldest first, with what can be done about it", async () => {
    network.items = [
      { id: "a", kind: "comment", user: "", label: "1 Cốp pha", reference: { doctype: "Task", name: "T-1" }, payload: { content: "@[Bình](b@x) xem" },
        photos: [{ size: 300000 }], state: "failed", tries: 2, error: "Dài quá", created: Date.now() - 60000 },
      { id: "b", kind: "progress", user: "", label: "1 Cốp pha", reference: { doctype: "Task", name: "T-1" }, payload: { task: "T-1", values: { progress_value: 30, note: "ghép 30%" } },
        photos: [], state: "waiting", tries: 0, error: "", created: Date.now() },
    ];
    const wrapper = mount(OutboxPage, { global: { plugins: [router()] } });
    await flushPromises();
    const text = wrapper.text();
    expect(text).toContain("@Bình xem · 1 ảnh (293 KB)");
    expect(text).toContain("Không gửi được: Dài quá");
    expect(text).toContain("30% · ghép 30%");
    expect(text.indexOf("Trao đổi")).toBeLessThan(text.indexOf("Báo cáo tiến độ"));
    expect(wrapper.findAll("button").some((b) => b.text().includes("Thử lại"))).toBe(true);
  });
});
