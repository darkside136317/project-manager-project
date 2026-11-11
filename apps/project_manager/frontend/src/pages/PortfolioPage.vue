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
import { columnText, extraColumns, percent, sparkline, toneText } from "../lib/people.js";
import { variance } from "../lib/work.js";

// Danh mục dự án: every running project I may read, the worst first: health and why, progress against plan, SPI,
// forecast end, current phase, open alerts; v2 (M9): work finished on time (4 weeks), members overloaded this week, the
// trend of the progress (8 weeks), and the columns of the industry layers (cost against the work done...).
const data = ref({ rows: [], totals: {}, alerts_open: 0 });
const health = ref("");
const loading = ref(false);
const error = ref("");
const rows = computed(() => (health.value ? data.value.rows.filter((r) => r.pm_health === health.value) : data.value.rows));
const link = (row, tab = "tong-quan") => `/du-an/${encodeURIComponent(row.name)}/${tab}`;
const extras = computed(() => extraColumns(data.value.rows));
const rateTone = (rate) => (rate === null || rate === undefined ? "" : rate < 0.7 ? "text-danger" : rate < 0.9 ? "text-warning" : "text-success");

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
    <table class="w-full text-sm" :style="{ minWidth: `${980 + extras.length * 90}px` }">
      <thead>
        <tr class="border-b border-line text-left text-xs text-ink-muted">
          <th class="px-4 py-2">Dự án</th><th class="px-2 py-2">Sức khỏe</th><th class="px-2 py-2">Tiến độ / kế hoạch</th>
          <th class="px-2 py-2 text-right">SPI</th><th class="px-2 py-2">Dự báo xong</th><th class="px-2 py-2">Giai đoạn hiện tại</th>
          <th class="px-2 py-2 text-right">Cảnh báo</th><th class="px-2 py-2 text-right">Quá hạn</th>
          <th class="px-2 py-2 text-right">Đúng hạn (4 tuần)</th><th class="px-2 py-2 text-right">Người quá tải</th>
          <th class="px-2 py-2">Xu hướng</th>
          <th v-for="col in extras" :key="col.key" class="px-2 py-2 text-right last:pr-4">{{ col.label }}</th>
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
          <td class="px-2 py-2 text-right" :class="row.late ? 'font-semibold text-danger' : ''">{{ row.late }}</td>
          <td class="px-2 py-2 text-right font-semibold" :class="rateTone(row.on_time_rate)" data-on-time>{{ percent(row.on_time_rate) }}</td>
          <td class="px-2 py-2 text-right" data-overloaded>
            <RouterLink v-if="row.overloaded" :to="`/khoi-luong-cong-viec?project=${encodeURIComponent(row.name)}`" class="font-semibold text-danger">{{ row.overloaded }}</RouterLink><span v-else>0</span>
          </td>
          <td class="px-2 py-2">
            <svg v-if="(row.trend || []).length > 1" width="64" height="20" viewBox="0 0 64 20" role="img" :aria-label="`Tiến độ 8 tuần: ${(row.trend || []).join(', ')}%`">
              <polyline :points="sparkline(row.trend, 64, 20)" fill="none" stroke="currentColor" stroke-width="1.5" class="text-primary" />
            </svg>
            <span v-else class="text-xs text-ink-muted">—</span>
          </td>
          <td v-for="col in extras" :key="col.key" class="px-2 py-2 text-right last:pr-4" :class="toneText(row.extra?.[col.key]?.tone)" :data-extra="col.key">{{ columnText(row.extra?.[col.key]) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p v-if="data.truncated" class="mt-2 text-xs text-ink-muted">Chỉ hiện 300 dự án đầu.</p>
</template>
