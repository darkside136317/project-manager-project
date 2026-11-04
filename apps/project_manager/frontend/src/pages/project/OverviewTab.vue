<script setup>
import { computed, inject } from "vue";
import Icon from "../../components/Icon.vue";
import ProgressBar from "../../components/ProgressBar.vue";
import SCurve from "../../components/SCurve.vue";
import { formatDate, formatDateTime } from "../../lib/format.js";
import { statusBadge, statusLabel, variance } from "../../lib/work.js";

// Tổng quan: actual against plan, the state of the work, where it is late and why, what happened lately.
const { overview, openTask, name } = inject("project");
const data = computed(() => overview.value);
const gap = computed(() => variance(data.value.project.percent_complete, data.value.planned_progress));
const base = computed(() => `/du-an/${encodeURIComponent(name.value)}`);
</script>

<template>
  <div class="grid gap-4 lg:grid-cols-3">
    <section class="card p-4 lg:col-span-2" aria-labelledby="ov-progress">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="ov-progress" class="m-0 text-sm font-semibold">Tiến độ dự án</h2>
        <p class="m-0 text-xs text-ink-muted">{{ formatDate(data.project.expected_start_date) || "—" }} → {{ formatDate(data.project.expected_end_date) || "—" }} · {{ data.project.pm_rollup_method }}</p>
      </div>
      <div class="mt-2 flex items-end gap-6">
        <p class="m-0"><span class="text-3xl font-semibold">{{ Math.round(data.project.percent_complete || 0) }}%</span> <span class="text-sm text-ink-muted">thực tế</span></p>
        <p class="m-0 text-sm text-ink-muted">Kế hoạch {{ Math.round(data.planned_progress) }}%
          <strong :class="gap < -5 ? 'text-danger' : 'text-success'">({{ gap >= 0 ? "+" : "" }}{{ gap }} điểm)</strong></p>
      </div>
      <ProgressBar class="mt-3" :value="data.project.percent_complete" :planned="data.planned_progress" />
      <div class="mt-4"><SCurve :points="data.curve" /></div>
    </section>

    <section class="card p-4" aria-labelledby="ov-work">
      <h2 id="ov-work" class="m-0 text-sm font-semibold">Công việc</h2>
      <dl class="mt-3 grid grid-cols-2 gap-3 text-sm">
        <div><dt class="text-ink-muted">Tổng số</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.total }}</dd></div>
        <div><dt class="text-ink-muted">Đã xong</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.done }}</dd></div>
        <div><dt class="text-ink-muted">Đang làm</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.working }}</dd></div>
        <div><dt class="text-ink-muted">Chờ duyệt</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.review }}</dd></div>
        <div><dt class="flex items-center gap-1 text-ink-muted"><Icon name="alert-triangle" :size="14" class="text-danger" /> Quá hạn</dt><dd class="m-0 text-lg font-semibold text-danger">{{ data.tasks.late }}</dd></div>
        <div><dt class="flex items-center gap-1 text-ink-muted"><Icon name="hourglass" :size="14" /> Hạn trong 7 ngày</dt><dd class="m-0 text-lg font-semibold">{{ data.tasks.soon }}</dd></div>
      </dl>
      <p v-if="data.pending_acceptance" class="mt-3 rounded-md bg-warning-soft px-3 py-2 text-sm">
        {{ data.pending_acceptance }} phân công chưa được nhận.
        <RouterLink :to="`${base}/ai-lam-gi`" class="font-medium underline">Xem ai làm gì</RouterLink>
      </p>
      <p v-if="!data.sees_all_tasks" class="mt-3 text-xs text-ink-muted">Bạn chỉ thấy các việc được giao cho mình hoặc đội của mình.</p>
    </section>

    <section v-if="data.phases.length" class="card p-4 lg:col-span-2" aria-labelledby="ov-phases">
      <h2 id="ov-phases" class="m-0 text-sm font-semibold">Giai đoạn</h2>
      <ul class="m-0 mt-3 list-none space-y-3 p-0">
        <li v-for="phase in data.phases" :key="phase.name">
          <button class="w-full text-left" type="button" @click="openTask(phase.name)">
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <span class="text-ink-muted">{{ phase.pm_wbs_code }}</span>
              <span class="font-medium">{{ phase.subject }}</span>
              <span :class="statusBadge(phase.status)">{{ statusLabel(phase.status) }}</span>
              <span v-if="phase.pm_is_overdue" class="badge badge-danger">Quá hạn</span>
              <span class="ml-auto text-xs text-ink-muted">{{ formatDate(phase.exp_start_date) }} → {{ formatDate(phase.exp_end_date) }}</span>
            </div>
            <div class="mt-1 flex items-center gap-3">
              <ProgressBar class="flex-1" :value="phase.progress" :planned="phase.planned_progress" :label="`Tiến độ ${phase.subject}`" />
              <span class="w-24 text-right text-xs">{{ Math.round(phase.progress || 0) }}% / {{ Math.round(phase.planned_progress) }}%</span>
            </div>
          </button>
        </li>
      </ul>
    </section>

    <section class="card p-4" aria-labelledby="ov-delays">
      <h2 id="ov-delays" class="m-0 text-sm font-semibold">Chậm ở đâu</h2>
      <p v-if="!data.delays.length" class="mt-3 text-sm text-ink-muted">Không có việc nào quá hạn.</p>
      <table v-else class="mt-3 w-full text-sm">
        <thead><tr class="text-left text-xs text-ink-muted"><th class="pb-1">Khâu / lý do</th><th class="pb-1 text-right">Việc</th><th class="pb-1 text-right">Ngày trễ</th></tr></thead>
        <tbody>
          <tr v-for="row in data.delays" :key="`${row.source}-${row.reason}`" class="border-t border-line">
            <td class="py-1.5">{{ row.source || "Chưa rõ khâu" }}<span class="block text-xs text-ink-muted">{{ row.reason || "Chưa ghi lý do" }}</span></td>
            <td class="text-right">{{ row.tasks }}</td><td class="text-right">{{ row.days }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="card p-4 lg:col-span-3" aria-labelledby="ov-recent">
      <h2 id="ov-recent" class="m-0 text-sm font-semibold">Hoạt động gần đây</h2>
      <p v-if="!data.recent.length" class="mt-3 text-sm text-ink-muted">Chưa có hoạt động nào.</p>
      <ul class="m-0 mt-3 list-none space-y-2 p-0">
        <li v-for="entry in data.recent" :key="entry.name" class="text-sm">
          <button v-if="entry.task" class="text-left hover:underline" type="button" @click="openTask(entry.task)">
            <strong>{{ entry.actor_name }}</strong> · <span class="font-medium">{{ entry.task_label }}</span>: {{ entry.content }}
          </button>
          <span v-else><strong>{{ entry.actor_name }}</strong> · {{ entry.content }}</span>
          <span class="ml-1 text-xs text-ink-muted">{{ entry.activity_type }} · {{ formatDateTime(entry.creation) }}</span>
        </li>
      </ul>
    </section>
  </div>
</template>
