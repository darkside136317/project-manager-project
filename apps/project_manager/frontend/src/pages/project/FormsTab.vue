<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { formatDateTime } from "../../lib/format.js";
import { SUB, formStateBadge } from "../../lib/forms.js";
import { toast } from "../../lib/toast.js";

// Biểu mẫu of a project: every form filled in, by state and kind; a new form for the project; Excel of one kind.
const { name: project, overview, version } = inject("project");
const router = useRouter();
const rows = ref([]);
const more = ref(false);
const templates = ref([]);
const loading = ref(false);
const filters = reactive({ state: "", code: "" });
const chosen = ref("");
const canFill = computed(() => Boolean(overview.value?.can?.["task.update"] || overview.value?.can?.["plan.edit"]));
const exportUrl = computed(() => (filters.code ? api.forms.exportUrl(project.value, filters.code) : ""));

async function load(append = false) {
  loading.value = true;
  try {
    const result = await api.forms.list({ project: project.value, state: filters.state, template_code: filters.code,
      start: append ? rows.value.length : 0 });
    rows.value = append ? [...rows.value, ...result.rows] : result.rows;
    more.value = result.more;
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    loading.value = false;
  }
}

async function start() {
  try {
    const result = await api.forms.start(chosen.value, project.value);
    router.push(`/bieu-mau/${result.name}`);
  } catch (e) {
    toast(e.message, "error", 7000);
  }
}

watch(() => [filters.state, filters.code], () => load());
watch(version, () => load());
onMounted(async () => {
  load();
  templates.value = await api.forms.inUse();
});
</script>

<template>
  <div class="mb-3 flex flex-wrap items-center gap-2">
    <select v-model="filters.state" class="input w-auto" aria-label="Trạng thái">
      <option value="">Mọi trạng thái</option>
      <option :value="SUB.SUBMITTED">Chờ duyệt</option>
      <option :value="SUB.APPROVED">Đã duyệt</option>
      <option :value="SUB.RETURNED">Trả lại</option>
      <option :value="SUB.DRAFT">Nháp của tôi</option>
    </select>
    <select v-model="filters.code" class="input w-auto max-w-xs" aria-label="Loại biểu mẫu">
      <option value="">Mọi biểu mẫu</option>
      <option v-for="item in templates" :key="item.code" :value="item.code">{{ item.title }}</option>
    </select>
    <a v-if="exportUrl" :href="exportUrl" class="btn"><Icon name="file-spreadsheet" :size="16" /> Xuất Excel</a>
    <Icon v-if="loading" name="loader" spin class="text-ink-muted" />
  </div>

  <div v-if="canFill" class="mb-4 flex flex-wrap gap-2">
    <select v-model="chosen" class="input min-w-0 flex-1 sm:max-w-sm" aria-label="Chọn biểu mẫu để điền cho dự án">
      <option value="">Điền biểu mẫu cho cả dự án...</option>
      <option v-for="item in templates" :key="item.code" :value="item.code">{{ item.title }}</option>
    </select>
    <button class="btn btn-primary" type="button" :disabled="!chosen" @click="start"><Icon name="pencil" :size="16" /> Điền</button>
  </div>

  <EmptyState v-if="!loading && !rows.length" icon="clipboard-list" title="Chưa có biểu mẫu nào" text="Biểu mẫu điền cho dự án hoặc công việc sẽ hiện ở đây." />
  <ul class="m-0 list-none space-y-2 p-0">
    <li v-for="row in rows" :key="row.name">
      <RouterLink :to="`/bieu-mau/${row.name}`" class="card flex flex-wrap items-center gap-2 px-4 py-3 text-ink no-underline hover:shadow-pop">
        <span :class="formStateBadge(row.state)">{{ row.state }}</span>
        <span class="font-medium">{{ row.title }}</span>
        <span class="text-xs text-ink-muted">số {{ row.name }}<template v-if="row.task_label"> · {{ row.task_label }}</template></span>
        <span class="ml-auto text-xs text-ink-muted">{{ row.who }}<template v-if="row.submitted_on"> · {{ formatDateTime(row.submitted_on) }}</template></span>
      </RouterLink>
    </li>
  </ul>
  <div v-if="more" class="mt-3 text-center"><button class="btn" type="button" :disabled="loading" @click="load(true)">Xem thêm</button></div>
</template>
