<script setup>
import { computed, provide, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import Icon from "../components/Icon.vue";
import TaskDrawer from "../components/TaskDrawer.vue";
import { api } from "../lib/api.js";
import { pageTitle } from "../lib/page.js";
import { PROJECT_TABS } from "../lib/work.js";
import BaselineTab from "./project/BaselineTab.vue";
import CalendarTab from "./project/CalendarTab.vue";
import FormsTab from "./project/FormsTab.vue";
import GanttTab from "./project/GanttTab.vue";
import KanbanTab from "./project/KanbanTab.vue";
import MembersTab from "./project/MembersTab.vue";
import OverviewTab from "./project/OverviewTab.vue";
import PeopleTab from "./project/PeopleTab.vue";
import WbsTab from "./project/WbsTab.vue";

// /pm/du-an/:id/:tab — one project. The overview is loaded here (title, permissions) and shared with the tabs; any
// tab opens a task in the drawer through `openTask`, and a change there asks the tab to reload (`version`).
const route = useRoute();
const router = useRouter();
const TABS = { "tong-quan": OverviewTab, "cong-viec": WbsTab, gantt: GanttTab, kanban: KanbanTab, lich: CalendarTab, "ai-lam-gi": PeopleTab,
  "bieu-mau": FormsTab, baseline: BaselineTab, "thanh-vien": MembersTab };

const project = computed(() => String(route.params.id || ""));
const tab = computed(() => (TABS[route.params.tab] ? String(route.params.tab) : "tong-quan"));
const overview = ref(null);
const error = ref("");
const task = ref(String(route.query.viec || ""));
const version = ref(0);

async function load() {
  error.value = "";
  try {
    overview.value = await api.projects.overview(project.value);
    pageTitle.value = overview.value.project.project_name;
  } catch (e) {
    error.value = e.message;
  }
}

function openTask(name) {
  task.value = name || "";
  router.replace({ query: { ...route.query, viec: name || undefined } });
}

function changed() {
  version.value += 1;
  load();
}

provide("project", { name: project, overview, openTask, version, reload: changed });
watch(project, () => {
  overview.value = null;
  load();
}, { immediate: true });
</script>

<template>
  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <template v-else>
    <header class="mb-4">
      <RouterLink to="/du-an" class="inline-flex items-center gap-1 text-xs text-ink-muted hover:underline"><Icon name="chevron-left" :size="14" /> Dự án</RouterLink>
      <h1 class="m-0 mt-1 text-xl font-semibold tracking-tight">{{ overview?.project.project_name || project }}</h1>
      <p v-if="overview" class="m-0 text-sm text-ink-muted">{{ overview.project.pm_code || overview.project.name }} · {{ overview.project.pm_state }}</p>
    </header>
    <nav class="-mx-1 mb-5 flex gap-1 overflow-x-auto border-b border-line px-1" aria-label="Các mục của dự án">
      <RouterLink v-for="item in PROJECT_TABS" :key="item.slug" :to="`/du-an/${encodeURIComponent(project)}/${item.slug}`"
        class="-mb-px flex shrink-0 items-center gap-1.5 border-b-2 px-3 py-2 text-sm no-underline"
        :class="tab === item.slug ? 'border-primary font-semibold text-primary' : 'border-transparent text-ink-muted hover:text-ink'"
        :aria-current="tab === item.slug ? 'page' : undefined">
        <Icon :name="item.icon" :size="16" /> {{ item.label }}
      </RouterLink>
    </nav>
    <component :is="TABS[tab]" v-if="overview" :key="`${project}-${tab}`" />
  </template>
  <TaskDrawer :name="task" @close="openTask('')" @changed="changed" />
</template>
