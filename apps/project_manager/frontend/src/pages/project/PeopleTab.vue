<script setup>
import { inject, onMounted, ref, watch } from "vue";
import EmptyState from "../../components/EmptyState.vue";
import Icon from "../../components/Icon.vue";
import { api } from "../../lib/api.js";
import { formatDateTime } from "../../lib/format.js";
import { toast } from "../../lib/toast.js";

// Ai làm gì: per person or crew, what they hold, what is late, what they have not accepted yet, when they last
// reported; and where the delays come from. Answers "who is on it" without asking around.
const { name: project, version } = inject("project");
const view = ref(null);
const loading = ref(false);

async function load() {
  loading.value = true;
  try {
    view.value = await api.tasks.whoDoesWhat(project.value);
  } catch (e) {
    toast(e.message, "error", 7000);
  } finally {
    loading.value = false;
  }
}

watch(version, load);
onMounted(load);
</script>

<template>
  <p v-if="loading && !view" class="flex items-center gap-2 text-sm text-ink-muted"><Icon name="loader" spin /> Đang tải...</p>
  <template v-if="view">
    <p v-if="!view.sees_all" class="mb-3 text-sm text-ink-muted">Bạn chỉ thấy phần việc của mình hoặc đội của mình.</p>
    <p v-if="view.unassigned" class="mb-3 rounded-md bg-warning-soft px-3 py-2 text-sm">
      <Icon name="alert-triangle" :size="14" class="inline" /> {{ view.unassigned }} việc chưa có người chịu trách nhiệm chính.
    </p>
    <EmptyState v-if="!view.rows.length" icon="user-check" title="Chưa giao việc cho ai" text="Mở một công việc rồi chọn Giao việc." />
    <div v-else class="card table-wrap">
      <table class="w-full min-w-[640px] text-left text-sm">
        <thead class="text-xs uppercase tracking-wide text-ink-muted">
          <tr class="border-b border-line">
            <th class="px-3 py-2">Người / đội</th>
            <th class="px-3 py-2 text-right">Chịu TN chính</th>
            <th class="px-3 py-2 text-right">Thực hiện</th>
            <th class="px-3 py-2 text-right">Đang mở</th>
            <th class="px-3 py-2 text-right">Quá hạn</th>
            <th class="px-3 py-2 text-right">Hạn 7 ngày</th>
            <th class="px-3 py-2 text-right">Chưa nhận</th>
            <th class="px-3 py-2">Báo cáo gần nhất</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in view.rows" :key="`${row.user}-${row.team}`" class="border-b border-line last:border-0">
            <td class="px-3 py-2 font-medium">{{ row.who }}</td>
            <td class="px-3 py-2 text-right">{{ row.accountable }}</td>
            <td class="px-3 py-2 text-right">{{ row.responsible }}</td>
            <td class="px-3 py-2 text-right">{{ row.open }}</td>
            <td class="px-3 py-2 text-right" :class="{ 'font-semibold text-danger': row.late }">{{ row.late }}</td>
            <td class="px-3 py-2 text-right">{{ row.soon }}</td>
            <td class="px-3 py-2 text-right" :class="{ 'font-semibold text-warning': row.pending }">{{ row.pending }}</td>
            <td class="px-3 py-2 text-ink-muted">{{ formatDateTime(row.last_report) || "Chưa báo cáo" }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <section v-if="view.delays.length" class="card mt-4 p-4" aria-labelledby="delay-title">
      <h2 id="delay-title" class="m-0 text-sm font-semibold">Việc quá hạn theo khâu gây chậm</h2>
      <ul class="m-0 mt-3 list-none space-y-2 p-0 text-sm">
        <li v-for="row in view.delays" :key="row.source" class="flex items-center gap-3">
          <span class="w-40 truncate">{{ row.source || "Chưa rõ khâu" }}</span>
          <span class="font-semibold">{{ row.tasks }} việc</span>
          <span class="text-ink-muted">· {{ row.days }} ngày trễ cộng dồn</span>
        </li>
      </ul>
    </section>
  </template>
</template>
