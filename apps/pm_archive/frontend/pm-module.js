// Screens of the archive layer (lưu trữ hồ sơ), switched on by the core when this app is installed (boot.modules has
// "archive"; the core's src/modules.js finds this file when the SPA is built). The sidebar entry comes from the server
// (hook pm_nav_items), only for whoever may read some archive.
import ArchiveFilePage from "./src/ArchiveFilePage.vue";
import ArchivePage from "./src/ArchivePage.vue";
import ArchiveTab from "./src/ArchiveTab.vue";

export default {
  name: "archive",
  projectTabs: [
    { slug: "ho-so-luu-tru", label: "Hồ sơ lưu trữ", icon: "archive", component: ArchiveTab, after: "tai-lieu" },
  ],
  routes: [
    { path: "/luu-tru", name: "archive", component: ArchivePage, meta: { title: "Lưu trữ hồ sơ" } },
    { path: "/luu-tru/:name", name: "archive-file", component: ArchiveFilePage, meta: { title: "Hồ sơ lưu trữ" } },
  ],
};
