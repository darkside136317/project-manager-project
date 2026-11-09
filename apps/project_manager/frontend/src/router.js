import { createRouter, createWebHistory } from "vue-router";
import { boot } from "./lib/boot.js";
import { pageTitle } from "./lib/page.js";
import DashboardHome from "./pages/DashboardHome.vue";
import ForbiddenPage from "./pages/ForbiddenPage.vue";
import FormSubmissionPage from "./pages/FormSubmissionPage.vue";
import FormTemplatePage from "./pages/FormTemplatePage.vue";
import FormTemplatesPage from "./pages/FormTemplatesPage.vue";
import LogsPage from "./pages/LogsPage.vue";
import MasterPage from "./pages/MasterPage.vue";
import MonitorPage from "./pages/MonitorPage.vue";
import MyTasksPage from "./pages/MyTasksPage.vue";
import NotFound from "./pages/NotFound.vue";
import OutboxPage from "./pages/OutboxPage.vue";
import ProjectPage from "./pages/ProjectPage.vue";
import ProjectsPage from "./pages/ProjectsPage.vue";
import RolesPage from "./pages/RolesPage.vue";
import TaskPage from "./pages/TaskPage.vue";
import UsersPage from "./pages/UsersPage.vue";

// Frappe serves this app for /pm and every /pm/... path (hooks.website_route_rules).
export const routes = [
  { path: "/", name: "home", component: DashboardHome, meta: { title: "Tổng quan" } },
  { path: "/viec-cua-toi", name: "my-tasks", component: MyTasksPage, meta: { title: "Việc của tôi" } },
  { path: "/du-an", name: "projects", component: ProjectsPage, meta: { title: "Dự án" } },
  { path: "/du-an/:id/:tab?", name: "project", component: ProjectPage, meta: { title: "Dự án" } },
  { path: "/cong-viec/:id", name: "task", component: TaskPage, meta: { title: "Công việc" } },
  { path: "/hang-doi", name: "outbox", component: OutboxPage, meta: { title: "Hàng đợi gửi" } },
  { path: "/bieu-mau/:id", name: "form", component: FormSubmissionPage, meta: { title: "Biểu mẫu" } },
  { path: "/bieu-mau-mau", name: "form-templates", component: FormTemplatesPage, meta: { title: "Mẫu biểu mẫu" } },
  { path: "/bieu-mau-mau/:name", name: "form-template", component: FormTemplatePage, meta: { title: "Mẫu biểu mẫu" } },
  { path: "/danh-muc/:slug", name: "master", component: MasterPage, meta: { title: "Danh mục", sources: ["masters"] } },
  { path: "/quan-tri/nguoi-dung", name: "users", component: UsersPage, meta: { title: "Người dùng" } },
  { path: "/quan-tri/phan-quyen", name: "roles", component: RolesPage, meta: { title: "Phân quyền" } },
  { path: "/quan-tri/nhat-ky", name: "logs", component: LogsPage, meta: { title: "Nhật ký hệ thống" } },
  { path: "/quan-tri/giam-sat", name: "monitor", component: MonitorPage, meta: { title: "Giám sát hệ thống" } },
  { path: "/quan-tri/:slug", name: "admin-screen", component: MasterPage, meta: { title: "Quản trị", sources: ["admin"] } },
  { path: "/khong-co-quyen", name: "forbidden", component: ForbiddenPage, meta: { title: "Không có quyền" } },
  { path: "/:pathMatch(.*)*", name: "not-found", component: NotFound, meta: { title: "Không tìm thấy" } },
];

/** May the user open `path`? Administration pages only when the server put them in the sidebar (it still enforces
 * every call; this only avoids showing a page that would answer "no permission"). */
export function routeAllowed(path, nav = boot.nav) {
  if (!path.startsWith("/quan-tri/")) return true;
  return nav.flatMap((group) => group.items).some((item) => item.route.replace(/^\/pm/, "") === path);
}

export function createAppRouter(history = createWebHistory("/pm")) {
  const router = createRouter({ history, routes, scrollBehavior: () => ({ top: 0 }) });
  router.beforeEach((to) => (routeAllowed(to.path) ? true : { name: "forbidden" }));
  router.afterEach(() => {
    pageTitle.value = "";
  });
  return router;
}
