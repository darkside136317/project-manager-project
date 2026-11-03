import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory } from "vue-router";
import { describe, expect, it } from "vitest";
import App from "../src/App.vue";
import { readBoot } from "../src/lib/boot.js";
import { createAppRouter, routeAllowed } from "../src/router.js";

describe("readBoot", () => {
  it("falls back to defaults without boot data", () => {
    const boot = readBoot(undefined);
    expect(boot.user).toMatchObject({ name: "", capabilities: [], all_projects: false });
    expect(boot).toMatchObject({ home: "/pm", nav: [], csrf_token: "" });
  });

  it("keeps the values the server sent and completes the user", () => {
    const boot = readBoot({ user: { name: "a@b.vn", full_name: "Nguyễn Văn A" }, csrf_token: "t", company: "CTXD" });
    expect(boot.user).toMatchObject({ name: "a@b.vn", full_name: "Nguyễn Văn A", roles: [] });
    expect(boot).toMatchObject({ csrf_token: "t", company: "CTXD", lang: "vi" });
  });

  it("ignores boot data that is not an object", () => {
    expect(readBoot("oops").user.name).toBe("");
  });
});

describe("router", () => {
  const nav = [{ group: "Quản trị", items: [{ route: "/pm/quan-tri/nguoi-dung" }] }];

  it("opens administration pages only when the server listed them", () => {
    expect(routeAllowed("/quan-tri/nguoi-dung", nav)).toBe(true);
    expect(routeAllowed("/quan-tri/nhat-ky", nav)).toBe(false);
    expect(routeAllowed("/danh-muc/loai-nut-wbs", nav)).toBe(true);
  });
});

describe("App", () => {
  it("renders the shell around the home page", async () => {
    const router = createAppRouter(createMemoryHistory());
    router.push("/");
    await router.isReady();
    const wrapper = mount(App, { global: { plugins: [router] } });
    await flushPromises();
    expect(wrapper.text()).toContain("Quản lý dự án");
    expect(wrapper.text()).toContain("Tổng quan");
  });
});
