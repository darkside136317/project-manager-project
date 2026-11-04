<script setup>
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import EmptyState from "../components/EmptyState.vue";
import Icon from "../components/Icon.vue";
import PageHeader from "../components/PageHeader.vue";
import ProgressBar from "../components/ProgressBar.vue";
import TaskDrawer from "../components/TaskDrawer.vue";
import { api } from "../lib/api.js";
import { formatDate } from "../lib/format.js";
import { deadlineText, deadlineTone, stateBadge, statusBadge, statusLabel } from "../lib/work.js";

// Việc của tôi: what was given to me (or my crew). Work waiting for my answer first, then late work, then by deadline.
const route = useRoute();
const router = useRouter();
const done = ref(false);
const rows = ref([]);
const counts = ref({});
const more = ref(false);
const loading = ref(false);
const error = ref("");
const open = ref(String(route.query.viec || ""));

async function load(append = false) {
  loading.value = true;
  error.value = "";
  try {
    const result = await api.tasks.mine({ done: done.value ? 1 : 0, start: append ? rows.value.length : 0 });
    rows.value = append ? [...rows.value, ...result.rows] : result.rows;
    counts.value = result.counts;
    more.value = result.more;
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

function show(name) {
  open.value = name;
  router.replace({ query: { ...route.query, viec: name || undefined } });
}

watch(done, () => load());
onMounted(load);
</script>

<template>
  <PageHeader title="Việc của tôi" subtitle="Việc được giao cho bạn hoặc đội của bạn.">
    <div class="flex rounded-lg border border-line p-0.5" role="tablist">
      <button class="btn btn-ghost !min-h-0 !py-1" :class="{ 'bg-surface-muted': !done }" type="button" role="tab" :aria-selected="!done" @click="done = false">Đang làm</button>
      <button class="btn btn-ghost !min-h-0 !py-1" :class="{ 'bg-surface-muted': done }" type="button" role="tab" :aria-selected="done" @click="done = true">Đã xong</button>
    </div>
  </PageHeader>

  <div v-if="!done" class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
    <div class="card px-4 py-3"><p class="m-0 text-xs text-ink-muted">Đang giao</p><p class="m-0 text-xl font-semibold">{{ counts.total || 0 }}</p></div>
    <div class="card px-4 py-3"><p class="m-0 text-xs text-ink-muted">Chờ bạn nhận</p><p class="m-0 text-xl font-semibold text-warning">{{ counts.pending || 0 }}</p></div>
    <div class="card px-4 py-3"><p class="m-0 text-xs text-ink-muted">Quá hạn</p><p class="m-0 text-xl font-semibold text-danger">{{ counts.late || 0 }}</p></div>
    <div class="card px-4 py-3"><p class="m-0 text-xs text-ink-muted">Sắp đến hạn (2 ngày)</p><p class="m-0 text-xl font-semibold">{{ counts.soon || 0 }}</p></div>
  </div>

  <p v-if="error" class="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger" role="alert">{{ error }}</p>
  <EmptyState v-else-if="!loading && !rows.length" icon="clipboard-check" :title="done ? 'Chưa có việc nào xong' : 'Bạn chưa được giao việc nào'" />

  <ul class="m-0 list-none space-y-2 p-0">
    <li v-for="row in rows" :key="row.assignment">
      <button class="card block w-full px-4 py-3 text-left hover:shadow-pop" type="button" @click="show(row.name)">
        <div class="flex flex-wrap items-center gap-2">
          <span :class="stateBadge(row.state)">{{ row.state }}</span>
          <span class="text-xs text-ink-muted">{{ row.raci }}<template v-if="row.team"> · đội {{ row.team }}</template></span>
          <span class="ml-auto text-xs" :class="deadlineTone(deadlineText(row))">{{ deadlineText(row) || formatDate(row.exp_end_date) }}</span>
        </div>
        <p class="m-0 mt-1 font-medium"><span class="text-ink-muted">{{ row.pm_wbs_code }}</span> {{ row.subject }}</p>
        <p class="m-0 text-xs text-ink-muted">{{ row.project_name }}</p>
        <div class="mt-2 flex items-center gap-3">
          <ProgressBar class="flex-1" :value="row.progress" />
          <span class="w-10 text-right text-xs">{{ Math.round(row.progress || 0) }}%</span>
          <span :class="statusBadge(row.status)">{{ statusLabel(row.status) }}</span>
        </div>
      </button>
    </li>
  </ul>
  <div v-if="more" class="mt-3 text-center">
    <button class="btn" type="button" :disabled="loading" @click="load(true)"><Icon v-if="loading" name="loader" spin /> Xem thêm</button>
  </div>

  <TaskDrawer :name="open" @close="show('')" @changed="load()" />
</template>
