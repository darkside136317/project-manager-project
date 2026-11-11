<script setup>
import { computed, onMounted, ref, watch } from "vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import ReasonDialog from "../components/ReasonDialog.vue";
import { api } from "../lib/api.js";
import { formatDateTime } from "../lib/format.js";
import { ALERT_OPEN, alertBadge, levelText, spaPath } from "../lib/health.js";
import { toast } from "../lib/toast.js";

// Cảnh báo của tôi: what the rules told me about, open ones first (highest escalation on top). "Đã biết" stops the
// escalation; the alert closes by itself once the condition is gone.
const TABS = [{ key: "open", label: "Đang mở" }, { key: "closed", label: "Đã hết" }];
const tab = ref("open");
const rows = ref([]);
const openCount = ref(0);
const loading = ref(false);
const error = ref("");
const acknowledging = ref(null);
const busy = ref(false);
const dialogError = ref("");

const groups = computed(() => {
  const out = new Map();
  for (const row of rows.value) {
    const key = row.project_name || row.project || "Khác";
    if (!out.has(key)) out.set(key, []);
    out.get(key).push(row);
  }
  return [...out.entries()];
});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const result = await api.alerts.mine(tab.value);
    rows.value = result.alerts;
    openCount.value = result.open;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function acknowledge(note) {
  busy.value = true;
  dialogError.value = "";
  try {
    const updated = await api.alerts.acknowledge(acknowledging.value.name, note);
    rows.value = rows.value.map((row) => (row.name === updated.name ? { ...row, ...updated } : row));
    openCount.value = Math.max(0, openCount.value - 1);
    acknowledging.value = null;
    toast("Đã xác nhận: cảnh báo sẽ không leo thang nữa");
  } catch (e) {
    dialogError.value = e.message;
  } finally {
    busy.value = false;
  }
}

watch(tab, load);
onMounted(load);
</script>

<template>
  <PageHeader title="Cảnh báo" :subtitle="openCount ? `${openCount} cảnh báo đang mở chờ bạn xử lý` : 'Không có cảnh báo nào đang chờ bạn.'" />

  <div class="mb-4 flex gap-2" role="tablist" aria-label="Lọc cảnh báo">
    <button v-for="item in TABS" :key="item.key" class="btn" :class="{ 'btn-primary': tab === item.key }" type="button"
            role="tab" :aria-selected="tab === item.key" @click="tab = item.key">{{ item.label }}</button>
  </div>

  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <EmptyState v-else-if="!loading && !rows.length" icon="bell-off" :title="tab === 'open' ? 'Không có cảnh báo đang mở' : 'Chưa có cảnh báo nào đã hết'"
              text="Cảnh báo đến từ các quy tắc: sắp đến hạn, quá hạn, nguy cơ trễ, chưa nhận việc..." />

  <section v-for="[project, items] in groups" :key="project" class="mb-5" :aria-label="`Cảnh báo của ${project}`">
    <h2 class="mb-2 text-sm font-semibold text-ink-muted">{{ project }}</h2>
    <ul class="m-0 list-none space-y-2 p-0">
      <li v-for="row in items" :key="row.name" class="card px-4 py-3" data-alert>
        <div class="flex flex-wrap items-center gap-2 text-xs">
          <span :class="alertBadge(row.state)">{{ row.state }}</span>
          <span class="badge badge-muted">{{ row.rule_type }}</span>
          <span v-if="levelText(row.level)" class="badge badge-warning"><Icon name="arrow-up" :size="12" /> {{ levelText(row.level) }}</span>
          <span class="ml-auto text-ink-muted">{{ formatDateTime(row.opened_on) }}</span>
        </div>
        <p class="m-0 mt-2 text-sm">{{ row.message }}</p>
        <p v-if="row.acknowledged_by" class="m-0 mt-1 text-xs text-ink-muted">Đã xác nhận lúc {{ formatDateTime(row.acknowledged_on) }}</p>
        <div class="mt-2 flex flex-wrap gap-2">
          <RouterLink :to="spaPath(row.link)" class="btn"><Icon name="external-link" :size="14" /> Mở</RouterLink>
          <button v-if="row.state === ALERT_OPEN" class="btn" type="button" @click="acknowledging = row">
            <Icon name="check" :size="14" /> Đã biết, đang xử lý
          </button>
        </div>
      </li>
    </ul>
  </section>

  <ReasonDialog :open="Boolean(acknowledging)" title="Xác nhận cảnh báo" :message="acknowledging?.message || ''"
                label="Ghi chú (không bắt buộc)" confirm-text="Xác nhận" :required="false" :busy="busy" :error="dialogError"
                @confirm="acknowledge" @cancel="acknowledging = null" />
</template>
