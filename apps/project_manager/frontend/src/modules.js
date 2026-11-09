// Screens of the industry layers. A layer app may ship `frontend/pm-module.js` (found here when the SPA is built: the
// core never names a layer); the server says which layers are installed (boot.modules, hook `pm_spa_modules`) and only
// those are switched on. A module looks like:
//   export default { name: "construction", projectTabs: [{ slug, label, icon, component, after: "cong-viec" }], routes: [] }
// Its files import the core through the "@pm" alias (vite.config.js).
import { boot } from "./lib/boot.js";

const found = import.meta.glob("../../../*/frontend/pm-module.js", { eager: true });

export const BUILT = Object.values(found).map((module) => module.default).filter((module) => module && module.name);

export function activeModules(installed = boot.modules || [], built = BUILT) {
  return built.filter((module) => installed.includes(module.name));
}

/** The project's tabs: the core's, with each module's tabs placed after the tab it names (at the end otherwise). */
export function projectTabs(base, modules = activeModules()) {
  const tabs = [...base];
  for (const module of modules) {
    for (const tab of module.projectTabs || []) {
      const at = tabs.findIndex((item) => item.slug === tab.after);
      const entry = { slug: tab.slug, label: tab.label, icon: tab.icon, component: tab.component };
      if (at >= 0) tabs.splice(at + 1, 0, entry);
      else tabs.push(entry);
    }
  }
  return tabs;
}

export const moduleRoutes = (modules = activeModules()) => modules.flatMap((module) => module.routes || []);
