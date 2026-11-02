import { mount } from "@vue/test-utils";
import App from "../src/App.vue";
import { readBoot } from "../src/lib/boot.js";

describe("readBoot", () => {
  it("falls back to defaults without boot data", () => {
    expect(readBoot(undefined)).toMatchObject({ user: "Guest", lang: "vi", csrf_token: "" });
  });

  it("keeps the values the server sent", () => {
    const boot = readBoot({ user: "a@b.vn", full_name: "Nguyễn Văn A", csrf_token: "t" });
    expect(boot).toMatchObject({ user: "a@b.vn", full_name: "Nguyễn Văn A", csrf_token: "t", lang: "vi" });
  });

  it("ignores boot data that is not an object", () => {
    expect(readBoot("oops").user).toBe("Guest");
  });
});

describe("App", () => {
  it("renders the shell", () => {
    const wrapper = mount(App);
    expect(wrapper.text()).toContain("Quản lý dự án");
    expect(wrapper.find('a[href="/desk"]').exists()).toBe(true);
  });
});
