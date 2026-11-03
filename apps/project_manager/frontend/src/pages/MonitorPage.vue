<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import { api } from "../lib/api.js";
import { SERVICE_LABELS, diskTone, queueText, serviceTone } from "../lib/admin.js";
import { formatDateTime, formatNumber } from "../lib/format.js";

// The state of the whole system on one screen: services, data volume, background jobs, storage, users and the log.
const data = ref(null);
const error = ref("");
const loading = ref(false);
let timer = null;

async function load() {
  loading.value = true;
  try {
    data.value = await api.monitor();
    error.value = "";
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
    clearTimeout(timer);
    timer = setTimeout(load, 30000);
  }
}
onMounted(load);
onBeforeUnmount(() => clearTimeout(timer));
const toneText = { success: "text-success", warning: "text-warning", danger: "text-danger", muted: "text-ink-muted" };
</script>

<template>
  <PageHeader title="Giám sát hệ thống" :subtitle="data ? `Site ${data.site} · cập nhật ${formatDateTime(data.checked_at)}` : 'Tình trạng vận hành của hệ thống.'">
    <button class="btn" type="button" :disabled="loading" @click="load"><Icon name="refresh-cw" :size="16" :spin="loading" /> Làm mới</button>
  </PageHeader>

  <EmptyState v-if="error" icon="alert-triangle" title="Không đọc được tình trạng hệ thống" :text="error" />
  <div v-else-if="!data" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><div v-for="n in 5" :key="n" class="card h-32 animate-pulse bg-surface-muted"></div></div>

  <div v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
    <section class="card px-4 py-4" aria-label="Dịch vụ">
      <h2 class="m-0 mb-3 flex items-center gap-2 text-sm font-semibold"><Icon name="server" :size="16" /> Dịch vụ</h2>
      <p v-for="(service, name) in data.services" :key="name" class="m-0 mb-2 text-sm">
        <span class="font-medium">{{ SERVICE_LABELS[name] || name }}</span>:
        <span :class="toneText[serviceTone(service)]">{{ service.ok ? "Bình thường" : "Cần xử lý" }}</span>
        <span class="block text-xs text-ink-muted">{{ service.message }}</span>
      </p>
    </section>

    <section class="card px-4 py-4" aria-label="Dữ liệu">
      <h2 class="m-0 mb-3 flex items-center gap-2 text-sm font-semibold"><Icon name="database" :size="16" /> Dữ liệu</h2>
      <p class="m-0 text-2xl font-semibold">{{ formatNumber(data.data.projects) }} dự án</p>
      <p class="m-0 text-sm text-ink-soft">{{ formatNumber(data.data.tasks) }} công việc · {{ formatNumber(data.data.activity) }} mục dòng thời gian</p>
    </section>

    <section class="card px-4 py-4" aria-label="Công việc nền">
      <h2 class="m-0 mb-3 flex items-center gap-2 text-sm font-semibold"><Icon name="activity" :size="16" /> Công việc nền</h2>
      <p class="m-0 text-sm">Hàng đợi: {{ queueText(data.jobs.queues) }}</p>
      <p class="m-0 text-sm text-ink-soft">{{ data.jobs.workers === null ? "Không đọc được số tiến trình" : `${data.jobs.workers} tiến trình xử lý` }}</p>
      <p class="m-0 mt-1 text-sm" :class="data.jobs.errors_24h ? 'text-warning' : 'text-ink-soft'">{{ formatNumber(data.jobs.errors_24h) }} lỗi hệ thống trong 24 giờ · {{ formatNumber(data.jobs.failed_7d) }} tác vụ định kỳ lỗi trong 7 ngày</p>
    </section>

    <section class="card px-4 py-4" aria-label="Lưu trữ">
      <h2 class="m-0 mb-3 flex items-center gap-2 text-sm font-semibold"><Icon name="hard-drive" :size="16" /> Lưu trữ</h2>
      <template v-if="data.storage.disk">
        <p class="m-0 text-2xl font-semibold" :class="toneText[diskTone(data.storage.disk)]">{{ data.storage.disk.used_percent }}% đã dùng</p>
        <p class="m-0 text-sm text-ink-soft">Còn {{ data.storage.disk.free_gb }} GB trên {{ data.storage.disk.total_gb }} GB</p>
      </template>
      <p class="m-0 mt-1 text-sm text-ink-soft">Tệp đính kèm: {{ data.storage.private_files_mb === null ? "đang tính…" : `${formatNumber(Math.round(data.storage.private_files_mb))} MB` }}</p>
    </section>

    <section class="card px-4 py-4" aria-label="Người dùng và nhật ký">
      <h2 class="m-0 mb-3 flex items-center gap-2 text-sm font-semibold"><Icon name="users" :size="16" /> Người dùng và nhật ký</h2>
      <p class="m-0 text-sm">{{ formatNumber(data.users.staff) }} nhân viên đang hoạt động</p>
      <p class="m-0 text-sm text-ink-soft">Nhật ký: {{ formatNumber(data.log.rows) }} dòng ({{ formatNumber(data.log.last_24h) }} trong 24 giờ qua)</p>
      <p class="m-0 mt-2 text-sm"><RouterLink to="/quan-tri/nguoi-dung">Người dùng</RouterLink> · <RouterLink to="/quan-tri/nhat-ky">Nhật ký</RouterLink></p>
    </section>
  </div>
</template>
