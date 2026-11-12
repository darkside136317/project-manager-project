<script setup>
import { onMounted, ref } from "vue";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import { api } from "../lib/api.js";
import { scheduleText } from "../lib/reports.js";

// The catalogue of reports the user may run, by group, and the reports they have scheduled.
// Copied from document_manager (pages/ReportsHub.vue, see docs/NGUON_GOC.md) and adapted.
const groups = ref([]);
const scheduled = ref([]);
const error = ref("");
const loading = ref(true);

onMounted(async () => {
  try {
    [groups.value, scheduled.value] = await Promise.all([api.reports.list(), api.reports.subscriptions()]);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <PageHeader title="Báo cáo" subtitle="Chọn một báo cáo, đặt điều kiện lọc rồi xem, xuất Excel, CSV, in, PDF, hoặc đặt lịch gửi." />

  <p v-if="error" class="mb-4 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <div v-if="loading" class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"><div v-for="n in 6" :key="n" class="card h-28 animate-pulse bg-surface-muted"></div></div>
  <EmptyState v-else-if="!groups.length" icon="file-chart-column" title="Chưa có báo cáo nào dành cho bạn" text="Tài khoản của bạn chưa xem được dữ liệu của các báo cáo." />

  <section v-for="group in groups" :key="group.group" class="mb-8" data-report-group>
    <h2 class="mb-3 text-sm font-semibold uppercase tracking-wide text-ink-muted">{{ group.group }}</h2>
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <RouterLink v-for="report in group.reports" :key="report.slug" :to="`/bao-cao/${report.slug}`"
                  class="card flex gap-4 p-4 text-ink no-underline transition-shadow hover:shadow-pop" data-report-card>
        <span class="grid h-11 w-11 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary"><Icon :name="report.icon" :size="22" /></span>
        <span class="min-w-0">
          <span class="block font-semibold leading-snug">{{ report.title }}</span>
          <span class="mt-1 block text-sm text-ink-muted">{{ report.description }}</span>
        </span>
      </RouterLink>
    </div>
  </section>

  <section v-if="scheduled.length" class="card p-4" aria-labelledby="scheduled-title">
    <h2 id="scheduled-title" class="m-0 mb-2 text-sm font-semibold">Báo cáo bạn đặt lịch gửi</h2>
    <ul class="m-0 list-none divide-y divide-line p-0 text-sm">
      <li v-for="row in scheduled" :key="row.name" class="flex flex-wrap items-center gap-2 py-2" data-scheduled>
        <RouterLink :to="`/bao-cao/${row.report}`" class="font-medium">{{ row.title }}</RouterLink>
        <span class="text-ink-muted">{{ scheduleText(row) }} · {{ row.file_format }} · {{ row.recipients.length }} người nhận</span>
        <span v-if="!row.is_active" class="badge badge-muted">Tạm dừng</span>
        <span v-if="row.last_error" class="badge badge-warning" :title="row.last_error">Có người không nhận được</span>
      </li>
    </ul>
  </section>
</template>
