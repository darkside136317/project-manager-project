import { describe, expect, it } from "vitest";
import { BUILT, activeModules, moduleRoutes, projectTabs } from "../src/modules.js";

const base = [{ slug: "tong-quan" }, { slug: "cong-viec" }, { slug: "trao-doi" }, { slug: "tai-lieu" }];
const layer = {
  name: "layer",
  projectTabs: [{ slug: "a", after: "cong-viec" }, { slug: "b", after: "trao-doi" }, { slug: "c", after: "nowhere" }],
  routes: [{ path: "/x" }],
};

describe("industry modules", () => {
  it("are found next to the core when the SPA is built", () => {
    expect(BUILT.map((module) => module.name)).toContain("construction");  // apps/pm_construction/frontend/pm-module.js
  });

  it("switch on only when the server says the layer is installed", () => {
    expect(activeModules([], [layer])).toEqual([]);
    expect(activeModules(["layer"], [layer])).toEqual([layer]);
  });

  it("place their tabs after the ones they name", () => {
    expect(projectTabs(base, [layer]).map((tab) => tab.slug)).toEqual(["tong-quan", "cong-viec", "a", "trao-doi", "b", "tai-lieu", "c"]);
    expect(projectTabs(base, []).map((tab) => tab.slug)).toEqual(base.map((tab) => tab.slug));
    expect(moduleRoutes([layer])).toEqual([{ path: "/x" }]);
  });
});
