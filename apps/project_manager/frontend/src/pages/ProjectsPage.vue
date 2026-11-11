<script setup>
import { onMounted, reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import Drawer from "../components/Drawer.vue";
import EmptyState from "../components/EmptyState.vue";
import HealthBadge from "../components/HealthBadge.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import ProgressBar from "../components/ProgressBar.vue";
import { api } from "../lib/api.js";
import { debounce, formatDate } from "../lib/format.js";
import { toast } from "../lib/toast.js";
import { variance } from "../lib/work.js";

// Dự án: every project the user may see, with progress against plan; new projects, empty or from a template.
const STATES = ["Chuẩn bị", "Đang thực hiện", "Tạm dừng", "Đóng", "Hủy"];
const METHODS = ["Theo thời lượng", "Theo trọng số", "Bằng nhau"];
const EMPTY = { project_name: "", pm_code: "", expected_start_date: "", expected_end_date: "", pm_rollup_method: "", template: "" };
const router = useRouter();
const filters = reactive({ search: "", state: "", templates: false });
const rows = ref([]);
const more = ref(false);
const canCreate = ref(false);
const loading = ref(false);
const error = ref("");
const creating = ref(false);
const templates = ref([]);
const form = reactive({ ...EMPTY });
const saving = ref(false);

async function load(append = false) {
  loading.value = true;
  error.value = "";
  try {
    const result = await api.projects.list({ search: filters.search, state: filters.state, templates: filters.templates ? 1 : 0,
      start: append ? rows.value.length : 0 });
    rows.value = append ? [...rows.value, ...result.rows] : result.rows;
    more.value = result.more;
    canCreate.value = result.can_create;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function openCreate() {
  Object.assign(form, EMPTY);
  creating.value = true;
  templates.value = (await api.projects.list({ templates: 1, limit: 200 })).rows;
}

async function create() {
  saving.value = true;
  try {
    const { template, ...values } = form;
    for (const key of Object.keys(values)) if (!values[key]) delete values[key];
    const result = await api.projects.create(values, template || null);
    toast(result.tasks ? `Đã tạo dự án với ${result.tasks} công việc từ mẫu` : "Đã tạo dự án");
    creating.value = false;
    router.push(`/du-an/${encodeURIComponent(result.name)}/tong-quan`);
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    saving.value = false;
  }
}

const reload = debounce(() => load(), 300);
watch(() => filters.search, reload);
watch(() => [filters.state, filters.templates], () => load());
onMounted(load);
</script>

<template>
  <PageHeader title="Dự án" subtitle="Tiến độ thực tế so với kế hoạch của từng dự án.">
    <button v-if="canCreate" class="btn btn-primary" type="button" @click="openCreate"><Icon name="plus" :size="16" /> Tạo dự án</button>
  </PageHeader>

  <div class="mb-4 flex flex-wrap items-center gap-2">
    <input v-model="filters.search" class="input max-w-xs" type="search" placeholder="Tìm theo tên hoặc mã" aria-label="Tìm dự án" />
    <select v-model="filters.state" class="input w-auto" aria-label="Tình trạng">
      <option value="">Mọi tình trạng</option>
      <option v-for="state in STATES" :key="state" :value="state">{{ state }}</option>
    </select>
    <label class="flex items-center gap-2 text-sm"><input v-model="filters.templates" type="checkbox" /> Dự án mẫu</label>
  </div>

  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <EmptyState v-else-if="!loading && !rows.length" icon="folder-kanban" title="Chưa có dự án nào" text="Dự án bạn tham gia hoặc được cấp quyền xem sẽ hiện ở đây." />

  <ul class="m-0 grid list-none grid-cols-1 gap-3 p-0 lg:grid-cols-2">
    <li v-for="row in rows" :key="row.name">
      <RouterLink :to="`/du-an/${encodeURIComponent(row.name)}/tong-quan`" class="card block px-4 py-3 text-ink no-underline hover:shadow-pop">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <p class="m-0 truncate font-semibold">{{ row.project_name }}</p>
            <p class="m-0 text-xs text-ink-muted">{{ row.pm_code || row.name }} · {{ row.manager_name || "Chưa có quản lý" }}</p>
          </div>
          <span class="flex shrink-0 items-center gap-1">
            <HealthBadge v-if="row.pm_health && !row.pm_is_template" :level="row.pm_health" :reason="row.pm_health_reason" short />
            <span class="badge badge-muted">{{ row.pm_is_template ? "Mẫu" : row.pm_state }}</span>
          </span>
        </div>
        <div class="mt-3 flex items-center gap-3">
          <ProgressBar class="flex-1" :value="row.percent_complete" :planned="row.planned_progress" />
          <span class="w-12 text-right text-sm font-semibold">{{ Math.round(row.percent_complete || 0) }}%</span>
        </div>
        <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
          <span>Kế hoạch {{ Math.round(row.planned_progress) }}%
            <strong :class="variance(row.percent_complete, row.planned_progress) < -5 ? 'text-danger' : 'text-success'">({{ variance(row.percent_complete, row.planned_progress) >= 0 ? "+" : "" }}{{ variance(row.percent_complete, row.planned_progress) }})</strong></span>
          <span>{{ row.done }}/{{ row.tasks }} việc xong</span>
          <span v-if="row.late" class="font-medium text-danger">{{ row.late }} việc quá hạn</span>
          <span>{{ formatDate(row.expected_start_date) }} → {{ formatDate(row.expected_end_date) }}</span>
          <span v-if="row.pm_forecast_end" :class="row.expected_end_date && row.pm_forecast_end > row.expected_end_date ? 'font-medium text-danger' : ''">Dự báo xong {{ formatDate(row.pm_forecast_end) }}</span>
        </div>
      </RouterLink>
    </li>
  </ul>
  <div v-if="more" class="mt-3 text-center"><button class="btn" type="button" :disabled="loading" @click="load(true)">Xem thêm</button></div>

  <Drawer :open="creating" title="Tạo dự án" @close="creating = false">
    <form id="create-project" class="space-y-4" @submit.prevent="create">
      <div><label class="label" for="p-name">Tên dự án *</label><input id="p-name" v-model="form.project_name" class="input" required /></div>
      <div><label class="label" for="p-code">Mã dự án</label><input id="p-code" v-model="form.pm_code" class="input" /></div>
      <div class="grid grid-cols-2 gap-3">
        <div><label class="label" for="p-start">Bắt đầu</label><input id="p-start" v-model="form.expected_start_date" class="input" type="date" /></div>
        <div><label class="label" for="p-end">Kết thúc</label><input id="p-end" v-model="form.expected_end_date" class="input" type="date" /></div>
      </div>
      <div>
        <label class="label" for="p-template">Từ dự án mẫu</label>
        <select id="p-template" v-model="form.template" class="input">
          <option value="">Không dùng mẫu (dự án trống)</option>
          <option v-for="item in templates" :key="item.name" :value="item.name">{{ item.project_name }} ({{ item.tasks }} việc)</option>
        </select>
        <p class="mt-1 text-xs text-ink-muted">Cây công việc của mẫu được chép sang, ngày dời theo ngày bắt đầu của dự án mới.</p>
      </div>
      <div>
        <label class="label" for="p-method">Cách tính tiến độ</label>
        <select id="p-method" v-model="form.pm_rollup_method" class="input">
          <option value="">Mặc định</option>
          <option v-for="method in METHODS" :key="method" :value="method">{{ method }}</option>
        </select>
      </div>
    </form>
    <template #footer>
      <button class="btn" type="button" @click="creating = false">Hủy</button>
      <button class="btn btn-primary" type="submit" form="create-project" :disabled="saving"><Icon v-if="saving" name="loader" spin /> Tạo</button>
    </template>
  </Drawer>
</template>
