<script setup>
import { computed, onMounted, ref } from "vue";
import EmptyState from "../components/EmptyState.vue";
import HealthBadge from "../components/HealthBadge.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import ProgressBar from "../components/ProgressBar.vue";
import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.js";
import { slipText, slipTone } from "../lib/gantt.js";
import { HEALTH, healthColour } from "../lib/health.js";
import { variance } from "../lib/work.js";

// Danh mục dự án: every running project I may read, the worst first: health and why, progress against plan, SPI,
// forecast end, current phase, open alerts.
const data = ref({ rows: [], totals: {}, alerts_open: 0 });
const health = ref("");
const loading = ref(false);
const error = ref("");
const rows = computed(() => (health.value ? data.value.rows.filter((r) => r.pm_health === health.value) : data.value.rows));
const link = (row, tab = "tong-quan") => `/du-an/${encodeURIComponent(row.name)}/${tab}`;

async function load() {
  loading.value = true;
  error.value = "";
  try {
    data.value = await api.alerts.portfolio();
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <PageHeader title="Danh mục dự án" subtitle="Các dự án đang chạy, dự án cần chú ý nhất ở trên.">
    <button class="btn btn-ghost" type="button" :disabled="loading" @click="load"><Icon name="refresh-cw" :size="16" /> Tải lại</button>
  </PageHeader>

  <div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4" role="group" aria-label="Lọc theo sức khỏe">
    <button v-for="level in HEALTH" :key="level" type="button" class="card px-4 py-3 text-left"
            :class="{ 'ring-2 ring-primary': health === level }" :aria-pressed="health === level"
            @click="health = health === level ? '' : level">
      <span class="block text-xs text-ink-muted">Sức khỏe {{ level }}</span>
      <span class="text-2xl font-semibold" :class="healthColour(level)">{{ data.totals[level] || 0 }}</span>
      <span class="text-xs text-ink-muted"> dự án</span>
    </button>
    <RouterLink to="/canh-bao" class="card block px-4 py-3 text-ink no-underline">
      <span class="block text-xs text-ink-muted">Cảnh báo đang mở</span>
      <span class="text-2xl font-semibold">{{ data.alerts_open }}</span>
    </RouterLink>
  </div>

  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <EmptyState v-else-if="!loading && !rows.length" icon="folder-kanban" title="Không có dự án nào"
              :text="health ? 'Không có dự án đang chạy nào ở mức sức khỏe này.' : 'Dự án bạn tham gia hoặc được cấp quyền xem sẽ hiện ở đây.'" />

  <div v-else class="card overflow-x-auto">
    <table class="w-full min-w-[860px] text-sm">
      <thead>
        <tr class="border-b border-line text-left text-xs text-ink-muted">
          <th class="px-4 py-2">Dự án</th><th class="px-2 py-2">Sức khỏe</th><th class="px-2 py-2">Tiến độ / kế hoạch</th>
          <th class="px-2 py-2 text-right">SPI</th><th class="px-2 py-2">Dự báo xong</th><th class="px-2 py-2">Giai đoạn hiện tại</th>
          <th class="px-2 py-2 text-right">Cảnh báo</th><th class="px-4 py-2 text-right">Quá hạn</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.name" class="border-b border-line last:border-0 align-top" data-portfolio-row>
          <td class="px-4 py-2">
            <RouterLink :to="link(row)" class="font-medium">{{ row.project_name }}</RouterLink>
            <span class="block text-xs text-ink-muted">{{ row.pm_code || row.name }} · {{ row.manager_name || "Chưa có quản lý" }}</span>
          </td>
          <td class="px-2 py-2"><HealthBadge :level="row.pm_health" :reason="row.pm_health_reason" detailed short /></td>
          <td class="px-2 py-2">
            <ProgressBar :value="row.percent_complete" :planned="row.planned_progress" :label="`Tiến độ ${row.project_name}`" />
            <span class="text-xs">{{ Math.round(row.percent_complete || 0) }}% / {{ Math.round(row.planned_progress || 0) }}%
              <strong :class="variance(row.percent_complete, row.planned_progress) < -5 ? 'text-danger' : 'text-success'">({{ variance(row.percent_complete, row.planned_progress) >= 0 ? "+" : "" }}{{ variance(row.percent_complete, row.planned_progress) }})</strong></span>
          </td>
          <td class="px-2 py-2 text-right" :class="row.pm_spi && row.pm_spi < 0.95 ? 'text-danger' : ''">{{ row.pm_spi ? Number(row.pm_spi).toFixed(2) : "—" }}</td>
          <td class="px-2 py-2">{{ formatDate(row.pm_forecast_end) || "—" }}<span class="block text-xs" :class="slipTone(row.forecast_slip)">{{ slipText(row.forecast_slip) }}</span></td>
          <td class="px-2 py-2">{{ row.phase || "—" }}<span v-if="row.phase_waiting" class="badge badge-warning ml-1">Chờ duyệt</span></td>
          <td class="px-2 py-2 text-right"><RouterLink v-if="row.alerts_open" :to="link(row)" class="font-semibold text-danger">{{ row.alerts_open }}</RouterLink><span v-else>0</span></td>
          <td class="px-4 py-2 text-right" :class="row.late ? 'font-semibold text-danger' : ''">{{ row.late }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p v-if="data.truncated" class="mt-2 text-xs text-ink-muted">Chỉ hiện 300 dự án đầu.</p>
</template>
